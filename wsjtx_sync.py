from __future__ import annotations

import os
import shutil
import sys
from dataclasses import dataclass
from datetime import datetime
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


SETTING_ENABLED = "wsjtx_sync_enabled"  # legacy compatibility
SETTING_LOG_PATH = "wsjtx_sync_log_path"
SETTING_PROFILE_NAME = "wsjtx_sync_profile_name"
SETTING_ON_STARTUP = "wsjtx_sync_on_startup"
SETTING_ON_SHUTDOWN = "wsjtx_sync_on_shutdown"
SETTING_ON_MANUAL = "wsjtx_sync_on_manual"

DEFAULT_TIME_TOLERANCE_SECONDS = 90
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
    sync_on_manual: bool = True


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

    # For a freshly configured profile, manual sync is the least surprising
    # default. Startup/shutdown stay opt-in.
    return False, False, True


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
    if sys.platform == "win32":
        return Path(os.environ.get("LOCALAPPDATA", Path.home()))
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support"
    return Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))


def re_strip_wsjt_prefix(value: str) -> str:
    if not value.casefold().startswith("wsjt-x"):
        return value
    return value[len("WSJT-X"):].lstrip(" -_") or "Standard"


def _profile_name_from_dir(dirname: str) -> str:
    raw = dirname.strip()
    if raw.casefold() == "wsjt-x":
        return "Standard"
    return re_strip_wsjt_prefix(raw)


def discover_wsjtx_profiles() -> list[WsjtxProfile]:
    root = _wsjtx_root()
    if not root.exists():
        return []

    try:
        children = sorted(root.iterdir(), key=lambda p: p.name.casefold())
    except OSError:
        return []

    profiles: list[WsjtxProfile] = []
    for child in children:
        try:
            if not child.is_dir() or not child.name.casefold().startswith("wsjt-x"):
                continue
        except OSError:
            continue

        profiles.append(
            WsjtxProfile(
                name=_profile_name_from_dir(child.name),
                directory=child,
                log_path=child / "wsjtx_log.adi",
            )
        )
    return profiles


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
        raise WsjtxSyncError(f"WSJT-X Log konnte nicht gelesen werden: {exc}") from exc

    if not text.strip():
        return []

    try:
        return [adif_fields_to_qso(fields) for fields in parse_adif(text)]
    except Exception as exc:
        raise WsjtxSyncError(f"WSJT-X ADIF konnte nicht ausgewertet werden: {exc}") from exc


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


def _frequency_compatible(left: dict[str, Any], right: dict[str, Any]) -> bool:
    try:
        a = float(str(left.get("freq") or "").replace(",", "."))
        b = float(str(right.get("freq") or "").replace(",", "."))
    except (TypeError, ValueError):
        return True

    return abs(a - b) <= 0.10


class QsoMatcher:
    def __init__(
        self,
        qsos: Iterable[dict[str, Any]],
        tolerance_seconds: int = DEFAULT_TIME_TOLERANCE_SECONDS,
    ):
        self.tolerance_seconds = max(0, int(tolerance_seconds))
        self.by_bucket: dict[
            tuple[str, str, str],
            list[tuple[datetime | None, dict[str, Any]]],
        ] = {}

        for qso in qsos:
            self.add(qso)

    def add(self, qso: dict[str, Any]) -> None:
        self.by_bucket.setdefault(_match_bucket(qso), []).append(
            (_qso_datetime(qso), qso)
        )

    def find(self, qso: dict[str, Any]) -> dict[str, Any] | None:
        target_dt = _qso_datetime(qso)

        for candidate_dt, candidate in self.by_bucket.get(_match_bucket(qso), []):
            if not _station_compatible(qso, candidate):
                continue
            if not _frequency_compatible(qso, candidate):
                continue

            if target_dt is None or candidate_dt is None:
                if (
                    _normalize_date(qso.get("qso_date"))
                    == _normalize_date(candidate.get("qso_date"))
                    and _normalize_time(qso.get("time_on"))
                    == _normalize_time(candidate.get("time_on"))
                ):
                    return candidate
                continue

            if abs((target_dt - candidate_dt).total_seconds()) <= self.tolerance_seconds:
                return candidate

        return None


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
            f"WSJT-X Backup konnte nicht erstellt werden: {exc}"
        ) from exc

    return str(target)


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
            f"WSJT-X Log konnte nicht ergänzt werden: {exc}"
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
            f"WSJT-X Log wurde geschrieben, aber "
            f"{len(missing_after_write)} QSO(s) konnten danach nicht verifiziert werden."
            + (f" Backup: {backup}" if backup else "")
        )

    return len(pending), backup


def sync_wsjtx_with_local(
    store,
    db,
    settings: WsjtxSyncSettings | None = None,
) -> WsjtxSyncResult:
    settings = settings or load_wsjtx_settings(db)
    path = settings.log_path

    if path is None:
        raise WsjtxSyncError(
            "Kein WSJT-X Profil bzw. keine wsjtx_log.adi ausgewählt."
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
            candidate["local_id"] = ""

        saved = store.add(candidate)
        db.ensure_local(saved["local_id"], qso_hash(saved))

        existing_ids.add(str(saved["local_id"]))
        normalized_saved = _normalize_qso(saved, db)
        local_matcher.add(normalized_saved)
        result.imported_to_local += 1

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

    return result


def format_wsjtx_result(
    result: WsjtxSyncResult,
    language: str = "de",
) -> str:
    if language == "en":
        lines = [
            "WSJT-X synchronization completed.",
            "",
            f"Local log: {result.local_before} → {result.local_after}",
            f"WSJT-X log: {result.wsjtx_before} → {result.wsjtx_after}",
            f"Imported into local log: {result.imported_to_local}",
            f"Added to WSJT-X: {result.appended_to_wsjtx}",
            f"Existing/duplicates ignored: {result.duplicates_from_wsjtx}",
            f"Invalid WSJT-X records skipped: {result.invalid_from_wsjtx}",
            f"Other station calls skipped: {result.scope_skipped_from_wsjtx}",
        ]

        if result.backup_path:
            lines.extend(["", f"Backup: {result.backup_path}"])

        return "\n".join(lines)

    lines = [
        "WSJT-X-Abgleich abgeschlossen.",
        "",
        f"Lokales Log: {result.local_before} → {result.local_after}",
        f"WSJT-X-Log: {result.wsjtx_before} → {result.wsjtx_after}",
        f"Neu ins lokale Log übernommen: {result.imported_to_local}",
        f"Neu zu WSJT-X ergänzt: {result.appended_to_wsjtx}",
        f"Vorhanden/Dubletten ignoriert: {result.duplicates_from_wsjtx}",
        f"Ungültige WSJT-X-Datensätze übersprungen: {result.invalid_from_wsjtx}",
        f"Andere Stationsrufzeichen übersprungen: {result.scope_skipped_from_wsjtx}",
    ]

    if result.backup_path:
        lines.extend(["", f"Backup: {result.backup_path}"])

    return "\n".join(lines)



class WsjtxSyncSettingsPanel(ttk.Frame):
    """Embedded WSJT-X settings page for the main Settings notebook."""

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

        self.profile_var = tk.StringVar()
        self.path_var = tk.StringVar()
        self.startup_var = tk.BooleanVar(value=False)
        self.shutdown_var = tk.BooleanVar(value=False)
        self.manual_var = tk.BooleanVar(value=True)
        self.status_var = tk.StringVar(value="")

        self.columnconfigure(0, weight=1)
        self.columnconfigure(1, weight=1)
        self.rowconfigure(0, weight=1)

        profile_card = ttk.Frame(
            self,
            style="Card.TFrame",
            padding=18,
        )
        profile_card.grid(
            row=0,
            column=0,
            sticky="nsew",
            padx=(0, 8),
        )
        profile_card.columnconfigure(0, weight=1)

        timing_card = ttk.Frame(
            self,
            style="Card.TFrame",
            padding=18,
        )
        timing_card.grid(
            row=0,
            column=1,
            sticky="nsew",
            padx=(8, 0),
        )
        timing_card.columnconfigure(0, weight=1)

        ttk.Label(
            profile_card,
            text=(
                "WSJT-X Profil & Logdatei"
                if self.language == "de"
                else "WSJT-X profile & log file"
            ),
            style="CardTitle.TLabel",
        ).grid(row=0, column=0, sticky="w")

        ttk.Label(
            profile_card,
            text=(
                "Wähle das WSJT-X Profil, das zu diesem Offline-Logger-Profil gehört. "
                "Auch mit --rig-name gestartete Instanzen werden getrennt erkannt."
                if self.language == "de"
                else
                "Select the WSJT-X profile belonging to this Offline Logger profile. "
                "Instances started with --rig-name are detected separately."
            ),
            style="Muted.Card.TLabel",
            wraplength=480,
        ).grid(
            row=1,
            column=0,
            sticky="ew",
            pady=(4, 16),
        )

        ttk.Label(
            profile_card,
            text="WSJT-X Profil" if self.language == "de" else "WSJT-X profile",
            style="Card.TLabel",
        ).grid(row=2, column=0, sticky="w", pady=(0, 3))

        profile_row = ttk.Frame(profile_card, style="Card.TFrame")
        profile_row.grid(row=3, column=0, sticky="ew")
        profile_row.columnconfigure(0, weight=1)

        self.profile_combo = ttk.Combobox(
            profile_row,
            textvariable=self.profile_var,
            state="readonly",
        )
        self.profile_combo.grid(row=0, column=0, sticky="ew")
        self.profile_combo.bind(
            "<<ComboboxSelected>>",
            self._profile_selected,
        )

        ttk.Button(
            profile_row,
            text="Neu suchen" if self.language == "de" else "Rescan",
            command=self._discover,
        ).grid(row=0, column=1, padx=(8, 0))

        ttk.Label(
            profile_card,
            text="wsjtx_log.adi",
            style="Card.TLabel",
        ).grid(row=4, column=0, sticky="w", pady=(16, 3))

        path_row = ttk.Frame(profile_card, style="Card.TFrame")
        path_row.grid(row=5, column=0, sticky="ew")
        path_row.columnconfigure(0, weight=1)

        ttk.Entry(
            path_row,
            textvariable=self.path_var,
        ).grid(row=0, column=0, sticky="ew")

        ttk.Button(
            path_row,
            text="Datei wählen …" if self.language == "de" else "Choose file …",
            command=self._browse,
        ).grid(row=0, column=1, padx=(8, 0))

        ttk.Separator(profile_card).grid(
            row=6,
            column=0,
            sticky="ew",
            pady=(18, 14),
        )

        ttk.Label(
            profile_card,
            text=(
                "Synchronisationsprinzip"
                if self.language == "de"
                else "Synchronization principle"
            ),
            style="CardTitle.TLabel",
        ).grid(row=7, column=0, sticky="w")

        ttk.Label(
            profile_card,
            text=(
                "Das lokale Logbuch ist der Merge-Hub. Fehlende QSOs werden aus WSJT-X "
                "ins lokale ADI übernommen und fehlende lokale QSOs zu WSJT-X ergänzt. "
                "Es wird nichts automatisch gelöscht."
                if self.language == "de"
                else
                "The local logbook is the merge hub. Missing QSOs are imported from "
                "WSJT-X into the local ADI and missing local QSOs are added to WSJT-X. "
                "Nothing is deleted automatically."
            ),
            style="Muted.Card.TLabel",
            wraplength=480,
        ).grid(
            row=8,
            column=0,
            sticky="ew",
            pady=(4, 0),
        )

        ttk.Label(
            timing_card,
            text=(
                "Automatischer Abgleich"
                if self.language == "de"
                else "Automatic synchronization"
            ),
            style="CardTitle.TLabel",
        ).grid(row=0, column=0, sticky="w")

        ttk.Label(
            timing_card,
            text=(
                "Diese Optionen gelten nur für das aktuell ausgewählte Offline-Logger-Profil "
                "und können unabhängig voneinander aktiviert werden."
                if self.language == "de"
                else
                "These options apply only to the currently selected Offline Logger profile "
                "and can be enabled independently."
            ),
            style="Muted.Card.TLabel",
            wraplength=480,
        ).grid(
            row=1,
            column=0,
            sticky="ew",
            pady=(4, 14),
        )

        ttk.Checkbutton(
            timing_card,
            text=(
                "Beim Start des Offline Loggers"
                if self.language == "de"
                else "When the Offline Logger starts"
            ),
            variable=self.startup_var,
        ).grid(row=2, column=0, sticky="w", pady=5)

        ttk.Checkbutton(
            timing_card,
            text=(
                "Beim Beenden des Offline Loggers"
                if self.language == "de"
                else "When the Offline Logger closes"
            ),
            variable=self.shutdown_var,
        ).grid(row=3, column=0, sticky="w", pady=5)

        ttk.Checkbutton(
            timing_card,
            text=(
                "Beim manuellen Gesamtsync"
                if self.language == "de"
                else "During a manual full sync"
            ),
            variable=self.manual_var,
        ).grid(row=4, column=0, sticky="w", pady=5)

        ttk.Separator(timing_card).grid(
            row=5,
            column=0,
            sticky="ew",
            pady=(18, 14),
        )

        ttk.Label(
            timing_card,
            text=(
                "Sicherheit"
                if self.language == "de"
                else "Safety"
            ),
            style="CardTitle.TLabel",
        ).grid(row=6, column=0, sticky="w")

        ttk.Label(
            timing_card,
            text=(
                "Vor Änderungen an einer vorhandenen wsjtx_log.adi wird automatisch ein "
                "Backup angelegt. Dubletten werden anhand von Rufzeichen, Band, Mode und "
                "Zeit mit kleiner Toleranz erkannt. Explizit fremde STATION_CALLSIGNs "
                "werden nicht in dieses Profil importiert."
                if self.language == "de"
                else
                "Before an existing wsjtx_log.adi is changed, a backup is created "
                "automatically. Duplicates are matched by callsign, band, mode and time "
                "with a small tolerance. Explicitly different STATION_CALLSIGN values "
                "are not imported into this profile."
            ),
            style="Muted.Card.TLabel",
            wraplength=480,
        ).grid(
            row=7,
            column=0,
            sticky="ew",
            pady=(4, 18),
        )

        actions = ttk.Frame(timing_card, style="Card.TFrame")
        actions.grid(row=8, column=0, sticky="ew")
        actions.columnconfigure(0, weight=1)

        self.sync_button = ttk.Button(
            actions,
            text=(
                "Jetzt vollständig abgleichen"
                if self.language == "de"
                else "Synchronize now"
            ),
            style="Primary.TButton",
            command=self._save_and_sync,
        )
        self.sync_button.grid(row=0, column=0, sticky="ew")

        ttk.Label(
            timing_card,
            textvariable=self.status_var,
            style="Muted.Card.TLabel",
            wraplength=480,
        ).grid(
            row=9,
            column=0,
            sticky="ew",
            pady=(12, 0),
        )

        self.reload(db, language=self.language)

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
            saved = str(current.log_path)
            for display, profile in self.profile_by_display.items():
                if str(profile.log_path) == saved:
                    self.profile_var.set(display)
                    selected = True
                    break

        if not selected:
            self.profile_var.set("")

        self._update_status()

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
        self.profile_by_display = {
            profile.display_name: profile
            for profile in self.profiles
        }
        values = list(self.profile_by_display)
        self.profile_combo.configure(values=values)

        if previous_path:
            for display, profile in self.profile_by_display.items():
                if str(profile.log_path) == previous_path:
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
        initialdir = (
            str(Path(initial).parent)
            if initial
            else str(_wsjtx_root())
        )

        selected = filedialog.askopenfilename(
            parent=self.winfo_toplevel(),
            title="wsjtx_log.adi",
            initialdir=initialdir,
            filetypes=[
                ("ADIF", "*.adi"),
                ("All files", "*.*"),
            ],
        )
        if selected:
            self.path_var.set(selected)
            self.profile_var.set("")
        self._update_status()

    def _settings(self) -> WsjtxSyncSettings:
        raw = self.path_var.get().strip()
        path = Path(raw).expanduser() if raw else None
        profile = self.profile_by_display.get(self.profile_var.get())
        profile_name = profile.name if profile else ""

        any_mode = (
            self.startup_var.get()
            or self.shutdown_var.get()
            or self.manual_var.get()
        )

        if any_mode and path is None:
            raise WsjtxSyncError(
                "Bitte ein WSJT-X Profil auswählen."
                if self.language == "de"
                else "Select a WSJT-X profile."
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
        try:
            self.save_to_db()
        except Exception as exc:
            messagebox.showerror(
                "WSJT-X Sync",
                str(exc),
                parent=self.winfo_toplevel(),
            )
            return

        if self.sync_callback is not None:
            self.sync_callback()

    def _update_status(self, *, saved: bool = False):
        path_text = self.path_var.get().strip()

        if not path_text:
            text = (
                "Noch kein WSJT-X Profil ausgewählt."
                if self.language == "de"
                else "No WSJT-X profile selected yet."
            )
        else:
            path = Path(path_text).expanduser()
            if path.exists():
                text = (
                    f"✓ Logdatei gefunden · {len(self.profiles)} WSJT-X Profil(e) erkannt"
                    if self.language == "de"
                    else f"✓ Log file found · {len(self.profiles)} WSJT-X profile(s) detected"
                )
            else:
                text = (
                    "Hinweis: Die ausgewählte Logdatei existiert noch nicht. "
                    "Sie kann beim ersten QSO bzw. Sync angelegt werden."
                    if self.language == "de"
                    else
                    "Note: The selected log file does not exist yet. "
                    "It can be created by the first QSO or synchronization."
                )

        if saved:
            text = (
                "✓ Einstellungen für dieses Logger-Profil gespeichert. " + text
                if self.language == "de"
                else "✓ Settings saved for this Logger profile. " + text
            )

        self.status_var.set(text)
