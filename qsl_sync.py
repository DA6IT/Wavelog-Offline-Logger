from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

from qsl_qso import (
    PreparedQslQso,
    prepare_upsert_batches,
    qsl_upsert_fingerprint,
)
from qsl_storage import (
    QslStorage,
    QslStorageError,
    normalize_qso_uid,
)


_ALLOWED_ACTIONS = {
    "created",
    "updated",
    "unchanged",
    "ignored",
}


class QslSyncError(RuntimeError):
    pass


@dataclass(frozen=True)
class QslMappedRecord:
    local_id: str
    qso_uid: str | None
    action: str
    qso: dict[str, Any]


@dataclass(frozen=True)
class QslSyncResult:
    total: int
    created: int
    updated: int
    unchanged: int
    ignored: int
    mapped: int
    synced_at: str
    records: tuple[QslMappedRecord, ...]


def _response_qso_uid(
    row: dict[str, Any],
) -> str | None:
    direct = str(
        row.get("qsoUid") or ""
    ).strip()

    nested = row.get("qso")
    nested = nested if isinstance(nested, dict) else {}

    nested_uid = str(
        nested.get("qsoUid") or ""
    ).strip()

    if direct and nested_uid and direct != nested_uid:
        raise QslSyncError(
            "QSL API liefert widersprüchliche qsoUid-Werte"
        )

    raw = direct or nested_uid

    if not raw:
        return None

    try:
        return normalize_qso_uid(raw)
    except QslStorageError as exc:
        raise QslSyncError(
            "QSL API liefert eine ungültige qsoUid"
        ) from exc


def _parse_stats(
    response: dict[str, Any],
    parsed: list[QslMappedRecord],
) -> tuple[int, int, int, int]:
    counts = {
        "created": 0,
        "updated": 0,
        "unchanged": 0,
        "ignored": 0,
    }

    for row in parsed:
        counts[row.action] += 1

    stats = response.get("stats")

    if isinstance(stats, dict):
        for name, actual in counts.items():
            raw = stats.get(name)

            if raw is None:
                continue

            try:
                server_value = int(raw)
            except (TypeError, ValueError) as exc:
                raise QslSyncError(
                    f"QSL API liefert ungültige Statistik für {name}"
                ) from exc

            if server_value != actual:
                raise QslSyncError(
                    "QSL API Statistik passt nicht zu records[] "
                    f"({name}: {server_value} != {actual})"
                )

    return (
        counts["created"],
        counts["updated"],
        counts["unchanged"],
        counts["ignored"],
    )


def map_upsert_response(
    storage: QslStorage,
    batch: list[PreparedQslQso],
    response: dict[str, Any],
) -> QslSyncResult:
    if not isinstance(response, dict):
        raise QslSyncError(
            "QSL-Upsert-Antwort muss ein Objekt sein"
        )

    raw_records = response.get("records")

    if not isinstance(raw_records, list):
        raise QslSyncError(
            "QSL-Upsert-Antwort enthält kein records[]"
        )

    if len(raw_records) != len(batch):
        raise QslSyncError(
            "QSL-Upsert-Antwort hat eine unerwartete Anzahl "
            "von records[]; Mapping wird aus Sicherheitsgründen "
            "nicht gespeichert"
        )

    parsed: list[QslMappedRecord] = []

    for prepared, raw in zip(batch, raw_records):
        if not isinstance(raw, dict):
            raise QslSyncError(
                "QSL-Upsert records[] enthält einen ungültigen Eintrag"
            )

        action = str(
            raw.get("action") or ""
        ).strip().lower()

        if action not in _ALLOWED_ACTIONS:
            raise QslSyncError(
                "QSL API liefert eine unbekannte Upsert-Aktion"
            )

        qso_uid = _response_qso_uid(raw)
        qso = raw.get("qso")
        qso = dict(qso) if isinstance(qso, dict) else {}

        if action != "ignored" and not qso_uid:
            raise QslSyncError(
                "QSL API liefert für ein erfolgreich verarbeitetes "
                "QSO keine qsoUid"
            )

        parsed.append(
            QslMappedRecord(
                local_id=prepared.local_id,
                qso_uid=qso_uid,
                action=action,
                qso=qso,
            )
        )

    # Validate the complete response before mutating local mappings.
    created, updated, unchanged, ignored = _parse_stats(
        response,
        parsed,
    )

    mapped = 0

    for prepared, row in zip(
        batch,
        parsed,
    ):
        if row.qso_uid is None:
            continue

        storage.bind_qso_uid(
            row.local_id,
            row.qso_uid,
        )

        storage.set_sync_fingerprint(
            prepared.local_id,
            qsl_upsert_fingerprint(
                prepared
            ),
        )

        if row.qso:
            storage.set_status_snapshot(
                row.qso_uid,
                row.qso,
            )

        mapped += 1

    return QslSyncResult(
        total=len(parsed),
        created=created,
        updated=updated,
        unchanged=unchanged,
        ignored=ignored,
        mapped=mapped,
        synced_at=str(
            response.get("syncedAt") or ""
        ).strip(),
        records=tuple(parsed),
    )


def sync_qsos(
    client,
    storage: QslStorage,
    qsos: Iterable[dict[str, Any]],
    *,
    batch_size: int = 1000,
) -> QslSyncResult:
    batches = prepare_upsert_batches(
        qsos,
        batch_size=batch_size,
    )

    all_records: list[QslMappedRecord] = []
    totals = {
        "created": 0,
        "updated": 0,
        "unchanged": 0,
        "ignored": 0,
        "mapped": 0,
    }
    synced_at = ""

    for batch in batches:
        response = client.upsert_qsos(
            [
                dict(item.record)
                for item in batch
            ]
        )

        result = map_upsert_response(
            storage,
            batch,
            response,
        )

        all_records.extend(result.records)
        totals["created"] += result.created
        totals["updated"] += result.updated
        totals["unchanged"] += result.unchanged
        totals["ignored"] += result.ignored
        totals["mapped"] += result.mapped

        if result.synced_at:
            synced_at = result.synced_at

    return QslSyncResult(
        total=len(all_records),
        created=totals["created"],
        updated=totals["updated"],
        unchanged=totals["unchanged"],
        ignored=totals["ignored"],
        mapped=totals["mapped"],
        synced_at=synced_at,
        records=tuple(all_records),
    )
