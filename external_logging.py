from __future__ import annotations

import ipaddress
import socket
import struct
import threading
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Callable, Iterable

from logger_core import adif_fields_to_qso, parse_adif


WSJTX_MAGIC = 0xADBCCBDA
WSJTX_MAX_SCHEMA = 3
WSJTX_HEARTBEAT = 0
WSJTX_QSO_LOGGED = 5
WSJTX_LOGGED_ADIF = 12


class ExternalLogError(RuntimeError):
    pass


class UnsupportedDatagram(ValueError):
    """Raised for UDP traffic that is neither WSJT-X nor ADIF."""


@dataclass(frozen=True)
class UdpLogConfig:
    bind_host: str = "127.0.0.1"
    port: int = 2237

    @classmethod
    def from_getter(cls, get_setting: Callable[[str, str], str]) -> "UdpLogConfig":
        raw_port = get_setting("udp_log_port", "2237").strip()
        try:
            port = int(raw_port)
        except ValueError as exc:
            raise ExternalLogError("Der UDP-Port muss eine ganze Zahl sein.") from exc
        return cls(
            bind_host=get_setting("udp_log_host", "127.0.0.1").strip() or "127.0.0.1",
            port=port,
        )

    def validate(self) -> None:
        try:
            address = ipaddress.ip_address(self.bind_host)
        except ValueError as exc:
            raise ExternalLogError("Die Bind-Adresse muss eine gültige IPv4-Adresse sein.") from exc
        if address.version != 4:
            raise ExternalLogError("Aktuell werden nur IPv4-Adressen unterstützt.")
        if not 1 <= int(self.port) <= 65535:
            raise ExternalLogError("Der UDP-Port muss zwischen 1 und 65535 liegen.")

    def settings(self) -> dict[str, str]:
        return {"udp_log_host": self.bind_host, "udp_log_port": str(self.port)}


@dataclass(frozen=True)
class DecodedDatagram:
    source: str
    qsos: tuple[dict[str, Any], ...] = ()
    heartbeat_reply: bytes | None = None
    client_id: str = ""
    schema: int = 0


@dataclass(frozen=True)
class UdpLogEvent:
    source: str
    qso: dict[str, Any]
    sender: tuple[str, int]


class _QtReader:
    def __init__(self, data: bytes):
        self.data = data
        self.pos = 0

    def _take(self, size: int) -> bytes:
        if size < 0 or self.pos + size > len(self.data):
            raise ValueError("Unvollständiges WSJT-X-Datagramm")
        value = self.data[self.pos:self.pos + size]
        self.pos += size
        return value

    @property
    def remaining(self) -> int:
        return len(self.data) - self.pos

    def u8(self) -> int:
        return self._take(1)[0]

    def u32(self) -> int:
        return struct.unpack(">I", self._take(4))[0]

    def i32(self) -> int:
        return struct.unpack(">i", self._take(4))[0]

    def u64(self) -> int:
        return struct.unpack(">Q", self._take(8))[0]

    def i64(self) -> int:
        return struct.unpack(">q", self._take(8))[0]

    def byte_array(self) -> bytes:
        size = self.u32()
        if size == 0xFFFFFFFF:
            return b""
        return self._take(size)

    def text(self) -> str:
        return self.byte_array().decode("utf-8", errors="replace")

    def datetime(self) -> datetime | None:
        # QDataStream Qt_5_4 serializes QDateTime as QDate (Julian day),
        # QTime (milliseconds since midnight), TimeSpec and optional detail.
        julian_day = self.i64()
        milliseconds = self.u32()
        time_spec = self.u8()
        offset_seconds = 0
        if time_spec == 2:  # Qt::OffsetFromUTC
            offset_seconds = self.i32()
        elif time_spec == 3:  # Qt::TimeZone
            self.byte_array()  # zone id; WSJT-X normally sends UTC
        if julian_day <= 0 or milliseconds == 0xFFFFFFFF:
            return None
        try:
            day = date.fromordinal(julian_day - 1721425)
            base = datetime(day.year, day.month, day.day) + timedelta(milliseconds=milliseconds)
        except (OverflowError, ValueError):
            return None
        if time_spec == 2:
            return base.replace(tzinfo=timezone(timedelta(seconds=offset_seconds))).astimezone(timezone.utc)
        # WSJT-X QSO timestamps are UTC. Treat an unexpected local/time-zone
        # marker conservatively as the transmitted wall time rather than using
        # the receiving computer's locale and silently shifting the QSO.
        return base.replace(tzinfo=timezone.utc)


def _qt_bytes(value: bytes) -> bytes:
    return struct.pack(">I", len(value)) + value


def _qt_text(value: str) -> bytes:
    return _qt_bytes(value.encode("utf-8"))


def build_heartbeat(client_id: str, schema: int, version: str) -> bytes:
    negotiated = min(max(int(schema), 1), WSJTX_MAX_SCHEMA)
    return b"".join((
        struct.pack(">III", WSJTX_MAGIC, negotiated, WSJTX_HEARTBEAT),
        _qt_text(client_id),
        struct.pack(">I", WSJTX_MAX_SCHEMA),
        _qt_text(version),
        _qt_text(""),
    ))


def _format_frequency_mhz(frequency_hz: int) -> str:
    value = Decimal(frequency_hz) / Decimal(1_000_000)
    return format(value.normalize(), "f")


def _qso_from_wsjt_qso_logged(reader: _QtReader) -> dict[str, Any]:
    off = reader.datetime()
    dx_call = reader.text().strip().upper()
    dx_grid = reader.text().strip().upper()
    frequency_hz = reader.u64()
    mode = reader.text().strip().upper()
    rst_sent = reader.text().strip()
    rst_rcvd = reader.text().strip()
    tx_power = reader.text().strip()
    comments = reader.text().strip()
    name = reader.text().strip()
    # These fields were appended over time. Older WSJT-X-compatible senders
    # can legally stop after Name, so consume every extension only if present.
    on = reader.datetime() if reader.remaining >= 13 else None
    operator = reader.text().strip().upper() if reader.remaining >= 4 else ""
    my_call = reader.text().strip().upper() if reader.remaining >= 4 else ""
    my_grid = reader.text().strip().upper() if reader.remaining >= 4 else ""
    exchange_sent = reader.text().strip() if reader.remaining >= 4 else ""
    exchange_received = reader.text().strip() if reader.remaining >= 4 else ""
    prop_mode = reader.text().strip().upper() if reader.remaining >= 4 else ""
    started = on or off
    if not started:
        raise ValueError("WSJT-X-QSO enthält keine gültige Startzeit")
    qso: dict[str, Any] = {
        "call": dx_call,
        "gridsquare": dx_grid,
        "freq": _format_frequency_mhz(frequency_hz),
        "mode": mode,
        "qso_date": started.strftime("%Y-%m-%d"),
        "time_on": started.strftime("%H%M%S"),
        "rst_sent": rst_sent,
        "rst_rcvd": rst_rcvd,
        "tx_pwr": tx_power,
        "comment": comments,
        "name": name,
        "operator_call": operator,
        "station_call": my_call,
        "my_gridsquare": my_grid,
        "stx_string": exchange_sent,
        "srx_string": exchange_received,
        "prop_mode": prop_mode,
    }
    if off:
        qso["qso_date_off"] = off.strftime("%Y-%m-%d")
        qso["time_off"] = off.strftime("%H%M%S")
    return qso


def _adif_qsos(text: str) -> tuple[dict[str, Any], ...]:
    fields = parse_adif(text)
    if not fields:
        raise ValueError("UDP-Datagramm enthält keinen vollständigen ADIF-Datensatz mit <EOR>.")
    return tuple(adif_fields_to_qso(record) for record in fields)


def decode_udp_datagram(data: bytes, *, app_version: str = "") -> DecodedDatagram:
    if len(data) >= 4 and struct.unpack(">I", data[:4])[0] == WSJTX_MAGIC:
        reader = _QtReader(data)
        reader.u32()  # magic
        schema = reader.u32()
        message_type = reader.u32()
        client_id = reader.text()
        if message_type == WSJTX_HEARTBEAT:
            return DecodedDatagram(
                source="WSJT-X",
                heartbeat_reply=build_heartbeat(client_id, schema, app_version),
                client_id=client_id,
                schema=schema,
            )
        if message_type == WSJTX_LOGGED_ADIF:
            qsos = _adif_qsos(reader.text())
            return DecodedDatagram("WSJT-X ADIF", qsos, client_id=client_id, schema=schema)
        if message_type == WSJTX_QSO_LOGGED:
            qso = _qso_from_wsjt_qso_logged(reader)
            return DecodedDatagram("WSJT-X", (qso,), client_id=client_id, schema=schema)
        return DecodedDatagram("WSJT-X", client_id=client_id, schema=schema)

    # Several loggers broadcast one ordinary ADIF record directly as UTF-8.
    # Decode only packets that look like complete ADIF so unrelated local UDP
    # traffic cannot produce noisy errors in the UI.
    upper = data.upper()
    if b"<EOR" not in upper or b"<CALL:" not in upper:
        raise UnsupportedDatagram("Unbekanntes UDP-Datagramm")
    text = data.decode("utf-8-sig", errors="replace").replace("\x00", "")
    return DecodedDatagram("ADIF-UDP", _adif_qsos(text))


def _identity_frequency(value: Any) -> str:
    raw = str(value or "").strip().replace(",", ".")
    if not raw:
        return ""
    try:
        return format(Decimal(raw).quantize(Decimal("0.000001")).normalize(), "f")
    except InvalidOperation:
        return raw


def qso_identity(qso: dict[str, Any]) -> tuple[str, ...]:
    time_on = "".join(ch for ch in str(qso.get("time_on") or "") if ch.isdigit())
    if len(time_on) == 4:
        time_on += "00"
    return (
        str(qso.get("call") or "").strip().upper(),
        str(qso.get("qso_date") or "").replace("-", "").strip(),
        time_on[:6],
        _identity_frequency(qso.get("freq")),
        str(qso.get("band") or "").strip().lower(),
        str(qso.get("mode") or "").strip().upper(),
        str(qso.get("station_call") or "").strip().upper(),
    )


def find_duplicate_qso(qsos: Iterable[dict[str, Any]], incoming: dict[str, Any]) -> dict[str, Any] | None:
    incoming_id = str(incoming.get("local_id") or "")
    identity = qso_identity(incoming)
    for qso in qsos:
        if incoming_id and str(qso.get("local_id") or "") == incoming_id:
            return qso
        if qso_identity(qso) == identity:
            return qso
    return None


class UdpLogReceiver:
    def __init__(self, *, app_version: str = ""):
        self.app_version = app_version
        self._lock = threading.RLock()
        self._socket: socket.socket | None = None
        self._thread: threading.Thread | None = None
        self._on_qso: Callable[[UdpLogEvent], None] | None = None
        self._on_error: Callable[[str], None] | None = None

    @property
    def running(self) -> bool:
        with self._lock:
            return self._socket is not None

    def start(
        self,
        config: UdpLogConfig,
        on_qso: Callable[[UdpLogEvent], None],
        on_error: Callable[[str], None] | None = None,
    ) -> None:
        config.validate()
        with self._lock:
            if self._socket is not None:
                raise ExternalLogError("UDP-Logging läuft bereits.")
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            try:
                sock.bind((config.bind_host, config.port))
                sock.settimeout(0.25)
            except OSError as exc:
                sock.close()
                if getattr(exc, "winerror", None) == 10048 or exc.errno in (48, 98, 10048):
                    raise ExternalLogError(
                        f"UDP-Port {config.port} ist bereits belegt. Bitte einen anderen Port wählen."
                    ) from exc
                raise ExternalLogError(
                    f"UDP-Listener auf {config.bind_host}:{config.port} konnte nicht gestartet werden: {exc}"
                ) from exc
            self._socket = sock
            self._on_qso = on_qso
            self._on_error = on_error
            self._thread = threading.Thread(target=self._run, args=(sock,), name="udp-log-listener", daemon=True)
            self._thread.start()

    def _run(self, sock: socket.socket) -> None:
        while True:
            with self._lock:
                if self._socket is not sock:
                    return
                on_qso = self._on_qso
                on_error = self._on_error
            try:
                data, sender = sock.recvfrom(65535)
            except socket.timeout:
                continue
            except OSError:
                return
            try:
                decoded = decode_udp_datagram(data, app_version=self.app_version)
                if decoded.heartbeat_reply is not None:
                    sock.sendto(decoded.heartbeat_reply, sender)
                if on_qso:
                    for qso in decoded.qsos:
                        on_qso(UdpLogEvent(decoded.source, qso, sender))
            except UnsupportedDatagram:
                continue
            except Exception as exc:
                if on_error:
                    on_error(str(exc))

    def stop(self) -> None:
        with self._lock:
            sock = self._socket
            thread = self._thread
            self._socket = None
            self._thread = None
            self._on_qso = None
            self._on_error = None
        if sock is not None:
            try:
                sock.close()
            except OSError:
                pass
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout=1.0)
