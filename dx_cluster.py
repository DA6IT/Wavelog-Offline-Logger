from __future__ import annotations

import re
import socket
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Callable

from logger_core import band_from_mhz


DEFAULT_CLUSTER_HOST = "dxcluster.afu-tools.de"
DEFAULT_CLUSTER_PORT = 7300


class DxClusterError(RuntimeError):
    pass


@dataclass(frozen=True)
class DxClusterConfig:
    host: str = DEFAULT_CLUSTER_HOST
    port: int = DEFAULT_CLUSTER_PORT
    callsign: str = ""

    @classmethod
    def from_getter(cls, getter: Callable[[str, str], str]) -> "DxClusterConfig":
        try:
            port = int(str(getter("dx_cluster_port", str(DEFAULT_CLUSTER_PORT))).strip())
        except (TypeError, ValueError):
            port = DEFAULT_CLUSTER_PORT
        return cls(
            host=str(getter("dx_cluster_host", DEFAULT_CLUSTER_HOST) or DEFAULT_CLUSTER_HOST).strip(),
            port=port,
            callsign=str(getter("dx_cluster_callsign", "") or "").strip().upper(),
        )

    def settings(self) -> dict[str, str]:
        return {
            "dx_cluster_host": self.host,
            "dx_cluster_port": str(self.port),
            "dx_cluster_callsign": self.callsign.upper(),
        }

    def validate(self) -> None:
        host = self.host.strip()
        if not host or len(host) > 253 or any(ch.isspace() for ch in host):
            raise DxClusterError("Bitte einen gültigen DX-Cluster-Host eintragen.")
        if not 1 <= self.port <= 65535:
            raise DxClusterError("Der DX-Cluster-Port muss zwischen 1 und 65535 liegen.")
        call = self.callsign.strip().upper()
        if not re.fullmatch(r"[A-Z0-9][A-Z0-9/.-]{1,31}", call) or not re.search(r"[A-Z]", call):
            raise DxClusterError("Bitte ein gültiges Login-Rufzeichen für den DX Cluster eintragen.")


@dataclass(frozen=True)
class DxSpot:
    spotter: str
    call: str
    frequency_hz: int
    band: str
    mode: str
    comment: str
    time_utc: str
    spotted_at_utc: datetime
    locator: str = ""

    @property
    def frequency_mhz(self) -> str:
        value = f"{self.frequency_hz / 1_000_000:.6f}".rstrip("0").rstrip(".")
        return value if "." in value else value + ".0"


_SPOT_RE = re.compile(
    r"^\s*DX\s+de\s+(?P<spotter>[^:\s]+)\s*:\s*"
    r"(?P<frequency>\d+(?:[.,]\d+)?)\s+(?P<call>[A-Z0-9/.-]+)(?P<tail>.*)$",
    re.IGNORECASE,
)
_SPOT_TIME_RE = re.compile(r"\b(?P<time>(?:[01]\d|2[0-3])[0-5]\d)Z\b", re.IGNORECASE)


def ssb_sideband_for_frequency(frequency_hz: int) -> str:
    band = band_from_mhz(frequency_hz / 1_000_000) or ""
    return "LSB" if band in {"160m", "80m", "40m"} else "USB"


def infer_spot_mode(comment: str, frequency_hz: int = 0) -> str:
    text = (comment or "").upper()
    patterns = (
        (r"\bFT\s*8\b", "FT8"),
        (r"\bFT\s*4\b", "FT4"),
        (r"\bJS\s*8\b", "JS8"),
        (r"\bPSK\s*31\b", "PSK31"),
        (r"\bRTTY\b", "RTTY"),
        (r"\bMFSK\b", "MFSK"),
        (r"\b(?:D-?STAR|DMR|C4FM|DIGITAL\s*VOICE)\b", "DIGITALVOICE"),
        (r"\b(?:NFM|WFM|FM)\b", "FM"),
        (r"\bAM\b", "AM"),
        (r"\bUSB\b", "USB"),
        (r"\bLSB\b", "LSB"),
        (r"\bCW\b", "CW"),
    )
    for pattern, mode in patterns:
        if re.search(pattern, text):
            return mode
    if re.search(r"\bSSB\b", text):
        return ssb_sideband_for_frequency(frequency_hz)
    # DX-Cluster-Zeilen enthalten häufig keinen Mode. In diesem Fall ist
    # bandabhängiges SSB die sinnvollste CAT-Vorgabe.
    return ssb_sideband_for_frequency(frequency_hz)


def spot_datetime_utc(time_utc: str, now: datetime | None = None) -> datetime:
    now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    if not time_utc:
        return now
    hour = int(time_utc[:2])
    minute = int(time_utc[2:])
    spotted = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    # Cluster lines carry only HHMM. Around midnight, a time noticeably ahead
    # of the current UTC time therefore belongs to the previous day.
    if spotted > now + timedelta(minutes=5):
        spotted -= timedelta(days=1)
    return spotted


def parse_dx_spot(line: str, *, now: datetime | None = None) -> DxSpot | None:
    match = _SPOT_RE.match((line or "").strip())
    if not match:
        return None
    try:
        frequency_khz = float(match.group("frequency").replace(",", "."))
    except ValueError:
        return None
    if not 100.0 <= frequency_khz <= 10_000_000.0:
        return None

    tail = match.group("tail").strip()
    time_match = _SPOT_TIME_RE.search(tail)
    if time_match:
        comment = tail[: time_match.start()].strip()
        trailing = tail[time_match.end() :].strip()
        spot_time = time_match.group("time")
        locator = trailing.split()[0].upper() if trailing else ""
    else:
        comment = tail
        spot_time = ""
        locator = ""

    frequency_hz = int(round(frequency_khz * 1000.0))
    return DxSpot(
        spotter=match.group("spotter").upper(),
        call=match.group("call").upper(),
        frequency_hz=frequency_hz,
        band=band_from_mhz(frequency_hz / 1_000_000) or "",
        mode=infer_spot_mode(comment, frequency_hz),
        comment=comment,
        time_utc=spot_time,
        spotted_at_utc=spot_datetime_utc(spot_time, now),
        locator=locator,
    )


def normalize_worked_mode(mode: str, frequency_hz: int = 0, band: str = "") -> str:
    value = (mode or "").strip().upper()
    aliases = {
        "FMN": "FM", "NFM": "FM", "WFM": "FM", "CWR": "CW", "RTTYR": "RTTY",
        "DATA-U": "USB", "DATA-L": "LSB", "PKTFM": "FM",
    }
    value = aliases.get(value, value)
    if value in {"PKTUSB"}:
        value = "USB"
    elif value in {"PKTLSB"}:
        value = "LSB"
    if value == "SSB":
        if band in {"160m", "80m", "40m"}:
            return "LSB"
        if band:
            return "USB"
        return ssb_sideband_for_frequency(frequency_hz)
    return value


SPOTTER_REGION_OPTIONS = (
    "Alle", "Europa", "Nordamerika", "Südamerika",
    "Asien/Pazifik", "Afrika", "Unbekannt",
)


def spotter_region_for_continent(continent: str) -> str:
    value = (continent or "").strip().upper()
    return {
        "EU": "Europa",
        "NA": "Nordamerika",
        "SA": "Südamerika",
        "AS": "Asien/Pazifik",
        "OC": "Asien/Pazifik",
        "AF": "Afrika",
    }.get(value, "Unbekannt")


def spot_sort_value(
    spot: DxSpot,
    key: str,
    dx_country: str = "",
    spotter_country: str = "",
    comment: str = "",
):
    values = {
        "time": spot.spotted_at_utc,
        "call": spot.call.casefold(),
        "dx_country": dx_country.casefold(),
        "frequency": spot.frequency_hz,
        "band": spot.frequency_hz,
        "mode": spot.mode.casefold(),
        "spotter": spot.spotter.casefold(),
        "spotter_country": spotter_country.casefold(),
        "comment": comment.casefold(),
    }
    return values.get(key, spot.spotted_at_utc)


def worked_flags(
    callsign: str,
    country: str,
    mode: str,
    worked_calls: set[tuple[str, str]],
    worked_countries: set[tuple[str, str]],
) -> tuple[bool, bool]:
    normalized_mode = normalize_worked_mode(mode)
    if not normalized_mode:
        return False, False
    worked_call = ((callsign or "").strip().upper(), normalized_mode) in worked_calls
    worked_country = worked_call or (
        bool(country) and country != "—" and (country, normalized_mode) in worked_countries
    )
    return worked_call, worked_country


class _TelnetFilter:
    IAC = 255
    DONT = 254
    DO = 253
    WONT = 252
    WILL = 251
    SB = 250
    SE = 240

    def __init__(self):
        self.state = "data"
        self.command = 0

    def feed(self, data: bytes) -> tuple[bytes, list[bytes]]:
        clean = bytearray()
        replies: list[bytes] = []
        for byte in data:
            if self.state == "data":
                if byte == self.IAC:
                    self.state = "iac"
                else:
                    clean.append(byte)
            elif self.state == "iac":
                if byte == self.IAC:
                    clean.append(byte)
                    self.state = "data"
                elif byte in {self.WILL, self.WONT, self.DO, self.DONT}:
                    self.command = byte
                    self.state = "option"
                elif byte == self.SB:
                    self.state = "subnegotiation"
                else:
                    self.state = "data"
            elif self.state == "option":
                if self.command == self.WILL:
                    replies.append(bytes((self.IAC, self.DONT, byte)))
                elif self.command == self.DO:
                    replies.append(bytes((self.IAC, self.WONT, byte)))
                self.state = "data"
            elif self.state == "subnegotiation":
                if byte == self.IAC:
                    self.state = "subnegotiation_iac"
            elif self.state == "subnegotiation_iac":
                self.state = "data" if byte == self.SE else "subnegotiation"
        return bytes(clean), replies


class DxClusterClient:
    def __init__(self):
        self._lock = threading.RLock()
        self._generation = 0
        self._thread: threading.Thread | None = None
        self._socket: socket.socket | None = None
        self._stop_event: threading.Event | None = None
        self._connected = False

    @property
    def running(self) -> bool:
        with self._lock:
            return self._thread is not None and self._thread.is_alive()

    @property
    def connected(self) -> bool:
        with self._lock:
            return self._connected

    def start(
        self,
        config: DxClusterConfig,
        on_spot: Callable[[DxSpot], None],
        on_status: Callable[[str], None] | None = None,
        on_error: Callable[[str], None] | None = None,
    ) -> None:
        config.validate()
        self.stop()
        with self._lock:
            self._generation += 1
            generation = self._generation
            stop_event = threading.Event()
            thread = threading.Thread(
                target=self._run,
                args=(generation, stop_event, config, on_spot, on_status, on_error),
                name="dx-cluster-telnet",
                daemon=True,
            )
            self._stop_event = stop_event
            self._thread = thread
            self._connected = False
        thread.start()

    def stop(self) -> None:
        with self._lock:
            self._generation += 1
            stop_event = self._stop_event
            connection = self._socket
            thread = self._thread
            self._stop_event = None
            self._socket = None
            self._connected = False
        if stop_event:
            stop_event.set()
        if connection:
            try:
                connection.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            try:
                connection.close()
            except OSError:
                pass
        if thread and thread is not threading.current_thread():
            thread.join(timeout=2.0)
        with self._lock:
            if self._thread is thread:
                self._thread = None

    def send_spot(self, call: str, frequency_hz: int, comment: str = "") -> None:
        call = (call or "").strip().upper()
        if not re.fullmatch(r"[A-Z0-9][A-Z0-9/.-]{1,31}", call):
            raise DxClusterError("Das zu spottende Rufzeichen ist ungültig.")
        if frequency_hz <= 0:
            raise DxClusterError("Für den DX-Spot wird eine gültige Frequenz benötigt.")
        safe_comment = re.sub(r"[\r\n]+", " ", comment or "").strip()[:80]
        frequency_khz = f"{frequency_hz / 1000.0:.1f}".rstrip("0").rstrip(".")
        command = f"DX {frequency_khz} {call}"
        if safe_comment:
            command += " " + safe_comment
        with self._lock:
            connection = self._socket
            connected = self._connected
            if connection is None or not connected:
                raise DxClusterError("Der DX Cluster ist nicht verbunden.")
            try:
                connection.sendall((command + "\n").encode("utf-8"))
            except OSError as exc:
                raise DxClusterError(f"DX-Spot konnte nicht gesendet werden: {exc}") from exc

    @staticmethod
    def _callback(callback, *args) -> None:
        if callback is None:
            return
        try:
            callback(*args)
        except Exception:
            pass

    def _is_current(self, generation: int, stop_event: threading.Event) -> bool:
        with self._lock:
            return generation == self._generation and self._stop_event is stop_event and not stop_event.is_set()

    def _run(self, generation, stop_event, config, on_spot, on_status, on_error) -> None:
        connection: socket.socket | None = None
        try:
            self._callback(on_status, f"Verbinde mit {config.host}:{config.port} …")
            connection = socket.create_connection((config.host, config.port), timeout=10.0)
            connection.settimeout(0.5)
            if not self._is_current(generation, stop_event):
                return
            with self._lock:
                self._socket = connection
                self._connected = False
            self._callback(on_status, f"Telnet verbunden · Anmeldung als {config.callsign} …")

            telnet_filter = _TelnetFilter()
            text_buffer = ""
            prompt_buffer = ""
            login_sent = False
            connected_at = time.monotonic()
            while self._is_current(generation, stop_event):
                try:
                    data = connection.recv(8192)
                except socket.timeout:
                    data = b""
                    timed_out = True
                else:
                    timed_out = False
                    if not data:
                        raise DxClusterError("Der DX Cluster hat die Telnet-Verbindung geschlossen.")

                if data:
                    clean, replies = telnet_filter.feed(data)
                    for reply in replies:
                        connection.sendall(reply)
                    text = clean.decode("utf-8", errors="replace").replace("\r", "\n")
                    text = re.sub(r"\n+", "\n", text)
                    prompt_buffer = (prompt_buffer + text)[-1024:]
                    text_buffer += text

                prompt_seen = bool(re.search(r"(?:login|call(?:sign)?)\s*[:>]?\s*$", prompt_buffer, re.IGNORECASE))
                if not login_sent and (prompt_seen or time.monotonic() - connected_at >= 2.0):
                    connection.sendall((config.callsign.upper() + "\n").encode("ascii"))
                    login_sent = True
                    prompt_buffer = ""
                    with self._lock:
                        if generation == self._generation:
                            self._connected = True
                    self._callback(on_status, f"DX Cluster aktiv · angemeldet als {config.callsign.upper()}")

                while "\n" in text_buffer:
                    line, text_buffer = text_buffer.split("\n", 1)
                    spot = parse_dx_spot(line)
                    if spot is not None:
                        self._callback(on_spot, spot)

                if timed_out:
                    continue
        except (OSError, DxClusterError) as exc:
            if self._is_current(generation, stop_event):
                self._callback(on_error, str(exc))
        finally:
            if connection:
                try:
                    connection.close()
                except OSError:
                    pass
            with self._lock:
                if generation == self._generation:
                    self._socket = None
                    self._connected = False
                    self._thread = None
                    self._stop_event = None
