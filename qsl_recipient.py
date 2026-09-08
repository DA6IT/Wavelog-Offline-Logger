from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from qsl_client import QslClientError
from qsl_storage import (
    QslStorage,
    QslStorageError,
    normalize_qso_uid,
)


RECIPIENT_ACTION = "recipient_check"
DEFAULT_RECIPIENT_BATCH = 12


class QslRecipientError(RuntimeError):
    pass


@dataclass(frozen=True)
class QslRecipientResult:
    pending_before: int
    processed: int
    email: int
    no_email: int
    not_found: int
    cached: int
    failed: int
    pending_after: int


def queue_recipient_check(
    storage: QslStorage,
    local_id: str,
) -> int:
    local_id = str(local_id or "").strip()

    if not local_id:
        raise QslRecipientError(
            "local_id für Empfängerprüfung fehlt"
        )

    for action in storage.list_pending_actions(
        ready_only=False,
        limit=5000,
    ):
        if (
            str(action.get("local_id") or "") == local_id
            and str(action.get("action_type") or "") == RECIPIENT_ACTION
        ):
            return int(action["id"])

    return storage.queue_action(
        local_id,
        RECIPIENT_ACTION,
        payload={},
    )


def _refresh_status_snapshot(
    client,
    storage: QslStorage,
    qso_uid: str,
) -> None:
    response = client.qso_status([qso_uid])

    if not isinstance(response, dict):
        raise QslRecipientError(
            "qsos/status hat kein Objekt geliefert"
        )

    statuses = response.get("statuses")

    if not isinstance(statuses, dict):
        raise QslRecipientError(
            "qsos/status enthält keine statuses-Map"
        )

    status = statuses.get(qso_uid)

    if not isinstance(status, dict):
        raise QslRecipientError(
            "qsos/status enthält keinen Zustand für die qsoUid"
        )

    returned_uid = str(
        status.get("qsoUid") or qso_uid
    ).strip()

    try:
        returned_uid = normalize_qso_uid(
            returned_uid
        )
    except QslStorageError as exc:
        raise QslRecipientError(
            "qsos/status liefert eine ungültige qsoUid"
        ) from exc

    if returned_uid != qso_uid:
        raise QslRecipientError(
            "qsos/status liefert eine fremde qsoUid"
        )

    storage.set_status_snapshot(
        qso_uid,
        status,
    )


def resolve_pending_recipients(
    client,
    storage: QslStorage,
    *,
    limit: int = DEFAULT_RECIPIENT_BATCH,
) -> QslRecipientResult:
    limit = max(1, min(int(limit), 100))

    all_pending = [
        action
        for action in storage.list_pending_actions(
            ready_only=False,
            limit=5000,
        )
        if str(action.get("action_type") or "") == RECIPIENT_ACTION
    ]

    ready = [
        action
        for action in all_pending
        if str(action.get("qso_uid") or "").strip()
    ][:limit]

    processed = 0
    email = 0
    no_email = 0
    not_found = 0
    cached = 0
    failed = 0

    for action in ready:
        action_id = int(action["id"])

        try:
            qso_uid = normalize_qso_uid(
                str(action.get("qso_uid") or "")
            )
        except QslStorageError as exc:
            storage.mark_action_error(
                action_id,
                "Ungültige qsoUid in recipient_check",
            )
            failed += 1
            continue

        try:
            response = client.qrz_recipient(
                qso_uid
            )

            if not isinstance(response, dict):
                raise QslRecipientError(
                    "POST qrz hat kein Objekt geliefert"
                )

            returned_uid = str(
                response.get("qsoUid") or qso_uid
            ).strip()

            try:
                returned_uid = normalize_qso_uid(
                    returned_uid
                )
            except QslStorageError as exc:
                raise QslRecipientError(
                    "POST qrz liefert eine ungültige qsoUid"
                ) from exc

            if returned_uid != qso_uid:
                raise QslRecipientError(
                    "POST qrz liefert eine fremde qsoUid"
                )

            if bool(response.get("cached")):
                cached += 1

            if str(response.get("email") or "").strip():
                email += 1
            else:
                no_email += 1

            _refresh_status_snapshot(
                client,
                storage,
                qso_uid,
            )

            storage.complete_action(
                action_id
            )
            processed += 1

        except QslClientError as exc:
            if exc.error_code == "qrz_not_found":
                try:
                    _refresh_status_snapshot(
                        client,
                        storage,
                        qso_uid,
                    )
                except Exception:
                    pass

                storage.complete_action(
                    action_id
                )
                processed += 1
                not_found += 1
                continue

            storage.mark_action_error(
                action_id,
                str(exc),
            )
            failed += 1

        except Exception as exc:
            storage.mark_action_error(
                action_id,
                str(exc),
            )
            failed += 1

    pending_after = len(
        [
            action
            for action in storage.list_pending_actions(
                ready_only=False,
                limit=5000,
            )
            if str(action.get("action_type") or "") == RECIPIENT_ACTION
        ]
    )

    return QslRecipientResult(
        pending_before=len(all_pending),
        processed=processed,
        email=email,
        no_email=no_email,
        not_found=not_found,
        cached=cached,
        failed=failed,
        pending_after=pending_after,
    )
