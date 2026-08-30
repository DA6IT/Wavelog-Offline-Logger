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
DEFAULT_SPOTTER_HOST = "dxcluster.afu-tools.de"
DEFAULT_SPOTTER_PORT = 7301


def select_dx_spot_candidate(current: dict, last_saved: dict | None) -> tuple[dict, bool]:
    """Select the form QSO or the last saved QSO for manual spotting.

    CAT polling may restore the current rig frequency immediately after the
    QSO form was cleared.  A frequency by itself is not a new spot candidate;
    until another callsign is entered the last saved QSO must remain usable.
    The boolean result indicates that the saved QSO was selected.
    """
    current_call = str(current.get("call") or "").strip()
    if not current_call and last_saved:
        return dict(last_saved), True
    return dict(current), False


class DxClusterError(RuntimeError):
    pass


@dataclass(frozen=True)
class DxClusterConfig:
    host: str = DEFAULT_CLUSTER_HOST
    port: int = DEFAULT_CLUSTER_PORT
    callsign: str = ""

    @classmethod
    def from_getter(
        cls, getter: Callable[[str, str], str], callsign: str = "",
    ) -> "DxClusterConfig":
        try:
            port = int(str(getter("dx_cluster_port", str(DEFAULT_CLUSTER_PORT))).strip())
        except (TypeError, ValueError):
            port = DEFAULT_CLUSTER_PORT
        return cls(
            host=str(getter("dx_cluster_host", DEFAULT_CLUSTER_HOST) or DEFAULT_CLUSTER_HOST).strip(),
            port=port,
            callsign=(callsign or "").strip().upper(),
        )

    def settings(self) -> dict[str, str]:
        return {
            "dx_cluster_host": self.host,
            "dx_cluster_port": str(self.port),
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
class DxSpotterConfig:
    host: str = DEFAULT_SPOTTER_HOST
    port: int = DEFAULT_SPOTTER_PORT
    callsign: str = ""

    @classmethod
    def from_getter(
        cls, getter: Callable[[str, str], str], callsign: str = "",
    ) -> "DxSpotterConfig":
        try:
            port = int(str(getter("dx_spotter_port", str(DEFAULT_SPOTTER_PORT))).strip())
        except (TypeError, ValueError):
            port = DEFAULT_SPOTTER_PORT
        return cls(
            host=str(getter("dx_spotter_host", DEFAULT_SPOTTER_HOST) or DEFAULT_SPOTTER_HOST).strip(),
            port=port,
            callsign=(callsign or "").strip().upper(),
        )

    def settings(self) -> dict[str, str]:
        return {
            "dx_spotter_host": self.host,
            "dx_spotter_port": str(self.port),
        }

    def validate(self) -> None:
        DxClusterConfig(self.host, self.port, self.callsign).validate()


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


_COMMENT_MODE_PATTERNS = (
    (r"\bFT[\s-]*8\b", "FT8"),
    (r"\bFT[\s-]*4\b", "FT4"),
    (r"\bJS[\s-]*8(?:CALL)?\b", "JS8"),
    (r"\bPSK[\s-]*31\b", "PSK31"),
    (r"\bRTTY\b", "RTTY"),
    (r"\b(?:MFSK\d*|OLIVIA|JT65|JT9|Q65|WSPR)\b", "MFSK"),
    (r"\b(?:D[\s-]*STAR|DMR|C4FM|FUSION|DIGITAL[\s-]*VOICE|DV)\b", "DIGITALVOICE"),
    (r"\b(?:NFM|WFM|FMN|FM)\b", "FM"),
    (r"\bAM\b", "AM"),
    (r"\bUSB\b", "USB"),
    (r"\bLSB\b", "LSB"),
    (r"\b(?:CW|MORSE)\b", "CW"),
)

# Conventional FT8 dial frequencies. A deliberately small tolerance avoids
# confusing nearby FT4 or other digital activity with FT8.
_FT8_DIAL_FREQUENCIES_HZ = (
    1_840_000, 3_573_000, 5_357_000, 7_074_000, 10_136_000,
    14_074_000, 18_100_000, 21_074_000, 24_915_000, 28_074_000,
    50_313_000, 144_174_000,
)

# High-confidence parts of the IARU Region 1 band plans. All-mode or mixed
# sections are intentionally omitted: there the normal sideband fallback is
# safer than pretending to know an exact mode. Generic digimode sections map
# to MFSK, which the logger uses as its neutral digital/CAT mode.
_REGION1_SPOT_MODE_RANGES_HZ = (
    (1_810_000, 1_838_000, "CW"),
    (1_838_000, 1_843_000, "MFSK"),
    (3_500_000, 3_570_000, "CW"),
    (3_570_000, 3_620_000, "MFSK"),
    (7_000_000, 7_040_000, "CW"),
    (7_040_000, 7_060_000, "MFSK"),
    (10_100_000, 10_130_000, "CW"),
    (10_130_000, 10_150_000, "MFSK"),
    (14_000_000, 14_070_000, "CW"),
    (14_070_000, 14_112_000, "MFSK"),
    (18_068_000, 18_095_000, "CW"),
    (18_095_000, 18_120_000, "MFSK"),
    (21_000_000, 21_070_000, "CW"),
    (21_070_000, 21_149_000, "MFSK"),
    (24_890_000, 24_915_000, "CW"),
    (24_915_000, 24_940_000, "MFSK"),
    (28_000_000, 28_070_000, "CW"),
    (28_070_000, 28_190_000, "MFSK"),
    (28_300_000, 28_320_000, "MFSK"),
    (29_100_000, 29_200_000, "FM"),
    (29_200_000, 29_300_000, "MFSK"),
    (29_520_000, 29_700_001, "FM"),
    (50_000_000, 50_100_000, "CW"),
    (50_300_000, 50_500_000, "MFSK"),
    (50_700_000, 50_900_000, "FM"),
    (51_200_000, 51_400_000, "FM"),
    (70_294_000, 70_500_001, "FM"),
    (144_025_000, 144_100_000, "CW"),
    (144_794_000, 144_975_000, "MFSK"),
    (144_975_000, 145_806_001, "FM"),
    (432_400_000, 432_500_000, "CW"),
    (433_000_000, 433_587_501, "FM"),
    (434_600_000, 434_987_501, "FM"),
)


def bandplan_spot_mode(frequency_hz: int) -> str:
    if frequency_hz <= 0:
        return ""
    if any(abs(frequency_hz - dial_hz) <= 1_000 for dial_hz in _FT8_DIAL_FREQUENCIES_HZ):
        return "FT8"
    for start_hz, end_hz, mode in _REGION1_SPOT_MODE_RANGES_HZ:
        if start_hz <= frequency_hz < end_hz:
            return mode
    return ""


def infer_spot_mode(comment: str, frequency_hz: int = 0) -> str:
    text = (comment or "").upper()
    for pattern, mode in _COMMENT_MODE_PATTERNS:
        if re.search(pattern, text):
            return mode
    if re.search(r"\bSSB\b", text):
        return ssb_sideband_for_frequency(frequency_hz)
    bandplan_mode = bandplan_spot_mode(frequency_hz)
    if bandplan_mode:
        return bandplan_mode
    # In all-mode/mixed segments, band-dependent SSB remains the conservative
    # CAT default instead of claiming an exact digital or voice mode.
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
    band: str,
    mode: str,
    worked_calls: set[tuple[str, str, str]],
    worked_countries: set[tuple[str, str, str]],
) -> tuple[bool, bool]:
    normalized_band = (band or "").strip()
    normalized_mode = normalize_worked_mode(mode, band=normalized_band)
    if not normalized_band or not normalized_mode:
        return False, False
    worked_call = (
        (callsign or "").strip().upper(), normalized_band, normalized_mode,
    ) in worked_calls
    worked_country = worked_call or (
        bool(country)
        and country != "—"
        and (country, normalized_band, normalized_mode) in worked_countries
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


def spot_comment_with_mode(comment: str, mode: str) -> str:
    """Return the DXSpider comment with an explicit mode token."""
    safe_comment = re.sub(r"[\r\n]+", " ", comment or "").strip()
    normalized_mode = (mode or "").strip().upper()
    if normalized_mode and not re.search(
        rf"(?<![A-Z0-9]){re.escape(normalized_mode)}(?![A-Z0-9])",
        safe_comment,
        re.IGNORECASE,
    ):
        safe_comment = f"{normalized_mode} {safe_comment}".strip()
    return safe_comment[:80].rstrip()


class DxClusterClient:
    def __init__(self):
        self._lock = threading.RLock()
        self._generation = 0
        self._thread: threading.Thread | None = None
        self._socket: socket.socket | None = None
        self._stop_event: threading.Event | None = None
        self._connected = False
        self._last_error = ""

    @property
    def running(self) -> bool:
        with self._lock:
            return self._thread is not None and self._thread.is_alive()

    @property
    def connected(self) -> bool:
        with self._lock:
            return self._connected

    def wait_until_connected(self, timeout: float = 12.0) -> None:
        deadline = time.monotonic() + max(0.1, timeout)
        while time.monotonic() < deadline:
            with self._lock:
                if self._connected:
                    return
                thread = self._thread
                last_error = self._last_error
            if thread is None or not thread.is_alive():
                raise DxClusterError(last_error or "Die Telnet-Verbindung konnte nicht hergestellt werden.")
            time.sleep(0.05)
        raise DxClusterError("Zeitüberschreitung beim Verbinden mit dem DX Cluster.")

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
            self._last_error = ""
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

    def send_spot(
        self, call: str, frequency_hz: int, comment: str = "", mode: str = "",
    ) -> None:
        call = (call or "").strip().upper()
        if not re.fullmatch(r"[A-Z0-9][A-Z0-9/.-]{1,31}", call):
            raise DxClusterError("Das zu spottende Rufzeichen ist ungültig.")
        if frequency_hz <= 0:
            raise DxClusterError("Für den DX-Spot wird eine gültige Frequenz benötigt.")
        safe_comment = spot_comment_with_mode(comment, mode)
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
                with self._lock:
                    if generation == self._generation:
                        self._last_error = str(exc)
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
