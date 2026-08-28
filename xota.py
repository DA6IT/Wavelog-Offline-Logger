from __future__ import annotations

import csv
import io
import json
import math
import os
import shutil
import subprocess
import sys
import threading
import urllib.parse
import urllib.request
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Iterable


XOTA_PROGRAMS = ("POTA", "SOTA", "WWFF", "IOTA", "COTA", "WCA")
SOTA_DIRECTORY_URL = "https://www.sotadata.org.uk/summitslist.csv"
WWFF_DIRECTORY_URL = "https://wwff.co/wwff-data/wwff_directory.csv"
POTA_DIRECTORY_URL = "https://pota.app/all_parks_ext.csv"
POTA_APPROXIMATE_RADIUS_KM = 10.0
POTA_FALLBACK_RADIUS_KM = 25.0
DEFAULT_REVERSE_GEOCODE_URL = "https://nominatim.openstreetmap.org/reverse"
COTA_MAX_DISTANCE_M = 1000.0


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def maidenhead_locator(latitude: float, longitude: float, precision: int = 6) -> str:
    """Convert WGS84 coordinates to a 2/4/6/8/10 character Maidenhead grid."""
    lat = float(latitude)
    lon = float(longitude)
    if not (-90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0):
        raise ValueError("Ungültige GPS-Koordinaten")
    precision = int(precision)
    if precision not in (2, 4, 6, 8, 10):
        raise ValueError("Locator-Länge muss 2, 4, 6, 8 oder 10 Zeichen betragen")
    # Keep the exact north/east boundary inside the final valid cell.
    lon = min(lon, math.nextafter(180.0, -math.inf)) + 180.0
    lat = min(lat, math.nextafter(90.0, -math.inf)) + 90.0
    out = [chr(65 + int(lon // 20)), chr(65 + int(lat // 10))]
    if precision >= 4:
        lon %= 20
        lat %= 10
        out.extend((str(int(lon // 2)), str(int(lat))))
    if precision >= 6:
        lon %= 2
        lat %= 1
        out.extend((chr(65 + int(lon * 12)), chr(65 + int(lat * 24))))
    if precision >= 8:
        lon = (lon * 12) % 1
        lat = (lat * 24) % 1
        out.extend((str(int(lon * 10)), str(int(lat * 10))))
    if precision >= 10:
        lon = (lon * 10) % 1
        lat = (lat * 10) % 1
        out.extend((chr(65 + int(lon * 24)), chr(65 + int(lat * 24))))
    return "".join(out)


def maidenhead_coordinates(locator: str) -> tuple[float, float]:
    """Return the WGS84 centre of a 2/4/6/8/10 character Maidenhead grid."""
    value = str(locator or "").strip().upper()
    if len(value) not in (2, 4, 6, 8, 10):
        raise ValueError("Locator-Länge muss 2, 4, 6, 8 oder 10 Zeichen betragen")
    if not ("A" <= value[0] <= "R" and "A" <= value[1] <= "R"):
        raise ValueError("Ungültiges Maidenhead-Feld")

    longitude = -180.0 + (ord(value[0]) - 65) * 20.0
    latitude = -90.0 + (ord(value[1]) - 65) * 10.0
    longitude_size, latitude_size = 20.0, 10.0
    if len(value) >= 4:
        if not (value[2].isdigit() and value[3].isdigit()):
            raise ValueError("Ungültiges Maidenhead-Großfeld")
        longitude_size, latitude_size = 2.0, 1.0
        longitude += int(value[2]) * longitude_size
        latitude += int(value[3]) * latitude_size
    if len(value) >= 6:
        if not ("A" <= value[4] <= "X" and "A" <= value[5] <= "X"):
            raise ValueError("Ungültiges Maidenhead-Unterfeld")
        longitude_size /= 24.0
        latitude_size /= 24.0
        longitude += (ord(value[4]) - 65) * longitude_size
        latitude += (ord(value[5]) - 65) * latitude_size
    if len(value) >= 8:
        if not (value[6].isdigit() and value[7].isdigit()):
            raise ValueError("Ungültiges erweitertes Maidenhead-Feld")
        longitude_size /= 10.0
        latitude_size /= 10.0
        longitude += int(value[6]) * longitude_size
        latitude += int(value[7]) * latitude_size
    if len(value) >= 10:
        if not ("A" <= value[8] <= "X" and "A" <= value[9] <= "X"):
            raise ValueError("Ungültiges erweitertes Maidenhead-Unterfeld")
        longitude_size /= 24.0
        latitude_size /= 24.0
        longitude += (ord(value[8]) - 65) * longitude_size
        latitude += (ord(value[9]) - 65) * latitude_size
    return latitude + latitude_size / 2.0, longitude + longitude_size / 2.0


def distance_m(latitude_a: float, longitude_a: float, latitude_b: float, longitude_b: float) -> float:
    """Great-circle distance using the WGS84 mean earth radius."""
    lat1, lat2 = math.radians(float(latitude_a)), math.radians(float(latitude_b))
    dlat = lat2 - lat1
    dlon = math.radians(float(longitude_b) - float(longitude_a))
    value = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 6_371_008.8 * 2 * math.atan2(math.sqrt(value), math.sqrt(max(0.0, 1 - value)))


def initial_bearing_degrees(
    latitude_a: float, longitude_a: float, latitude_b: float, longitude_b: float,
) -> float:
    """Return the initial great-circle bearing from point A to point B."""
    lat1, lat2 = math.radians(float(latitude_a)), math.radians(float(latitude_b))
    dlon = math.radians(float(longitude_b) - float(longitude_a))
    y = math.sin(dlon) * math.cos(lat2)
    x = math.cos(lat1) * math.sin(lat2) - math.sin(lat1) * math.cos(lat2) * math.cos(dlon)
    return (math.degrees(math.atan2(y, x)) + 360.0) % 360.0


def _json_list(value: Any) -> list[str]:
    if isinstance(value, str):
        try:
            decoded = json.loads(value)
            if isinstance(decoded, list):
                value = decoded
            else:
                value = [part for part in value.replace(";", ",").split(",")]
        except Exception:
            value = [part for part in value.replace(";", ",").split(",")]
    if not isinstance(value, (list, tuple, set)):
        value = [] if value in (None, "") else [value]
    out: list[str] = []
    for item in value:
        normalized = str(item or "").strip().upper()
        if normalized and normalized not in out:
            out.append(normalized)
    return out


def normalize_references(references: dict[str, Any] | None) -> dict[str, list[str]]:
    source = references or {}
    return {program: _json_list(source.get(program, [])) for program in XOTA_PROGRAMS}


@dataclass(frozen=True)
class GPSFix:
    latitude: float
    longitude: float
    accuracy: float | None = None
    timestamp: str = field(default_factory=utc_now)
    source: str = "OS"


@dataclass
class ReferenceCandidate:
    provider: str
    program: str
    reference: str
    name: str
    latitude: float
    longitude: float
    locator: str = ""
    distance_m: float = 0.0
    references: dict[str, list[str]] = field(default_factory=dict)
    warning: str = ""
    eligible: bool = True
    updated_at: str = ""

    def __post_init__(self):
        self.program = str(self.program or "").upper()
        self.reference = str(self.reference or "").upper()
        self.references = normalize_references(self.references or {self.program: [self.reference]})


def merge_candidate_references(
    candidates: Iterable[ReferenceCandidate], current: dict[str, Any] | None = None,
) -> dict[str, list[str]]:
    """Merge one or more confirmed xOTA candidates without duplicating refs."""
    merged = normalize_references(current)
    for candidate in candidates:
        for program, references in normalize_references(candidate.references).items():
            for reference in references:
                if reference not in merged[program]:
                    merged[program].append(reference)
    return merged


@dataclass
class XotaActivation:
    uuid: str
    profile_id: str
    callsign: str
    latitude: float | None = None
    longitude: float | None = None
    gps_accuracy: float | None = None
    gps_timestamp: str = ""
    gridsquare: str = ""
    city: str = ""
    state: str = ""
    country: str = ""
    dxcc: str = ""
    cq_zone: str = ""
    itu_zone: str = ""
    references: dict[str, list[str]] = field(default_factory=dict)
    power: str = ""
    note: str = ""
    started_at: str = ""
    ended_at: str = ""
    created_at: str = field(default_factory=utc_now)
    status: str = "draft"
    wavelog_station_id: int | None = None
    wavelog_station_uuid: str = ""
    sync_status: str = "local_only"

    def __post_init__(self):
        self.callsign = self.callsign.strip().upper()
        self.gridsquare = self.gridsquare.strip().upper()
        self.references = normalize_references(self.references)


class XotaRepository:
    """Profile-local activation and reference-cache persistence."""

    def __init__(self, metadata_db):
        self.db = metadata_db
        with self.db.lock:
            self.db.conn.executescript("""
                CREATE TABLE IF NOT EXISTS xota_activations (
                    activation_uuid TEXT PRIMARY KEY,
                    profile_id TEXT NOT NULL,
                    callsign TEXT NOT NULL,
                    latitude REAL,
                    longitude REAL,
                    gps_accuracy REAL,
                    gps_timestamp TEXT,
                    gridsquare TEXT,
                    city TEXT,
                    state TEXT,
                    country TEXT,
                    dxcc TEXT,
                    cq_zone TEXT,
                    itu_zone TEXT,
                    references_json TEXT NOT NULL DEFAULT '{}',
                    power TEXT,
                    note TEXT,
                    started_at TEXT,
                    ended_at TEXT,
                    created_at TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'draft',
                    wavelog_station_id INTEGER,
                    wavelog_station_uuid TEXT,
                    sync_status TEXT NOT NULL DEFAULT 'local_only'
                );
                CREATE INDEX IF NOT EXISTS idx_xota_activation_status ON xota_activations(status, created_at);
                CREATE INDEX IF NOT EXISTS idx_xota_activation_station ON xota_activations(wavelog_station_id);
                CREATE TABLE IF NOT EXISTS xota_activation_qsos (
                    activation_uuid TEXT NOT NULL,
                    local_id TEXT PRIMARY KEY,
                    station_id INTEGER,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(activation_uuid) REFERENCES xota_activations(activation_uuid)
                );
                CREATE INDEX IF NOT EXISTS idx_xota_qso_activation ON xota_activation_qsos(activation_uuid);
                CREATE TABLE IF NOT EXISTS xota_reference_cache (
                    provider TEXT NOT NULL,
                    program TEXT NOT NULL,
                    reference TEXT NOT NULL,
                    name TEXT,
                    latitude REAL NOT NULL,
                    longitude REAL NOT NULL,
                    locator TEXT,
                    extra_json TEXT NOT NULL DEFAULT '{}',
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY(provider, program, reference)
                );
                CREATE INDEX IF NOT EXISTS idx_xota_reference_location ON xota_reference_cache(latitude, longitude);
                CREATE TABLE IF NOT EXISTS xota_geocode_cache (
                    cache_key TEXT PRIMARY KEY,
                    payload TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
            """)
            self.db.conn.commit()

    @staticmethod
    def _row_to_activation(row) -> XotaActivation:
        data = dict(row)
        return XotaActivation(
            uuid=str(data["activation_uuid"]), profile_id=str(data["profile_id"]),
            callsign=str(data["callsign"]), latitude=data["latitude"], longitude=data["longitude"],
            gps_accuracy=data["gps_accuracy"], gps_timestamp=str(data["gps_timestamp"] or ""),
            gridsquare=str(data["gridsquare"] or ""), city=str(data["city"] or ""),
            state=str(data["state"] or ""), country=str(data["country"] or ""),
            dxcc=str(data["dxcc"] or ""), cq_zone=str(data["cq_zone"] or ""),
            itu_zone=str(data["itu_zone"] or ""), references=json.loads(data["references_json"] or "{}"),
            power=str(data["power"] or ""), note=str(data["note"] or ""),
            started_at=str(data["started_at"] or ""), ended_at=str(data["ended_at"] or ""),
            created_at=str(data["created_at"] or ""), status=str(data["status"] or "draft"),
            wavelog_station_id=data["wavelog_station_id"],
            wavelog_station_uuid=str(data["wavelog_station_uuid"] or ""),
            sync_status=str(data["sync_status"] or "local_only"),
        )

    def save(self, activation: XotaActivation) -> XotaActivation:
        activation.references = normalize_references(activation.references)
        values = (
            activation.uuid, activation.profile_id, activation.callsign, activation.latitude,
            activation.longitude, activation.gps_accuracy, activation.gps_timestamp,
            activation.gridsquare, activation.city, activation.state, activation.country,
            activation.dxcc, activation.cq_zone, activation.itu_zone,
            json.dumps(activation.references, ensure_ascii=False), activation.power, activation.note,
            activation.started_at, activation.ended_at, activation.created_at, activation.status,
            activation.wavelog_station_id, activation.wavelog_station_uuid, activation.sync_status,
        )
        with self.db.lock:
            self.db.conn.execute("""
                INSERT INTO xota_activations(
                    activation_uuid,profile_id,callsign,latitude,longitude,gps_accuracy,gps_timestamp,
                    gridsquare,city,state,country,dxcc,cq_zone,itu_zone,references_json,power,note,
                    started_at,ended_at,created_at,status,wavelog_station_id,wavelog_station_uuid,sync_status
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(activation_uuid) DO UPDATE SET
                    callsign=excluded.callsign,latitude=excluded.latitude,longitude=excluded.longitude,
                    gps_accuracy=excluded.gps_accuracy,gps_timestamp=excluded.gps_timestamp,
                    gridsquare=excluded.gridsquare,city=excluded.city,state=excluded.state,country=excluded.country,
                    dxcc=excluded.dxcc,cq_zone=excluded.cq_zone,itu_zone=excluded.itu_zone,
                    references_json=excluded.references_json,power=excluded.power,note=excluded.note,
                    started_at=excluded.started_at,ended_at=excluded.ended_at,status=excluded.status,
                    wavelog_station_id=excluded.wavelog_station_id,
                    wavelog_station_uuid=excluded.wavelog_station_uuid,sync_status=excluded.sync_status
            """, values)
            self.db.conn.commit()
        return activation

    def create(self, profile_id: str, callsign: str, **values: Any) -> XotaActivation:
        activation = XotaActivation(uuid=str(uuid.uuid4()), profile_id=profile_id, callsign=callsign, **values)
        return self.save(activation)

    def get(self, activation_uuid: str) -> XotaActivation | None:
        with self.db.lock:
            row = self.db.conn.execute(
                "SELECT * FROM xota_activations WHERE activation_uuid=?", (activation_uuid,),
            ).fetchone()
        return self._row_to_activation(row) if row else None

    def active(self) -> XotaActivation | None:
        with self.db.lock:
            row = self.db.conn.execute(
                "SELECT * FROM xota_activations WHERE status='active' ORDER BY started_at DESC LIMIT 1"
            ).fetchone()
        return self._row_to_activation(row) if row else None

    def list(self, limit: int = 100) -> list[XotaActivation]:
        with self.db.lock:
            rows = self.db.conn.execute(
                "SELECT * FROM xota_activations ORDER BY COALESCE(started_at,created_at) DESC LIMIT ?",
                (max(1, int(limit)),),
            ).fetchall()
        return [self._row_to_activation(row) for row in rows]

    def start(self, activation_uuid: str) -> XotaActivation:
        with self.db.lock:
            current = self.db.conn.execute(
                "SELECT activation_uuid FROM xota_activations WHERE status='active' AND activation_uuid<>?",
                (activation_uuid,),
            ).fetchone()
            if current:
                raise ValueError("Es läuft bereits eine andere xOTA-Aktivierung")
            self.db.conn.execute(
                "UPDATE xota_activations SET status='active',started_at=?,ended_at='' WHERE activation_uuid=?",
                (utc_now(), activation_uuid),
            )
            self.db.conn.commit()
        result = self.get(activation_uuid)
        if result is None:
            raise KeyError(activation_uuid)
        return result

    def finish(self, activation_uuid: str) -> XotaActivation:
        with self.db.lock:
            self.db.conn.execute(
                "UPDATE xota_activations SET status='finished',ended_at=? WHERE activation_uuid=?",
                (utc_now(), activation_uuid),
            )
            self.db.conn.commit()
        result = self.get(activation_uuid)
        if result is None:
            raise KeyError(activation_uuid)
        return result

    def bind_qso(self, activation_uuid: str, local_id: str) -> None:
        activation = self.get(activation_uuid)
        if activation is None:
            raise KeyError(activation_uuid)
        with self.db.lock:
            self.db.conn.execute(
                "INSERT INTO xota_activation_qsos(activation_uuid,local_id,station_id,created_at) VALUES(?,?,?,?) "
                "ON CONFLICT(local_id) DO UPDATE SET activation_uuid=excluded.activation_uuid,station_id=excluded.station_id",
                (activation_uuid, local_id, activation.wavelog_station_id, utc_now()),
            )
            self.db.conn.commit()

    def qso_count(self, activation_uuid: str) -> int:
        with self.db.lock:
            row = self.db.conn.execute(
                "SELECT COUNT(*) FROM xota_activation_qsos WHERE activation_uuid=?", (activation_uuid,),
            ).fetchone()
        return int(row[0]) if row else 0

    def qso_ids(self, activation_uuid: str) -> list[str]:
        with self.db.lock:
            return [str(row[0]) for row in self.db.conn.execute(
                "SELECT local_id FROM xota_activation_qsos WHERE activation_uuid=? ORDER BY created_at",
                (activation_uuid,),
            )]

    def set_wavelog_station(self, activation_uuid: str, station_id: int, station_uuid: str = "") -> None:
        with self.db.lock:
            self.db.conn.execute(
                "UPDATE xota_activations SET wavelog_station_id=?,wavelog_station_uuid=?,sync_status='pending' "
                "WHERE activation_uuid=?", (int(station_id), station_uuid, activation_uuid),
            )
            self.db.conn.execute(
                "UPDATE xota_activation_qsos SET station_id=? WHERE activation_uuid=?",
                (int(station_id), activation_uuid),
            )
            self.db.conn.commit()

    def station_id_for_qso(self, local_id: str) -> int | None:
        with self.db.lock:
            row = self.db.conn.execute(
                "SELECT station_id FROM xota_activation_qsos WHERE local_id=?", (local_id,),
            ).fetchone()
        return int(row[0]) if row and row[0] not in (None, "") else None

    def station_ids(self) -> list[int]:
        with self.db.lock:
            rows = self.db.conn.execute(
                "SELECT DISTINCT station_id FROM xota_activation_qsos WHERE station_id IS NOT NULL"
            ).fetchall()
        return sorted({int(row[0]) for row in rows})

    def activation_for_station(self, station_id: int) -> XotaActivation | None:
        with self.db.lock:
            row = self.db.conn.execute(
                "SELECT * FROM xota_activations WHERE wavelog_station_id=? ORDER BY created_at DESC LIMIT 1",
                (int(station_id),),
            ).fetchone()
        return self._row_to_activation(row) if row else None

    def bind_remote_qso(self, station_id: int, local_id: str) -> None:
        activation = self.activation_for_station(station_id)
        if activation:
            self.bind_qso(activation.uuid, local_id)

    def upsert_reference(self, candidate: ReferenceCandidate) -> None:
        extra = {"references": normalize_references(candidate.references)}
        with self.db.lock:
            self.db.conn.execute("""
                INSERT INTO xota_reference_cache(provider,program,reference,name,latitude,longitude,locator,extra_json,updated_at)
                VALUES(?,?,?,?,?,?,?,?,?) ON CONFLICT(provider,program,reference) DO UPDATE SET
                    name=excluded.name,latitude=excluded.latitude,longitude=excluded.longitude,
                    locator=excluded.locator,extra_json=excluded.extra_json,updated_at=excluded.updated_at
            """, (
                candidate.provider, candidate.program, candidate.reference, candidate.name,
                float(candidate.latitude), float(candidate.longitude), candidate.locator,
                json.dumps(extra, ensure_ascii=False), candidate.updated_at or utc_now(),
            ))
            self.db.conn.commit()

    def replace_provider_references(self, provider: str, rows: Iterable[ReferenceCandidate]) -> int:
        prepared = list(rows)
        with self.db.lock:
            self.db.conn.execute("DELETE FROM xota_reference_cache WHERE provider=?", (provider,))
            values = []
            for row in prepared:
                extra = json.dumps({"references": normalize_references(row.references)}, ensure_ascii=False)
                values.append((provider, row.program, row.reference, row.name, float(row.latitude), float(row.longitude),
                               row.locator, extra, row.updated_at or utc_now()))
            self.db.conn.executemany(
                "INSERT INTO xota_reference_cache(provider,program,reference,name,latitude,longitude,locator,extra_json,updated_at) "
                "VALUES(?,?,?,?,?,?,?,?,?)", values,
            )
            self.db.conn.commit()
        return len(prepared)

    def nearby_references(self, latitude: float, longitude: float, radius_km: float = 25.0) -> list[ReferenceCandidate]:
        lat_delta = radius_km / 111.0
        lon_delta = radius_km / max(1.0, 111.0 * math.cos(math.radians(latitude)))
        with self.db.lock:
            rows = self.db.conn.execute("""
                SELECT * FROM xota_reference_cache
                WHERE latitude BETWEEN ? AND ? AND longitude BETWEEN ? AND ?
            """, (latitude - lat_delta, latitude + lat_delta, longitude - lon_delta, longitude + lon_delta)).fetchall()
        result: list[ReferenceCandidate] = []
        for row in rows:
            data = dict(row)
            dist = distance_m(latitude, longitude, data["latitude"], data["longitude"])
            if dist > radius_km * 1000:
                continue
            try:
                extra = json.loads(data["extra_json"] or "{}")
            except Exception:
                extra = {}
            program = str(data["program"])
            warning = ""
            eligible = True
            if program in ("COTA", "COTA/WCA") and dist > COTA_MAX_DISTANCE_M:
                eligible = False
                warning = "Außerhalb des deutschen COTA-Aktivierungsradius von 1000 m"
            result.append(ReferenceCandidate(
                provider=str(data["provider"]), program=program, reference=str(data["reference"]),
                name=str(data["name"] or ""), latitude=float(data["latitude"]),
                longitude=float(data["longitude"]), locator=str(data["locator"] or ""),
                distance_m=dist, references=extra.get("references") or {program: [data["reference"]]},
                warning=warning, eligible=eligible, updated_at=str(data["updated_at"] or ""),
            ))
        result.sort(key=lambda item: (item.distance_m, item.program, item.reference))
        return result

    def provider_status(self) -> dict[str, dict[str, Any]]:
        with self.db.lock:
            rows = self.db.conn.execute("""
                SELECT provider,COUNT(*) AS count,MAX(updated_at) AS updated_at
                FROM xota_reference_cache GROUP BY provider ORDER BY provider
            """).fetchall()
        return {str(row["provider"]): {"count": int(row["count"]), "updated_at": str(row["updated_at"] or "")} for row in rows}

    def get_geocode(self, latitude: float, longitude: float) -> dict[str, Any] | None:
        key = f"{latitude:.5f},{longitude:.5f}"
        with self.db.lock:
            row = self.db.conn.execute("SELECT payload FROM xota_geocode_cache WHERE cache_key=?", (key,)).fetchone()
        if not row:
            return None
        try:
            return json.loads(row[0])
        except Exception:
            return None

    def set_geocode(self, latitude: float, longitude: float, payload: dict[str, Any]) -> None:
        key = f"{latitude:.5f},{longitude:.5f}"
        with self.db.lock:
            self.db.conn.execute(
                "INSERT INTO xota_geocode_cache(cache_key,payload,updated_at) VALUES(?,?,?) "
                "ON CONFLICT(cache_key) DO UPDATE SET payload=excluded.payload,updated_at=excluded.updated_at",
                (key, json.dumps(payload, ensure_ascii=False), utc_now()),
            )
            self.db.conn.commit()


class GPSService:
    """Best-effort OS location access; manual coordinates always remain available."""

    @staticmethod
    def current_position(timeout: int = 20) -> GPSFix:
        override = os.environ.get("WAVELOG_LOGGER_GPS", "").strip()
        if override:
            parts = [part.strip() for part in override.split(",")]
            return GPSFix(float(parts[0]), float(parts[1]), float(parts[2]) if len(parts) > 2 else None, source="Test/Umgebung")
        if sys.platform == "win32":
            return GPSService._windows(timeout)
        if sys.platform == "darwin":
            return GPSService._command_location(("CoreLocationCLI", "-once", "-json"), timeout, "macOS Core Location")
        for command in (("where-am-i", "-f", "json"), ("geoclue-where-am-i", "-f", "json")):
            if shutil.which(command[0]):
                return GPSService._command_location(command, timeout, "GeoClue")
        raise RuntimeError("Kein unterstützter GPS-Dienst gefunden. Koordinaten können manuell eingegeben werden.")

    @staticmethod
    def _command_location(command: tuple[str, ...], timeout: int, source: str) -> GPSFix:
        if not shutil.which(command[0]):
            raise RuntimeError(f"{source} ist auf diesem System nicht verfügbar")
        result = subprocess.run(command, capture_output=True, text=True, timeout=timeout, check=False)
        if result.returncode != 0:
            raise RuntimeError((result.stderr or result.stdout or f"{source} fehlgeschlagen").strip())
        data = json.loads(result.stdout)
        latitude = data.get("latitude", data.get("Latitude"))
        longitude = data.get("longitude", data.get("Longitude"))
        accuracy = data.get("accuracy", data.get("Accuracy"))
        return GPSFix(float(latitude), float(longitude), float(accuracy) if accuracy not in (None, "") else None, source=source)

    @staticmethod
    def _windows(timeout: int) -> GPSFix:
        powershell = shutil.which("powershell.exe") or shutil.which("powershell")
        if not powershell:
            raise RuntimeError("Windows PowerShell wurde nicht gefunden")
        script = r'''
$ErrorActionPreference='Stop'
Add-Type -AssemblyName System.Runtime.WindowsRuntime
$null=[Windows.Devices.Geolocation.Geolocator,Windows.Devices.Geolocation,ContentType=WindowsRuntime]
function Await-WinRT($Operation,[Type]$ResultType) {
  $method=[System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object {
    $_.Name -eq 'AsTask' -and $_.IsGenericMethod -and $_.GetParameters().Count -eq 1
  } | Select-Object -First 1
  $task=$method.MakeGenericMethod($ResultType).Invoke($null,@($Operation))
  if(-not $task.Wait(18000)){ throw 'GPS-Zeitüberschreitung' }
  return $task.Result
}
$access=Await-WinRT ([Windows.Devices.Geolocation.Geolocator]::RequestAccessAsync()) ([Windows.Devices.Geolocation.GeolocationAccessStatus])
if($access.ToString() -ne 'Allowed'){ throw "Standortzugriff: $access" }
$locator=New-Object Windows.Devices.Geolocation.Geolocator
$locator.DesiredAccuracyInMeters=50
$position=Await-WinRT ($locator.GetGeopositionAsync()) ([Windows.Devices.Geolocation.Geoposition])
$c=$position.Coordinate
@{latitude=$c.Point.Position.Latitude;longitude=$c.Point.Position.Longitude;accuracy=$c.Accuracy;timestamp=$c.Timestamp.ToString('o')} | ConvertTo-Json -Compress
'''
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        result = subprocess.run(
            (powershell, "-NoProfile", "-STA", "-Command", script), capture_output=True,
            text=True, timeout=timeout + 5, creationflags=flags, check=False,
        )
        if result.returncode != 0:
            detail = (result.stderr or result.stdout or "Windows-Ortung fehlgeschlagen").strip()
            raise RuntimeError(detail.splitlines()[-1])
        data = json.loads(result.stdout.strip().splitlines()[-1])
        return GPSFix(float(data["latitude"]), float(data["longitude"]), float(data.get("accuracy") or 0), str(data.get("timestamp") or utc_now()), "Windows Location")


def _download(url: str, timeout: int = 30) -> bytes:
    from logger_core import USER_AGENT, secure_urlopen
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json,text/csv,*/*"})
    with secure_urlopen(request, timeout=timeout) as response:
        return response.read()


def _value(row: dict[str, Any], *names: str) -> str:
    lookup = {str(key).strip().lower().replace(" ", "_"): value for key, value in row.items()}
    for name in names:
        value = lookup.get(name.lower().replace(" ", "_"))
        if value not in (None, ""):
            return str(value).strip()
    return ""


def _float_value(row: dict[str, Any], *names: str) -> float | None:
    value = _value(row, *names).replace(",", ".")
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def parse_reference_csv(payload: bytes, provider: str, default_program: str) -> list[ReferenceCandidate]:
    text = payload.decode("utf-8-sig", errors="replace")
    sample = text[:8192]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
    except csv.Error:
        dialect = csv.excel
    result: list[ReferenceCandidate] = []
    for raw in csv.DictReader(io.StringIO(text), dialect=dialect):
        row = {str(k or ""): v for k, v in raw.items()}
        lat = _float_value(row, "latitude", "lat", "summit_latitude")
        lon = _float_value(row, "longitude", "lon", "lng", "summit_longitude")
        if lat is None or lon is None:
            continue
        reference = _value(row, "reference", "ref", "summitcode", "summit_code", "code", "wca_ref", "wca")
        cota = _value(row, "cota_ref", "cota")
        wca = _value(row, "wca_ref", "wca")
        # Some catalogues use "type" for the kind of park/summit rather than
        # the xOTA programme. Only accept a known programme identifier here.
        program = _value(row, "program").upper()
        if program not in XOTA_PROGRAMS:
            program = default_program
        references = normalize_references({program: [reference], "COTA": [cota], "WCA": [wca]})
        if not reference:
            reference = cota or wca
        if not reference:
            continue
        name = _value(row, "name", "summitname", "summit_name", "reference_name", "parkname", "park_name", "castle")
        locator = _value(row, "locator", "gridsquare", "grid").upper() or maidenhead_locator(lat, lon)
        result.append(ReferenceCandidate(
            provider=provider, program=program, reference=reference, name=name,
            latitude=lat, longitude=lon, locator=locator, references=references, updated_at=utc_now(),
        ))
    return result


class ActivationReferenceProvider:
    name = "Provider"
    program = ""
    directory_url = ""

    def __init__(self, repository: XotaRepository, directory_url: str = ""):
        self.repository = repository
        self.url = directory_url or self.directory_url

    def is_available(self) -> bool:
        return bool(self.repository.provider_status().get(self.name))

    def update_cache(self, latitude: float | None = None, longitude: float | None = None) -> int:
        if not self.url:
            raise RuntimeError(f"Für {self.name} ist keine Datenquelle konfiguriert")
        rows = parse_reference_csv(_download(self.url), self.name, self.program)
        if not rows:
            raise RuntimeError(f"{self.name} lieferte keine lesbaren Referenzen")
        return self.repository.replace_provider_references(self.name, rows)

    def find_nearby(self, latitude: float, longitude: float, radius_km: float = 25.0) -> list[ReferenceCandidate]:
        return [row for row in self.repository.nearby_references(latitude, longitude, radius_km) if row.provider == self.name]


class SotaProvider(ActivationReferenceProvider):
    name = "SOTA"
    program = "SOTA"
    directory_url = SOTA_DIRECTORY_URL


class WwffProvider(ActivationReferenceProvider):
    name = "WWFF"
    program = "WWFF"
    directory_url = WWFF_DIRECTORY_URL


class CsvReferenceProvider(ActivationReferenceProvider):
    pass


class PotaProvider(ActivationReferenceProvider):
    name = "POTA"
    program = "POTA"
    directory_url = POTA_DIRECTORY_URL


class ActivationReferenceService:
    def __init__(self, repository: XotaRepository, get_setting):
        self.repository = repository
        self.providers: list[ActivationReferenceProvider] = [
            PotaProvider(repository), SotaProvider(repository), WwffProvider(repository),
            CsvReferenceProvider(repository, get_setting("xota_iota_data_url", "")),
            CsvReferenceProvider(repository, get_setting("xota_cota_wca_data_url", "")),
        ]
        self.providers[3].name, self.providers[3].program = "IOTA", "IOTA"
        self.providers[4].name, self.providers[4].program = "COTA/WCA", "COTA"

    def update_all(self, latitude: float | None = None, longitude: float | None = None) -> dict[str, Any]:
        results: dict[str, Any] = {}
        for provider in self.providers:
            if isinstance(provider, CsvReferenceProvider) and not provider.url:
                results[provider.name] = "keine Datenquelle konfiguriert"
                continue
            try:
                results[provider.name] = provider.update_cache(latitude, longitude)
            except Exception as exc:
                results[provider.name] = str(exc)
        return results

    def find_nearby(self, latitude: float, longitude: float, radius_km: float = 25.0, refresh_pota: bool = False) -> list[ReferenceCandidate]:
        status = self.repository.provider_status().get("POTA", {})
        # Older builds cached only one small area. Replace such a partial cache
        # once with the complete official POTA catalogue; subsequent searches
        # are local and also work without an internet connection.
        if refresh_pota and int(status.get("count") or 0) < 1000:
            try:
                self.providers[0].update_cache(latitude, longitude)
            except Exception:
                pass
        rows = self.repository.nearby_references(
            latitude, longitude, max(float(radius_km), POTA_FALLBACK_RADIUS_KM)
        )
        result: list[ReferenceCandidate] = []
        for row in rows:
            if row.provider != "POTA" and row.distance_m > float(radius_km) * 1000:
                continue
            if row.provider == "POTA":
                if row.distance_m > POTA_FALLBACK_RADIUS_KM * 1000:
                    continue
                marker_km = row.distance_m / 1000.0
                if marker_km <= POTA_APPROXIMATE_RADIUS_KM:
                    prefix = f"Naher POTA-Marker ({marker_km:.1f} km). "
                else:
                    prefix = f"Großer Park möglich; POTA-Marker {marker_km:.1f} km entfernt. "
                row.warning = (
                    prefix + "Die POTA-Katalogkoordinate ist nur ein Näherungspunkt und kein Nachweis, "
                    "dass der aktuelle Standort innerhalb der Parkgrenze liegt. Bitte die Grenze "
                    "auf pota-map.info oder in einer amtlichen Quelle prüfen."
                )
            result.append(row)
        return result


class ReverseGeocodeService:
    def __init__(self, repository: XotaRepository, endpoint: str = DEFAULT_REVERSE_GEOCODE_URL):
        self.repository = repository
        self.endpoint = endpoint.strip() or DEFAULT_REVERSE_GEOCODE_URL
        self.lock = threading.Lock()

    def reverse(self, latitude: float, longitude: float) -> dict[str, str]:
        cached = self.repository.get_geocode(latitude, longitude)
        if cached:
            return {str(k): str(v or "") for k, v in cached.items()}
        query = urllib.parse.urlencode({"lat": f"{latitude:.7f}", "lon": f"{longitude:.7f}", "format": "jsonv2", "addressdetails": 1, "zoom": 10})
        payload = json.loads(_download(self.endpoint + ("&" if "?" in self.endpoint else "?") + query, timeout=15).decode("utf-8"))
        address = payload.get("address") if isinstance(payload.get("address"), dict) else {}
        result = {
            "city": str(address.get("city") or address.get("town") or address.get("village") or address.get("municipality") or ""),
            "state": str(address.get("state") or address.get("region") or ""),
            "country": str(address.get("country") or ""),
            "country_code": str(address.get("country_code") or "").upper(),
            "attribution": "© OpenStreetMap contributors",
        }
        self.repository.set_geocode(latitude, longitude, result)
        return result


def station_payload(activation: XotaActivation, name: str = "") -> dict[str, Any]:
    refs = normalize_references(activation.references)
    title_parts = [activation.callsign]
    for program in ("POTA", "SOTA", "WWFF", "IOTA", "WCA", "COTA"):
        if refs[program]:
            title_parts.append(refs[program][0])
    generated_name = " · ".join(title_parts[:4])[:80]
    payload: dict[str, Any] = {
        "name": (name or generated_name or "xOTA").strip()[:80],
        "callsign": activation.callsign,
        "gridsquare": activation.gridsquare,
        "city": activation.city,
        "dxcc": int(activation.dxcc) if str(activation.dxcc).isdigit() else None,
        "cq": int(activation.cq_zone) if str(activation.cq_zone).isdigit() else None,
        "itu": int(activation.itu_zone) if str(activation.itu_zone).isdigit() else None,
        "state": activation.state,
        "iota": refs["IOTA"][0] if refs["IOTA"] else "",
        "sota": refs["SOTA"][0] if refs["SOTA"] else "",
        "wwff": refs["WWFF"][0] if refs["WWFF"] else "",
        "pota": refs["POTA"][0] if refs["POTA"] else "",
        "sig": "WCA" if refs["WCA"] else "",
        "sig_info": refs["WCA"][0] if refs["WCA"] else "",
        "power": float(activation.power) if str(activation.power).replace(".", "", 1).isdigit() else None,
    }
    return {key: value for key, value in payload.items() if value not in (None, "")}


def station_match_score(activation: XotaActivation, station: dict[str, Any]) -> tuple[int, list[str]]:
    score, reasons = 0, []
    payload = station_payload(activation)
    if str(station.get("callsign") or "").upper() == activation.callsign:
        score += 35; reasons.append("Rufzeichen")
    grid_a = activation.gridsquare.upper()
    grid_b = str(station.get("gridsquare") or "").upper()
    if grid_a and grid_b:
        if grid_a[:6] == grid_b[:6]:
            score += 25; reasons.append("Locator")
        elif grid_a[:4] == grid_b[:4]:
            score += 10; reasons.append("Locator-Feld")
    if activation.dxcc and str(station.get("dxcc") or "") == str(activation.dxcc):
        score += 8; reasons.append("DXCC")
    for field_name, points in (("pota", 25), ("sota", 25), ("wwff", 25), ("iota", 20), ("sig_info", 20)):
        wanted = str(payload.get(field_name) or "").upper()
        actual = str(station.get(field_name) or "").upper()
        if wanted and actual == wanted:
            score += points; reasons.append(field_name.upper())
        elif wanted and actual and actual != wanted:
            score -= points
    return score, reasons


class WavelogStationService:
    def __init__(self, client):
        self.client = client

    def candidates(self, activation: XotaActivation, stations: Iterable[dict[str, Any]]) -> list[tuple[int, list[str], dict[str, Any]]]:
        rows = [(score, reasons, station) for station in stations for score, reasons in [station_match_score(activation, station)] if score > 0]
        rows.sort(key=lambda row: row[0], reverse=True)
        return rows

    def confident_match(self, activation: XotaActivation, stations: Iterable[dict[str, Any]]) -> dict[str, Any] | None:
        rows = self.candidates(activation, stations)
        if not rows or rows[0][0] < 60:
            return None
        if len(rows) > 1 and rows[1][0] == rows[0][0]:
            return None
        return rows[0][2]

    def create(self, activation: XotaActivation, name: str = "") -> dict[str, Any]:
        return self.client.create_station(station_payload(activation, name))
