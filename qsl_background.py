from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Iterable

from qsl_qso import qsl_upsert_fingerprint, qso_to_upsert_record
from qsl_recipient import QslRecipientResult, resolve_pending_recipients
from qsl_storage import QslStorage, QslStorageError, normalize_qso_uid
from qsl_sync import QslSyncResult, sync_qsos
from qsl_templates import (
    QslTemplateCatalog,
    choose_template_profile_response,
    normalize_station_profile,
)


QSL_BACKGROUND_INTERVAL_MS = 30 * 60 * 1000
QSL_BACKGROUND_RETRY_MS = 5 * 60 * 1000
QSL_BACKGROUND_NEW_QSO_MS = 1500
QSL_BACKGROUND_RECIPIENT_LIMIT = 50
QSL_STATUS_BATCH_SIZE = 1000
QSL_STATUS_REFRESH_LIMIT = 250
QSL_STATUS_ACTIVE_MIN_AGE_SECONDS = 30 * 60
QSL_STATUS_STABLE_MIN_AGE_SECONDS = 24 * 60 * 60


@dataclass(frozen=True)
class QslBackgroundResult:
    bootstrap: dict[str, Any]
    sync: QslSyncResult
    recipient: QslRecipientResult
    statuses_refreshed: int
    template_profile: str
    template_count: int
    personal_layout_count: int
    errors: tuple[str, ...]


def _empty_sync_result() -> QslSyncResult:
    return QslSyncResult(
        total=0,
        created=0,
        updated=0,
        unchanged=0,
        ignored=0,
        mapped=0,
        synced_at="",
        records=(),
    )


def _empty_recipient_result(storage: QslStorage) -> QslRecipientResult:
    pending = len(
        [
            action
            for action in storage.list_pending_actions(
                ready_only=False,
                limit=5000,
            )
            if str(action.get("action_type") or "") == "recipient_check"
        ]
    )

    return QslRecipientResult(
        pending_before=pending,
        processed=0,
        email=0,
        no_email=0,
        not_found=0,
        cached=0,
        failed=0,
        pending_after=pending,
    )


def unmapped_qsos(
    storage: QslStorage,
    qsos: Iterable[dict[str, Any]],
) -> list[dict[str, Any]]:
    mapped_local_ids = {
        str(row.get("local_id") or "").strip()
        for row in storage.list_mappings()
    }

    result: list[dict[str, Any]] = []
    seen: set[str] = set()

    for raw in qsos:
        if not isinstance(raw, dict):
            continue

        local_id = str(raw.get("local_id") or "").strip()

        if (
            not local_id
            or local_id in seen
            or local_id in mapped_local_ids
        ):
            continue

        seen.add(local_id)
        result.append(raw)

    return result


def qso_sync_candidates(
    storage: QslStorage,
    qsos: Iterable[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Return new QSOs plus mapped QSOs whose QSL payload changed."""
    mapped_local_ids = {
        str(
            row.get("local_id")
            or ""
        ).strip()
        for row in storage.list_mappings()
    }

    result: list[dict[str, Any]] = []
    seen: set[str] = set()

    for raw in qsos:
        if not isinstance(raw, dict):
            continue

        local_id = str(
            raw.get("local_id")
            or ""
        ).strip()

        if not local_id or local_id in seen:
            continue

        seen.add(local_id)

        if local_id not in mapped_local_ids:
            result.append(raw)
            continue

        prepared = qso_to_upsert_record(raw)
        current = qsl_upsert_fingerprint(
            prepared
        )
        previous = storage.sync_fingerprint_for_local(
            local_id
        )

        # Pre-0.20.1 mappings have no fingerprint. Send them once so the
        # richer designer/ADIF payload is backfilled, then only resend on
        # actual QSL payload changes.
        if previous != current:
            result.append(raw)

    return result


def _status_timestamp(
    value: object,
) -> datetime | None:
    raw = str(value or "").strip()

    if not raw:
        return None

    try:
        parsed = datetime.fromisoformat(
            raw.replace("Z", "+00:00")
        )
    except ValueError:
        return None

    if parsed.tzinfo is None:
        parsed = parsed.replace(
            tzinfo=timezone.utc
        )

    return parsed.astimezone(
        timezone.utc
    )


def _status_is_active(
    payload: dict[str, Any],
) -> bool:
    mail_status = str(
        payload.get("mailStatus")
        or ""
    ).strip().lower()
    card_status = str(
        payload.get("cardStatus")
        or ""
    ).strip().lower()

    return (
        mail_status
        in {
            "queued",
            "queue",
            "pending",
            "processing",
            "sending",
        }
        or card_status
        in {
            "queued",
            "queue",
            "pending",
            "processing",
            "generating",
        }
    )


def status_refresh_candidates(
    storage: QslStorage,
    *,
    now: datetime | None = None,
    limit: int = QSL_STATUS_REFRESH_LIMIT,
) -> list[str]:
    """Select a bounded oldest-first set of QSL statuses to refresh."""
    limit = max(
        1,
        min(
            int(limit),
            QSL_STATUS_BATCH_SIZE,
        ),
    )
    now_utc = (
        now.astimezone(timezone.utc)
        if now is not None
        else datetime.now(timezone.utc)
    )

    snapshots = (
        storage.list_status_snapshots_by_local()
    )

    missing: list[
        tuple[datetime, str]
    ] = []
    active: list[
        tuple[datetime, str]
    ] = []
    stable: list[
        tuple[datetime, str]
    ] = []

    oldest = datetime.min.replace(
        tzinfo=timezone.utc
    )

    for row in storage.list_mappings():
        local_id = str(
            row.get("local_id")
            or ""
        ).strip()
        raw_uid = str(
            row.get("qso_uid")
            or ""
        ).strip()

        if not local_id or not raw_uid:
            continue

        try:
            uid = normalize_qso_uid(
                raw_uid
            )
        except QslStorageError:
            continue

        snapshot = snapshots.get(
            local_id
        )

        if not snapshot:
            missing.append(
                (oldest, uid)
            )
            continue

        payload = snapshot.get(
            "payload"
        )
        payload = (
            payload
            if isinstance(payload, dict)
            else {}
        )
        fetched = _status_timestamp(
            snapshot.get("fetched_at")
        )

        if fetched is None:
            missing.append(
                (oldest, uid)
            )
            continue

        age_seconds = max(
            0.0,
            (
                now_utc
                - fetched
            ).total_seconds(),
        )

        if _status_is_active(
            payload
        ):
            if (
                age_seconds
                >= QSL_STATUS_ACTIVE_MIN_AGE_SECONDS
            ):
                active.append(
                    (fetched, uid)
                )
        elif (
            age_seconds
            >= QSL_STATUS_STABLE_MIN_AGE_SECONDS
        ):
            stable.append(
                (fetched, uid)
            )

    ordered = (
        sorted(missing)
        + sorted(active)
        + sorted(stable)
    )

    result: list[str] = []
    seen: set[str] = set()

    for _fetched, uid in ordered:
        if uid in seen:
            continue

        seen.add(uid)
        result.append(uid)

        if len(result) >= limit:
            break

    return result


def refresh_status_snapshots(
    client,
    storage: QslStorage,
) -> int:
    qso_uids = status_refresh_candidates(
        storage
    )

    refreshed = 0

    for offset in range(
        0,
        len(qso_uids),
        QSL_STATUS_BATCH_SIZE,
    ):
        batch = qso_uids[
            offset:
            offset + QSL_STATUS_BATCH_SIZE
        ]
        response = client.qso_status(
            batch
        )

        if not isinstance(response, dict):
            raise RuntimeError(
                "qsos/status hat kein Objekt geliefert"
            )

        statuses = response.get(
            "statuses"
        )

        if not isinstance(
            statuses,
            dict,
        ):
            raise RuntimeError(
                "qsos/status enthält keine statuses-Map"
            )

        for uid in batch:
            payload = statuses.get(
                uid
            )

            if not isinstance(
                payload,
                dict,
            ):
                continue

            returned = str(
                payload.get("qsoUid")
                or uid
            ).strip()

            try:
                returned = normalize_qso_uid(
                    returned
                )
            except QslStorageError as exc:
                raise RuntimeError(
                    "qsos/status liefert eine ungültige qsoUid"
                ) from exc

            if returned != uid:
                raise RuntimeError(
                    "qsos/status liefert eine fremde qsoUid"
                )

            storage.set_status_snapshot(
                uid,
                payload,
            )
            refreshed += 1

    return refreshed


def refresh_template_catalog(
    client,
    db,
    candidates: Iterable[str],
) -> tuple[str, int, int]:
    profiles: list[str] = []

    for raw in candidates:
        try:
            profile = normalize_station_profile(raw)
        except Exception:
            continue

        if profile not in profiles:
            profiles.append(profile)

    if not profiles:
        return "", 0, 0

    responses: dict[str, dict[str, Any]] = {}
    last_error: Exception | None = None

    for profile in profiles:
        try:
            response = client.templates(profile)
            if isinstance(response, dict):
                responses[profile] = response
        except Exception as exc:
            last_error = exc

    if not responses:
        if last_error is not None:
            raise last_error
        raise RuntimeError("Kein QSL-Motivkatalog konnte geladen werden")

    resolved_profile, response, personal_count = choose_template_profile_response(
        profiles,
        responses,
    )

    catalog = QslTemplateCatalog(db)
    templates = catalog.cache_response(resolved_profile, response)
    db.set_setting("qsl_layout_profile_key", resolved_profile)

    return resolved_profile, len(templates), personal_count


def run_qsl_background_sync(
    client,
    storage: QslStorage,
    db,
    qsos: Iterable[dict[str, Any]],
    *,
    template_candidates: Iterable[str] = (),
) -> QslBackgroundResult:
    # Bootstrap stays first so the stable server contract is validated before
    # any state-changing call is attempted.
    bootstrap = client.bootstrap()

    qso_list = [item for item in qsos if isinstance(item, dict)]
    errors: list[str] = []

    sync_result = _empty_sync_result()
    try:
        pending_qsos = qso_sync_candidates(
            storage,
            qso_list,
        )
        if pending_qsos:
            sync_result = sync_qsos(
                client,
                storage,
                pending_qsos,
            )
    except Exception as exc:
        errors.append("QSO-Sync: " + str(exc))

    recipient_result = _empty_recipient_result(storage)
    try:
        recipient_result = resolve_pending_recipients(
            client,
            storage,
            limit=QSL_BACKGROUND_RECIPIENT_LIMIT,
        )
    except Exception as exc:
        errors.append("Empfängerprüfung: " + str(exc))

    statuses_refreshed = 0
    try:
        statuses_refreshed = refresh_status_snapshots(client, storage)
    except Exception as exc:
        errors.append("Status: " + str(exc))

    template_profile = ""
    template_count = 0
    personal_layout_count = 0
    try:
        (
            template_profile,
            template_count,
            personal_layout_count,
        ) = refresh_template_catalog(
            client,
            db,
            template_candidates,
        )
    except Exception as exc:
        errors.append("Motive: " + str(exc))

    return QslBackgroundResult(
        bootstrap=dict(bootstrap if isinstance(bootstrap, dict) else {}),
        sync=sync_result,
        recipient=recipient_result,
        statuses_refreshed=statuses_refreshed,
        template_profile=template_profile,
        template_count=template_count,
        personal_layout_count=personal_layout_count,
        errors=tuple(errors),
    )
