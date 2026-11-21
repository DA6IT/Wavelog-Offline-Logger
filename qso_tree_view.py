"""Incremental Treeview updates for the logbook view.

Rebuilding a 20 000-row ``ttk.Treeview`` after every saved, edited or deleted
QSO costs seconds of Tk work.  ``plan_row_diff`` compares the rows currently
shown with the new rows and returns a small list of operations when the
relative order of the remaining rows is unchanged (the normal case for add,
edit, delete and status changes).  Otherwise ``None`` is returned and the
caller performs a full rebuild.

Rows are ``(iid, tag, values)`` tuples.  Inserting/updating uses direct Tcl
calls: ttk's generic option formatting dominated the per-row cost.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Any, Iterable, Sequence

Row = tuple[str, str, tuple]
DEFAULT_MAX_OPS = 2000


def plan_row_diff(old: Sequence[Row], new: Sequence[Row], *, max_ops: int = DEFAULT_MAX_OPS) -> list[tuple] | None:
    """Return ``[("delete", iid) | ("insert", index, row) | ("update", row)]`` or ``None``.

    Applying the operations in order to a tree that shows ``old`` yields
    exactly ``new`` (same ids, order, tags and values).
    """
    old_ids = [row[0] for row in old]
    new_ids = [row[0] for row in new]
    old_set = set(old_ids)
    new_set = set(new_ids)
    if len(old_set) != len(old_ids) or len(new_set) != len(new_ids):
        return None  # duplicate ids: let the full rebuild handle them
    if [iid for iid in old_ids if iid in new_set] != [iid for iid in new_ids if iid in old_set]:
        return None  # reordered rows: full rebuild is simpler and safe
    ops: list[tuple] = [("delete", iid) for iid in old_ids if iid not in new_set]
    if len(ops) > max_ops:
        return None
    old_by_id = {row[0]: row for row in old}
    for index, row in enumerate(new):
        previous = old_by_id.get(row[0])
        if previous is None:
            ops.append(("insert", index, row))
        elif previous[1] != row[1] or tuple(previous[2]) != tuple(row[2]):
            ops.append(("update", row))
        if len(ops) > max_ops:
            return None
    return ops


# Column index of the callsign in a logbook row's values.
CALL_COLUMN = 2


def normalize_call_query(query: object) -> str:
    """Search text as typed by the user -> comparable form ("dl1ab " -> "DL1AB")."""
    return "".join(str(query or "").split()).upper()


def filter_rows_by_call(rows: Sequence[Row], query: object) -> list[Row]:
    """Rows whose callsign contains ``query`` (case-insensitive, substring).

    An empty query returns all rows.  ``*`` and ``?`` act as wildcards for
    "any characters" / "one character", e.g. ``DL*AB`` or ``DL?AB``.
    """
    needle = normalize_call_query(query)
    if not needle:
        return list(rows)
    if "*" in needle or "?" in needle:
        import re

        pattern = re.compile(
            ".*".join(".".join(re.escape(part) for part in chunk.split("?")) for chunk in needle.split("*"))
        )
        return [row for row in rows if pattern.search(_call_of(row))]
    return [row for row in rows if needle in _call_of(row)]


# Column indexes of a logbook row's values (see feature_qso_sync rows).
DATE_COLUMN = 0
BAND_COLUMN = 5
MODE_COLUMN = 6
EMAIL_QSL_COLUMN = 10
QSL_SERVICE_COLUMNS = {"qrz": 11, "lotw": 12, "eqsl": 13, "clublog": 14, "dcl": 15}
QSL_CONFIRMED_MARK = "✓"
EMAIL_QSL_SENT_MARK = "✅"

# Filter choices: key -> German label (the UI translates labels).
PERIOD_CHOICES: tuple[tuple[str, str], ...] = (
    ("", "Alle Zeiträume"),
    ("today", "Heute (UTC)"),
    ("7d", "Letzte 7 Tage"),
    ("30d", "Letzte 30 Tage"),
    ("365d", "Letzte 12 Monate"),
)
QSL_CHOICES: tuple[tuple[str, str], ...] = (
    ("", "Alle QSL-Status"),
    ("confirmed", "Bestätigt (irgendein Dienst)"),
    ("unconfirmed", "Nicht bestätigt"),
    ("lotw", "LoTW bestätigt"),
    ("qrz", "QRZ bestätigt"),
    ("eqsl", "eQSL bestätigt"),
    ("clublog", "ClubLog bestätigt"),
    ("dcl", "DCL bestätigt"),
    ("email_sent", "E-Mail-QSL versendet"),
    ("email_open", "E-Mail-QSL nicht versendet"),
)
SYNC_CHOICES: tuple[tuple[str, str], ...] = (
    ("", "Alle Sync-Status"),
    ("local", "Nur lokal"),
    ("wavelog", "In Wavelog"),
    ("open", "Offen/Konflikt/Fehler"),
)
_OPEN_SYNC_TAGS = frozenset({"modified", "conflict", "error"})


@dataclass(frozen=True)
class QsoFilter:
    """All logbook filters; empty strings mean "no restriction"."""

    call: str = ""
    band: str = ""
    mode: str = ""
    period: str = ""  # "", today, 7d, 30d, 365d, year:YYYY
    country: str = ""
    qsl: str = ""
    sync: str = ""

    @property
    def active(self) -> bool:
        return any((self.call, self.band, self.mode, self.period, self.country, self.qsl, self.sync))

    @property
    def only_call(self) -> bool:
        return bool(self.call) and not any(
            (self.band, self.mode, self.period, self.country, self.qsl, self.sync)
        )


def period_bounds(period: str, today: date | None = None) -> tuple[str, str] | None:
    """``(first, last)`` ISO dates (inclusive) for a period key, or ``None``."""
    key = str(period or "").strip()
    if not key:
        return None
    today = today or datetime.now(timezone.utc).date()
    if key == "today":
        return today.isoformat(), today.isoformat()
    days = {"7d": 7, "30d": 30, "365d": 365}.get(key)
    if days:
        return (today - timedelta(days=days - 1)).isoformat(), today.isoformat()
    if key.startswith("year:") and len(key) == 9 and key[5:].isdigit():
        return f"{key[5:]}-01-01", f"{key[5:]}-12-31"
    return None


def normalize_qso_date(value: object) -> str:
    """``20261120`` / ``2026-11-20`` -> ``2026-11-20`` (``""`` if unknown)."""
    raw = str(value or "").strip()
    digits = raw.replace("-", "")
    if len(digits) >= 8 and digits[:8].isdigit():
        return f"{digits[:4]}-{digits[4:6]}-{digits[6:8]}"
    return ""


def filter_rows(
    rows: Sequence[Row],
    criteria: QsoFilter,
    countries: dict[str, str] | None = None,
    *,
    today: date | None = None,
) -> list[Row]:
    """Rows matching every set criterion (AND); see :class:`QsoFilter`.

    ``countries`` maps a row id to its DXCC country name (computed once per
    logbook refresh, since the country is not a visible column).
    """
    result = filter_rows_by_call(rows, criteria.call) if criteria.call else list(rows)
    if not (criteria.band or criteria.mode or criteria.period or criteria.country or criteria.qsl or criteria.sync):
        return result

    band = criteria.band.strip().casefold()
    mode = criteria.mode.strip().casefold()
    bounds = period_bounds(criteria.period, today)
    country = criteria.country.strip().casefold()
    countries = countries or {}
    qsl = criteria.qsl
    sync = criteria.sync

    def keep(row: Row) -> bool:
        values = row[2]
        if band and _cell(values, BAND_COLUMN).casefold() != band:
            return False
        if mode and _cell(values, MODE_COLUMN).casefold() != mode:
            return False
        if bounds:
            qso_date = normalize_qso_date(_cell(values, DATE_COLUMN))
            if not qso_date or not (bounds[0] <= qso_date <= bounds[1]):
                return False
        if country and str(countries.get(row[0], "")).casefold() != country:
            return False
        if qsl and not _qsl_matches(values, qsl):
            return False
        if sync:
            tag = str(row[1] or "")
            if sync == "open":
                if tag not in _OPEN_SYNC_TAGS:
                    return False
            elif tag != sync:
                return False
        return True

    return [row for row in result if keep(row)]


def _qsl_matches(values: Sequence[Any], key: str) -> bool:
    if key in QSL_SERVICE_COLUMNS:
        return _cell(values, QSL_SERVICE_COLUMNS[key]) == QSL_CONFIRMED_MARK
    confirmed = any(_cell(values, index) == QSL_CONFIRMED_MARK for index in QSL_SERVICE_COLUMNS.values())
    if key == "confirmed":
        return confirmed
    if key == "unconfirmed":
        return not confirmed
    email_sent = _cell(values, EMAIL_QSL_COLUMN) == EMAIL_QSL_SENT_MARK
    if key == "email_sent":
        return email_sent
    if key == "email_open":
        return not email_sent
    return True


def _cell(values: Sequence[Any], index: int) -> str:
    try:
        return str(values[index] or "").strip()
    except (IndexError, TypeError):
        return ""


def filter_choices(rows: Sequence[Row], countries: dict[str, str] | None = None) -> dict[str, list[str]]:
    """Distinct bands, modes, years and countries present in ``rows``."""
    bands: set[str] = set()
    modes: set[str] = set()
    years: set[str] = set()
    names: dict[str, str] = {}
    countries = countries or {}
    for row in rows:
        values = row[2]
        band = _cell(values, BAND_COLUMN)
        if band:
            bands.add(band)
        mode = _cell(values, MODE_COLUMN)
        if mode:
            modes.add(mode.upper())
        qso_date = normalize_qso_date(_cell(values, DATE_COLUMN))
        if qso_date:
            years.add(qso_date[:4])
        name = str(countries.get(row[0], "") or "").strip()
        if name and name != "—":
            # "GERMANY" (imported) and "Germany" (cty.dat) are one country;
            # prefer the mixed-case spelling for display.
            key = name.casefold()
            current = names.get(key)
            if current is None or (current.isupper() and not name.isupper()):
                names[key] = name
    return {
        "bands": sorted(bands, key=_band_sort_key),
        "modes": sorted(modes),
        "years": sorted(years, reverse=True),
        "countries": sorted(names.values(), key=str.casefold),
    }


def _band_sort_key(band: str) -> tuple[int, float, str]:
    """Long wavelengths first: 160m, 80m, … 2m, 70cm, 23cm."""
    text = band.strip().lower()
    try:
        if text.endswith("cm"):
            return 0, -float(text[:-2]) / 100.0, text
        if text.endswith("mm"):
            return 0, -float(text[:-2]) / 1000.0, text
        if text.endswith("m"):
            return 0, -float(text[:-1]), text
    except ValueError:
        pass
    return 1, 0.0, text


def _call_of(row: Row) -> str:
    values = row[2]
    try:
        return str(values[CALL_COLUMN] or "").upper()
    except (IndexError, TypeError):
        return ""


def _text(values: Iterable[Any]) -> tuple[str, ...]:
    # Same display as ttk's insert(values=...): every cell as text.
    return tuple(str(value) for value in values)


def insert_row(tree: Any, index: Any, row: Row) -> None:
    iid, tag, values = row
    tree.tk.call(tree._w, "insert", "", index, "-id", iid, "-values", _text(values), "-tags", (tag,))


def update_row(tree: Any, row: Row) -> None:
    iid, tag, values = row
    tree.tk.call(tree._w, "item", iid, "-values", _text(values), "-tags", (tag,))


def apply_row_diff(tree: Any, ops: Iterable[tuple]) -> None:
    ops = list(ops)
    deletes = [op[1] for op in ops if op[0] == "delete"]
    if deletes:
        existing = [iid for iid in deletes if tree.exists(iid)]
        if existing:
            tree.delete(*existing)
    for op in ops:
        if op[0] == "insert":
            insert_row(tree, op[1], op[2])
        elif op[0] == "update":
            update_row(tree, op[1])
