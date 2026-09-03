from __future__ import annotations

import base64
import ctypes
import hashlib
import json
import os
import re
import shutil
import sqlite3
import ssl
import sys
import threading
import urllib.error
import urllib.parse
import urllib.request
import uuid
import zipfile
from ctypes import wintypes
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

APP_NAME = "DA6IT.de Wavelog Offline Logger"
VERSION = "0.19.0"
ADIF_VERSION = "3.1.7"
USER_AGENT = f"DA6IT.de-Wavelog-Offline-Logger/{VERSION}"
APP_ID_FIELD = "APP_AFUTOOLS_ID"


_tls_context = None
_tls_context_lock = threading.Lock()


def secure_tls_context():
    """Return a verified TLS context backed by the native OS trust store.

    ``truststore`` lets Windows and macOS use their native certificate APIs,
    including safe intermediate-certificate discovery. Linux uses its system
    OpenSSL trust configuration. The fallback remains fully verified and can
    additionally use certifi's Mozilla CA bundle in portable runtimes.
    """
    global _tls_context
    with _tls_context_lock:
        if _tls_context is not None:
            return _tls_context
        try:
            import truststore
            context = truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        except (ImportError, OSError, RuntimeError):
            context = ssl.create_default_context()
            try:
                import certifi
                context.load_verify_locations(cafile=certifi.where())
            except (ImportError, OSError, ssl.SSLError):
                pass
        context.check_hostname = True
        context.verify_mode = ssl.CERT_REQUIRED
        _tls_context = context
        return context


def secure_urlopen(request, *, timeout: int = 15):
    """Open HTTPS with certificate verification; never silently downgrade."""
    return urllib.request.urlopen(request, timeout=timeout, context=secure_tls_context())

BAND_RANGES = [
    (0.1357, 0.1378, "2190m"), (0.472, 0.479, "630m"),
    (1.8, 2.0, "160m"), (3.5, 4.0, "80m"), (5.25, 5.45, "60m"),
    (7.0, 7.3, "40m"), (10.1, 10.15, "30m"), (14.0, 14.35, "20m"),
    (18.068, 18.168, "17m"), (21.0, 21.45, "15m"), (24.89, 24.99, "12m"),
    (28.0, 29.7, "10m"), (50.0, 54.0, "6m"), (70.0, 70.5, "4m"),
    (144.0, 148.0, "2m"), (430.0, 440.0, "70cm"), (1240.0, 1300.0, "23cm"),
]
BANDS = [x[2] for x in BAND_RANGES] + ["SAT"]
MODES = ["SSB", "USB", "LSB", "CW", "FT8", "FT4", "FM", "AM", "RTTY", "PSK31", "JS8", "MFSK", "DIGITALVOICE"]

# Hash schema v2 (v0.11+): contest exchange fields are part of the synchronized QSO.
SYNC_FIELDS = [
    "call", "band", "mode", "freq", "qso_date", "time_on", "rst_sent", "rst_rcvd",
    "gridsquare", "name", "qth", "comment", "notes", "pota_ref", "sota_ref", "wwff_ref", "tx_pwr",
    "operator_call", "contest_id", "stx", "srx", "stx_string", "srx_string",
]

# v0.10 and earlier did not include the contest fields in the sync hash.  Keep
# that exact schema so old metadata can be upgraded without being mistaken for
# a real local+remote edit (which would otherwise create mass conflicts).
LEGACY_SYNC_FIELDS_V010 = [
    "call", "band", "mode", "freq", "qso_date", "time_on", "rst_sent", "rst_rcvd",
    "gridsquare", "name", "qth", "comment", "notes", "pota_ref", "sota_ref", "wwff_ref", "tx_pwr",
    "operator_call",
]


def app_data_dir() -> Path:
    if sys.platform == "win32":
        root = Path(os.environ.get("LOCALAPPDATA", Path.home()))
    elif sys.platform == "darwin":
        root = Path.home() / "Library" / "Application Support"
    else:
        root = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    p = root / "AFU-Tools" / "WavelogOfflineLogger"
    p.mkdir(parents=True, exist_ok=True)
    return p


def default_log_dir() -> Path:
    docs = Path.home() / "Documents"
    if not docs.exists():
        docs = Path.home()
    p = docs / "DA6IT.de Wavelog Logger" / "Logs"
    p.mkdir(parents=True, exist_ok=True)
    return p


def _safe_profile_name(value: str) -> str:
    value = re.sub(r"[^A-Za-z0-9._-]+", "-", (value or "Profil").strip()).strip("-._")
    return value or "Profil"


class ProfileManager:
    """Manage completely isolated logger profiles.

    Every profile owns its own settings/sync SQLite database and a dedicated
    default ADI directory.  Profiles are addressed by UUID so renaming a
    profile can never move/collide with another profile's data.
    """
    def __init__(self, root: Path, *, log_root: Path | None = None):
        self.root = Path(root)
        # Tests and portable callers can keep generated ADI files below an
        # isolated root. Normal application use keeps the established
        # Documents/DA6IT.de Wavelog Logger/Profiles layout.
        self.log_root = Path(log_root) if log_root is not None else None
        self.root.mkdir(parents=True, exist_ok=True)
        self.registry_path = self.root / "profiles.json"
        self.profiles_root = self.root / "profiles"
        self.profiles_root.mkdir(parents=True, exist_ok=True)
        self._registry = self._load_registry()
        if not self._registry.get("profiles"):
            self._bootstrap_first_profile()
        self._normalize_registry()
        self._save_registry()

    def _load_registry(self) -> dict[str, Any]:
        try:
            data = json.loads(self.registry_path.read_text(encoding="utf-8"))
            if isinstance(data, dict) and isinstance(data.get("profiles"), list):
                return data
        except Exception:
            pass
        return {"version": 1, "active_id": "", "profiles": []}

    def _save_registry(self):
        tmp = self.registry_path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(self._registry, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(self.registry_path)

    def _normalize_registry(self):
        seen_ids, seen_names = set(), set()
        cleaned = []
        for raw in self._registry.get("profiles", []):
            pid = str(raw.get("id") or "").strip()
            name = str(raw.get("name") or "").strip()
            if not pid or not name or pid in seen_ids:
                continue
            base, n = name, 2
            while name.casefold() in seen_names:
                name = f"{base} ({n})"; n += 1
            seen_ids.add(pid); seen_names.add(name.casefold())
            cleaned.append({"id": pid, "name": name, "created_at": raw.get("created_at") or utc_now_iso()})
        self._registry["profiles"] = cleaned
        ids = {x["id"] for x in cleaned}
        if self._registry.get("active_id") not in ids and cleaned:
            self._registry["active_id"] = cleaned[0]["id"]

    def _legacy_profile_name(self, db_path: Path) -> str:
        try:
            con = sqlite3.connect(db_path)
            try:
                rows = dict(con.execute("SELECT key,value FROM settings").fetchall())
            finally:
                con.close()
            return (rows.get("station_call") or rows.get("operator_call") or "Importiertes Profil").strip()
        except Exception:
            return "Importiertes Profil"

    def _bootstrap_first_profile(self):
        legacy = self.root / "metadata_v04.db"
        if legacy.exists():
            name = self._legacy_profile_name(legacy)
            p = self.create(name, make_active=True, _save=False)
            # Copy instead of move: v0.9 remains a rollback path.
            try:
                shutil.copy2(legacy, self.metadata_path(p["id"]))
            except Exception:
                pass
        else:
            self.create("Standard", make_active=True, _save=False)

    def list_profiles(self) -> list[dict[str, str]]:
        return [dict(x) for x in self._registry.get("profiles", [])]

    @property
    def active_id(self) -> str:
        return str(self._registry.get("active_id") or "")

    def active_profile(self) -> dict[str, str]:
        p = self.get(self.active_id)
        if not p:
            raise RuntimeError("Kein aktives Profil vorhanden")
        return p

    def get(self, profile_id: str) -> dict[str, str] | None:
        for p in self._registry.get("profiles", []):
            if p["id"] == profile_id:
                return dict(p)
        return None

    def by_name(self, name: str) -> dict[str, str] | None:
        key = (name or "").strip().casefold()
        for p in self._registry.get("profiles", []):
            if p["name"].casefold() == key:
                return dict(p)
        return None

    def profile_dir(self, profile_id: str) -> Path:
        p = self.profiles_root / profile_id
        p.mkdir(parents=True, exist_ok=True)
        return p

    def metadata_path(self, profile_id: str) -> Path:
        return self.profile_dir(profile_id) / "metadata.db"

    def default_log_dir(self, profile_id: str) -> Path:
        p = self.get(profile_id) or {"name": "Profil"}
        if self.log_root is None:
            docs = Path.home() / "Documents"
            if not docs.exists():
                docs = Path.home()
            base = docs / "DA6IT.de Wavelog Logger" / "Profiles"
        else:
            base = self.log_root
        folder = f"{_safe_profile_name(p['name'])}-{profile_id[:6]}"
        out = base / folder / "Logs"
        out.mkdir(parents=True, exist_ok=True)
        return out

    def _unique_name(self, requested: str, exclude_id: str | None = None) -> str:
        name = (requested or "").strip()
        if not name:
            raise ValueError("Bitte einen Profilnamen eingeben")
        for p in self._registry.get("profiles", []):
            if p["id"] != exclude_id and p["name"].casefold() == name.casefold():
                raise ValueError(f"Ein Profil namens '{name}' existiert bereits")
        return name

    def create(self, name: str, *, duplicate_from: str | None = None, make_active: bool = False, _save: bool = True) -> dict[str, str]:
        name = self._unique_name(name)
        pid = uuid.uuid4().hex
        row = {"id": pid, "name": name, "created_at": utc_now_iso()}
        self._registry.setdefault("profiles", []).append(row)
        self.profile_dir(pid)
        target = MetadataDB(self.metadata_path(pid))
        try:
            if duplicate_from:
                src_path = self.metadata_path(duplicate_from)
                if src_path.exists():
                    con = sqlite3.connect(src_path)
                    try:
                        settings = con.execute("SELECT key,value FROM settings").fetchall()
                    finally:
                        con.close()
                    for key, value in settings:
                        if key == "log_dir":
                            continue
                        target.set_setting(str(key), value)
            target.set_setting("log_dir", str(self.default_log_dir(pid)))
        finally:
            target.close()
        if make_active or not self._registry.get("active_id"):
            self._registry["active_id"] = pid
        if _save:
            self._save_registry()
        return dict(row)

    def rename(self, profile_id: str, new_name: str):
        new_name = self._unique_name(new_name, exclude_id=profile_id)
        found = False
        for p in self._registry.get("profiles", []):
            if p["id"] == profile_id:
                p["name"] = new_name
                found = True
                break
        if not found:
            raise KeyError(profile_id)
        self._save_registry()

    def set_active(self, profile_id: str):
        if not self.get(profile_id):
            raise KeyError(profile_id)
        self._registry["active_id"] = profile_id
        self._save_registry()

    def delete(self, profile_id: str, *, delete_adi: bool = False) -> dict[str, Any]:
        """Delete a *local logger profile* only.

        This method deliberately has no Wavelog client dependency and therefore
        cannot delete a remote station profile or remote QSOs.  Optionally it
        removes only ``*.adi`` files from the profile's configured local log
        directory.  Other files are left untouched.
        """
        if len(self._registry.get("profiles", [])) <= 1:
            raise ValueError("Das letzte Profil kann nicht gelöscht werden")
        p = self.get(profile_id)
        if not p:
            return {"log_dir": None, "adi_deleted": 0}

        log_dir = None
        db_path = self.metadata_path(profile_id)
        if db_path.exists():
            try:
                con = sqlite3.connect(db_path)
                row = con.execute("SELECT value FROM settings WHERE key='log_dir'").fetchone()
                con.close()
                if row and row[0]:
                    log_dir = Path(str(row[0])).expanduser()
            except Exception:
                pass

        # Never delete ADI files from a directory that another profile also uses.
        adi_deleted = 0
        if delete_adi and log_dir and log_dir.exists():
            shared_by = []
            for other in self._registry.get("profiles", []):
                if other["id"] == profile_id:
                    continue
                try:
                    odb = self.metadata_path(other["id"])
                    if not odb.exists():
                        continue
                    con = sqlite3.connect(odb)
                    row = con.execute("SELECT value FROM settings WHERE key='log_dir'").fetchone()
                    con.close()
                    if row and row[0] and Path(str(row[0])).expanduser().resolve() == log_dir.resolve():
                        shared_by.append(other["name"])
                except Exception:
                    continue
            if shared_by:
                raise ValueError(
                    "Die ADI-Dateien wurden nicht gelöscht, weil der Log-Ordner auch von "
                    + ", ".join(shared_by) + " verwendet wird."
                )
            for adi in list(log_dir.glob("*.adi")):
                try:
                    adi.unlink()
                    adi_deleted += 1
                except FileNotFoundError:
                    pass

        self._registry["profiles"] = [x for x in self._registry["profiles"] if x["id"] != profile_id]
        if self._registry.get("active_id") == profile_id:
            self._registry["active_id"] = self._registry["profiles"][0]["id"]
        self._save_registry()

        # Internal settings/sync metadata are deleted. Remote Wavelog data is
        # intentionally outside the scope of profile deletion.
        shutil.rmtree(self.profiles_root / profile_id, ignore_errors=True)
        return {"log_dir": log_dir, "adi_deleted": adi_deleted}


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def band_from_mhz(mhz: float) -> str | None:
    for lo, hi, band in BAND_RANGES:
        if lo <= mhz <= hi:
            return band
    return None


def build_fast_log_qso(
    call: str,
    band: str,
    mode: str,
    freq: str,
    rst_sent: str,
    rst_rcvd: str,
    tx_pwr: str,
    profile: dict[str, Any],
    country_fields: dict[str, str] | None = None,
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Build a minimal local QSO for the DXpedition/Fast-Log workflow."""
    normalized_call = (call or "").strip().upper()
    if not normalized_call:
        raise ValueError("Bitte ein Rufzeichen eingeben")
    normalized_band = (band or "").strip()
    normalized_mode = (mode or "").strip().upper()
    if normalized_band not in BANDS:
        raise ValueError("Bitte ein gültiges Band auswählen")
    if normalized_mode not in MODES:
        raise ValueError("Bitte einen gültigen Mode auswählen")
    normalized_freq = (freq or "").strip().replace(",", ".")
    if normalized_freq and float(normalized_freq) <= 0:
        raise ValueError("Die Frequenz muss größer als 0 sein")
    normalized_power = (tx_pwr or "").strip().replace(",", ".")
    if normalized_power and float(normalized_power) < 0:
        raise ValueError("Die Leistung darf nicht negativ sein")
    station_call = str(profile.get("station_call") or profile.get("operator_call") or "").strip().upper()
    if not station_call:
        raise ValueError("Bitte in den Einstellungen mindestens das eigene/Stations-Rufzeichen eintragen")
    timestamp = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    country = dict(country_fields or {})
    return {
        "call": normalized_call,
        "country": country.get("country", ""),
        "cont": country.get("cont", ""),
        "cqz": country.get("cqz", ""),
        "ituz": country.get("ituz", ""),
        "band": normalized_band,
        "mode": normalized_mode,
        "freq": normalized_freq,
        "qso_date": timestamp.strftime("%Y-%m-%d"),
        "time_on": timestamp.strftime("%H%M%S"),
        "rst_sent": (rst_sent or "").strip(),
        "rst_rcvd": (rst_rcvd or "").strip(),
        "gridsquare": "",
        "name": "",
        "qth": "",
        "pota_ref": "",
        "sota_ref": "",
        "wwff_ref": "",
        "comment": "",
        "notes": "",
        "tx_pwr": normalized_power,
        **profile,
        "station_call": station_call,
    }


def sanitize_call_for_filename(call: str) -> str:
    value = (call or "NOCALL").strip().upper().replace("/", "_")
    return re.sub(r"[^A-Z0-9_-]", "_", value) or "NOCALL"




@dataclass
class CountryInfo:
    country: str
    cqz: str
    ituz: str
    cont: str
    primary_prefix: str
    matched_prefix: str = ""


class CountryDB:
    """Offline amateur-radio country lookup using a standard CTY.DAT file."""
    def __init__(self, path: Path):
        self.path = Path(path)
        self.exact: dict[str, CountryInfo] = {}
        self.prefixes: list[tuple[str, CountryInfo]] = []
        self.loaded = False
        self._load()

    @staticmethod
    def _clean_alias(token: str) -> tuple[str, bool, str | None, str | None, str | None]:
        token = token.strip().rstrip(';')
        exact = token.startswith('=')
        if exact:
            token = token[1:]
        m = re.match(r"([A-Z0-9/]+)", token.upper())
        if not m:
            return "", exact, None, None, None
        base = m.group(1)
        cq = re.search(r"\((\d+)\)", token)
        itu = re.search(r"\[(\d+)\]", token)
        cont = re.search(r"\{([A-Z]{2})\}", token.upper())
        return base, exact, cq.group(1) if cq else None, itu.group(1) if itu else None, cont.group(1) if cont else None

    def _load(self):
        if not self.path.exists():
            return
        try:
            lines = self.path.read_text(encoding="utf-8-sig", errors="replace").splitlines()
        except Exception:
            return
        current = None
        aliases: list[str] = []

        def finish():
            nonlocal current, aliases
            if not current:
                return
            country, cqz, ituz, cont, primary = current
            primary = primary.lstrip('*').strip().upper()
            base_info = CountryInfo(country, cqz, ituz, cont, primary, primary)
            if primary:
                self.prefixes.append((primary.upper(), base_info))
            text = "".join(aliases)
            for tok in text.split(','):
                base, exact, cq_override, itu_override, cont_override = self._clean_alias(tok)
                if not base:
                    continue
                info = CountryInfo(
                    country, cq_override or cqz, itu_override or ituz, cont_override or cont, primary, base
                )
                if exact:
                    self.exact[base] = info
                else:
                    self.prefixes.append((base, info))
            current = None
            aliases = []

        for line in lines:
            if not line.strip():
                continue
            # Header lines have the fixed CTY.DAT fields separated by colons.
            parts = line.split(':')
            if len(parts) >= 9 and not line[:1].isspace():
                finish()
                try:
                    country = parts[0].strip()
                    cqz = str(int(parts[1].strip()))
                    ituz = str(int(parts[2].strip()))
                    cont = parts[3].strip().upper()
                    primary = parts[7].strip()
                    current = (country, cqz, ituz, cont, primary)
                except Exception:
                    current = None
                continue
            if current:
                aliases.append(line.strip())
                if ';' in line:
                    finish()
        finish()
        # Longest prefix wins; exact calls are checked first.
        self.prefixes.sort(key=lambda x: len(x[0]), reverse=True)
        self.loaded = bool(self.prefixes)

    def lookup(self, callsign: str) -> CountryInfo | None:
        call = re.sub(r"[^A-Z0-9/]", "", (callsign or "").strip().upper())
        if not call:
            return None
        if call in self.exact:
            return self.exact[call]
        # Exact portable/special entries can still exist for the full call.
        for prefix, info in self.prefixes:
            if call.startswith(prefix):
                return info
        return None

def _qso_hash_with_fields(qso: dict[str, Any], fields: list[str]) -> str:
    obj = {}
    for k in fields:
        v = qso.get(k)
        if v == "":
            v = None
        if k == "freq" and v not in (None, ""):
            try:
                v = round(float(v), 6)
            except Exception:
                pass
        if k == "tx_pwr" and v not in (None, ""):
            try:
                v = round(float(v), 2)
            except Exception:
                pass
        obj[k] = v
    return hashlib.sha256(json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")).hexdigest()


def qso_hash(qso: dict[str, Any]) -> str:
    return _qso_hash_with_fields(qso, SYNC_FIELDS)


def legacy_qso_hash_v010(qso: dict[str, Any]) -> str:
    return _qso_hash_with_fields(qso, LEGACY_SYNC_FIELDS_V010)


# ---------- DPAPI token protection ----------
class DATA_BLOB(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_byte))]


def _blob_from_bytes(data: bytes):
    buf = ctypes.create_string_buffer(data)
    return DATA_BLOB(len(data), ctypes.cast(buf, ctypes.POINTER(ctypes.c_byte))), buf


def protect_text(text: str) -> str:
    raw = (text or "").encode("utf-8")
    if not raw:
        return ""
    if sys.platform != "win32":
        return "plain:" + base64.b64encode(raw).decode("ascii")
    try:
        crypt32 = ctypes.windll.crypt32
        kernel32 = ctypes.windll.kernel32
        in_blob, keepalive = _blob_from_bytes(raw)
        out_blob = DATA_BLOB()
        if not crypt32.CryptProtectData(ctypes.byref(in_blob), APP_NAME, None, None, None, 0, ctypes.byref(out_blob)):
            raise ctypes.WinError()
        try:
            encrypted = ctypes.string_at(out_blob.pbData, out_blob.cbData)
            return "dpapi:" + base64.b64encode(encrypted).decode("ascii")
        finally:
            kernel32.LocalFree(out_blob.pbData)
    except Exception as exc:
        # Never silently downgrade token storage on Windows. Existing
        # ``plain:`` values remain readable for migration, but all new writes
        # must be protected by DPAPI or fail visibly.
        raise RuntimeError(
            "Die Zugangsdaten konnten nicht sicher mit Windows-DPAPI gespeichert werden"
        ) from exc


def unprotect_text(value: str | None) -> str:
    if not value:
        return ""
    if value.startswith("plain:"):
        try:
            return base64.b64decode(value[6:]).decode("utf-8")
        except Exception:
            return ""
    if not value.startswith("dpapi:") or sys.platform != "win32":
        return ""
    try:
        encrypted = base64.b64decode(value[6:])
        crypt32 = ctypes.windll.crypt32
        kernel32 = ctypes.windll.kernel32
        in_blob, keepalive = _blob_from_bytes(encrypted)
        out_blob = DATA_BLOB()
        if not crypt32.CryptUnprotectData(ctypes.byref(in_blob), None, None, None, None, 0, ctypes.byref(out_blob)):
            raise ctypes.WinError()
        try:
            return ctypes.string_at(out_blob.pbData, out_blob.cbData).decode("utf-8")
        finally:
            kernel32.LocalFree(out_blob.pbData)
    except Exception:
        return ""


# ---------- ADIF ----------
FIELD_RE = re.compile(r"<([^:>]+):(\d+)(?::[^>]*)?>", re.IGNORECASE)


def adif_field(name: str, value: Any) -> str:
    if value is None:
        return ""
    s = str(value)
    if s == "":
        return ""
    return f"<{name.upper()}:{len(s)}>{s}"


def parse_adif(text: str) -> list[dict[str, str]]:
    # Ignore file header; parse each record between previous EOR/start and EOR.
    pos = 0
    eoh = re.search(r"<EOH\s*>", text, re.IGNORECASE)
    if eoh:
        pos = eoh.end()
    out: list[dict[str, str]] = []
    while True:
        eor = re.search(r"<EOR\s*>", text[pos:], re.IGNORECASE)
        if not eor:
            break
        end = pos + eor.start()
        chunk = text[pos:end]
        fields: dict[str, str] = {}
        p = 0
        while True:
            m = FIELD_RE.search(chunk, p)
            if not m:
                break
            name = m.group(1).upper().strip()
            length = int(m.group(2))
            start = m.end()
            value = chunk[start:start + length]
            fields[name] = value
            p = start + length
        if fields:
            out.append(fields)
        pos = pos + eor.end()
    return out


def adif_header() -> str:
    lines = [
        f"Generated by {APP_NAME} {VERSION}",
        adif_field("ADIF_VER", ADIF_VERSION) + adif_field("PROGRAMID", "DA6IT.de OfflineLogger") + adif_field("PROGRAMVERSION", VERSION) + "<EOH>",
        "",
    ]
    return "\n".join(lines)


def _mode_for_adif(mode: str) -> tuple[str, str | None]:
    mode = (mode or "").upper()
    if mode in ("USB", "LSB"):
        return "SSB", mode
    if mode == "FT8" or mode == "FT4":
        return "MFSK", mode
    if mode == "JS8":
        return "MFSK", "JS8"
    if mode == "PSK31":
        return "PSK", "PSK31"
    return mode, None


def qso_to_adif_fields(qso: dict[str, Any]) -> dict[str, Any]:
    mode, submode = _mode_for_adif(str(qso.get("mode") or ""))
    f: dict[str, Any] = {
        APP_ID_FIELD: qso.get("local_id"),
        "CALL": (qso.get("call") or "").upper(),
        "QSO_DATE": str(qso.get("qso_date") or "").replace("-", ""),
        "TIME_ON": str(qso.get("time_on") or "").replace(":", "")[:6],
        "QSO_DATE_OFF": str(qso.get("qso_date_off") or "").replace("-", ""),
        "TIME_OFF": str(qso.get("time_off") or "").replace(":", "")[:6],
        "BAND": qso.get("band"),
        "MODE": mode,
        "SUBMODE": submode,
        "FREQ": qso.get("freq"),
        "RST_SENT": qso.get("rst_sent"),
        "RST_RCVD": qso.get("rst_rcvd"),
        "GRIDSQUARE": qso.get("gridsquare"),
        "COUNTRY": qso.get("country"),
        "CONT": qso.get("cont"),
        "CQZ": qso.get("cqz"),
        "ITUZ": qso.get("ituz"),
        "NAME": qso.get("name"),
        "QTH": qso.get("qth"),
        "COMMENT": qso.get("comment"),
        "NOTES": qso.get("notes"),
        "TX_PWR": qso.get("tx_pwr"),
        "POTA_REF": qso.get("pota_ref"),
        "SOTA_REF": qso.get("sota_ref"),
        "WWFF_REF": qso.get("wwff_ref"),
        "OPERATOR": (qso.get("operator_call") or "").upper(),
        "STATION_CALLSIGN": (qso.get("station_call") or "").upper(),
        "CONTEST_ID": (qso.get("contest_id") or "").upper(),
        "STX": qso.get("stx"),
        "SRX": qso.get("srx"),
        "STX_STRING": qso.get("stx_string"),
        "SRX_STRING": qso.get("srx_string"),
        "PROP_MODE": (qso.get("prop_mode") or "").upper(),
        "MY_GRIDSQUARE": (qso.get("my_gridsquare") or "").upper(),
        "MY_CITY": qso.get("my_qth"),
        "MY_STATE": qso.get("my_state"),
        "MY_DXCC": qso.get("my_dxcc"),
        "MY_CQ_ZONE": qso.get("my_cq_zone"),
        "MY_ITU_ZONE": qso.get("my_itu_zone"),
        "MY_POTA_REF": qso.get("my_pota_ref"),
        "MY_SOTA_REF": qso.get("my_sota_ref"),
        "MY_WWFF_REF": qso.get("my_wwff_ref"),
        "MY_IOTA": qso.get("my_iota"),
        "MY_SIG": qso.get("my_sig"),
        "MY_SIG_INFO": qso.get("my_sig_info"),
    }
    return f


def adif_fields_to_qso(f: dict[str, str]) -> dict[str, Any]:
    qso_date = f.get("QSO_DATE", "")
    if len(qso_date) == 8:
        qso_date = f"{qso_date[:4]}-{qso_date[4:6]}-{qso_date[6:8]}"
    time_on = f.get("TIME_ON", "")
    if len(time_on) == 4:
        time_on += "00"
    qso_date_off = f.get("QSO_DATE_OFF", "")
    if len(qso_date_off) == 8:
        qso_date_off = f"{qso_date_off[:4]}-{qso_date_off[4:6]}-{qso_date_off[6:8]}"
    time_off = f.get("TIME_OFF", "")
    if len(time_off) == 4:
        time_off += "00"
    mode = f.get("SUBMODE") or f.get("MODE") or ""
    return {
        "local_id": f.get(APP_ID_FIELD) or str(uuid.uuid4()),
        "call": f.get("CALL", "").upper(),
        "band": f.get("BAND", ""),
        "mode": mode.upper(),
        "freq": f.get("FREQ", ""),
        "qso_date": qso_date,
        "time_on": time_on[:6],
        "qso_date_off": qso_date_off,
        "time_off": time_off[:6],
        "rst_sent": f.get("RST_SENT", ""),
        "rst_rcvd": f.get("RST_RCVD", ""),
        "gridsquare": f.get("GRIDSQUARE", "").upper(),
        "country": f.get("COUNTRY", ""),
        "cont": f.get("CONT", "").upper(),
        "cqz": f.get("CQZ", ""),
        "ituz": f.get("ITUZ", ""),
        "name": f.get("NAME", ""),
        "qth": f.get("QTH", ""),
        "comment": f.get("COMMENT", ""),
        "notes": f.get("NOTES", ""),
        "tx_pwr": f.get("TX_PWR", ""),
        "pota_ref": f.get("POTA_REF", ""),
        "sota_ref": f.get("SOTA_REF", ""),
        "wwff_ref": f.get("WWFF_REF", ""),
        "operator_call": f.get("OPERATOR", "").upper(),
        "station_call": f.get("STATION_CALLSIGN", "").upper(),
        "contest_id": f.get("CONTEST_ID", "").upper(),
        "stx": f.get("STX", ""),
        "srx": f.get("SRX", ""),
        "stx_string": f.get("STX_STRING", ""),
        "srx_string": f.get("SRX_STRING", ""),
        "prop_mode": f.get("PROP_MODE", "").upper(),
        "my_gridsquare": f.get("MY_GRIDSQUARE", "").upper(),
        "my_qth": f.get("MY_CITY", ""),
        "my_state": f.get("MY_STATE", ""),
        "my_dxcc": f.get("MY_DXCC", ""),
        "my_cq_zone": f.get("MY_CQ_ZONE", ""),
        "my_itu_zone": f.get("MY_ITU_ZONE", ""),
        "my_pota_ref": f.get("MY_POTA_REF", ""),
        "my_sota_ref": f.get("MY_SOTA_REF", ""),
        "my_wwff_ref": f.get("MY_WWFF_REF", ""),
        "my_iota": f.get("MY_IOTA", ""),
        "my_sig": f.get("MY_SIG", ""),
        "my_sig_info": f.get("MY_SIG_INFO", ""),
    }


def qso_to_adif_record(qso: dict[str, Any]) -> str:
    fields = qso_to_adif_fields(qso)
    order = [
        APP_ID_FIELD, "CALL", "QSO_DATE", "TIME_ON", "QSO_DATE_OFF", "TIME_OFF", "BAND", "FREQ", "MODE", "SUBMODE",
        "RST_SENT", "RST_RCVD", "GRIDSQUARE", "COUNTRY", "CONT", "CQZ", "ITUZ", "NAME", "QTH", "POTA_REF", "SOTA_REF", "WWFF_REF",
        "TX_PWR", "COMMENT", "NOTES", "OPERATOR", "STATION_CALLSIGN", "CONTEST_ID", "STX", "SRX", "STX_STRING", "SRX_STRING", "PROP_MODE", "MY_GRIDSQUARE", "MY_CITY",
        "MY_STATE", "MY_DXCC", "MY_CQ_ZONE", "MY_ITU_ZONE",
        "MY_POTA_REF", "MY_SOTA_REF", "MY_WWFF_REF", "MY_IOTA", "MY_SIG", "MY_SIG_INFO",
    ]
    return "".join(adif_field(k, fields.get(k)) for k in order) + "<EOR>\n"


class LogStore:
    def __init__(self, log_dir: Path, profile_key: str = ""):
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.profile_key = re.sub(r"[^A-Za-z0-9_-]", "", str(profile_key or ""))[:12]
        self.lock = threading.RLock()
        self.migration_report: dict[str, Any] | None = None
        self._consolidate_existing_files()

    @property
    def canonical_path(self) -> Path:
        suffix = f"-{self.profile_key[:6]}" if self.profile_key else ""
        return self.log_dir / f"wavelog-offline-logbook{suffix}.adi"

    def set_dir(self, path: Path, profile_key: str | None = None):
        with self.lock:
            self.log_dir = Path(path)
            self.log_dir.mkdir(parents=True, exist_ok=True)
            if profile_key is not None:
                self.profile_key = re.sub(r"[^A-Za-z0-9_-]", "", str(profile_key or ""))[:12]
            self._consolidate_existing_files()

    def file_for(self, qso: dict[str, Any]) -> Path:
        # A profile owns one continuously maintained ADIF file.  The filename
        # is intentionally independent from date and callsign changes.
        return self.canonical_path

    @staticmethod
    def _decode_adif(path: Path) -> str:
        raw = path.read_bytes()
        try:
            return raw.decode("utf-8-sig")
        except UnicodeDecodeError:
            return raw.decode("iso-8859-1")

    def _read_file_strict(self, path: Path) -> list[dict[str, Any]]:
        if not path.exists() or path.stat().st_size == 0:
            return []
        text = self._decode_adif(path)
        fields = parse_adif(text)
        if "<EOR" in text.upper() and not fields:
            raise ValueError(f"ADIF-Datei kann nicht gelesen werden: {path.name}")
        if "<EOR" not in text.upper() and text.strip():
            raise ValueError(f"ADIF-Datei enthält keinen vollständigen QSO-Datensatz: {path.name}")
        records = []
        for values in fields:
            qso = adif_fields_to_qso(values)
            qso["_file"] = str(path)
            records.append(qso)
        return records

    def _read_file(self, path: Path) -> list[dict[str, Any]]:
        if not path.exists():
            return []
        try:
            return self._read_file_strict(path)
        except Exception:
            return []

    def _write_file(self, path: Path, records: Iterable[dict[str, Any]]):
        recs = list(records)
        if not recs:
            if path.exists():
                path.unlink()
            return
        tmp = path.with_suffix(path.suffix + ".tmp")
        data = adif_header() + "".join(qso_to_adif_record(q) for q in recs)
        tmp.write_text(data, encoding="utf-8", newline="\n")
        os.replace(tmp, path)

    @staticmethod
    def _record_signature(qso: dict[str, Any]) -> str:
        return hashlib.sha256(qso_to_adif_record(qso).encode("utf-8")).hexdigest()

    def _backup_files(self, paths: Iterable[Path], label: str) -> Path | None:
        existing = [Path(path) for path in paths if Path(path).exists()]
        if not existing:
            return None
        backup_dir = self.log_dir / ".migration-backups"
        backup_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
        target = backup_dir / f"{label}-{stamp}.zip"
        with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for path in existing:
                archive.write(path, arcname=path.name)
        return target

    def _consolidate_existing_files(self) -> None:
        """Safely migrate daily ADIF files into the profile's single file.

        Source files are zipped first and moved into a recovery directory only
        after the new file was written and parsed back byte-semantically.
        """
        with self.lock:
            sources = sorted(path for path in self.log_dir.glob("*.adi") if path.is_file())
            target = self.canonical_path
            if not sources or (sources == [target]):
                return
            all_records: list[dict[str, Any]] = []
            seen_ids: dict[str, str] = {}
            reassigned = 0
            for path in sources:
                for qso in self._read_file_strict(path):
                    local_id = str(qso.get("local_id") or "")
                    signature = self._record_signature(qso)
                    if local_id in seen_ids:
                        if seen_ids[local_id] == signature:
                            continue
                        # Preserve both contacts. Only the second identity is
                        # changed; the original sync mapping remains untouched.
                        qso["local_id"] = str(uuid.uuid4())
                        local_id = qso["local_id"]
                        signature = self._record_signature(qso)
                        reassigned += 1
                    seen_ids[local_id] = signature
                    all_records.append(qso)
            backup = self._backup_files(sources, "adif-consolidation")
            self._write_file(target, all_records)
            verified = self._read_file_strict(target)
            expected = sorted(self._record_signature(row) for row in all_records)
            actual = sorted(self._record_signature(row) for row in verified)
            if expected != actual:
                raise RuntimeError("Die zusammengeführte ADIF-Datei konnte nicht vollständig verifiziert werden")
            recovery_dir = self.log_dir / ".migration-backups" / f"sources-{datetime.now().strftime('%Y%m%d-%H%M%S-%f')}"
            moved = 0
            for path in sources:
                if path == target:
                    continue
                recovery_dir.mkdir(parents=True, exist_ok=True)
                os.replace(path, recovery_dir / path.name)
                moved += 1
            self.migration_report = {
                "records": len(all_records), "sources": len(sources), "archived": moved,
                "reassigned_ids": reassigned, "backup": str(backup or ""), "target": str(target),
            }

    def scan(self) -> list[dict[str, Any]]:
        with self.lock:
            out = self._read_file(self.canonical_path)
            out.sort(key=lambda q: (q.get("qso_date", ""), q.get("time_on", "")), reverse=True)
            return out

    def find(self, local_id: str) -> dict[str, Any] | None:
        with self.lock:
            for q in self.scan():
                if q.get("local_id") == local_id:
                    return q
        return None

    def add(self, qso: dict[str, Any]) -> dict[str, Any]:
        with self.lock:
            q = dict(qso)
            q["local_id"] = q.get("local_id") or str(uuid.uuid4())
            path = self.file_for(q)
            records = self._read_file(path)
            records.append(q)
            self._write_file(path, records)
            q["_file"] = str(path)
            return q

    def update(self, local_id: str, new_qso: dict[str, Any]) -> dict[str, Any]:
        with self.lock:
            old = self.find(local_id)
            if not old:
                raise KeyError("QSO nicht gefunden")
            old_path = Path(old["_file"])
            updated = dict(new_qso)
            updated["local_id"] = local_id
            new_path = self.file_for(updated)
            old_records = [q for q in self._read_file(old_path) if q.get("local_id") != local_id]
            self._write_file(old_path, old_records)
            target_records = self._read_file(new_path)
            target_records = [q for q in target_records if q.get("local_id") != local_id]
            target_records.append(updated)
            self._write_file(new_path, target_records)
            updated["_file"] = str(new_path)
            return updated

    def delete(self, local_id: str) -> bool:
        with self.lock:
            old = self.find(local_id)
            if not old:
                return False
            path = Path(old["_file"])
            records = [q for q in self._read_file(path) if q.get("local_id") != local_id]
            self._write_file(path, records)
            return True

    @staticmethod
    def _natural_key(qso: dict[str, Any]) -> tuple[str, ...]:
        return tuple(str(qso.get(key) or "").strip().upper() for key in (
            "call", "qso_date", "time_on", "band", "mode", "freq", "station_call",
        ))

    def import_adif(self, source: Path) -> dict[str, Any]:
        source = Path(source)
        with self.lock:
            incoming = self._read_file_strict(source)
            existing = self.scan()
            existing_ids = {str(row.get("local_id") or "") for row in existing}
            existing_keys = {self._natural_key(row) for row in existing}
            imported, skipped, invalid = [], 0, []
            for index, row in enumerate(incoming, start=1):
                if not row.get("call") or not row.get("qso_date") or not row.get("time_on"):
                    invalid.append(f"Datensatz {index}: CALL/QSO_DATE/TIME_ON fehlt")
                    continue
                if not row.get("band") and row.get("freq"):
                    row["band"] = band_from_mhz(str(row.get("freq") or ""))
                if not row.get("band") or not row.get("mode"):
                    invalid.append(f"Datensatz {index}: BAND oder MODE fehlt")
                    continue
                natural_key = self._natural_key(row)
                if natural_key in existing_keys:
                    skipped += 1
                    continue
                local_id = str(row.get("local_id") or "")
                if not local_id or local_id in existing_ids:
                    row["local_id"] = str(uuid.uuid4())
                existing_ids.add(row["local_id"])
                existing_keys.add(natural_key)
                imported.append(row)
            backup = self._backup_files([self.canonical_path], "before-adif-import")
            combined = existing + imported
            self._write_file(self.canonical_path, combined)
            verified = self._read_file_strict(self.canonical_path)
            if sorted(self._record_signature(row) for row in combined) != sorted(self._record_signature(row) for row in verified):
                raise RuntimeError("Der ADIF-Import konnte nach dem Schreiben nicht verifiziert werden")
            return {
                "parsed": len(incoming), "imported": len(imported), "skipped": skipped,
                "invalid": invalid, "backup": str(backup or ""), "target": str(self.canonical_path),
            }

    def export_adif(self, target: Path, local_ids: Iterable[str] | None = None) -> dict[str, Any]:
        target = Path(target)
        with self.lock:
            records = self.scan()
            if local_ids is not None:
                wanted = {str(value) for value in local_ids}
                records = [row for row in records if str(row.get("local_id")) in wanted]
            if not records:
                raise ValueError("Keine QSOs für den Export vorhanden")
            target.parent.mkdir(parents=True, exist_ok=True)
            tmp = target.with_suffix(target.suffix + ".tmp")
            tmp.write_text(adif_header() + "".join(qso_to_adif_record(row) for row in records), encoding="utf-8", newline="\n")
            parsed = self._read_file_strict(tmp)
            if len(parsed) != len(records):
                tmp.unlink(missing_ok=True)
                raise RuntimeError("Der ADIF-Export konnte nicht verifiziert werden")
            os.replace(tmp, target)
            return {"exported": len(records), "target": str(target)}


# ---------- settings + sync metadata database ----------
class MetadataDB:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        self.conn = sqlite3.connect(self.path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        with self.lock:
            self.conn.executescript("""
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY,
                    value TEXT
                );
                CREATE TABLE IF NOT EXISTS sync_meta (
                    local_id TEXT PRIMARY KEY,
                    wavelog_id INTEGER UNIQUE,
                    status TEXT NOT NULL DEFAULT 'pending',
                    last_synced_hash TEXT,
                    remote_hash TEXT,
                    last_error TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    last_synced_at TEXT
                );
                CREATE INDEX IF NOT EXISTS idx_sync_status ON sync_meta(status);
                CREATE INDEX IF NOT EXISTS idx_sync_wid ON sync_meta(wavelog_id);
                CREATE TABLE IF NOT EXISTS qsl_meta (
                    wavelog_id INTEGER PRIMARY KEY,
                    qrz TEXT NOT NULL DEFAULT 'unknown',
                    lotw TEXT NOT NULL DEFAULT 'unknown',
                    eqsl TEXT NOT NULL DEFAULT 'unknown',
                    clublog TEXT NOT NULL DEFAULT 'unknown',
                    dcl TEXT NOT NULL DEFAULT 'unknown',
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS callbook_cache (
                    callsign TEXT NOT NULL,
                    source TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY(callsign, source)
                );
                CREATE INDEX IF NOT EXISTS idx_callbook_updated ON callbook_cache(updated_at);
            """)
            qsl_columns = {
                str(row[1]).lower() for row in self.conn.execute("PRAGMA table_info(qsl_meta)")
            }
            if "clublog" not in qsl_columns:
                self.conn.execute(
                    "ALTER TABLE qsl_meta ADD COLUMN clublog TEXT NOT NULL DEFAULT 'unknown'"
                )
            # v0.5: "pending" from older builds means the same as LOCAL ONLY.
            self.conn.execute("UPDATE sync_meta SET status='local_only' WHERE status='pending' AND wavelog_id IS NULL")
            self.conn.commit()

    def close(self):
        with self.lock:
            self.conn.close()

    def get_setting(self, key: str, default: str = "") -> str:
        with self.lock:
            r = self.conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
            return str(r["value"]) if r and r["value"] is not None else default

    def set_setting(self, key: str, value: Any):
        with self.lock:
            self.conn.execute(
                "INSERT INTO settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (key, "" if value is None else str(value)),
            )
            self.conn.commit()

    def get_token(self) -> str:
        return self.get_secret("wavelog_token")

    def set_token(self, token: str):
        self.set_secret("wavelog_token", token)

    def get_secret(self, key: str) -> str:
        return unprotect_text(self.get_setting(key, ""))

    def set_secret(self, key: str, value: str):
        self.set_setting(key, protect_text(value))

    def set_callbook_cache(self, callsign: str, source: str, payload: str):
        call = (callsign or "").strip().upper()
        source = (source or "").strip().lower()
        if not call or not source or not payload:
            return
        now = utc_now_iso()
        with self.lock:
            self.conn.execute(
                """INSERT INTO callbook_cache(callsign,source,payload,updated_at) VALUES(?,?,?,?)
                   ON CONFLICT(callsign,source) DO UPDATE SET
                   payload=excluded.payload,updated_at=excluded.updated_at""",
                (call, source, payload, now),
            )
            self.conn.commit()

    def get_callbook_cache(self, callsign: str, source: str, max_age_seconds: int = 604800) -> str | None:
        call = (callsign or "").strip().upper()
        source = (source or "").strip().lower()
        with self.lock:
            row = self.conn.execute(
                "SELECT payload,updated_at FROM callbook_cache WHERE callsign=? AND source=?",
                (call, source),
            ).fetchone()
        if not row:
            return None
        try:
            stamp = datetime.fromisoformat(str(row["updated_at"]).replace("Z", "+00:00"))
            if stamp.tzinfo is None:
                stamp = stamp.replace(tzinfo=timezone.utc)
            age = (datetime.now(timezone.utc) - stamp.astimezone(timezone.utc)).total_seconds()
            if age > max(0, int(max_age_seconds)):
                return None
        except Exception:
            return None
        return str(row["payload"])

    def get_meta(self, local_id: str) -> dict[str, Any] | None:
        with self.lock:
            r = self.conn.execute("SELECT * FROM sync_meta WHERE local_id=?", (local_id,)).fetchone()
            return dict(r) if r else None

    def get_by_wavelog_id(self, wid: int) -> dict[str, Any] | None:
        with self.lock:
            r = self.conn.execute("SELECT * FROM sync_meta WHERE wavelog_id=?", (int(wid),)).fetchone()
            return dict(r) if r else None

    def ensure_local(self, local_id: str, current_hash: str):
        now = utc_now_iso()
        with self.lock:
            r = self.conn.execute("SELECT * FROM sync_meta WHERE local_id=?", (local_id,)).fetchone()
            if not r:
                self.conn.execute(
                    "INSERT INTO sync_meta(local_id,status,created_at,updated_at) VALUES(?,'local_only',?,?)",
                    (local_id, now, now),
                )
            else:
                row = dict(r)
                if row["status"] == "synced" and row.get("last_synced_hash") and current_hash != row["last_synced_hash"]:
                    self.conn.execute("UPDATE sync_meta SET status='modified',updated_at=? WHERE local_id=?", (now, local_id))
            self.conn.commit()

    def mark_pending_delete(self, local_id: str):
        with self.lock:
            r = self.conn.execute("SELECT * FROM sync_meta WHERE local_id=?", (local_id,)).fetchone()
            if not r:
                return
            if r["wavelog_id"] is None:
                self.conn.execute("DELETE FROM sync_meta WHERE local_id=?", (local_id,))
            else:
                self.conn.execute("UPDATE sync_meta SET status='pending_delete',updated_at=? WHERE local_id=?", (utc_now_iso(), local_id))
            self.conn.commit()

    def reconcile_index(self, local_qsos: list[dict[str, Any]]):
        ids = {q["local_id"] for q in local_qsos if q.get("local_id")}
        for q in local_qsos:
            self.ensure_local(q["local_id"], qso_hash(q))
        with self.lock:
            rows = [dict(r) for r in self.conn.execute("SELECT * FROM sync_meta")]
            for r in rows:
                if r["local_id"] not in ids and r["status"] not in ("pending_delete",):
                    if r["wavelog_id"] is None:
                        self.conn.execute("DELETE FROM sync_meta WHERE local_id=?", (r["local_id"],))
                    # A linked QSO missing from the current ADI scan is not an
                    # implicit delete request. The file may have been moved,
                    # damaged, or temporarily unreadable. Keep its metadata so
                    # SyncEngine can restore the local record from Wavelog.
                    # Only the explicit UI deletion path calls
                    # mark_pending_delete() and may delete remotely.
            self.conn.commit()

    def set_status(self, local_id: str, status: str, *, wavelog_id: int | None = None,
                   last_synced_hash: str | None = None, remote_hash: str | None = None,
                   error: str | None = None):
        now = utc_now_iso()
        with self.lock:
            self.conn.execute(
                "INSERT OR IGNORE INTO sync_meta(local_id,status,created_at,updated_at) VALUES(?,?,?,?)",
                (local_id, status, now, now),
            )
            sets = ["status=?", "updated_at=?", "last_error=?"]
            vals: list[Any] = [status, now, error]
            if wavelog_id is not None:
                sets.append("wavelog_id=?"); vals.append(int(wavelog_id))
            if last_synced_hash is not None:
                sets.append("last_synced_hash=?"); vals.append(last_synced_hash)
                sets.append("last_synced_at=?"); vals.append(now)
            if remote_hash is not None:
                sets.append("remote_hash=?"); vals.append(remote_hash)
            vals.append(local_id)
            self.conn.execute(f"UPDATE sync_meta SET {','.join(sets)} WHERE local_id=?", vals)
            self.conn.commit()

    def delete_meta(self, local_id: str):
        with self.lock:
            r = self.conn.execute("SELECT wavelog_id FROM sync_meta WHERE local_id=?", (local_id,)).fetchone()
            if r and r["wavelog_id"] is not None:
                self.conn.execute("DELETE FROM qsl_meta WHERE wavelog_id=?", (int(r["wavelog_id"]),))
            self.conn.execute("DELETE FROM sync_meta WHERE local_id=?", (local_id,))
            self.conn.commit()

    def get_qsl_status(self, wavelog_id: int | None) -> dict[str, Any]:
        if not wavelog_id:
            return {"qrz":"unknown","lotw":"unknown","eqsl":"unknown","clublog":"unknown","dcl":"unknown"}
        with self.lock:
            r = self.conn.execute("SELECT * FROM qsl_meta WHERE wavelog_id=?", (int(wavelog_id),)).fetchone()
            return dict(r) if r else {"qrz":"unknown","lotw":"unknown","eqsl":"unknown","clublog":"unknown","dcl":"unknown"}

    def set_qsl_status(self, wavelog_id: int, statuses: dict[str, str]):
        now = utc_now_iso()
        vals = [statuses.get(k, "unknown") for k in ("qrz","lotw","eqsl","clublog","dcl")]
        with self.lock:
            self.conn.execute(
                """INSERT INTO qsl_meta(wavelog_id,qrz,lotw,eqsl,clublog,dcl,updated_at) VALUES(?,?,?,?,?,?,?)
                   ON CONFLICT(wavelog_id) DO UPDATE SET qrz=excluded.qrz,lotw=excluded.lotw,
                   eqsl=excluded.eqsl,clublog=excluded.clublog,dcl=excluded.dcl,
                   updated_at=excluded.updated_at""",
                (int(wavelog_id), *vals, now),
            )
            self.conn.commit()

    def delete_qsl_status(self, wavelog_id: int | None):
        if not wavelog_id:
            return
        with self.lock:
            self.conn.execute("DELETE FROM qsl_meta WHERE wavelog_id=?", (int(wavelog_id),))
            self.conn.commit()

    def list_meta(self) -> list[dict[str, Any]]:
        with self.lock:
            return [dict(r) for r in self.conn.execute("SELECT * FROM sync_meta ORDER BY created_at")]

    def list_candidates(self) -> list[dict[str, Any]]:
        with self.lock:
            return [dict(r) for r in self.conn.execute(
                "SELECT * FROM sync_meta WHERE status IN ('local_only','pending','modified','pending_delete','error') ORDER BY created_at"
            )]

    def list_new_upload_candidates(self) -> list[dict[str, Any]]:
        """Return only never-linked QSOs safe for a first automatic upload.

        Rows in ``error`` are deliberately excluded. A failed request may have
        reached Wavelog before the response was lost; the next full sync must
        link it safely instead of risking a duplicate blind retry.
        """
        with self.lock:
            return [dict(r) for r in self.conn.execute(
                "SELECT * FROM sync_meta WHERE wavelog_id IS NULL AND status IN ('local_only','pending') ORDER BY created_at"
            )]

    def xota_station_id_for_qso(self, local_id: str) -> int | None:
        with self.lock:
            exists = self.conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='xota_activation_qsos'"
            ).fetchone()
            if not exists:
                return None
            row = self.conn.execute(
                "SELECT station_id FROM xota_activation_qsos WHERE local_id=?", (local_id,),
            ).fetchone()
        return int(row[0]) if row and row[0] not in (None, "") else None

    def xota_station_ids(self) -> list[int]:
        with self.lock:
            exists = self.conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='xota_activation_qsos'"
            ).fetchone()
            if not exists:
                return []
            rows = self.conn.execute(
                "SELECT DISTINCT station_id FROM xota_activation_qsos WHERE station_id IS NOT NULL"
            ).fetchall()
        return sorted({int(row[0]) for row in rows})

    def bind_xota_remote_qso(self, station_id: int, local_id: str) -> None:
        with self.lock:
            exists = self.conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='xota_activations'"
            ).fetchone()
            if not exists:
                return
            row = self.conn.execute(
                "SELECT activation_uuid FROM xota_activations WHERE wavelog_station_id=? ORDER BY created_at DESC LIMIT 1",
                (int(station_id),),
            ).fetchone()
            if not row:
                return
            self.conn.execute(
                "INSERT INTO xota_activation_qsos(activation_uuid,local_id,station_id,created_at) VALUES(?,?,?,?) "
                "ON CONFLICT(local_id) DO UPDATE SET activation_uuid=excluded.activation_uuid,station_id=excluded.station_id",
                (str(row[0]), local_id, int(station_id), utc_now_iso()),
            )
            self.conn.commit()


# ---------- Wavelog API ----------
class WavelogError(RuntimeError):
    pass


@dataclass(frozen=True)
class WavelogOnlineSettings:
    base_url: str
    token: str
    station_id: int
    auto_sync: bool = False
    full_sync_on_start: bool = False
    full_sync_on_exit: bool = False

    @classmethod
    def from_storage(cls, get_setting, get_token) -> "WavelogOnlineSettings":
        raw_station_id = str(get_setting("station_profile_id", "0") or "0").strip()
        try:
            station_id = int(raw_station_id)
        except ValueError:
            station_id = 0
        return cls(
            base_url=str(get_setting("wavelog_url", "") or "").strip(),
            token=str(get_token() or "").strip(),
            station_id=station_id,
            auto_sync=str(get_setting("auto_sync_online", "0") or "0") == "1",
            full_sync_on_start=str(get_setting("full_sync_on_start", "0") or "0") == "1",
            full_sync_on_exit=str(get_setting("full_sync_on_exit", "0") or "0") == "1",
        )

    @property
    def configured(self) -> bool:
        return (
            self.base_url.startswith(("http://", "https://"))
            and bool(self.token)
            and self.station_id > 0
        )

    def should_auto_sync(self, *, online: bool, sync_busy: bool, candidate_count: int) -> bool:
        return self.configured and self.auto_sync and online and not sync_busy and candidate_count > 0


class WavelogClient:
    def __init__(self, base_url: str, token: str, timeout: int = 15):
        base = (base_url or "").strip().rstrip("/")
        if base.endswith("/index.php"):
            base = base[:-10]
        self.base = base
        self.token = (token or "").strip()
        self.timeout = timeout

    def _url(self, resource: str, ident: int | None = None, params: dict[str, Any] | None = None) -> str:
        url = f"{self.base}/index.php/api/v2/{resource}"
        if ident is not None:
            url += f"/{int(ident)}"
        if params:
            clean = {k: v for k, v in params.items() if v not in (None, "")}
            if clean:
                url += "?" + urllib.parse.urlencode(clean)
        return url

    def _request(self, method: str, resource: str, ident: int | None = None,
                 params: dict[str, Any] | None = None, payload: dict[str, Any] | None = None) -> dict[str, Any] | None:
        if not self.base.startswith(("http://", "https://")):
            raise WavelogError("Wavelog-URL muss mit http:// oder https:// beginnen")
        if not self.token:
            raise WavelogError("Kein Wavelog API-v2-Token eingetragen")
        data = None
        headers = {"Authorization": f"Bearer {self.token}", "User-Agent": USER_AGENT, "Accept": "application/json"}
        if payload is not None:
            data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            headers["Content-Type"] = "application/json"
        req = urllib.request.Request(self._url(resource, ident, params), data=data, headers=headers, method=method)
        try:
            with secure_urlopen(req, timeout=self.timeout) as resp:
                raw = resp.read()
                if not raw:
                    return None
                return json.loads(raw.decode("utf-8"))
        except urllib.error.HTTPError as e:
            raw = e.read().decode("utf-8", errors="replace")
            try:
                j = json.loads(raw)
                error = j.get("error") if isinstance(j, dict) else None
                if isinstance(error, dict):
                    code = str(error.get("code") or "").strip()
                    message = str(error.get("message") or "").strip()
                    details = error.get("details")
                    msg = f"{code}: {message}" if code and message else (message or code or raw)
                    if details not in (None, "", [], {}):
                        msg += " · " + json.dumps(details, ensure_ascii=False, separators=(",", ":"))
                else:
                    msg = raw
            except Exception:
                msg = raw or str(e)
            raise WavelogError(f"HTTP {e.code}: {msg}") from e
        except urllib.error.URLError as e:
            raise WavelogError(f"Verbindung fehlgeschlagen: {e.reason}") from e

    def token_info(self) -> dict[str, Any]:
        r = self._request("GET", "token") or {}
        return r.get("data") or {}

    def stations(self) -> list[dict[str, Any]]:
        r = self._request("GET", "station") or {}
        data = r.get("data") or []
        return data if isinstance(data, list) else []

    def get_station(self, station_id: int) -> dict[str, Any]:
        r = self._request("GET", "station", ident=int(station_id)) or {}
        return r.get("data") or {}

    def create_station(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Create a location through Wavelog API v2 (Wavelog >= 3.1.0)."""
        r = self._request("POST", "station", payload=payload) or {}
        return r.get("data") or {}

    def lookup_callsign(self, callsign: str, *, band: str = "", mode: str = "", include_callbook: bool = True) -> dict[str, Any]:
        params = {
            "callsign": (callsign or "").strip().upper(),
            "detail": "full",
            "callbook": "true" if include_callbook else "false",
            "band": band,
            "mode": mode,
        }
        return self._request("GET", "lookup", params=params) or {}

    def list_qsos(self, *, since_id: int = 0, qso_since: str | None = None, qso_until: str | None = None,
                  station_ids: Iterable[int] | None = None) -> list[dict[str, Any]]:
        page = 1
        out: list[dict[str, Any]] = []
        while True:
            station_filter = ",".join(str(int(value)) for value in (station_ids or []))
            params = {"since_id": since_id, "qso_since": qso_since, "qso_until": qso_until,
                      "station_id": station_filter, "page": page, "per_page": 5000}
            r = self._request("GET", "qso", params=params) or {}
            data = r.get("data") or []
            if isinstance(data, list):
                out.extend(data)
            meta = r.get("meta") or {}
            if not meta.get("has_more"):
                break
            page += 1
        return out

    def export_qsos_adif(self, *, qso_since: str | None = None, qso_until: str | None = None,
                         station_ids: Iterable[int] | None = None) -> list[dict[str, str]]:
        page = 1
        out: list[dict[str, str]] = []
        while True:
            station_filter = ",".join(str(int(value)) for value in (station_ids or []))
            params = {"format":"adif", "qso_since":qso_since, "qso_until":qso_until,
                      "station_id": station_filter, "page":page, "per_page":5000}
            r = self._request("GET", "qso", params=params) or {}
            data = r.get("data") or {}
            adif = data.get("adif") if isinstance(data, dict) else None
            if adif:
                out.extend(parse_adif(adif))
            meta = r.get("meta") or {}
            if not meta.get("has_more"):
                break
            page += 1
        return out

    def list_confirmations(
        self, *, station_ids: Iterable[int] | None = None,
        qso_since: str | None = None, qso_until: str | None = None,
        types: str = "lotw,eqsl,qrz,clublog",
    ) -> list[dict[str, Any]]:
        page = 1
        out: list[dict[str, Any]] = []
        while True:
            station_filter = ",".join(str(int(value)) for value in (station_ids or []))
            params = {
                "type": types, "station_id": station_filter,
                "qso_since": qso_since, "qso_until": qso_until,
                "page": page, "per_page": 1000,
            }
            r = self._request("GET", "confirmation", params=params) or {}
            data = r.get("data") or []
            if isinstance(data, list):
                out.extend(data)
            meta = r.get("meta") or {}
            if not meta.get("has_more"):
                break
            page += 1
        return out

    def get_qso(self, wid: int) -> dict[str, Any]:
        r = self._request("GET", "qso", ident=wid) or {}
        return r.get("data") or {}

    def create_qso(self, payload: dict[str, Any]) -> dict[str, Any]:
        r = self._request("POST", "qso", payload=payload) or {}
        return r.get("data") or {}

    def patch_qso(self, wid: int, payload: dict[str, Any]) -> dict[str, Any]:
        r = self._request("PATCH", "qso", ident=wid, payload=payload) or {}
        return r.get("data") or {}

    def delete_qso(self, wid: int):
        self._request("DELETE", "qso", ident=wid)

    def contest_catalog(self) -> list[dict[str, Any]]:
        r = self._request("GET", "catalog", params={"topic": "contest"}) or {}
        data = r.get("data") or []
        return data if isinstance(data, list) else []

    def contests(self, station_ids: Iterable[int] | None = None) -> list[dict[str, Any]]:
        station_filter = ",".join(str(int(value)) for value in (station_ids or []))
        r = self._request("GET", "contest", params={"station_id": station_filter}) or {}
        data = r.get("data") or []
        return data if isinstance(data, list) else []

    def get_contest(self, contest_session_id: int) -> dict[str, Any]:
        r = self._request("GET", "contest", ident=int(contest_session_id)) or {}
        return r.get("data") or {}

    def create_contest(self, payload: dict[str, Any]) -> dict[str, Any]:
        r = self._request("POST", "contest", payload=payload) or {}
        return r.get("data") or {}

    def patch_contest(self, contest_session_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        r = self._request("PATCH", "contest", ident=int(contest_session_id), payload=payload) or {}
        return r.get("data") or {}


def _status_from_adif(fields: dict[str, str], sent_names: tuple[str, ...], rcvd_names: tuple[str, ...]) -> str:
    def values(names):
        return [(fields.get(n) or "").strip().upper() for n in names if n in fields]
    rvals = values(rcvd_names)
    if any(v in ("Y", "V") for v in rvals):
        return "confirmed"
    svals = values(sent_names)
    if any(v in ("Y", "V") for v in svals):
        return "sent"
    if any(v in ("Q", "M", "R") for v in svals):
        return "pending"
    if svals and all(v in ("N", "") for v in svals):
        return "none"
    return "unknown"


def service_statuses_from_adif(fields: dict[str, str]) -> dict[str, str]:
    return {
        "lotw": _status_from_adif(fields, ("LOTW_QSL_SENT",), ("LOTW_QSL_RCVD",)),
        "eqsl": _status_from_adif(fields, ("EQSL_QSL_SENT",), ("EQSL_QSL_RCVD",)),
        "qrz": _status_from_adif(
            fields,
            ("QRZCOM_QSO_UPLOAD_STATUS", "QRZ_QSO_UPLOAD_STATUS"),
            ("QRZCOM_QSL_RCVD", "QRZ_QSL_RCVD", "QRZCOM_QSO_DOWNLOAD_STATUS"),
        ),
        "clublog": _status_from_adif(fields, ("CLUBLOG_QSO_UPLOAD_STATUS",), ()),
        "dcl": _status_from_adif(fields, ("DCL_QSL_SENT",), ("DCL_QSL_RCVD",)),
    }


def _remote_status_key(remote: dict[str, Any]) -> tuple[str, str, str, str]:
    call = str(remote.get("call") or "").upper()
    dt = str(remote.get("qso_date") or "")
    date = dt[:10].replace("-", "")
    timepart = ""
    if " " in dt:
        timepart = dt.split(" ",1)[1].replace(":", "")[:6]
    band = str(remote.get("band") or "").upper()
    return call, date, timepart, band


def _adif_status_key(fields: dict[str, str]) -> tuple[str, str, str, str]:
    return (
        str(fields.get("CALL") or "").upper(),
        str(fields.get("QSO_DATE") or "").replace("-", "")[:8],
        (str(fields.get("TIME_ON") or "").replace(":", "") + "000000")[:6],
        str(fields.get("BAND") or "").upper(),
    )

def local_to_wavelog(q: dict[str, Any], station_profile_id: int, *, include_operator: bool = False) -> dict[str, Any]:
    freq_hz = None
    if q.get("freq") not in (None, ""):
        try:
            freq_hz = int(round(float(q["freq"]) * 1_000_000))
        except Exception:
            freq_hz = None
    p: dict[str, Any] = {
        "station_profile_id": int(station_profile_id),
        "call": (q.get("call") or "").upper(),
        "band": q.get("band"),
        "mode": q.get("mode"),
        "qso_date": q.get("qso_date"),
        "time_on": q.get("time_on"),
        "freq": freq_hz,
        "rst_sent": q.get("rst_sent") or None,
        "rst_rcvd": q.get("rst_rcvd") or None,
        "gridsquare": q.get("gridsquare") or None,
        "name": q.get("name") or None,
        "qth": q.get("qth") or None,
        "comment": q.get("comment") or None,
        "notes": q.get("notes") or None,
        "tx_pwr": float(q["tx_pwr"]) if q.get("tx_pwr") not in (None, "") else None,
        "pota_ref": q.get("pota_ref") or None,
        "sota_ref": q.get("sota_ref") or None,
        "wwff_ref": q.get("wwff_ref") or None,
        "srx": int(q["srx"]) if str(q.get("srx") or "").strip().isdigit() else None,
        "stx": int(q["stx"]) if str(q.get("stx") or "").strip().isdigit() else None,
        "srx_string": q.get("srx_string") or None,
        "stx_string": q.get("stx_string") or None,
    }
    # OPERATOR is especially important for club/special callsigns. Wavelog
    # accepts it when creating a QSO; for member-scoped club tokens Wavelog
    # intentionally overwrites it with the acting member. PATCH does not
    # document OPERATOR as an editable field, so only include it on create.
    if include_operator and q.get("operator_call"):
        p["operator"] = str(q.get("operator_call") or "").upper()
    # API v2 accepts any valid ADIF field name when creating a QSO. CONTEST_ID
    # is therefore sent on create/import, but not on PATCH because it is not in
    # Wavelog's documented PATCH field allow-list.
    if include_operator and q.get("contest_id"):
        p["contest_id"] = str(q.get("contest_id") or "").upper()
    return {k: v for k, v in p.items() if v is not None}


def remote_to_local(r: dict[str, Any], station: dict[str, Any] | None = None) -> dict[str, Any]:
    qdt = str(r.get("qso_date") or "")
    if " " in qdt:
        date, tm = qdt.split(" ", 1)
        time_on = tm.replace(":", "")[:6]
    else:
        date = qdt[:10]
        time_on = str(r.get("time_on") or "").replace(":", "")[:6]
    freq_mhz = ""
    if r.get("freq") not in (None, ""):
        try:
            freq_mhz = f"{float(r['freq']) / 1_000_000:.6f}".rstrip("0").rstrip(".")
        except Exception:
            pass
    st = station or {}
    return {
        "local_id": str(uuid.uuid4()),
        "call": str(r.get("call") or "").upper(),
        "band": str(r.get("band") or ""),
        "mode": str(r.get("submode") or r.get("mode") or "").upper(),
        "freq": freq_mhz,
        "qso_date": date,
        "time_on": time_on,
        "rst_sent": r.get("rst_sent") or "",
        "rst_rcvd": r.get("rst_rcvd") or "",
        "gridsquare": str(r.get("gridsquare") or "").upper(),
        "country": r.get("country") or "",
        "cont": str(r.get("cont") or "").upper(),
        "cqz": str(r.get("cqz") or ""),
        "ituz": str(r.get("ituz") or ""),
        "name": r.get("name") or "",
        "qth": r.get("qth") or "",
        "comment": r.get("comment") or "",
        "notes": r.get("notes") or "",
        "tx_pwr": r.get("tx_pwr") or "",
        "pota_ref": r.get("pota_ref") or "",
        "sota_ref": r.get("sota_ref") or "",
        "wwff_ref": r.get("wwff_ref") or "",
        "operator_call": str(r.get("operator") or "").upper(),
        "station_call": str(r.get("station_callsign") or st.get("callsign") or "").upper(),
        "contest_id": str(r.get("contest_id") or "").upper(),
        "stx": str(r.get("stx") or ""),
        "srx": str(r.get("srx") or ""),
        "stx_string": str(r.get("stx_string") or ""),
        "srx_string": str(r.get("srx_string") or ""),
        "my_gridsquare": str(st.get("gridsquare") or "").upper(),
        "my_qth": st.get("city") or "",
        "my_pota_ref": st.get("pota") or "",
        "my_sota_ref": st.get("sota") or "",
        "my_wwff_ref": st.get("wwff") or "",
    }


def remote_hash(r: dict[str, Any]) -> str:
    return qso_hash(remote_to_local(r, {}))


def legacy_remote_hash_v010(r: dict[str, Any]) -> str:
    return legacy_qso_hash_v010(remote_to_local(r, {}))


def remote_station_profile_id(remote: dict[str, Any]) -> int | None:
    """Read Wavelog's station-location id without assuming one JSON spelling."""
    for key in ("station_profile_id", "station_id"):
        value = remote.get(key)
        try:
            if value not in (None, ""):
                return int(value)
        except (TypeError, ValueError):
            continue
    for key in ("station_profile", "station"):
        value = remote.get(key)
        if isinstance(value, dict):
            try:
                return int(value.get("id"))
            except (TypeError, ValueError):
                pass
    return None


def remote_qsos_for_station(
    remote_rows: Iterable[dict[str, Any]], station_profile_id: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Split QSO rows into the selected station location and everything else.

    Wavelog's QSO list is token-scoped, not necessarily station-scoped. Importing
    rows without checking their station id mixes multiple station logbooks into
    one local logger profile. Unknown rows are deliberately out of scope: data
    safety is more important than guessing.
    """
    selected = int(station_profile_id)
    scoped: list[dict[str, Any]] = []
    excluded: list[dict[str, Any]] = []
    for row in remote_rows:
        (scoped if remote_station_profile_id(row) == selected else excluded).append(row)
    return scoped, excluded


@dataclass
class SyncSummary:
    pushed: int = 0
    patched: int = 0
    deleted: int = 0
    pulled: int = 0
    linked: int = 0
    remote_updated: int = 0
    remote_deleted: int = 0
    conflicts: int = 0
    errors: int = 0
    qsl_updated: int = 0
    qsl_errors: int = 0
    scope_skipped: int = 0


@dataclass
class ContestSyncSummary:
    available: bool = True
    created: int = 0
    updated: int = 0
    pulled: int = 0
    linked: int = 0
    skipped: int = 0
    errors: int = 0
    history_imported: int = 0
    reason: str = ""


def _contest_exchange_fields(preset: dict[str, Any]) -> list[str]:
    fields: list[str] = []
    if preset.get("use_serial"):
        fields.append("serial")
    if preset.get("use_grid"):
        fields.append("gridsquare")
    if preset.get("use_text"):
        fields.append("exchange")
    return fields or ["serial"]


def valid_contest_adif_name(value: object) -> bool:
    name = str(value or "").strip().upper()
    return bool(
        not name.isdigit()
        and re.fullmatch(r"[A-Z0-9][A-Z0-9_-]{1,63}", name)
        and re.search(r"[A-Z]", name)
    )


def _contest_preset_from_remote(remote: dict[str, Any], existing: dict[str, Any] | None = None) -> dict[str, Any]:
    preset = dict(existing or {})
    settings = remote.get("settings") if isinstance(remote.get("settings"), dict) else {}
    exchange = settings.get("exchangefields") if isinstance(settings.get("exchangefields"), list) else ["serial"]
    contest = str(remote.get("contest") or "").strip().upper()
    start = str(remote.get("time_start") or "")
    label = str(remote.get("contest_name") or contest or "Contest").strip()
    if not existing:
        label = f"{label} · {start[:16]}" if start else label
    preset.update({
        "name": str(preset.get("name") or label), "contest_id": contest,
        "use_serial": "serial" in exchange, "use_grid": "gridsquare" in exchange,
        "use_text": "exchange" in exchange, "time_start": start,
        "time_end": str(remote.get("time_end") or ""), "comment": str(remote.get("comment") or ""),
        "station_id": int(remote.get("station_id") or 0),
        "wavelog_session_id": int(remote.get("id") or 0),
        "wavelog_updated_at": str(remote.get("updated_at") or ""),
        "sync_dirty": False, "sync_enabled": True,
        "serial_per_band": bool(settings.get("serial_per_band", False)),
        "serial_scope": str(settings.get("serial_scope") or "station"),
    })
    preset.setdefault("start_serial", 1)
    preset.setdefault("freq", "")
    preset.setdefault("band", "2m")
    preset.setdefault("mode", "SSB")
    preset.setdefault("rst_default", "59")
    preset.setdefault("sent_exchange", "")
    return preset


class ContestSyncEngine:
    """Mirrors Wavelog contest sessions without making local logging depend on it."""

    def __init__(self, store: LogStore, db: MetadataDB, client: WavelogClient):
        self.store, self.db, self.client = store, db, client

    def _load_presets(self) -> list[dict[str, Any]]:
        try:
            rows = json.loads(self.db.get_setting("contest_presets", "[]") or "[]")
            return [dict(row) for row in rows if isinstance(row, dict)]
        except Exception:
            return []

    def _merge_qso_history(self, presets: list[dict[str, Any]], summary: ContestSyncSummary) -> list[dict[str, Any]]:
        """Recover selectable contests from synchronized ADIF CONTEST_ID data.

        Released Wavelog versions can synchronize the QSO fields even when
        their contest-session API is not present yet. Grouping by ADIF name
        and year mirrors Wavelog's "Import Historical Contests" fallback and
        keeps the desktop contest chooser useful without pretending that a
        server-side session was created.
        """
        groups: dict[tuple[str, str], list[dict[str, Any]]] = {}
        for qso in self.store.scan():
            contest = str(qso.get("contest_id") or "").strip().upper()
            date = str(qso.get("qso_date") or "")[:10]
            if not contest or len(date) < 4:
                continue
            groups.setdefault((contest, date[:4]), []).append(qso)

        for (contest, year), qsos in sorted(groups.items()):
            local_ids = [str(qso.get("local_id")) for qso in qsos if qso.get("local_id")]
            existing = next((
                row for row in presets
                if str(row.get("contest_id") or "").upper() == contest
                and (str(row.get("time_start") or "")[:4] in ("", year))
            ), None)
            if existing is not None:
                merged_ids = list(existing.get("local_qso_ids") or [])
                for local_id in local_ids:
                    if local_id not in merged_ids:
                        merged_ids.append(local_id)
                existing["local_qso_ids"] = merged_ids
                continue

            ordered = sorted(qsos, key=lambda q: (str(q.get("qso_date") or ""), str(q.get("time_on") or "")))
            first, last = ordered[0], ordered[-1]
            first_time = (str(first.get("time_on") or "000000") + "000000")[:6]
            last_time = (str(last.get("time_on") or "235959") + "235959")[:6]
            modes = [str(q.get("mode") or "") for q in ordered if q.get("mode")]
            bands = [str(q.get("band") or "") for q in ordered if q.get("band")]
            presets.append({
                "name": f"{contest} · {year}", "contest_id": contest,
                "time_start": f"{str(first.get('qso_date'))[:10]} {first_time[:2]}:{first_time[2:4]}:{first_time[4:6]}",
                "time_end": f"{str(last.get('qso_date'))[:10]} {last_time[:2]}:{last_time[2:4]}:{last_time[4:6]}",
                "comment": "Aus synchronisierten Wavelog-QSOs rekonstruiert",
                "use_serial": any(str(q.get("stx") or "").strip() for q in ordered),
                "use_grid": any(str(q.get("gridsquare") or "").strip() for q in ordered),
                "use_text": any(str(q.get("stx_string") or "").strip() for q in ordered),
                "start_serial": 1, "sent_exchange": "", "freq": "",
                "band": max(set(bands), key=bands.count) if bands else "2m",
                "mode": max(set(modes), key=modes.count) if modes else "SSB",
                "rst_default": "59", "local_qso_ids": local_ids,
                "sync_dirty": False, "sync_enabled": True,
                "session_source": "qso_history",
            })
            summary.history_imported += 1
        return presets

    @staticmethod
    def _catalog_from_presets(presets: list[dict[str, Any]]) -> list[dict[str, Any]]:
        values: dict[str, dict[str, Any]] = {}
        for preset in presets:
            contest = str(preset.get("contest_id") or "").strip().upper()
            if contest and not contest.isdigit():
                values.setdefault(contest, {"adif_name": contest, "name": contest, "source": "local"})
        return [values[key] for key in sorted(values)]

    def _link_pending_presets(self, presets: list[dict[str, Any]], summary: ContestSyncSummary) -> None:
        """Attach already-uploaded local QSOs to their Wavelog contest session."""
        for preset in presets:
            remote_id = int(preset.get("wavelog_session_id") or 0)
            if not remote_id:
                continue
            qso_ids: list[int] = []
            for local_id in preset.get("local_qso_ids") or []:
                meta = self.db.get_meta(str(local_id))
                if meta and meta.get("wavelog_id"):
                    qso_ids.append(int(meta["wavelog_id"]))
            if not qso_ids:
                continue
            try:
                result = self.client.patch_contest(remote_id, {"link_qso_ids": sorted(set(qso_ids))})
                summary.linked += int(result.get("linked") or 0)
                summary.skipped += len(result.get("skipped") or [])
                preset.pop("sync_error", None)
            except Exception as exc:
                preset["sync_error"] = str(exc)
                summary.errors += 1

    def link_pending(self) -> ContestSyncSummary:
        """Small companion operation for the automatic new-QSO push.

        It deliberately avoids catalog and session-list requests. If an older
        Wavelog instance does not expose the contest resource, normal QSO
        upload remains successful and the reason is retained for the UI.
        """
        summary = ContestSyncSummary()
        presets = self._load_presets()
        self._link_pending_presets(presets, summary)
        self.db.set_setting("contest_presets", json.dumps(presets, ensure_ascii=False))
        if summary.errors:
            summary.available = False
            summary.reason = next((str(row.get("sync_error")) for row in presets if row.get("sync_error")), "Fehler")
            self.db.set_setting("contest_sync_status", summary.reason)
        return summary

    def sync(self, station_id: int) -> ContestSyncSummary:
        summary = ContestSyncSummary()
        presets = self._load_presets()
        catalog: list[dict[str, Any]] = []
        catalog_error = ""
        try:
            catalog = self.client.contest_catalog()
            self.db.set_setting("contest_catalog", json.dumps(catalog, ensure_ascii=False))
        except WavelogError as exc:
            catalog_error = str(exc)

        try:
            remote_rows = self.client.contests([station_id])
        except WavelogError as exc:
            text = str(exc)
            scope_missing = "insufficient_scope" in text or "contest:read" in text or "required scope: contest" in text.lower()
            if "HTTP 404" in text or "HTTP 405" in text or scope_missing:
                summary.available = False
                summary.reason = (
                    "Der API-v2-Token benötigt contest:read und contest:write. "
                    "Contest-QSOs werden mit CONTEST_ID weiterhin normal synchronisiert."
                    if scope_missing else
                    "Diese Wavelog-Version bietet noch keine Contest-Session-API. "
                    "Contest-QSOs werden mit CONTEST_ID normal synchronisiert; "
                    "eine Wavelog-Session kann erst nach einem Wavelog-Update automatisch angelegt werden."
                )
                presets = self._merge_qso_history(presets, summary)
                if not catalog:
                    catalog = self._catalog_from_presets(presets)
                    self.db.set_setting("contest_catalog", json.dumps(catalog, ensure_ascii=False))
                self.db.set_setting("contest_presets", json.dumps(presets, ensure_ascii=False))
                self.db.set_setting("contest_sync_status", summary.reason)
                return summary
            summary.errors += 1
            summary.reason = text
            self.db.set_setting("contest_sync_status", text)
            return summary

        by_remote = {int(row.get("id") or 0): row for row in remote_rows if int(row.get("id") or 0) > 0}
        if catalog_error and not catalog:
            # Some transitional Wavelog builds expose /contest before the
            # catalog resource. Derive a safe dropdown from returned sessions.
            catalog = [
                {"adif_name": str(row.get("contest") or "").upper(), "name": str(row.get("contest_name") or row.get("contest") or "")}
                for row in remote_rows if row.get("contest")
            ]
            self.db.set_setting("contest_catalog", json.dumps(catalog, ensure_ascii=False))

        # Local edits are pushed first; numeric ids are always assigned by
        # Wavelog and are never invented by the desktop client.
        for index, preset in enumerate(presets):
            if not preset.get("sync_enabled", True) or not preset.get("sync_dirty"):
                continue
            if not valid_contest_adif_name(preset.get("contest_id")):
                preset["sync_error"] = "Ungültiger ADIF-Contest-Name; eine numerische Wavelog-ID ist nicht zulässig."
                summary.errors += 1
                continue
            try:
                payload = {
                    "contest": str(preset.get("contest_id") or "").upper(),
                    "time_start": str(preset.get("time_start") or ""),
                    "time_end": str(preset.get("time_end") or ""),
                    "station_id": int(preset.get("station_id") or station_id),
                    "comment": str(preset.get("comment") or ""),
                    "settings": {
                        "exchangefields": _contest_exchange_fields(preset),
                        "serial_per_band": bool(preset.get("serial_per_band", False)),
                        "serial_scope": str(preset.get("serial_scope") or "station"),
                    },
                }
                remote_id = int(preset.get("wavelog_session_id") or 0)
                if remote_id:
                    remote = self.client.patch_contest(remote_id, payload)
                    summary.updated += 1
                else:
                    remote = self.client.create_contest(payload)
                    summary.created += 1
                presets[index] = _contest_preset_from_remote(remote, preset)
                by_remote[int(remote.get("id") or 0)] = remote
            except Exception as exc:
                preset["sync_error"] = str(exc)
                summary.errors += 1

        # Pull every remote session and its explicit QSO linkage.
        for remote_id, row in sorted(by_remote.items()):
            try:
                detail = self.client.get_contest(remote_id)
                position = next((i for i, item in enumerate(presets) if int(item.get("wavelog_session_id") or 0) == remote_id), None)
                existing = presets[position] if position is not None else None
                merged = _contest_preset_from_remote(detail, existing)
                local_ids = list(merged.get("local_qso_ids") or [])
                for remote_qso_id in detail.get("qso_ids") or []:
                    meta = self.db.get_by_wavelog_id(int(remote_qso_id))
                    if meta and meta.get("local_id") not in local_ids:
                        local_ids.append(meta["local_id"])
                merged["local_qso_ids"] = local_ids
                if position is None:
                    base_name = str(merged.get("name") or "Contest")
                    used_names = {str(item.get("name") or "").casefold() for item in presets}
                    suffix = 2
                    while str(merged.get("name") or "").casefold() in used_names:
                        merged["name"] = f"{base_name} ({suffix})"
                        suffix += 1
                    presets.append(merged); summary.pulled += 1
                else:
                    presets[position] = merged
            except Exception as exc:
                summary.errors += 1
                summary.reason = str(exc)

        # Link locally logged contest QSOs after the normal QSO sync assigned
        # their Wavelog ids. Re-sending the list is idempotent server-side.
        self._link_pending_presets(presets, summary)

        self.db.set_setting("contest_presets", json.dumps(presets, ensure_ascii=False))
        self.db.set_setting("contest_sync_status", "ok" if not summary.errors else (summary.reason or "Fehler"))
        return summary


class SyncEngine:
    """Bidirectional reconciler.

    LOCAL ONLY records have no Wavelog id and are uploaded on sync.
    Once a record has a Wavelog id it belongs to the synchronized set:
    - remote-only changes are pulled to ADI
    - local-only changes are patched to Wavelog
    - remote deletions delete unchanged local records
    - local deletions are propagated to Wavelog
    - changes on both sides become a conflict
    """

    def __init__(self, store: LogStore, db: MetadataDB, client: WavelogClient):
        self.store = store
        self.db = db
        self.client = client

    def push_new_only(self, station_profile_id: int) -> SyncSummary:
        """Upload new LOCAL ONLY QSOs without pulling, patching or deleting.

        This is the narrow online-mode operation. It intentionally performs no
        remote listing, QSL refresh, conflict resolution, PATCH or DELETE.
        """
        summary = SyncSummary()
        local_qsos = self.store.scan()
        self.db.reconcile_index(local_qsos)
        local_map = {q["local_id"]: q for q in local_qsos}
        for meta in self.db.list_new_upload_candidates():
            local_id = meta["local_id"]
            qso = local_map.get(local_id)
            if not qso:
                self.db.delete_meta(local_id)
                continue
            try:
                target_station_id = self.db.xota_station_id_for_qso(local_id) or station_profile_id
                remote = self.client.create_qso(
                    local_to_wavelog(qso, target_station_id, include_operator=True)
                )
                wavelog_id = int(remote.get("id"))
                self.db.set_status(
                    local_id,
                    "synced",
                    wavelog_id=wavelog_id,
                    last_synced_hash=qso_hash(qso),
                    remote_hash=remote_hash(remote),
                )
                summary.pushed += 1
            except Exception as exc:
                self.db.set_status(local_id, "error", error=str(exc))
                summary.errors += 1
        return summary

    def _local_map(self) -> dict[str, dict[str, Any]]:
        qsos = self.store.scan()
        self.db.reconcile_index(qsos)
        return {q["local_id"]: q for q in qsos}

    @staticmethod
    def _match_local(remote: dict[str, Any], locals_: Iterable[dict[str, Any]]) -> dict[str, Any] | None:
        rq = remote_to_local(remote, {})
        for q in locals_:
            if (q.get("call") or "").upper() != rq["call"]:
                continue
            if q.get("qso_date") != rq["qso_date"] or q.get("band") != rq["band"]:
                continue
            # within 90 seconds
            try:
                a = int(q.get("time_on", "000000")[:2]) * 3600 + int(q.get("time_on", "000000")[2:4]) * 60 + int(q.get("time_on", "000000")[4:6] or 0)
                b = int(rq["time_on"][:2]) * 3600 + int(rq["time_on"][2:4]) * 60 + int(rq["time_on"][4:6] or 0)
                if abs(a - b) <= 90:
                    return q
            except Exception:
                if q.get("time_on", "")[:4] == rq.get("time_on", "")[:4]:
                    return q
        return None

    @staticmethod
    def _station_for(remote: dict[str, Any], station_map: dict[int, dict[str, Any]]) -> dict[str, Any]:
        try:
            return station_map.get(int(remote.get("station_id") or remote.get("station_profile_id") or 0), {})
        except Exception:
            return {}

    def _replace_local_from_remote(self, local_id: str, remote: dict[str, Any], station_map: dict[int, dict[str, Any]]) -> dict[str, Any]:
        rq = remote_to_local(remote, self._station_for(remote, station_map))
        rq["local_id"] = local_id
        if self.store.find(local_id):
            return self.store.update(local_id, rq)
        return self.store.add(rq)

    def _enrich_remote_identity_from_adif(self, remote_rows: list[dict[str, Any]], station_ids: Iterable[int] | None = None) -> None:
        """Fill OPERATOR/STATION_CALLSIGN when the compact JSON QSO object omits them.

        Wavelog's ADIF export carries the standard identity fields. Matching is
        done with the same call/date/time/band key already used for QSL status.
        This is particularly useful for clubstation logs where OPERATOR is the
        actual member who made the contact while STATION_CALLSIGN is the club call.
        Failure is deliberately non-fatal: JSON sync can continue without it.
        """
        if not remote_rows:
            return
        dates = []
        for r in remote_rows:
            dt = str(r.get("qso_date") or "")[:10]
            if len(dt) == 10:
                dates.append(dt)
        qso_since = min(dates) if dates else None
        try:
            adif_rows = self.client.export_qsos_adif(qso_since=qso_since, station_ids=station_ids)
        except Exception:
            return
        by_key: dict[tuple[str, str, str, str], list[dict[str, Any]]] = {}
        for r in sorted(remote_rows, key=lambda x: int(x.get("id") or 0)):
            by_key.setdefault(_remote_status_key(r), []).append(r)
        for f in adif_rows:
            candidates = by_key.get(_adif_status_key(f)) or []
            if not candidates:
                continue
            r = candidates.pop(0)
            op = str(f.get("OPERATOR") or "").strip().upper()
            stcall = str(f.get("STATION_CALLSIGN") or "").strip().upper()
            if op and not r.get("operator"):
                r["operator"] = op
            if stcall and not r.get("station_callsign"):
                r["station_callsign"] = stcall
            # Contest exchange fields are standard ADIF but are not guaranteed
            # to be present in Wavelog's compact JSON list representation.
            for adif_name, json_name in (("CONTEST_ID","contest_id"),("STX","stx"),("SRX","srx"),
                                          ("STX_STRING","stx_string"),("SRX_STRING","srx_string")):
                value = str(f.get(adif_name) or "").strip()
                if value and not r.get(json_name):
                    r[json_name] = value

    def _refresh_qsl_statuses(self, station_profile_id: int, station_ids: Iterable[int] | None = None) -> tuple[int, int]:
        """Refresh cached service status for linked Wavelog QSOs.

        Sent/upload state is read from Wavelog's ADIF export where present.
        Received/confirmed state is overlaid from API v2 /confirmation when
        the token has confirmation:read. Missing optional data never breaks QSO sync.
        """
        metas = [m for m in self.db.list_meta() if m.get("wavelog_id")]
        if not metas:
            return 0, 0
        linked = {int(m["wavelog_id"]): m for m in metas}
        errors = 0
        updated = 0
        # Limit exports to the date range represented by the local synchronized set.
        dates = []
        local_map = self._local_map()
        for m in metas:
            q = local_map.get(m["local_id"])
            if q and q.get("qso_date"):
                dates.append(str(q["qso_date"])[:10])
        qso_since = min(dates) if dates else None

        try:
            allowed = {int(value) for value in (station_ids or [station_profile_id])}
            all_remote_rows = self.client.list_qsos(since_id=0, qso_since=qso_since, station_ids=allowed)
            remote_rows = [row for row in all_remote_rows if remote_station_profile_id(row) in allowed]
        except Exception:
            return 0, 1
        remote_linked = [r for r in remote_rows if str(r.get("id") or "").isdigit() and int(r["id"]) in linked]
        by_key: dict[tuple[str,str,str,str], list[int]] = {}
        for r in sorted(remote_linked, key=lambda x: int(x.get("id") or 0)):
            by_key.setdefault(_remote_status_key(r), []).append(int(r["id"]))

        visible_ids = {int(r.get("id")) for r in remote_linked if str(r.get("id") or "").isdigit()}
        # Only refresh records actually visible to this token. This matters for
        # member-scoped clubstation tokens, which intentionally see only their
        # own OPERATOR QSOs; cached status for other operators must not be wiped.
        statuses: dict[int, dict[str,str]] = {
            wid: {"qrz":"unknown","lotw":"unknown","eqsl":"unknown","clublog":"unknown","dcl":"unknown"}
            for wid in linked if wid in visible_ids
        }
        try:
            adif_rows = self.client.export_qsos_adif(qso_since=qso_since, station_ids=allowed)
            for f in adif_rows:
                ids = by_key.get(_adif_status_key(f)) or []
                if not ids:
                    continue
                wid = ids.pop(0)
                statuses[wid].update(service_statuses_from_adif(f))
        except Exception:
            errors += 1

        # Confirmation endpoint is authoritative for received confirmations.
        try:
            for c in self.client.list_confirmations(
                station_ids=allowed, qso_since=qso_since,
                types="lotw,eqsl,qrz,clublog",
            ):
                try:
                    wid = int(c.get("qso_id"))
                except Exception:
                    continue
                if wid not in statuses:
                    continue
                typ = str(c.get("type") or "").lower()
                if typ == "lotw": statuses[wid]["lotw"] = "confirmed"
                elif typ == "eqsl": statuses[wid]["eqsl"] = "confirmed"
                elif typ in ("qrz.com", "qrz"): statuses[wid]["qrz"] = "confirmed"
                elif typ == "clublog": statuses[wid]["clublog"] = "confirmed"
        except Exception:
            # Typically means confirmation:read is missing. Keep ADIF sent states.
            errors += 1

        for wid, st in statuses.items():
            self.db.set_qsl_status(wid, st)
            updated += 1
        return updated, errors

    def sync(self, station_profile_id: int, station_map: dict[int, dict[str, Any]] | None = None) -> SyncSummary:
        summary = SyncSummary()
        station_map = station_map or {}
        locals_map = self._local_map()
        allowed_station_ids = {int(station_profile_id), *self.db.xota_station_ids()}

        # Clubstation safety: a normal member token intentionally sees only the
        # QSOs of its acting OPERATOR. In that case an absent QSO must NOT be
        # interpreted as remotely deleted for a different operator. club:read is
        # only offered to officers/admins and therefore acts as an explicit
        # signal that club-wide reconciliation is safe.
        current_operator = str(self.db.get_setting("operator_call", "") or "").upper()
        selected_station = station_map.get(int(station_profile_id), {}) if station_map else {}
        selected_station_call = str(selected_station.get("callsign") or "").upper()
        club_mode = bool(selected_station_call and current_operator and selected_station_call != current_operator)
        club_full_visibility = not club_mode
        if club_mode:
            try:
                token_info = self.client.token_info()
                club_full_visibility = "club:read" in set(token_info.get("scopes") or [])
            except Exception:
                club_full_visibility = False

        # Fetch the complete current Wavelog view first. This is what lets us
        # detect remote edits and deletions, not just newly created IDs.
        try:
            all_remote_rows = self.client.list_qsos(since_id=0, station_ids=allowed_station_ids)
        except Exception:
            summary.errors += 1
            return summary

        remote_rows = [row for row in all_remote_rows if remote_station_profile_id(row) in allowed_station_ids]
        excluded_remote_rows = [row for row in all_remote_rows if remote_station_profile_id(row) not in allowed_station_ids]
        if all_remote_rows and not any(
            remote_station_profile_id(row) is not None for row in all_remote_rows
        ):
            raise WavelogError(
                "Wavelog liefert beim QSO-Download keine Stationsprofil-ID. "
                "Der sichere profilspezifische Import wurde abgebrochen; lokale QSOs bleiben unverändert."
            )
        summary.scope_skipped = len(excluded_remote_rows)

        # The compact JSON QSO representation may not expose all ADIF identity
        # fields. Supplement OPERATOR/STATION_CALLSIGN from the ADIF view.
        self._enrich_remote_identity_from_adif(remote_rows, allowed_station_ids)

        remote_by_id: dict[int, dict[str, Any]] = {}
        for r in remote_rows:
            try:
                remote_by_id[int(r.get("id"))] = r
            except Exception:
                continue

        all_remote_by_id: dict[int, dict[str, Any]] = {}
        for r in all_remote_rows:
            try:
                all_remote_by_id[int(r.get("id"))] = r
            except Exception:
                continue

        claimed_remote: set[int] = set()

        # 1) Reconcile records that are already linked to Wavelog.
        for m in list(self.db.list_meta()):
            wid = m.get("wavelog_id")
            if not wid:
                continue
            wid = int(wid)
            lid = m["local_id"]
            q = locals_map.get(lid)
            remote = remote_by_id.get(wid)
            if remote is not None:
                claimed_remote.add(wid)

            try:
                # Intentional local deletion: propagate it to Wavelog.
                if m.get("status") == "pending_delete":
                    if remote is not None:
                        self.client.delete_qso(wid)
                        summary.deleted += 1
                    self.db.delete_meta(lid)
                    locals_map.pop(lid, None)
                    continue

                # A local profile may contain an older link created before
                # station-scoped downloads were enforced. Preserve both the
                # ADI record and its remote id, but make the mismatch visible.
                # In particular, do this before the external-ADI-loss branch:
                # dropping the metadata there would make later diagnosis and
                # safe manual repair impossible.
                if remote is None:
                    other_station = all_remote_by_id.get(wid)
                    if other_station is not None:
                        actual_station_id = remote_station_profile_id(other_station)
                        self.db.set_status(
                            lid,
                            "error",
                            wavelog_id=wid,
                            error=(
                                "Das verknüpfte Wavelog-QSO gehört zum Stationsprofil "
                                f"{actual_station_id if actual_station_id is not None else 'unbekannt'}, "
                                f"nicht zum ausgewählten Profil {station_profile_id}."
                            ),
                        )
                        summary.errors += 1
                        continue

                # An ADI record disappeared outside the app. If Wavelog still
                # has it, restore it rather than silently deleting remote data.
                if q is None:
                    if remote is not None:
                        restored = self._replace_local_from_remote(lid, remote, station_map)
                        self.db.set_status(lid, "synced", wavelog_id=wid,
                                           last_synced_hash=qso_hash(restored), remote_hash=remote_hash(remote))
                        locals_map[lid] = restored
                        summary.remote_updated += 1
                    else:
                        self.db.delete_meta(lid)
                    continue

                local_now_hash = qso_hash(q)

                # v0.11.0 introduced contest exchange fields into the hash. Existing
                # v0.10 baselines therefore looked changed on BOTH sides even when
                # the QSO itself had not changed. Detect that exact schema-only
                # transition and upgrade the stored baselines safely. This also
                # auto-heals conflicts that v0.11.0 already marked as both_changed.
                if remote is not None and m.get("last_synced_hash") and m.get("remote_hash"):
                    remote_now_hash_for_migration = remote_hash(remote)
                    if (m.get("last_synced_hash") == legacy_qso_hash_v010(q) and
                            m.get("remote_hash") == legacy_remote_hash_v010(remote) and
                            (m.get("last_synced_hash") != local_now_hash or
                             m.get("remote_hash") != remote_now_hash_for_migration)):
                        self.db.set_status(lid, "synced", wavelog_id=wid,
                                           last_synced_hash=local_now_hash,
                                           remote_hash=remote_now_hash_for_migration)
                        continue

                local_changed = bool(m.get("last_synced_hash") and local_now_hash != m.get("last_synced_hash"))
                if not m.get("last_synced_hash") and m.get("status") in ("modified", "error"):
                    local_changed = True

                # Keep genuine unresolved conflicts unresolved until the user decides.
                if m.get("status") == "conflict":
                    summary.conflicts += 1
                    continue

                # Remote deletion. For an unchanged WAVELOG record this means
                # delete it locally too. If the local copy changed meanwhile,
                # preserve data and ask the user to resolve the conflict.
                if remote is None:
                    q_operator = str(q.get("operator_call") or "").upper()
                    # With a member-scoped club token, another member's QSO is
                    # invisible and looks exactly like a 404/deletion. Preserve
                    # those records until an officer token with club:read is used.
                    if club_mode and not club_full_visibility and q_operator and q_operator != current_operator:
                        continue
                    if local_changed:
                        self.db.set_status(lid, "conflict", wavelog_id=wid, error="remote_deleted")
                        summary.conflicts += 1
                    else:
                        self.store.delete(lid)
                        self.db.delete_meta(lid)
                        locals_map.pop(lid, None)
                        summary.remote_deleted += 1
                    continue

                remote_now_hash = remote_hash(remote)
                remote_changed = bool(m.get("remote_hash") and remote_now_hash != m.get("remote_hash"))

                if local_changed and remote_changed:
                    self.db.set_status(lid, "conflict", wavelog_id=wid, error="both_changed")
                    summary.conflicts += 1
                elif local_changed:
                    target_station_id = self.db.xota_station_id_for_qso(lid) or station_profile_id
                    patched = self.client.patch_qso(wid, local_to_wavelog(q, target_station_id))
                    rh = remote_hash(patched) if patched else local_now_hash
                    self.db.set_status(lid, "synced", wavelog_id=wid,
                                       last_synced_hash=local_now_hash, remote_hash=rh)
                    summary.patched += 1
                elif remote_changed:
                    updated = self._replace_local_from_remote(lid, remote, station_map)
                    self.db.set_status(lid, "synced", wavelog_id=wid,
                                       last_synced_hash=qso_hash(updated), remote_hash=remote_now_hash)
                    locals_map[lid] = updated
                    summary.remote_updated += 1
                else:
                    # Establish/refresh the baseline for older metadata rows.
                    self.db.set_status(lid, "synced", wavelog_id=wid,
                                       last_synced_hash=local_now_hash, remote_hash=remote_now_hash)
            except Exception as e:
                self.db.set_status(lid, "error", wavelog_id=wid, error=str(e))
                summary.errors += 1

        # 2) New/previously unlinked Wavelog records -> link to a matching
        # LOCAL ONLY QSO or create a new ADI record.
        locals_now = self.store.scan()
        for wid, r in sorted(remote_by_id.items()):
            if wid in claimed_remote or self.db.get_by_wavelog_id(wid):
                continue
            candidates = []
            for q in locals_now:
                meta = self.db.get_meta(q["local_id"])
                if not meta or meta.get("wavelog_id") is None:
                    candidates.append(q)
            match = self._match_local(r, candidates)
            if match:
                # Wavelog becomes the synchronized representation of this QSO.
                updated = self._replace_local_from_remote(match["local_id"], r, station_map)
                self.db.set_status(match["local_id"], "synced", wavelog_id=wid,
                                   last_synced_hash=qso_hash(updated), remote_hash=remote_hash(r))
                actual_station_id = remote_station_profile_id(r)
                if actual_station_id in set(self.db.xota_station_ids()):
                    self.db.bind_xota_remote_qso(actual_station_id, match["local_id"])
                locals_now = [updated if q.get("local_id") == match["local_id"] else q for q in locals_now]
                summary.linked += 1
            else:
                q = remote_to_local(r, self._station_for(r, station_map))
                q = self.store.add(q)
                self.db.set_status(q["local_id"], "synced", wavelog_id=wid,
                                   last_synced_hash=qso_hash(q), remote_hash=remote_hash(r))
                actual_station_id = remote_station_profile_id(r)
                if actual_station_id in set(self.db.xota_station_ids()):
                    self.db.bind_xota_remote_qso(actual_station_id, q["local_id"])
                locals_now.append(q)
                summary.pulled += 1

        # 3) Upload everything that is still LOCAL ONLY (including a failed
        # first upload from an earlier run). This happens after linking remote
        # rows so the same QSO is not duplicated.
        locals_map = {q["local_id"]: q for q in self.store.scan()}
        for m in list(self.db.list_meta()):
            if m.get("wavelog_id") is not None:
                continue
            if m.get("status") not in ("local_only", "pending", "error"):
                continue
            lid = m["local_id"]
            q = locals_map.get(lid)
            if not q:
                self.db.delete_meta(lid)
                continue
            try:
                target_station_id = self.db.xota_station_id_for_qso(lid) or station_profile_id
                remote = self.client.create_qso(local_to_wavelog(q, target_station_id, include_operator=True))
                wid = int(remote.get("id"))
                self.db.set_status(lid, "synced", wavelog_id=wid,
                                   last_synced_hash=qso_hash(q), remote_hash=remote_hash(remote))
                summary.pushed += 1
            except Exception as e:
                self.db.set_status(lid, "error", error=str(e))
                summary.errors += 1

        try:
            summary.qsl_updated, summary.qsl_errors = self._refresh_qsl_statuses(station_profile_id, allowed_station_ids)
        except Exception:
            summary.qsl_errors += 1
        return summary

    def status_for(self, local_id: str) -> str:
        m = self.db.get_meta(local_id)
        return (m or {}).get("status", "local_only")
