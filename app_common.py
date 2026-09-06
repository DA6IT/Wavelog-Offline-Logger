from __future__ import annotations

import time
from datetime import datetime, timezone

from callbook import (
    CALLBOOK_SOURCE_DISABLED,
    CALLBOOK_SOURCE_QRZ,
    CALLBOOK_SOURCE_WAVELOG,
)
from logger_core import app_data_dir


BASE_UI_WIDTH = 1420
BASE_UI_HEIGHT = 820
MIN_UI_WIDTH = 900
MIN_UI_HEIGHT = 580

CALLBOOK_SOURCE_LABELS_DE = {
    "Über Wavelog (empfohlen)": CALLBOOK_SOURCE_WAVELOG,
    "Direkt über QRZ.com": CALLBOOK_SOURCE_QRZ,
    "Deaktiviert": CALLBOOK_SOURCE_DISABLED,
}
CALLBOOK_SOURCE_LABELS_EN = {
    "Via Wavelog (recommended)": CALLBOOK_SOURCE_WAVELOG,
    "Directly via QRZ.com": CALLBOOK_SOURCE_QRZ,
    "Disabled": CALLBOOK_SOURCE_DISABLED,
}
CALLBOOK_SOURCE_LABELS = {
    **CALLBOOK_SOURCE_LABELS_DE,
    **CALLBOOK_SOURCE_LABELS_EN,
}


def responsive_ui_scale(width: int, height: int) -> float:
    """Return a stable, bounded zoom factor for the main application window."""
    width = max(1, int(width))
    height = max(1, int(height))
    raw = min(width / BASE_UI_WIDTH, height / BASE_UI_HEIGHT)
    stepped = round(raw * 20.0) / 20.0
    return max(0.65, min(1.10, stepped))


def responsive_spacing_scale(ui_scale: float) -> float:
    """Shrink decorative spacing faster than readable text."""
    return max(0.35, min(1.10, (float(ui_scale) - 0.65) / 0.35))


def callbook_source_labels(language: str) -> dict[str, str]:
    return CALLBOOK_SOURCE_LABELS_EN if language == "en" else CALLBOOK_SOURCE_LABELS_DE


def callbook_source_name(source: str, language: str) -> str:
    labels = callbook_source_labels(language)
    names = {value: key for key, value in labels.items()}
    return names.get(source, names[CALLBOOK_SOURCE_WAVELOG])


def write_startup_log(text: str) -> None:
    try:
        path = app_data_dir() / "startup.log"
        with path.open("a", encoding="utf-8") as handle:
            handle.write(f"[{datetime.now().isoformat(timespec='seconds')}] {text}\n")
    except Exception:
        pass


def utc_from_form(date_s: str, time_s: str, time_mode: str) -> tuple[str, str]:
    date_s = date_s.strip()
    time_s = time_s.strip().replace(":", "")
    if len(time_s) == 4:
        time_s += "00"
    if len(time_s) != 6:
        raise ValueError("Uhrzeit muss HHMM, HHMMSS oder HH:MM:SS sein")
    dt = datetime.strptime(date_s + time_s, "%Y-%m-%d%H%M%S")
    if time_mode == "LOCAL":
        timestamp = time.mktime(dt.timetuple())
        value = datetime.fromtimestamp(timestamp, timezone.utc)
    else:
        value = dt.replace(tzinfo=timezone.utc)
    return value.strftime("%Y-%m-%d"), value.strftime("%H%M%S")


def display_now(time_mode: str) -> datetime:
    return (
        datetime.now().astimezone()
        if time_mode == "LOCAL"
        else datetime.now(timezone.utc)
    )
