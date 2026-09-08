from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Iterable


MAX_UPSERT_BATCH = 1000


class QslQsoError(ValueError):
    pass


@dataclass(frozen=True)
class PreparedQslQso:
    local_id: str
    record: dict[str, str]


def _digits(value: Any) -> str:
    return "".join(
        character
        for character in str(value or "")
        if character.isdigit()
    )


def _qso_date(value: Any) -> str:
    digits = _digits(value)

    if len(digits) != 8:
        raise QslQsoError("QSO_DATE muss ein gültiges UTC-Datum enthalten")

    try:
        datetime.strptime(digits, "%Y%m%d")
    except ValueError as exc:
        raise QslQsoError("QSO_DATE ist ungültig") from exc

    return digits


def _time_on(value: Any) -> str:
    digits = _digits(value)

    if len(digits) == 4:
        digits += "00"

    if len(digits) != 6:
        raise QslQsoError("TIME_ON muss eine gültige UTC-Zeit enthalten")

    try:
        datetime.strptime(digits, "%H%M%S")
    except ValueError as exc:
        raise QslQsoError("TIME_ON ist ungültig") from exc

    return digits


def _text(
    value: Any,
    *,
    upper: bool = False,
) -> str:
    result = str(value or "").strip()
    return result.upper() if upper else result


def qso_to_upsert_record(
    qso: dict[str, Any],
) -> PreparedQslQso:
    if not isinstance(qso, dict):
        raise QslQsoError("QSO muss ein Objekt sein")

    local_id = _text(qso.get("local_id"))

    if not local_id:
        raise QslQsoError("QSO hat keine local_id")

    call = _text(qso.get("call"), upper=True)
    band = _text(qso.get("band"))
    mode = _text(qso.get("mode"), upper=True)
    station_call = _text(
        qso.get("station_call"),
        upper=True,
    )

    missing = [
        name
        for name, value in (
            ("CALL", call),
            ("BAND", band),
            ("MODE", mode),
            ("STATION_CALLSIGN", station_call),
        )
        if not value
    ]

    if missing:
        raise QslQsoError(
            "QSO-Felder fehlen: " + ", ".join(missing)
        )

    record = {
        "CALL": call,
        "QSO_DATE": _qso_date(qso.get("qso_date")),
        "TIME_ON": _time_on(qso.get("time_on")),
        "BAND": band,
        "MODE": mode,
        "STATION_CALLSIGN": station_call,
    }

    frequency = _text(qso.get("freq")).replace(",", ".")

    if frequency:
        try:
            if float(frequency) <= 0:
                raise ValueError
        except ValueError as exc:
            raise QslQsoError("FREQ ist ungültig") from exc

        record["FREQ"] = frequency

    rst_sent = _text(qso.get("rst_sent"))
    rst_rcvd = _text(qso.get("rst_rcvd"))

    if rst_sent:
        record["RST_SENT"] = rst_sent

    if rst_rcvd:
        record["RST_RCVD"] = rst_rcvd

    return PreparedQslQso(
        local_id=local_id,
        record=record,
    )


def prepare_upsert_batches(
    qsos: Iterable[dict[str, Any]],
    *,
    batch_size: int = MAX_UPSERT_BATCH,
) -> list[list[PreparedQslQso]]:
    batch_size = int(batch_size)

    if batch_size < 1 or batch_size > MAX_UPSERT_BATCH:
        raise QslQsoError(
            f"Batchgröße muss zwischen 1 und {MAX_UPSERT_BATCH} liegen"
        )

    batches: list[list[PreparedQslQso]] = []
    current: list[PreparedQslQso] = []

    for qso in qsos:
        current.append(qso_to_upsert_record(qso))

        if len(current) >= batch_size:
            batches.append(current)
            current = []

    if current:
        batches.append(current)

    return batches


def upsert_payload(
    batch: Iterable[PreparedQslQso],
) -> dict[str, list[dict[str, str]]]:
    rows = list(batch)

    if not rows:
        raise QslQsoError("Leerer QSL-Upsert-Batch")

    if len(rows) > MAX_UPSERT_BATCH:
        raise QslQsoError(
            f"QSL-Upsert-Batch enthält mehr als {MAX_UPSERT_BATCH} QSOs"
        )

    return {
        "records": [
            dict(row.record)
            for row in rows
        ],
    }
