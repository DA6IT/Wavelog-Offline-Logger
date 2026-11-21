from __future__ import annotations

import contextlib
import json
import ntpath
import os
import re
import shutil
import sys
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from typing import Any, Iterable

from logger_core import (
    adif_field,
    adif_fields_to_qso,
    band_from_mhz,
    parse_adif,
    qso_hash,
    qso_to_adif_fields,
)

from qso_duplicates import DEFAULT_TIME_TOLERANCE_SECONDS, QsoMatcher


SETTING_ENABLED = "wsjtx_sync_enabled"  # legacy compatibility
SETTING_LOG_PATH = "wsjtx_sync_log_path"
SETTING_PROFILE_NAME = "wsjtx_sync_profile_name"
SETTING_ON_STARTUP = "wsjtx_sync_on_startup"
SETTING_ON_SHUTDOWN = "wsjtx_sync_on_shutdown"
SETTING_ON_MANUAL = "wsjtx_sync_on_manual"
SETTING_LAST_RESULT = "wsjtx_sync_last_result"

_MISSING = "__WSJTX_SETTING_MISSING__"


class WsjtxSyncError(RuntimeError):
    pass


@dataclass(frozen=True)
class WsjtxProfile:
    name: str
    directory: Path
    log_path: Path

    @property
    def display_name(self) -> str:
        return f"{self.name}  ·  {self.log_path}"


@dataclass(frozen=True)
class WsjtxSyncSettings:
    # "enabled" stays for backwards compatibility with the first implementation.
    # New code should use the three reason-specific switches below.
    enabled: bool = False
    log_path: Path | None = None
    profile_name: str = ""
    sync_on_startup: bool = False
    sync_on_shutdown: bool = False
    sync_on_manual: bool = False


@dataclass
class WsjtxSyncResult:
    local_before: int = 0
    wsjtx_before: int = 0
    imported_to_local: int = 0
    appended_to_wsjtx: int = 0
    duplicates_from_wsjtx: int = 0
    invalid_from_wsjtx: int = 0
    scope_skipped_from_wsjtx: int = 0
    backup_path: str = ""
    local_after: int = 0
    wsjtx_after: int = 0
    log_path: str = ""


def _as_bool(value: Any) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _read_reason_settings(db) -> tuple[bool, bool, bool]:
    startup_raw = db.get_setting(SETTING_ON_STARTUP, _MISSING)
    shutdown_raw = db.get_setting(SETTING_ON_SHUTDOWN, _MISSING)
    manual_raw = db.get_setting(SETTING_ON_MANUAL, _MISSING)

    new_settings_exist = any(
        value != _MISSING
        for value in (startup_raw, shutdown_raw, manual_raw)
    )

    if new_settings_exist:
        return (
            _as_bool(startup_raw) if startup_raw != _MISSING else False,
            _as_bool(shutdown_raw) if shutdown_raw != _MISSING else False,
            _as_bool(manual_raw) if manual_raw != _MISSING else False,
        )

    # Migration from the first WSJT-X-sync implementation:
    # "enabled" meant "participate in every full profile sync". Preserve that.
    if _as_bool(db.get_setting(SETTING_ENABLED, "0")):
        return True, True, True

    # A fresh Logger profile must not implicitly enable WSJT-X integration.
    # WSJT-X only participates after the user explicitly enables a sync reason.
    return False, False, False


def load_wsjtx_settings(db) -> WsjtxSyncSettings:
    raw_path = str(db.get_setting(SETTING_LOG_PATH, "") or "").strip()
    on_startup, on_shutdown, on_manual = _read_reason_settings(db)
    enabled = on_startup or on_shutdown or on_manual

    return WsjtxSyncSettings(
        enabled=enabled,
        log_path=Path(raw_path).expanduser() if raw_path else None,
        profile_name=str(db.get_setting(SETTING_PROFILE_NAME, "") or "").strip(),
        sync_on_startup=on_startup,
        sync_on_shutdown=on_shutdown,
        sync_on_manual=on_manual,
    )


def save_wsjtx_settings(db, settings: WsjtxSyncSettings) -> None:
    enabled = (
        settings.sync_on_startup
        or settings.sync_on_shutdown
        or settings.sync_on_manual
    )

    # Keep the old master flag up to date for compatibility with older builds.
    db.set_setting(SETTING_ENABLED, "1" if enabled else "0")
    db.set_setting(SETTING_LOG_PATH, str(settings.log_path or ""))
    db.set_setting(SETTING_PROFILE_NAME, settings.profile_name or "")
    db.set_setting(
        SETTING_ON_STARTUP,
        "1" if settings.sync_on_startup else "0",
    )
    db.set_setting(
        SETTING_ON_SHUTDOWN,
        "1" if settings.sync_on_shutdown else "0",
    )
    db.set_setting(
        SETTING_ON_MANUAL,
        "1" if settings.sync_on_manual else "0",
    )


def should_wsjtx_sync_for_reason(
    settings: WsjtxSyncSettings,
    reason: str,
) -> bool:
    reason = str(reason or "").strip().lower()

    if reason == "startup":
        return bool(settings.sync_on_startup)
    if reason == "shutdown":
        return bool(settings.sync_on_shutdown)
    if reason == "manual":
        return bool(settings.sync_on_manual)

    return False


def _wsjtx_root() -> Path:
    """Data location (QStandardPaths::DataLocation parent) of WSJT-X and WS."""
    if sys.platform == "win32":
        return Path(os.environ.get("LOCALAPPDATA", Path.home()))
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support"
    return Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))


def _wsjtx_config_root() -> Path:
    """Where WSJT-X/WS keep ``<AppName>.ini`` outside Windows.

    On Windows the ini lives in the program's data folder itself
    (``%LOCALAPPDATA%\\WS\\WS.ini``); Linux and macOS keep all ini files side
    by side in one configuration directory.
    """
    if sys.platform == "win32":
        return _wsjtx_root()
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Preferences"
    return Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))


# WS ("WS - Digital Mode Suite", formerly WSJT-X Improved, since 3.2.0) uses
# the application name "WS" and, started with --rig-name <name>, "WS - <name>".
# Its data folder is named after the application (%LOCALAPPDATA%\WS - DA6IT)
# and the ADIF log keeps the WSJT-X file name wsjtx_log.adi unless the user
# picked another file (Configuration/MyLog in the ini).
_WS_DIR_RE = re.compile(r"^ws(?: - (?P<instance>.+))?$", re.IGNORECASE)
_WSJTX_DIR_RE = re.compile(r"^wsjt-x(?P<rest>.*)$", re.IGNORECASE)
WSJTX_DEFAULT_LOG_NAME = "wsjtx_log.adi"


def classify_wsjtx_dir(dirname: str) -> tuple[str, str] | None:
    """Return ``(program, instance)`` for a WSJT-X or WS data folder name.

    ``program`` is ``"WS"`` or ``"WSJT-X"``; ``instance`` is the --rig-name
    part ("" for the standard instance).  Other folders return ``None``.
    """
    raw = str(dirname or "").strip()
    match = _WS_DIR_RE.match(raw)
    if match:
        return "WS", (match.group("instance") or "").strip()
    match = _WSJTX_DIR_RE.match(raw)
    if match:
        return "WSJT-X", match.group("rest").lstrip(" -_").strip()
    return None


def re_strip_wsjt_prefix(value: str) -> str:
    if not value.casefold().startswith("wsjt-x"):
        return value
    return value[len("WSJT-X"):].lstrip(" -_") or "Standard"


def _profile_name_from_dir(dirname: str) -> str:
    classified = classify_wsjtx_dir(dirname)
    if classified is None:
        return dirname.strip()
    program, instance = classified
    return f"{program} · {instance}" if instance else program


def _decode_qsettings_value(raw: str) -> str:
    """Decode a QSettings ini string value (quotes and backslash escapes)."""
    value = raw.strip()
    if value.startswith("@"):
        # @Variant(...), @ByteArray(...) etc. are not plain paths/callsigns.
        return ""
    out: list[str] = []
    in_quotes = False
    i = 0
    while i < len(value):
        ch = value[i]
        if ch == '"':
            in_quotes = not in_quotes
        elif ch == "\\" and i + 1 < len(value):
            nxt = value[i + 1]
            if nxt == "x":
                j = i + 2
                digits = ""
                while j < len(value) and len(digits) < 4 and value[j] in "0123456789abcdefABCDEF":
                    digits += value[j]
                    j += 1
                if digits:
                    out.append(chr(int(digits, 16)))
                    i = j
                    continue
            out.append({"n": "\n", "t": "\t", "r": "\r", "0": "\0"}.get(nxt, nxt))
            i += 2
            continue
        elif ch == ";" and not in_quotes:
            break
        else:
            out.append(ch)
        i += 1
    return "".join(out).strip()


_QT_KEY_ESCAPE_RE = re.compile(r"%U([0-9A-Fa-f]{4})|%([0-9A-Fa-f]{2})")


def _unescape_qt_key(value: str) -> str:
    """Undo QSettings' ini key escaping (``%XX`` Latin-1, ``%UXXXX`` UTF-16)."""
    return _QT_KEY_ESCAPE_RE.sub(
        lambda m: chr(int(m.group(1) or m.group(2), 16)), value
    )


def read_wsjtx_ini(path: Path) -> dict[str, str]:
    """Read a WSJT-X/WS ini into ``{"Section/Key/Sub": value}`` (read-only)."""
    result: dict[str, str] = {}
    try:
        text = _read_text(Path(path))
    except (OSError, UnicodeError):
        return result
    section = ""
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith(";"):
            continue
        if stripped.startswith("[") and stripped.endswith("]"):
            section = _unescape_qt_key(stripped[1:-1].strip())
            if section.casefold() == "general":
                section = ""
            continue
        if "=" not in stripped:
            continue
        key, _sep, value = stripped.partition("=")
        key = "/".join(_unescape_qt_key(part) for part in key.strip().split("\\"))
        full = f"{section}/{key}" if section else key
        result[full] = _decode_qsettings_value(value)
    return result


def _ini_candidates(directory: Path) -> list[Path]:
    name = directory.name
    candidates = [directory / f"{name}.ini", _wsjtx_config_root() / f"{name}.ini"]
    unique: list[Path] = []
    for candidate in candidates:
        if candidate not in unique:
            unique.append(candidate)
    return unique


def _usable_log_path(value: str) -> Path | None:
    """Only absolute paths: WS resolves a relative MyLog against its own
    working directory, which the logger cannot know."""
    raw = str(value or "").strip()
    if not raw:
        return None
    path = Path(raw)
    if not (path.is_absolute() or ntpath.isabs(raw)):
        return None
    return path


def _configured_logs(directory: Path) -> list[tuple[str, Path, str]]:
    """Log files of a WS/WSJT-X data folder: ``[(config_label, path, call)]``.

    The active configuration comes first (``MyLog`` or the default
    ``wsjtx_log.adi``); alternative configurations (MultiSettings) follow when
    they name a different file.  The ini is only read, never written.
    """
    default_log = directory / WSJTX_DEFAULT_LOG_NAME
    for ini_path in _ini_candidates(directory):
        try:
            if not ini_path.is_file():
                continue
        except OSError:
            continue
        values = read_wsjtx_ini(ini_path)
        my_call = values.get("Configuration/MyCall", "").strip().upper()
        logs: list[tuple[str, Path, str]] = [
            ("", _usable_log_path(values.get("Configuration/MyLog", "")) or default_log, my_call)
        ]
        suffix = "/Configuration/MyLog"
        for key, value in sorted(values.items()):
            if key == "Configuration/MyLog" or not key.endswith(suffix):
                continue
            log_path = _usable_log_path(value)
            if log_path is None:
                continue
            group = key[: -len(suffix)]
            label = group.split("/")[-1]
            call = values.get(f"{group}/Configuration/MyCall", "").strip().upper() or my_call
            logs.append((label, log_path, call))
        return logs
    return [("", default_log, "")]


def _same_path(a: Path, b: Path) -> bool:
    return os.path.normcase(os.path.normpath(str(a))) == os.path.normcase(os.path.normpath(str(b)))


def discover_wsjtx_profiles() -> list[WsjtxProfile]:
    """Find WS and WSJT-X data folders (incl. --rig-name instances).

    WS folders come first because WS replaces WSJT-X Improved and keeps a
    one-off copy of the old WSJT-X log; the old folder is no longer written.
    """
    root = _wsjtx_root()
    if not root.exists():
        return []

    try:
        children = sorted(root.iterdir(), key=lambda p: p.name.casefold())
    except OSError:
        return []

    found: list[tuple[int, str, WsjtxProfile]] = []
    for child in children:
        classified = classify_wsjtx_dir(child.name)
        if classified is None:
            continue
        try:
            if not child.is_dir():
                continue
        except OSError:
            continue

        program, instance = classified
        base_name = _profile_name_from_dir(child.name)
        seen: list[Path] = []
        for config_label, log_path, my_call in _configured_logs(child):
            if any(_same_path(log_path, other) for other in seen):
                continue
            seen.append(log_path)
            label = f"{base_name} ({my_call})" if my_call else base_name
            name = f"{label} – {config_label}" if config_label else label
            found.append(
                (
                    0 if program == "WS" else 1,
                    child.name.casefold(),
                    WsjtxProfile(name=name, directory=child, log_path=log_path),
                )
            )

    found.sort(key=lambda item: (item[0], item[1]))
    return [profile for _order, _name, profile in found]


def ws_replacement_hint(log_path: Path | None, profiles: Iterable[WsjtxProfile] | None = None) -> WsjtxProfile | None:
    """Return the WS profile that replaced the selected WSJT-X folder, if any.

    WS copies the WSJT-X log once and then writes only into its own folder,
    so a sync that still points at ``WSJT-X[ - rig]`` misses new QSOs.
    """
    if log_path is None:
        return None
    classified = classify_wsjtx_dir(Path(log_path).parent.name)
    if classified is None or classified[0] != "WSJT-X":
        return None
    instance = classified[1].casefold()
    for profile in profiles if profiles is not None else discover_wsjtx_profiles():
        other = classify_wsjtx_dir(profile.directory.name)
        if (
            other
            and other[0] == "WS"
            and other[1].casefold() == instance
            and not _same_path(profile.log_path, Path(log_path))
        ):
            return profile
    return None


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8-sig")
    except UnicodeDecodeError:
        return path.read_text(encoding="latin-1")


def read_wsjtx_qsos(path: Path) -> list[dict[str, Any]]:
    path = Path(path)
    if not path.exists():
        return []

    try:
        text = _read_text(path)
    except OSError as exc:
        raise WsjtxSyncError(f"WSJT-X/WS-Log konnte nicht gelesen werden: {exc}") from exc

    if not text.strip():
        return []

    try:
        return [adif_fields_to_qso(fields) for fields in parse_adif(text)]
    except Exception as exc:
        raise WsjtxSyncError(f"WSJT-X/WS-ADIF konnte nicht ausgewertet werden: {exc}") from exc


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


def _active_station_call(db) -> str:
    return str(
        db.get_setting("station_call", "")
        or db.get_setting("operator_call", "")
        or ""
    ).strip().upper()


def _belongs_to_active_station(qso: dict[str, Any], db) -> bool:
    """
    Reject only an explicitly conflicting STATION_CALLSIGN.

    Missing STATION_CALLSIGN is accepted because older/external WSJT-X logs
    often do not contain it. The active logger profile then supplies the
    station identity during normalization.
    """
    active = _active_station_call(db)
    station = str(qso.get("station_call") or "").strip().upper()
    return not (active and station and station != active)


def _normalize_qso(qso: dict[str, Any], db=None) -> dict[str, Any]:
    row = dict(qso)
    row.pop("_file", None)

    row["call"] = str(row.get("call") or "").strip().upper()
    row["qso_date"] = _normalize_date(row.get("qso_date"))
    row["time_on"] = _normalize_time(row.get("time_on"))
    row["mode"] = str(row.get("mode") or "").strip().upper()
    row["band"] = str(row.get("band") or "").strip()

    freq = str(row.get("freq") or "").strip().replace(",", ".")
    row["freq"] = freq
    if not row["band"] and freq:
        try:
            row["band"] = band_from_mhz(float(freq)) or ""
        except (TypeError, ValueError):
            pass

    if db is not None:
        if not str(row.get("station_call") or "").strip():
            row["station_call"] = _active_station_call(db)

        if not str(row.get("operator_call") or "").strip():
            row["operator_call"] = str(
                db.get_setting("operator_call", "") or ""
            ).strip().upper()

        defaults = {
            # Current Logger profile setting first, optional legacy aliases after it.
            "my_gridsquare": ("locator", "my_gridsquare"),
            "my_qth": ("qth", "my_qth", "my_city"),
            "my_state": ("my_state",),
            "my_dxcc": ("my_dxcc",),
            "my_cq_zone": ("my_cq_zone",),
            "my_itu_zone": ("my_itu_zone",),
            "my_pota_ref": ("my_pota_ref",),
            "my_sota_ref": ("my_sota_ref",),
            "my_wwff_ref": ("my_wwff_ref",),
        }
        for field, setting_names in defaults.items():
            if str(row.get(field) or "").strip():
                continue
            for setting in setting_names:
                value = str(db.get_setting(setting, "") or "").strip()
                if value:
                    row[field] = value
                    break

    row["station_call"] = str(row.get("station_call") or "").strip().upper()
    row["operator_call"] = str(row.get("operator_call") or "").strip().upper()
    return row


def _valid_qso(qso: dict[str, Any]) -> bool:
    return bool(
        qso.get("call")
        and qso.get("qso_date")
        and qso.get("time_on")
        and qso.get("band")
        and qso.get("mode")
    )


WSJTX_EXPORT_FIELDS = [
    "CALL",
    "QSO_DATE",
    "TIME_ON",
    "QSO_DATE_OFF",
    "TIME_OFF",
    "BAND",
    "FREQ",
    "MODE",
    "SUBMODE",
    "RST_SENT",
    "RST_RCVD",
    "GRIDSQUARE",
    "COUNTRY",
    "CONT",
    "CQZ",
    "ITUZ",
    "NAME",
    "QTH",
    "TX_PWR",
    "COMMENT",
    "NOTES",
    "OPERATOR",
    "STATION_CALLSIGN",
    "CONTEST_ID",
    "STX",
    "SRX",
    "STX_STRING",
    "SRX_STRING",
    "PROP_MODE",
    "MY_GRIDSQUARE",
    "MY_CITY",
    "MY_STATE",
    "MY_DXCC",
    "MY_CQ_ZONE",
    "MY_ITU_ZONE",
    "POTA_REF",
    "SOTA_REF",
    "WWFF_REF",
    "MY_POTA_REF",
    "MY_SOTA_REF",
    "MY_WWFF_REF",
    "MY_IOTA",
    "MY_SIG",
    "MY_SIG_INFO",
]


def qso_to_wsjtx_adif_record(qso: dict[str, Any]) -> str:
    fields = qso_to_adif_fields(qso)
    return "".join(
        adif_field(name, fields.get(name))
        for name in WSJTX_EXPORT_FIELDS
    ) + "<EOR>\n"


def _backup_wsjtx_log(path: Path) -> str:
    if not path.exists() or path.stat().st_size == 0:
        return ""

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    target = path.with_name(f"{path.name}.backup-{stamp}")
    counter = 2

    while target.exists():
        target = path.with_name(f"{path.name}.backup-{stamp}-{counter}")
        counter += 1

    try:
        shutil.copy2(path, target)
    except OSError as exc:
        raise WsjtxSyncError(
            f"WSJT-X/WS-Backup konnte nicht erstellt werden: {exc}"
        ) from exc

    return str(target)


# Backups of the WSJT-X/WS log made before each writing sync.  Only the newest
# ones are kept; older ones are removed after a verified write.
WSJTX_BACKUP_KEEP = 10


def prune_wsjtx_backups(
    path: Path,
    keep: int = WSJTX_BACKUP_KEEP,
    *,
    protect: str = "",
    now: datetime | None = None,
    daily_days: int = 7,
) -> int:
    """Delete old backups of ``path``; return how many were deleted.

    Kept: the newest ``keep`` backups, additionally the newest backup of each
    of the last ``daily_days`` days (so frequent syncs cannot push yesterday's
    state out), every backup dated in the future (wrong clock – its order
    cannot be trusted) and ``protect`` (the backup just made).

    Only files named exactly ``<log>.backup-YYYYMMDD-HHMMSS[-n]`` next to the
    log are considered, so the log itself and foreign files are never touched.
    The name is compared case-insensitively only on Windows.
    """
    path = Path(path)
    flags = re.IGNORECASE if os.name == "nt" else 0
    pattern = re.compile(
        re.escape(path.name) + r"\.backup-(\d{8}-\d{6})(?:-(\d+))?",
        flags,
    )
    now = now or datetime.now()
    try:
        candidates = list(path.parent.iterdir())
    except OSError:
        return 0

    backups: list[tuple[datetime, int, Path]] = []
    for candidate in candidates:
        match = pattern.fullmatch(candidate.name)
        if not match:
            continue
        try:
            stamp = datetime.strptime(match.group(1), "%Y%m%d-%H%M%S")
        except ValueError:
            continue
        if stamp > now + timedelta(minutes=5):
            continue  # future-dated: never pruned, never counted
        try:
            if not candidate.is_file():
                continue
        except OSError:
            continue
        backups.append((stamp, int(match.group(2) or 1), candidate))

    backups.sort(key=lambda item: (item[0], item[1]), reverse=True)
    keep_paths = {item[2] for item in backups[: max(0, int(keep))]}
    first_day = (now - timedelta(days=max(0, int(daily_days)) - 1)).date()
    seen_days: set = set()
    for stamp, _counter, candidate in backups:
        day = stamp.date()
        if day >= first_day and day not in seen_days:
            seen_days.add(day)
            keep_paths.add(candidate)

    removed = 0
    for _stamp, _counter, candidate in backups:
        if candidate in keep_paths:
            continue
        if protect and _same_path(candidate, Path(protect)):
            continue
        try:
            candidate.unlink()
            removed += 1
        except OSError:
            # A locked or read-only backup simply stays; never fail the sync.
            continue
    return removed


def _append_records(path: Path, qsos: list[dict[str, Any]]) -> tuple[int, str]:
    if not qsos:
        return 0, ""

    path.parent.mkdir(parents=True, exist_ok=True)

    # Re-read immediately before writing because WSJT-X could have logged
    # another QSO since the first scan.
    latest = read_wsjtx_qsos(path)
    matcher = QsoMatcher(latest)

    pending: list[dict[str, Any]] = []
    for qso in qsos:
        if matcher.find(qso) is None:
            pending.append(qso)
            matcher.add(qso)

    if not pending:
        return 0, ""

    backup = _backup_wsjtx_log(path)
    payload = "".join(qso_to_wsjtx_adif_record(qso) for qso in pending)

    try:
        needs_newline = False

        if path.exists() and path.stat().st_size:
            with path.open("rb") as current:
                current.seek(-1, os.SEEK_END)
                needs_newline = current.read(1) not in {b"\n", b"\r"}

        with path.open("a", encoding="utf-8", newline="\n") as handle:
            if needs_newline:
                handle.write("\n")
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())

    except OSError as exc:
        raise WsjtxSyncError(
            f"WSJT-X/WS-Log konnte nicht ergänzt werden: {exc}"
        ) from exc

    verified = read_wsjtx_qsos(path)
    verified_matcher = QsoMatcher(verified)
    missing_after_write = [
        qso
        for qso in pending
        if verified_matcher.find(qso) is None
    ]

    if missing_after_write:
        raise WsjtxSyncError(
            f"WSJT-X/WS-Log wurde geschrieben, aber "
            f"{len(missing_after_write)} QSO(s) konnten danach nicht verifiziert werden."
            + (f" Backup: {backup}" if backup else "")
        )

    # Verified: now it is safe to drop backups beyond the newest ones.
    if backup:
        prune_wsjtx_backups(path, protect=backup)

    return len(pending), backup


def sync_wsjtx_with_local(
    store,
    db,
    settings: WsjtxSyncSettings | None = None,
) -> WsjtxSyncResult:
    settings = settings or load_wsjtx_settings(db)
    try:
        return _sync_wsjtx_with_local(store, db, settings)
    except Exception as exc:
        # Record the failure too, so "last synchronization" never keeps
        # showing an older success after a failed run.
        _remember_failed_result(db, settings.log_path, str(exc))
        raise


def _sync_wsjtx_with_local(store, db, settings: WsjtxSyncSettings) -> WsjtxSyncResult:
    path = settings.log_path

    if path is None:
        raise WsjtxSyncError(
            "Kein WSJT-X/WS Profil bzw. keine wsjtx_log.adi ausgewählt."
        )

    result = WsjtxSyncResult()

    local_qsos = [_normalize_qso(qso, db) for qso in store.scan()]
    raw_wsjtx_qsos = read_wsjtx_qsos(path)

    result.local_before = len(local_qsos)
    result.wsjtx_before = len(raw_wsjtx_qsos)

    local_matcher = QsoMatcher(local_qsos)
    existing_ids = {
        str(qso.get("local_id") or "")
        for qso in local_qsos
    }

    # WSJT-X -> local master log.
    pending_import: list[dict[str, Any]] = []
    for raw_incoming in raw_wsjtx_qsos:
        if not _belongs_to_active_station(raw_incoming, db):
            result.scope_skipped_from_wsjtx += 1
            continue

        incoming = _normalize_qso(raw_incoming, db)

        if not _valid_qso(incoming):
            result.invalid_from_wsjtx += 1
            continue

        if local_matcher.find(incoming) is not None:
            result.duplicates_from_wsjtx += 1
            continue

        candidate = dict(incoming)
        incoming_id = str(candidate.get("local_id") or "")

        if not incoming_id or incoming_id in existing_ids:
            # Assigned here (instead of inside store.add) so the batch below
            # can be matched against later WSJT-X records before writing.
            candidate["local_id"] = str(uuid.uuid4())

        pending_import.append(candidate)
        existing_ids.add(str(candidate["local_id"]))
        local_matcher.add(_normalize_qso(candidate, db))
        result.imported_to_local += 1

    if pending_import:
        # One journaled append and one metadata transaction for the whole
        # import instead of an fsync + commit per QSO.
        saved_rows = store.add_many(pending_import)
        bulk = getattr(db, "bulk", None)
        with (bulk() if bulk is not None else contextlib.nullcontext()):
            for saved in saved_rows:
                db.ensure_local(saved["local_id"], qso_hash(saved))

    # Local master log -> selected WSJT-X profile.
    merged_local = [_normalize_qso(qso, db) for qso in store.scan()]
    wsjtx_now = [
        _normalize_qso(qso, db)
        for qso in read_wsjtx_qsos(path)
        if _belongs_to_active_station(qso, db)
    ]
    wsjtx_matcher = QsoMatcher(wsjtx_now)

    missing_for_wsjtx: list[dict[str, Any]] = []

    for qso in merged_local:
        if not _valid_qso(qso):
            continue

        if wsjtx_matcher.find(qso) is None:
            missing_for_wsjtx.append(qso)
            wsjtx_matcher.add(qso)

    appended, backup = _append_records(path, missing_for_wsjtx)

    result.appended_to_wsjtx = appended
    result.backup_path = backup
    result.local_after = len(store.scan())
    result.wsjtx_after = len(read_wsjtx_qsos(path))
    result.log_path = str(path)

    _remember_last_result(db, result)
    return result


def _remember_last_result(db, result: WsjtxSyncResult) -> None:
    """Store when and with which outcome the last sync ran (for the UI)."""
    try:
        db.set_setting(
            SETTING_LAST_RESULT,
            json.dumps(
                {
                    "at": datetime.now().strftime("%Y-%m-%d %H:%M"),
                    "path": result.log_path,
                    "imported": result.imported_to_local,
                    "appended": result.appended_to_wsjtx,
                    "local": result.local_after,
                    "wsjtx": result.wsjtx_after,
                },
                ensure_ascii=False,
            ),
        )
    except Exception:
        # Purely informational; never fail a finished sync because of it.
        pass


def _remember_failed_result(db, path: Path | None, message: str) -> None:
    try:
        db.set_setting(
            SETTING_LAST_RESULT,
            json.dumps(
                {
                    "at": datetime.now().strftime("%Y-%m-%d %H:%M"),
                    "path": str(path or ""),
                    "error": str(message or "")[:300],
                },
                ensure_ascii=False,
            ),
        )
    except Exception:
        pass


def load_last_result(db) -> dict[str, Any]:
    try:
        data = json.loads(db.get_setting(SETTING_LAST_RESULT, "") or "{}")
    except (TypeError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def format_last_result(data: dict[str, Any], language: str = "de") -> str:
    if not data.get("at"):
        return (
            "Noch kein Abgleich für dieses Logger-Profil."
            if language != "en"
            else "No synchronization for this Logger profile yet."
        )
    at = str(data.get("at"))
    try:
        stamp = datetime.strptime(at, "%Y-%m-%d %H:%M").strftime(
            "%d.%m.%Y %H:%M" if language != "en" else "%Y-%m-%d %H:%M"
        )
    except ValueError:
        stamp = at
    path_text = str(data.get("path") or "")
    file_note = ""
    if path_text:
        parent = ntpath.basename(ntpath.dirname(path_text.replace("/", "\\")))
        name = ntpath.basename(path_text.replace("/", "\\"))
        file_note = f" · {parent}\\{name}" if parent else f" · {name}"
    if data.get("error"):
        error = str(data.get("error"))
        if language == "en":
            return f"Last synchronization FAILED: {stamp}{file_note} · {error}"
        return f"Letzter Abgleich FEHLGESCHLAGEN: {stamp}{file_note} · {error}"
    try:
        imported = int(data.get("imported") or 0)
        appended = int(data.get("appended") or 0)
        in_file = int(data.get("wsjtx") or 0)
    except (TypeError, ValueError):
        imported = appended = in_file = 0
    if language == "en":
        return (
            f"Last synchronization: {stamp}{file_note} · local +{imported} · "
            f"file +{appended} · {in_file} QSOs in the file"
        )
    return (
        f"Letzter Abgleich: {stamp}{file_note} · lokal +{imported} · "
        f"Datei +{appended} · {in_file} QSOs in der Datei"
    )


def format_wsjtx_result(
    result: WsjtxSyncResult,
    language: str = "de",
) -> str:
    if language == "en":
        lines = [
            "WSJT-X/WS synchronization completed.",
            "",
            f"Local log: {result.local_before} → {result.local_after}",
            f"WSJT-X/WS log: {result.wsjtx_before} → {result.wsjtx_after}",
            f"Imported into local log: {result.imported_to_local}",
            f"Added to WSJT-X/WS: {result.appended_to_wsjtx}",
            f"Existing/duplicates ignored: {result.duplicates_from_wsjtx}",
            f"Invalid WSJT-X/WS records skipped: {result.invalid_from_wsjtx}",
            f"Other station calls skipped: {result.scope_skipped_from_wsjtx}",
        ]

        if result.log_path:
            lines.extend(["", f"File: {result.log_path}"])
        if result.backup_path:
            lines.extend(["", f"Backup: {result.backup_path}"])
        hint = ws_replacement_hint(Path(result.log_path)) if result.log_path else None
        if hint is not None:
            lines.extend(["", _ws_hint_text(hint, "en")])

        return "\n".join(lines)

    lines = [
        "WSJT-X/WS-Abgleich abgeschlossen.",
        "",
        f"Lokales Log: {result.local_before} → {result.local_after}",
        f"WSJT-X/WS-Log: {result.wsjtx_before} → {result.wsjtx_after}",
        f"Neu ins lokale Log übernommen: {result.imported_to_local}",
        f"Neu zu WSJT-X/WS ergänzt: {result.appended_to_wsjtx}",
        f"Vorhanden/Dubletten ignoriert: {result.duplicates_from_wsjtx}",
        f"Ungültige WSJT-X/WS-Datensätze übersprungen: {result.invalid_from_wsjtx}",
        f"Andere Stationsrufzeichen übersprungen: {result.scope_skipped_from_wsjtx}",
    ]

    if result.log_path:
        lines.extend(["", f"Datei: {result.log_path}"])
    if result.backup_path:
        lines.extend(["", f"Backup: {result.backup_path}"])
    hint = ws_replacement_hint(Path(result.log_path)) if result.log_path else None
    if hint is not None:
        lines.extend(["", _ws_hint_text(hint, "de")])

    return "\n".join(lines)


def _ws_hint_text(profile: WsjtxProfile, language: str) -> str:
    if language == "en":
        return (
            f"Note: WS was found ({profile.name}). WS writes new QSOs only to "
            f"{profile.log_path}; the selected WSJT-X log is no longer updated. "
            "Select the WS profile in Settings → WSJT-X / WS Sync."
        )
    return (
        f"Hinweis: WS gefunden ({profile.name}). WS schreibt neue QSOs nur noch in "
        f"{profile.log_path}; die gewählte WSJT-X-Datei wird nicht mehr fortgeschrieben. "
        "Bitte unter Einstellungen → WSJT-X / WS Sync das WS-Profil wählen."
    )



class WsjtxSyncSettingsPanel(ttk.Frame):
    """Embedded WSJT-X / WS settings page for the main Settings notebook."""

    def __init__(
        self,
        parent,
        db,
        *,
        language: str = "de",
        sync_callback=None,
    ):
        super().__init__(parent)
        self.db = db
        self.language = "en" if language == "en" else "de"
        self.sync_callback = sync_callback
        self.profiles: list[WsjtxProfile] = []
        self.profile_by_display: dict[str, WsjtxProfile] = {}
        de = self.language == "de"

        self.profile_var = tk.StringVar()
        self.path_var = tk.StringVar()
        self.startup_var = tk.BooleanVar(value=False)
        self.shutdown_var = tk.BooleanVar(value=False)
        self.manual_var = tk.BooleanVar(value=False)
        self.status_var = tk.StringVar(value="")
        self.last_result_var = tk.StringVar(value="")

        # Equal columns: a long text on one side must not squeeze the other.
        self.columnconfigure(0, weight=1, uniform="wsjtx_cards")
        self.columnconfigure(1, weight=1, uniform="wsjtx_cards")
        self.rowconfigure(0, weight=1)

        profile_card = ttk.Frame(self, style="Card.TFrame", padding=18)
        profile_card.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        profile_card.columnconfigure(0, weight=1)

        timing_card = ttk.Frame(self, style="Card.TFrame", padding=18)
        timing_card.grid(row=0, column=1, sticky="nsew", padx=(8, 0))
        timing_card.columnconfigure(0, weight=1)

        # -- left: program/profile, log file and the manual sync -------------
        ttk.Label(
            profile_card,
            text="WSJT-X / WS Profil & Logdatei" if de else "WSJT-X / WS profile & log file",
            style="CardTitle.TLabel",
        ).grid(row=0, column=0, sticky="w")

        ttk.Label(
            profile_card,
            text=(
                "Wähle das WS- oder WSJT-X-Profil, das zu diesem Offline-Logger-Profil gehört. "
                "WS (früher WSJT-X Improved) wird unter „WS“ bzw. „WS - <Rigname>“ erkannt, "
                "auch mit --rig-name gestartete Instanzen."
                if de
                else
                "Select the WS or WSJT-X profile belonging to this Offline Logger profile. "
                "WS (formerly WSJT-X Improved) is detected as \"WS\" or \"WS - <rig name>\", "
                "including instances started with --rig-name."
            ),
            style="Muted.Card.TLabel",
            wraplength=480,
        ).grid(row=1, column=0, sticky="ew", pady=(4, 12))

        ttk.Label(
            profile_card,
            text="Programm / Profil" if de else "Program / profile",
            style="Card.TLabel",
        ).grid(row=2, column=0, sticky="w", pady=(0, 3))

        profile_row = ttk.Frame(profile_card, style="Card.TFrame")
        profile_row.grid(row=3, column=0, sticky="ew")
        profile_row.columnconfigure(0, weight=1)

        self.profile_combo = ttk.Combobox(profile_row, textvariable=self.profile_var, state="readonly")
        self.profile_combo.grid(row=0, column=0, sticky="ew")
        self.profile_combo.bind("<<ComboboxSelected>>", self._profile_selected)

        ttk.Button(
            profile_row,
            text="Neu suchen" if de else "Rescan",
            command=self._discover,
        ).grid(row=0, column=1, padx=(8, 0))

        ttk.Label(
            profile_card,
            text="Logdatei (wsjtx_log.adi)" if de else "Log file (wsjtx_log.adi)",
            style="Card.TLabel",
        ).grid(row=4, column=0, sticky="w", pady=(12, 3))

        path_row = ttk.Frame(profile_card, style="Card.TFrame")
        path_row.grid(row=5, column=0, sticky="ew")
        path_row.columnconfigure(0, weight=1)

        path_entry = ttk.Entry(path_row, textvariable=self.path_var)
        path_entry.grid(row=0, column=0, sticky="ew")
        path_entry.bind("<FocusOut>", lambda _e: self._update_status())

        ttk.Button(
            path_row,
            text="Datei wählen …" if de else "Choose file …",
            command=self._browse,
        ).grid(row=0, column=1, padx=(8, 0))

        ttk.Separator(profile_card).grid(row=6, column=0, sticky="ew", pady=(16, 12))

        ttk.Label(
            profile_card,
            text="Manuell abgleichen" if de else "Synchronize manually",
            style="CardTitle.TLabel",
        ).grid(row=7, column=0, sticky="w")

        self.sync_button = ttk.Button(
            profile_card,
            text="Jetzt mit WSJT-X / WS abgleichen" if de else "Synchronize with WSJT-X / WS now",
            style="Primary.TButton",
            command=self._save_and_sync,
        )
        self.sync_button.grid(row=8, column=0, sticky="ew", pady=(8, 0))

        ttk.Label(
            profile_card,
            textvariable=self.last_result_var,
            style="Card.TLabel",
            wraplength=480,
        ).grid(row=9, column=0, sticky="ew", pady=(8, 0))

        ttk.Label(
            profile_card,
            textvariable=self.status_var,
            style="Card.TLabel",
            wraplength=480,
        ).grid(row=10, column=0, sticky="ew", pady=(6, 0))

        ttk.Label(
            profile_card,
            text=(
                "Speichert die Auswahl und gleicht sofort ab – unabhängig von den "
                "automatischen Auslösern rechts. Den Knopf gibt es auch unter „Logbuch & Sync“."
                if de
                else
                "Saves the selection and synchronizes immediately, independent of the "
                "automatic triggers on the right. The button is also on \"Logbook & Sync\"."
            ),
            style="Muted.Card.TLabel",
            wraplength=480,
        ).grid(row=11, column=0, sticky="ew", pady=(6, 0))

        # -- right: automatic triggers, principle and safety ------------------
        ttk.Label(
            timing_card,
            text="Automatischer Abgleich" if de else "Automatic synchronization",
            style="CardTitle.TLabel",
        ).grid(row=0, column=0, sticky="w")

        ttk.Label(
            timing_card,
            text=(
                "Diese Optionen gelten nur für das aktuell ausgewählte Offline-Logger-Profil "
                "und können unabhängig voneinander aktiviert werden."
                if de
                else
                "These options apply only to the currently selected Offline Logger profile "
                "and can be enabled independently."
            ),
            style="Muted.Card.TLabel",
            wraplength=480,
        ).grid(row=1, column=0, sticky="ew", pady=(4, 10))

        ttk.Checkbutton(
            timing_card,
            text="Beim Start des Offline Loggers" if de else "When the Offline Logger starts",
            variable=self.startup_var,
        ).grid(row=2, column=0, sticky="w", pady=4)

        ttk.Checkbutton(
            timing_card,
            text="Beim Beenden des Offline Loggers" if de else "When the Offline Logger closes",
            variable=self.shutdown_var,
        ).grid(row=3, column=0, sticky="w", pady=4)

        ttk.Checkbutton(
            timing_card,
            text="Beim manuellen Gesamtsync" if de else "During a manual full sync",
            variable=self.manual_var,
        ).grid(row=4, column=0, sticky="w", pady=4)

        ttk.Label(
            timing_card,
            text=(
                "Gesamtsync = Knopf „Synchronisieren“ unter Logbuch & Sync (mit Wavelog)."
                if de
                else "Full sync = the \"Synchronize\" button on Logbook & Sync (with Wavelog)."
            ),
            style="Muted.Card.TLabel",
            wraplength=480,
        ).grid(row=5, column=0, sticky="ew", pady=(0, 2))

        ttk.Separator(timing_card).grid(row=6, column=0, sticky="ew", pady=(14, 12))

        ttk.Label(
            timing_card,
            text="Synchronisationsprinzip & Sicherheit" if de else "Principle & safety",
            style="CardTitle.TLabel",
        ).grid(row=7, column=0, sticky="w")

        ttk.Label(
            timing_card,
            text=(
                "Das lokale Logbuch ist der Merge-Hub: Fehlende QSOs werden aus WSJT-X/WS "
                "übernommen und fehlende lokale QSOs in die Logdatei ergänzt. Es wird nichts "
                "gelöscht. Vor Änderungen an einer vorhandenen Logdatei entsteht ein Backup "
                "(die letzten 10 und je eines pro Tag der letzten Woche bleiben erhalten); "
                "Dubletten werden über Rufzeichen, Band, Mode und Zeit erkannt, fremde "
                "STATION_CALLSIGNs nicht übernommen."
                if de
                else
                "The local logbook is the merge hub: missing QSOs are imported from WSJT-X/WS "
                "and missing local QSOs are added to the log file. Nothing is deleted. A backup "
                "(the newest 10 and one per day of the last week are kept) is made before an existing log file is changed; duplicates are matched by "
                "callsign, band, mode and time, other STATION_CALLSIGNs are not imported."
            ),
            style="Muted.Card.TLabel",
            wraplength=480,
        ).grid(row=8, column=0, sticky="ew", pady=(4, 0))

        # Wrap texts to the real card width so nothing is cut off in small
        # windows or with Windows display scaling.
        for card in (profile_card, timing_card):
            card.bind("<Configure>", lambda event, c=card: self._rewrap(c, event.width), add="+")

        self.reload(db, language=self.language)

    @staticmethod
    def _rewrap(card, width: int) -> None:
        wrap = max(200, int(width) - 40)
        for child in card.winfo_children():
            if isinstance(child, ttk.Label):
                try:
                    if int(str(child.cget("wraplength") or 0)) not in (0, wrap):
                        child.configure(wraplength=wrap)
                except (tk.TclError, ValueError):
                    pass

    def reload(self, db=None, *, language: str | None = None):
        if db is not None:
            self.db = db
        if language is not None:
            self.language = "en" if language == "en" else "de"

        current = load_wsjtx_settings(self.db)
        self.path_var.set(str(current.log_path or ""))
        self.startup_var.set(current.sync_on_startup)
        self.shutdown_var.set(current.sync_on_shutdown)
        self.manual_var.set(current.sync_on_manual)

        self._discover(select_saved=False)

        selected = False
        if current.log_path:
            for display, profile in self.profile_by_display.items():
                if _same_path(profile.log_path, current.log_path):
                    self.profile_var.set(display)
                    selected = True
                    break

        if not selected:
            self.profile_var.set("")

        self.refresh_last_result()
        self._update_status()

    def refresh_last_result(self):
        try:
            self.last_result_var.set(format_last_result(load_last_result(self.db), self.language))
        except Exception:
            self.last_result_var.set("")

    def save_to_db(self, db=None) -> WsjtxSyncSettings:
        if db is not None:
            self.db = db

        settings = self._settings()
        save_wsjtx_settings(self.db, settings)
        self._update_status(saved=True)
        return settings

    def _discover(self, select_saved: bool = True):
        previous_path = self.path_var.get().strip()
        self.profiles = discover_wsjtx_profiles()
        self.profile_by_display = {profile.display_name: profile for profile in self.profiles}
        self.profile_combo.configure(values=list(self.profile_by_display))

        if previous_path:
            for display, profile in self.profile_by_display.items():
                if _same_path(profile.log_path, Path(previous_path).expanduser()):
                    self.profile_var.set(display)
                    self._update_status()
                    return

        if select_saved and self.profiles and not previous_path:
            first = self.profiles[0]
            self.profile_var.set(first.display_name)
            self.path_var.set(str(first.log_path))

        self._update_status()

    def _profile_selected(self, _event=None):
        profile = self.profile_by_display.get(self.profile_var.get())
        if profile:
            self.path_var.set(str(profile.log_path))
        self._update_status()

    def _browse(self):
        initial = self.path_var.get().strip()
        initialdir = str(Path(initial).parent) if initial else str(_wsjtx_root())

        selected = filedialog.askopenfilename(
            parent=self.winfo_toplevel(),
            title="wsjtx_log.adi",
            initialdir=initialdir,
            filetypes=[("ADIF", "*.adi *.adif"), ("All files", "*.*")],
        )
        if selected:
            self.path_var.set(selected)
            self.profile_var.set("")
            for display, profile in self.profile_by_display.items():
                if _same_path(profile.log_path, Path(selected)):
                    self.profile_var.set(display)
                    break
        self._update_status()

    def _settings(self) -> WsjtxSyncSettings:
        raw = self.path_var.get().strip()
        path = Path(raw).expanduser() if raw else None
        profile = self.profile_by_display.get(self.profile_var.get())
        profile_name = profile.name if profile else ""

        any_mode = self.startup_var.get() or self.shutdown_var.get() or self.manual_var.get()

        if any_mode and path is None:
            raise WsjtxSyncError(
                "Bitte ein WSJT-X/WS Profil auswählen."
                if self.language == "de"
                else "Select a WSJT-X/WS profile."
            )

        return WsjtxSyncSettings(
            enabled=bool(any_mode),
            log_path=path,
            profile_name=profile_name,
            sync_on_startup=bool(self.startup_var.get()),
            sync_on_shutdown=bool(self.shutdown_var.get()),
            sync_on_manual=bool(self.manual_var.get()),
        )

    def _save_and_sync(self):
        if not self.path_var.get().strip():
            messagebox.showerror(
                "WSJT-X/WS Sync",
                "Bitte zuerst ein WSJT-X/WS Profil oder eine Logdatei auswählen."
                if self.language == "de"
                else "Select a WSJT-X/WS profile or log file first.",
                parent=self.winfo_toplevel(),
            )
            return
        try:
            self.save_to_db()
        except Exception as exc:
            messagebox.showerror("WSJT-X/WS Sync", str(exc), parent=self.winfo_toplevel())
            return

        if self.sync_callback is not None:
            self.sync_callback()

    def _update_status(self, *, saved: bool = False):
        path_text = self.path_var.get().strip()
        de = self.language == "de"
        count = len(self.profiles)

        if not path_text:
            if count:
                text = (
                    f"Noch kein Profil ausgewählt · {count} WSJT-X/WS-Profil(e) gefunden."
                    if de
                    else f"No profile selected yet · {count} WSJT-X/WS profile(s) found."
                )
            else:
                text = (
                    "Kein WSJT-X/WS-Ordner gefunden. Logdatei über „Datei wählen …“ auswählen."
                    if de
                    else "No WSJT-X/WS folder found. Choose the log file with \"Choose file …\"."
                )
        else:
            path = Path(path_text).expanduser()
            if path.exists():
                text = (
                    f"✓ Logdatei gefunden · {count} WSJT-X/WS-Profil(e) erkannt"
                    if de
                    else f"✓ Log file found · {count} WSJT-X/WS profile(s) detected"
                )
            else:
                text = (
                    "Hinweis: Die ausgewählte Logdatei existiert noch nicht. "
                    "Sie wird beim ersten QSO bzw. Abgleich angelegt."
                    if de
                    else
                    "Note: The selected log file does not exist yet. "
                    "It will be created by the first QSO or synchronization."
                )
            hint = ws_replacement_hint(path, self.profiles)
            if hint is not None:
                text += "\n" + _ws_hint_text(hint, self.language)

        if saved:
            text = (
                "✓ Einstellungen für dieses Logger-Profil gespeichert. " + text
                if de
                else "✓ Settings saved for this Logger profile. " + text
            )

        self.status_var.set(text)
