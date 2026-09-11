from __future__ import annotations

from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Iterable


DEFAULT_TIME_TOLERANCE_SECONDS = 90
DEFAULT_FREQUENCY_TOLERANCE_MHZ = 0.010
FUZZY_DIGITAL_MODES = frozenset({
    "FT8", "FT4", "JS8", "JT65", "JT9", "Q65",
    "MSK144", "FST4", "FST4W", "WSPR", "MFSK",
})


def _digits(value: Any) -> str:
    return "".join(ch for ch in str(value or "") if ch.isdigit())


def _normalize_date(value: Any) -> str:
    raw = str(value or "").strip()
    digits = _digits(raw)
    if len(digits) >= 8:
        return f"{digits[:4]}-{digits[4:6]}-{digits[6:8]}"
    return raw[:10]


def _normalize_time(value: Any) -> str:
    digits = _digits(value)
    if len(digits) == 4:
        digits += "00"
    return digits[:6]


def _normalize_frequency(value: Any) -> str:
    raw = str(value or "").strip().replace(",", ".")
    if not raw:
        return ""
    try:
        return format(
            Decimal(raw).quantize(Decimal("0.000001")).normalize(),
            "f",
        )
    except InvalidOperation:
        return raw


def _qso_datetime(qso: dict[str, Any]) -> datetime | None:
    date = _normalize_date(qso.get("qso_date"))
    time_on = _normalize_time(qso.get("time_on"))
    try:
        return datetime.strptime(date + time_on, "%Y-%m-%d%H%M%S")
    except ValueError:
        return None


def _match_bucket(qso: dict[str, Any]) -> tuple[str, str, str]:
    return (
        str(qso.get("call") or "").strip().upper(),
        str(qso.get("band") or "").strip().upper(),
        str(qso.get("mode") or "").strip().upper(),
    )


def _station_compatible(left: dict[str, Any], right: dict[str, Any]) -> bool:
    a = str(left.get("station_call") or "").strip().upper()
    b = str(right.get("station_call") or "").strip().upper()
    return not (a and b and a != b)


def _frequency_compatible(
    left: dict[str, Any],
    right: dict[str, Any],
    tolerance_mhz: float,
) -> bool:
    try:
        a = float(str(left.get("freq") or "").replace(",", "."))
        b = float(str(right.get("freq") or "").replace(",", "."))
    except (TypeError, ValueError):
        return True
    return abs(a - b) <= max(0.0, float(tolerance_mhz))


def _strict_same_contact(
    left: dict[str, Any],
    right: dict[str, Any],
) -> bool:
    return (
        _normalize_date(left.get("qso_date"))
        == _normalize_date(right.get("qso_date"))
        and _normalize_time(left.get("time_on"))
        == _normalize_time(right.get("time_on"))
        and _normalize_frequency(left.get("freq"))
        == _normalize_frequency(right.get("freq"))
    )


class QsoMatcher:
    """Duplicate matcher for externally supplied QSOs.

    WSJT-family digital modes use a short tolerant time/frequency window so a
    repeated final exchange does not create two or three QSOs. Other modes use
    strict date/time/frequency equality to avoid collapsing legitimate repeats.
    """

    def __init__(
        self,
        qsos: Iterable[dict[str, Any]],
        tolerance_seconds: int = DEFAULT_TIME_TOLERANCE_SECONDS,
        frequency_tolerance_mhz: float = DEFAULT_FREQUENCY_TOLERANCE_MHZ,
    ):
        self.tolerance_seconds = max(0, int(tolerance_seconds))
        self.frequency_tolerance_mhz = max(
            0.0,
            float(frequency_tolerance_mhz),
        )
        self.by_id: dict[str, dict[str, Any]] = {}
        self.by_bucket: dict[
            tuple[str, str, str],
            list[tuple[datetime | None, dict[str, Any]]],
        ] = {}
        for qso in qsos:
            self.add(qso)

    def add(self, qso: dict[str, Any]) -> None:
        local_id = str(qso.get("local_id") or "").strip()
        if local_id:
            self.by_id[local_id] = qso
        self.by_bucket.setdefault(_match_bucket(qso), []).append(
            (_qso_datetime(qso), qso)
        )

    def find(self, qso: dict[str, Any]) -> dict[str, Any] | None:
        local_id = str(qso.get("local_id") or "").strip()
        if local_id and local_id in self.by_id:
            return self.by_id[local_id]

        bucket = _match_bucket(qso)
        target_mode = bucket[2]
        target_dt = _qso_datetime(qso)

        for candidate_dt, candidate in self.by_bucket.get(bucket, []):
            if not _station_compatible(qso, candidate):
                continue

            if target_mode not in FUZZY_DIGITAL_MODES:
                if _strict_same_contact(qso, candidate):
                    return candidate
                continue

            if not _frequency_compatible(
                qso,
                candidate,
                self.frequency_tolerance_mhz,
            ):
                continue

            if target_dt is None or candidate_dt is None:
                if _strict_same_contact(qso, candidate):
                    return candidate
                continue

            if abs((target_dt - candidate_dt).total_seconds()) <= self.tolerance_seconds:
                return candidate
        return None


def find_duplicate_qso(
    qsos: Iterable[dict[str, Any]],
    incoming: dict[str, Any],
    *,
    tolerance_seconds: int = DEFAULT_TIME_TOLERANCE_SECONDS,
    frequency_tolerance_mhz: float = DEFAULT_FREQUENCY_TOLERANCE_MHZ,
) -> dict[str, Any] | None:
    return QsoMatcher(
        qsos,
        tolerance_seconds=tolerance_seconds,
        frequency_tolerance_mhz=frequency_tolerance_mhz,
    ).find(incoming)
