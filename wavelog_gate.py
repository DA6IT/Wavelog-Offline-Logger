"""Built-in replacement for WaveLogGate.

The DA6IT.de Wavelog Offline Logger already talks to the radio (Hamlib /
FLRig through rigctld), the rotator (rotctld) and WSJT-X (UDP).  This module
adds the three Wavelog-facing parts WaveLogGate provides, so a separate
gateway is no longer needed:

* **Radio status to Wavelog** – the current frequency/mode is pushed to the
  Wavelog API v2 ``radio`` resource (token scope ``radio:write``).  Wavelog
  shows it in the QSO form, bandmap and DX cluster like any CAT radio.
* **QSY from Wavelog** – a tiny HTTP server on ``127.0.0.1:54321`` answers
  Wavelog's ``GET /{frequency_hz}/{mode}`` requests (click on a DX spot or the
  bandmap) and tunes the radio.
* **Live WebSocket** – ``ws://127.0.0.1:54322`` broadcasts ``radio_status``
  messages in the format Wavelog's ``cat.js`` expects and receives
  ``lookup_result`` / ``satellite_position`` messages (rotor follow).

Security: both local servers bind to the loopback interface only and accept
browser requests exclusively from the configured Wavelog origin(s).  Without
that check any web page could retune the radio or turn the rotator.

The protocol details mirror Wavelog 3.2.5 (``assets/js/cat.js``) and
WaveLogGate 2.2.3 (``internal/qsy``, ``internal/ws``).
"""
from __future__ import annotations

import base64
import hashlib
import json
import queue
import socket
import socketserver
import struct
import threading
import time
import urllib.parse
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Callable, Iterable

DEFAULT_QSY_PORT = 54321
DEFAULT_WS_PORT = 54322
DEFAULT_RADIO_NAME = "Offline Logger"
LOOPBACK = "127.0.0.1"
WS_GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"
MAX_WS_PAYLOAD = 64 * 1024
MAX_WS_CLIENTS = 16
RADIO_PUSH_MIN_INTERVAL = 1.0
RADIO_PUSH_HEARTBEAT = 300.0
# A CAT reading older than this is stale: no heartbeat to Wavelog any more.
RADIO_STALE_AFTER = 60.0
# Re-broadcast radio_status with a fresh timestamp (Wavelog's cat.js treats
# old timestamps as a CAT timeout).
WS_REFRESH_INTERVAL = 30.0
WS_SEND_QUEUE = 32

# Modes Wavelog's cat.js sends for a QSY request (performRadioTuning()).
WAVELOG_QSY_MODES = {
    "lsb": "LSB", "usb": "USB", "cw": "CW", "fm": "FM", "am": "AM", "rtty": "RTTY",
    "pkt": "PKTUSB", "dig": "PKTUSB", "pktusb": "PKTUSB", "pktlsb": "PKTLSB", "pktfm": "PKTFM",
}


class GateError(RuntimeError):
    pass


def url_origin(url: str) -> str:
    """Normalised ``scheme://host[:port]`` of a URL, or "" when invalid."""
    try:
        parts = urllib.parse.urlsplit(str(url or "").strip())
        scheme = (parts.scheme or "").lower()
        host = (parts.hostname or "").lower().rstrip(".")
        port = parts.port
    except ValueError:
        return ""
    if scheme not in {"http", "https"} or not host:
        return ""
    if ":" in host:  # IPv6 literal
        host = f"[{host}]"
    default = 443 if scheme == "https" else 80
    return f"{scheme}://{host}" + (f":{port}" if port and port != default else "")


def parse_origins(values: Iterable[str] | str) -> tuple[str, ...]:
    if isinstance(values, str):
        values = values.replace(";", ",").replace("\n", ",").split(",")
    out: list[str] = []
    for value in values:
        origin = url_origin(value)
        if origin and origin not in out:
            out.append(origin)
    return tuple(out)


def wavelog_qsy_mode(mode: str, frequency_hz: int = 0) -> str:
    """Map a Wavelog QSY mode to a Hamlib mode ("" = leave the mode alone).

    Wavelog already picks the sideband for phone spots (determineRadioMode()
    in radiohelpers.js) and maps data modes to RTTY/PKTUSB, so the mode is
    passed through exactly like WaveLogGate does.
    """
    return WAVELOG_QSY_MODES.get(str(mode or "").strip().lower(), "")


@dataclass(frozen=True)
class GateConfig:
    radio_push: bool = False
    radio_name: str = DEFAULT_RADIO_NAME
    qsy: bool = False
    qsy_port: int = DEFAULT_QSY_PORT
    qsy_set_mode: bool = True
    websocket: bool = False
    ws_port: int = DEFAULT_WS_PORT
    rotor_follow: bool = False
    allowed_origins: tuple[str, ...] = field(default_factory=tuple)

    @classmethod
    def from_getter(cls, getter: Callable[[str, str], str], wavelog_url: str = "") -> "GateConfig":
        def flag(key: str, default: str = "0") -> bool:
            return str(getter(key, default) or default).strip() == "1"

        def port(key: str, default: int) -> int:
            try:
                return int(str(getter(key, str(default)) or default).strip())
            except ValueError:
                return default

        extra = str(getter("gate_allowed_origins", "") or "")
        origins = parse_origins([wavelog_url, *parse_origins(extra)])
        return cls(
            radio_push=flag("gate_radio_push"),
            radio_name=(str(getter("gate_radio_name", DEFAULT_RADIO_NAME) or "").strip() or DEFAULT_RADIO_NAME)[:60],
            qsy=flag("gate_qsy"),
            qsy_port=port("gate_qsy_port", DEFAULT_QSY_PORT),
            qsy_set_mode=flag("gate_qsy_set_mode", "1"),
            websocket=flag("gate_websocket"),
            ws_port=port("gate_ws_port", DEFAULT_WS_PORT),
            rotor_follow=flag("gate_rotor_follow"),
            allowed_origins=origins,
        )

    def settings(self, extra_origins: str = "") -> dict[str, str]:
        return {
            "gate_radio_push": "1" if self.radio_push else "0",
            "gate_radio_name": self.radio_name,
            "gate_qsy": "1" if self.qsy else "0",
            "gate_qsy_port": str(self.qsy_port),
            "gate_qsy_set_mode": "1" if self.qsy_set_mode else "0",
            "gate_websocket": "1" if self.websocket else "0",
            "gate_ws_port": str(self.ws_port),
            "gate_rotor_follow": "1" if self.rotor_follow else "0",
            "gate_allowed_origins": extra_origins,
        }

    @property
    def any_enabled(self) -> bool:
        return self.radio_push or self.qsy or self.websocket

    def validate(self) -> None:
        for label, value in (("QSY", self.qsy_port), ("WebSocket", self.ws_port)):
            if not 1024 <= int(value) <= 65535:
                raise GateError(f"Der {label}-Port muss zwischen 1024 und 65535 liegen")
        if self.qsy and self.websocket and self.qsy_port == self.ws_port:
            raise GateError("QSY- und WebSocket-Port müssen verschieden sein")
        if not self.radio_name.strip():
            raise GateError("Bitte einen Funkgerätenamen für Wavelog eintragen")
        if (self.qsy or self.websocket) and not self.allowed_origins:
            raise GateError(
                "Für QSY und WebSocket wird die Wavelog-Adresse benötigt. "
                "Bitte zuerst die Wavelog-URL in den Einstellungen eintragen."
            )


@dataclass(frozen=True)
class RadioState:
    frequency_hz: int
    mode: str
    power_w: float | None = None
    frequency_rx_hz: int | None = None
    prop_mode: str = ""
    sat_name: str = ""

    def key(self) -> tuple[Any, ...]:
        return (self.frequency_hz, self.mode, self.power_w, self.frequency_rx_hz, self.prop_mode, self.sat_name)

    def api_payload(self, radio_name: str) -> dict[str, Any]:
        payload: dict[str, Any] = {"radio": radio_name, "frequency": int(self.frequency_hz), "mode": self.mode[:10]}
        if self.power_w:
            payload["power"] = round(float(self.power_w), 3)
        if self.frequency_rx_hz:
            payload["frequency_rx"] = int(self.frequency_rx_hz)
        if self.prop_mode:
            payload["prop_mode"] = self.prop_mode[:10]
        if self.sat_name:
            payload["sat_name"] = self.sat_name[:255]
        return payload

    def ws_message(self, radio_name: str) -> dict[str, Any]:
        msg: dict[str, Any] = {
            "type": "radio_status",
            "frequency": int(self.frequency_hz),
            "mode": self.mode,
            "radio": radio_name,
            "timestamp": int(time.time() * 1000),
        }
        if self.power_w:
            msg["power"] = float(self.power_w)
        if self.frequency_rx_hz:
            msg["frequency_rx"] = int(self.frequency_rx_hz)
        if self.prop_mode:
            msg["prop_mode"] = self.prop_mode
        if self.sat_name:
            msg["satname"] = self.sat_name
        return msg


# ---------------------------------------------------------------------------
# QSY HTTP server
# ---------------------------------------------------------------------------
class _QsyHTTPServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = False

    def __init__(self, address, handler, gate: "WavelogGate"):
        super().__init__(address, handler)
        self.gate = gate


class _QsyHandler(BaseHTTPRequestHandler):
    server_version = "DA6IT-OfflineLogger-Gate"
    sys_version = ""

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002  (silence stderr)
        return

    def _origin_ok(self) -> bool:
        origin = self.headers.get("Origin")
        return self.server.gate.origin_allowed(origin)  # type: ignore[attr-defined]

    def _cors(self) -> None:
        origin = self.headers.get("Origin") or ""
        if origin:
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Vary", "Origin")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        # Chrome's Private/Local Network Access preflight for public -> loopback.
        self.send_header("Access-Control-Allow-Private-Network", "true")

    def _reply(self, status: int, text: str) -> None:
        body = text.encode("utf-8")
        self.send_response(status)
        self._cors()
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self) -> None:  # noqa: N802
        if not self._origin_ok():
            self._reply(403, "Origin not allowed")
            return
        self.send_response(204)
        self._cors()
        self.send_header("Access-Control-Max-Age", "600")
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_GET(self) -> None:  # noqa: N802
        if not self._origin_ok():
            self.server.gate.log("QSY abgelehnt: unbekannter Ursprung " + str(self.headers.get("Origin") or "(ohne Origin)"))  # type: ignore[attr-defined]
            self._reply(403, "Origin not allowed")
            return
        parts = [p for p in urllib.parse.urlsplit(self.path).path.split("/") if p]
        if not parts:
            self._reply(200, "DA6IT.de Wavelog Offline Logger QSY")
            return
        try:
            frequency_hz = int(parts[0])
        except ValueError:
            self._reply(400, "Invalid frequency")
            return
        if not 100_000 <= frequency_hz <= 300_000_000_000:
            self._reply(400, "Frequency out of range")
            return
        mode = parts[1] if len(parts) > 1 else ""
        try:
            self.server.gate.handle_qsy(frequency_hz, mode)  # type: ignore[attr-defined]
        except Exception as exc:
            self._reply(500, str(exc)[:200] or "QSY failed")
            return
        self._reply(200, "OK")


# ---------------------------------------------------------------------------
# Minimal RFC 6455 WebSocket server (text frames only)
# ---------------------------------------------------------------------------
def websocket_accept(key: str) -> str:
    digest = hashlib.sha1((key.strip() + WS_GUID).encode("ascii"), usedforsecurity=False).digest()
    return base64.b64encode(digest).decode("ascii")


def encode_ws_frame(payload: bytes, opcode: int = 0x1) -> bytes:
    header = bytearray([0x80 | (opcode & 0x0F)])
    length = len(payload)
    if length < 126:
        header.append(length)
    elif length < 65536:
        header.append(126)
        header += struct.pack("!H", length)
    else:
        header.append(127)
        header += struct.pack("!Q", length)
    return bytes(header) + payload


def _recv_exact(sock: socket.socket, count: int) -> bytes:
    data = bytearray()
    while len(data) < count:
        chunk = sock.recv(count - len(data))
        if not chunk:
            raise ConnectionError("WebSocket closed")
        data += chunk
    return bytes(data)


def read_ws_frame(sock: socket.socket) -> tuple[int, bool, bytes]:
    """Read one client frame; returns (opcode, fin, unmasked payload)."""
    b1, b2 = _recv_exact(sock, 2)
    fin = bool(b1 & 0x80)
    opcode = b1 & 0x0F
    masked = bool(b2 & 0x80)
    length = b2 & 0x7F
    if length == 126:
        length = struct.unpack("!H", _recv_exact(sock, 2))[0]
    elif length == 127:
        length = struct.unpack("!Q", _recv_exact(sock, 8))[0]
    if length > MAX_WS_PAYLOAD:
        raise ConnectionError("WebSocket frame too large")
    if not masked:
        # RFC 6455 5.1: a server MUST close the connection on unmasked client frames.
        raise ConnectionError("Unmasked client frame")
    mask = _recv_exact(sock, 4)
    payload = bytearray(_recv_exact(sock, length))
    for index in range(length):
        payload[index] ^= mask[index % 4]
    return opcode, fin, bytes(payload)


class _WsClient:
    """One browser connection.  Sending never blocks the caller: frames go
    through a bounded queue to a writer thread; a client that stops reading
    is disconnected when the queue is full (same as WaveLogGate)."""

    def __init__(self, sock: socket.socket):
        self.sock = sock
        self.lock = threading.Lock()
        self.alive = True
        self.queue: "queue.Queue[bytes | None]" = queue.Queue(maxsize=WS_SEND_QUEUE)
        self.writer = threading.Thread(target=self._write_loop, name="gate-ws-writer", daemon=True)
        self.writer.start()

    def send_text(self, text: str) -> bool:
        return self._send(encode_ws_frame(text.encode("utf-8"), 0x1))

    def _send(self, frame: bytes) -> bool:
        if not self.alive:
            return False
        try:
            self.queue.put_nowait(frame)
            return True
        except queue.Full:
            self.close()
            return False

    def _write_loop(self) -> None:
        while self.alive:
            frame = self.queue.get()
            if frame is None:
                break
            try:
                # Blocking send in this thread only.  A client that stops
                # reading fills the queue and is then closed by _send(), which
                # also unblocks this sendall() via shutdown().
                with self.lock:
                    self.sock.sendall(frame)
            except OSError:
                self.alive = False
                break
        try:
            self.sock.close()
        except OSError:
            pass

    def close(self) -> None:
        if not self.alive:
            return
        self.alive = False
        try:
            self.queue.put_nowait(None)
        except queue.Full:
            pass
        try:
            self.sock.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        try:
            self.sock.close()
        except OSError:
            pass


class _WsTCPServer(socketserver.ThreadingTCPServer):
    daemon_threads = True
    allow_reuse_address = False

    def __init__(self, address, handler, gate: "WavelogGate"):
        super().__init__(address, handler)
        self.gate = gate


class _WsHandler(socketserver.BaseRequestHandler):
    def handle(self) -> None:
        gate: WavelogGate = self.server.gate  # type: ignore[attr-defined]
        sock: socket.socket = self.request
        sock.settimeout(10)
        try:
            raw = bytearray()
            while b"\r\n\r\n" not in raw:
                chunk = sock.recv(4096)
                if not chunk:
                    return
                raw += chunk
                if len(raw) > 16384:
                    return
            head = raw.split(b"\r\n\r\n", 1)[0].decode("iso-8859-1")
            lines = head.split("\r\n")
            request = lines[0].split(" ")
            headers = {}
            for line in lines[1:]:
                if ":" in line:
                    name, value = line.split(":", 1)
                    headers[name.strip().lower()] = value.strip()
            key = headers.get("sec-websocket-key", "")
            if (len(request) < 2 or request[0] != "GET" or "websocket" not in headers.get("upgrade", "").lower()
                    or not key or headers.get("sec-websocket-version") != "13"):
                sock.sendall(b"HTTP/1.1 400 Bad Request\r\nContent-Length: 0\r\nConnection: close\r\n\r\n")
                return
            if not gate.origin_allowed(headers.get("origin")):
                gate.log("WebSocket abgelehnt: unbekannter Ursprung " + str(headers.get("origin") or "(ohne Origin)"))
                sock.sendall(b"HTTP/1.1 403 Forbidden\r\nContent-Length: 0\r\nConnection: close\r\n\r\n")
                return
            sock.sendall((
                "HTTP/1.1 101 Switching Protocols\r\n"
                "Upgrade: websocket\r\nConnection: Upgrade\r\n"
                f"Sec-WebSocket-Accept: {websocket_accept(key)}\r\n\r\n"
            ).encode("ascii"))
            sock.settimeout(None)
            client = _WsClient(sock)
            if not gate._ws_add(client):
                client._send(encode_ws_frame(struct.pack("!H", 1013), 0x8))
                client.close()
                return
            try:
                self._read_loop(gate, client, sock)
            finally:
                gate._ws_remove(client)
                client.close()
        except (OSError, ConnectionError, ValueError):
            return

    @staticmethod
    def _read_loop(gate: "WavelogGate", client: _WsClient, sock: socket.socket) -> None:
        fragments = bytearray()
        while client.alive:
            opcode, fin, payload = read_ws_frame(sock)
            if opcode == 0x8:  # close
                client._send(encode_ws_frame(payload[:2], 0x8))
                return
            if opcode == 0x9:  # ping
                client._send(encode_ws_frame(payload, 0xA))
                continue
            if opcode == 0xA:  # pong
                continue
            if opcode in (0x1, 0x0):
                fragments += payload
                if len(fragments) > MAX_WS_PAYLOAD:
                    return
                if fin:
                    text = bytes(fragments).decode("utf-8", errors="replace")
                    fragments = bytearray()
                    gate.handle_ws_message(text)
                continue
            # Binary frames are not part of the protocol: ignore.


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------
class WavelogGate:
    """Runs QSY server, WebSocket hub and radio-status upload.

    Callbacks are invoked from worker threads; the Tk feature marshals them.

    ``on_qsy(frequency_hz, hamlib_mode)`` must tune the radio (raise on error).
    ``on_bearing(azimuth, elevation_or_None)`` receives rotor targets.
    ``client_factory()`` returns a ``WavelogClient``-like object with
    ``post_radio(payload)`` or None when Wavelog is not configured.
    """

    def __init__(self, *, on_qsy: Callable[[int, str], None] | None = None,
                 on_bearing: Callable[[float, float | None], None] | None = None,
                 client_factory: Callable[[], Any] | None = None,
                 on_log: Callable[[str], None] | None = None,
                 on_status: Callable[[dict[str, Any]], None] | None = None):
        self.on_qsy = on_qsy
        self.on_bearing = on_bearing
        self.client_factory = client_factory
        self.on_log = on_log
        self.on_status = on_status
        self.config = GateConfig()
        self._lock = threading.RLock()
        self._qsy_server: _QsyHTTPServer | None = None
        self._ws_server: _WsTCPServer | None = None
        self._threads: list[threading.Thread] = []
        self._ws_clients: set[_WsClient] = set()
        self._last_state: RadioState | None = None
        self._last_state_at = 0.0
        self._last_broadcast_at = 0.0
        self._last_ws_message: str | None = None
        self._push_queue: "queue.Queue[RadioState | None]" = queue.Queue()
        self._push_thread: threading.Thread | None = None
        self._push_stop = threading.Event()
        self.status: dict[str, Any] = {
            "qsy": "aus", "websocket": "aus", "radio_push": "aus",
            "ws_clients": 0, "last_qsy": "", "last_push": "", "push_error": "",
        }

    # -- lifecycle -----------------------------------------------------------
    def start(self, config: GateConfig) -> None:
        config.validate()
        self.stop()
        errors: list[str] = []
        with self._lock:
            self.config = config
            if config.qsy:
                try:
                    server = _QsyHTTPServer((LOOPBACK, int(config.qsy_port)), _QsyHandler, self)
                    self._qsy_server = server
                    self._spawn(server.serve_forever, "gate-qsy")
                    self.status["qsy"] = f"aktiv auf http://{LOOPBACK}:{config.qsy_port}"
                except OSError as exc:
                    self.status["qsy"] = f"Port {config.qsy_port} belegt"
                    errors.append(f"QSY-Port {config.qsy_port} ist belegt ({exc.strerror or exc}). "
                                  "Läuft noch WaveLogGate? Bitte beenden.")
            if config.websocket:
                try:
                    server = _WsTCPServer((LOOPBACK, int(config.ws_port)), _WsHandler, self)
                    self._ws_server = server
                    self._spawn(server.serve_forever, "gate-ws")
                    self.status["websocket"] = f"aktiv auf ws://{LOOPBACK}:{config.ws_port}"
                except OSError as exc:
                    self.status["websocket"] = f"Port {config.ws_port} belegt"
                    errors.append(f"WebSocket-Port {config.ws_port} ist belegt ({exc.strerror or exc}). "
                                  "Läuft noch WaveLogGate? Bitte beenden.")
            if config.radio_push:
                # Fresh stop event and queue per run: a previous push thread
                # still waiting for an HTTP timeout can never read this run's queue.
                stop_event = threading.Event()
                push_queue: "queue.Queue[RadioState | None]" = queue.Queue()
                self._push_stop = stop_event
                self._push_queue = push_queue
                self._push_thread = self._spawn(lambda: self._push_loop(stop_event, push_queue), "gate-radio-push")
                self.status["radio_push"] = "wartet auf CAT-Daten"
                self.status["push_error"] = ""
        self._emit_status()
        if errors:
            raise GateError("\n".join(errors))

    def stop(self) -> None:
        with self._lock:
            qsy, ws = self._qsy_server, self._ws_server
            self._qsy_server = self._ws_server = None
            clients = list(self._ws_clients)
            self._ws_clients.clear()
            push_thread = self._push_thread
            self._push_thread = None
            self._push_stop.set()
            self._push_queue.put(None)
        for server in (qsy, ws):
            if server is not None:
                try:
                    server.shutdown()
                    server.server_close()
                except OSError:
                    pass
        for client in clients:
            client.close()
        if push_thread is not None and push_thread is not threading.current_thread():
            # Short wait only: stop() runs in the Tk thread.  A thread stuck
            # in an HTTP request ends on its own (its stop event is set).
            push_thread.join(timeout=0.2)
        self._threads = [t for t in self._threads if t.is_alive()]
        self.status.update({"qsy": "aus", "websocket": "aus", "radio_push": "aus", "ws_clients": 0})
        self._last_state = None
        self._emit_status()

    @property
    def running(self) -> bool:
        return bool(self._qsy_server or self._ws_server or self._push_thread)

    def _spawn(self, target: Callable[[], None], name: str) -> threading.Thread:
        thread = threading.Thread(target=target, name=name, daemon=True)
        thread.start()
        self._threads.append(thread)
        return thread

    # -- helpers ---------------------------------------------------------------
    def log(self, message: str) -> None:
        if self.on_log is not None:
            try:
                self.on_log(message)
            except Exception:
                pass

    def _emit_status(self) -> None:
        if self.on_status is not None:
            try:
                self.on_status(dict(self.status))
            except Exception:
                pass

    def origin_allowed(self, origin: str | None) -> bool:
        if not origin:
            # Browsers always send Origin on cross-origin fetch()/WebSocket.
            # Requests without it (e.g. <img src=...>) are rejected on purpose.
            return False
        return url_origin(origin) in self.config.allowed_origins

    # -- QSY -------------------------------------------------------------------
    def handle_qsy(self, frequency_hz: int, mode: str) -> None:
        if self.on_qsy is None:
            raise GateError("CAT ist nicht verfügbar")
        hamlib_mode = wavelog_qsy_mode(mode, frequency_hz) if self.config.qsy_set_mode else ""
        self.on_qsy(int(frequency_hz), hamlib_mode)
        self.status["last_qsy"] = f"{frequency_hz / 1_000_000:.4f} MHz {hamlib_mode}".strip()
        self._emit_status()

    # -- WebSocket -------------------------------------------------------------
    def _ws_add(self, client: _WsClient) -> bool:
        with self._lock:
            if len(self._ws_clients) >= MAX_WS_CLIENTS:
                return False
            self._ws_clients.add(client)
            self.status["ws_clients"] = len(self._ws_clients)
            state = self._last_state if time.monotonic() - self._last_state_at < RADIO_STALE_AFTER else None
            name = self.config.radio_name
        client.send_text(json.dumps({"type": "welcome", "message": "Connected to DA6IT.de Wavelog Offline Logger"}))
        if state is not None:
            # Fresh timestamp: an old one makes cat.js report a CAT timeout.
            client.send_text(json.dumps(state.ws_message(name), ensure_ascii=False, separators=(",", ":")))
        self._emit_status()
        return True

    def _ws_remove(self, client: _WsClient) -> None:
        with self._lock:
            self._ws_clients.discard(client)
            self.status["ws_clients"] = len(self._ws_clients)
        self._emit_status()

    def broadcast(self, message: dict[str, Any]) -> int:
        text = json.dumps(message, ensure_ascii=False, separators=(",", ":"))
        with self._lock:
            if message.get("type") == "radio_status":
                self._last_ws_message = text
            clients = list(self._ws_clients)
        sent = 0
        for client in clients:
            if client.send_text(text):
                sent += 1
            else:
                self._ws_remove(client)
        return sent

    def handle_ws_message(self, text: str) -> None:
        try:
            message = json.loads(text)
        except ValueError:
            return
        if not isinstance(message, dict):
            return
        kind = message.get("type")
        if kind == "lookup_result" and self.config.rotor_follow:
            payload = message.get("payload") or {}
            azimuth = _number(payload.get("azimuth"))
            if azimuth is not None and 0 <= azimuth <= 360 and self.on_bearing is not None:
                self.on_bearing(azimuth, None)
        elif kind == "satellite_position" and self.config.rotor_follow:
            data = message.get("data") or {}
            azimuth, elevation = _number(data.get("azimuth")), _number(data.get("elevation"))
            if (azimuth is not None and elevation is not None and 0 <= azimuth <= 360
                    and 0 <= elevation <= 90 and self.on_bearing is not None):
                self.on_bearing(azimuth, elevation)
        elif kind == "qso_logged":
            data = message.get("data") or {}
            call = str(data.get("callsign") or data.get("call") or "").upper()[:20]
            self.log("Wavelog meldet geloggtes QSO" + (f": {call}" if call else ""))

    # -- radio status ------------------------------------------------------------
    def update_radio(self, state: RadioState) -> None:
        """Called after every CAT poll; cheap when nothing changed."""
        if state.frequency_hz <= 0:
            return
        now = time.monotonic()
        with self._lock:
            changed = self._last_state is None or self._last_state.key() != state.key()
            self._last_state = state
            self._last_state_at = now
            refresh = now - self._last_broadcast_at >= WS_REFRESH_INTERVAL
            if config_ws := self.config.websocket:
                if changed or refresh:
                    self._last_broadcast_at = now
            config = self.config
            push_queue = self._push_queue if self._push_thread is not None else None
        if config_ws and (changed or refresh):
            self.broadcast(state.ws_message(config.radio_name))
        if config.radio_push and push_queue is not None:
            push_queue.put(state)

    def clear_radio(self) -> None:
        """CAT stopped or failing: forget the state, no heartbeats any more."""
        with self._lock:
            self._last_state = None
            self._last_state_at = 0.0
            self._last_ws_message = None
            push_queue = self._push_queue if self._push_thread is not None else None
        if push_queue is not None:
            while True:
                try:
                    push_queue.get_nowait()
                except queue.Empty:
                    break

    def _push_loop(self, stop_event: threading.Event, push_queue: "queue.Queue[RadioState | None]") -> None:
        last_sent_key: tuple[Any, ...] | None = None
        last_sent_at = 0.0
        pending: RadioState | None = None
        backoff_until = 0.0
        while not stop_event.is_set():
            timeout = 1.0 if pending is not None else 5.0
            try:
                item = push_queue.get(timeout=timeout)
                if item is None:
                    break
                pending = item
                # Coalesce bursts: only the newest state matters.
                while True:
                    try:
                        newer = push_queue.get_nowait()
                    except queue.Empty:
                        break
                    if newer is None:
                        return
                    pending = newer
            except queue.Empty:
                pass
            if stop_event.is_set():
                break
            now = time.monotonic()
            if pending is None:
                continue
            with self._lock:
                fresh = self._last_state is not None and now - self._last_state_at < RADIO_STALE_AFTER
            if not fresh:
                # CAT stopped/failing: never keep a stale radio "alive" in Wavelog.
                pending = None
                continue
            due_change = pending.key() != last_sent_key
            due_heartbeat = now - last_sent_at >= RADIO_PUSH_HEARTBEAT
            if not (due_change or due_heartbeat):
                continue
            if now < backoff_until or now - last_sent_at < RADIO_PUSH_MIN_INTERVAL:
                continue
            client = self.client_factory() if self.client_factory else None
            if client is None:
                self.status["radio_push"] = "Wavelog nicht eingerichtet"
                backoff_until = now + 30
                self._emit_status()
                continue
            try:
                client.post_radio(pending.api_payload(self.config.radio_name))
                if stop_event.is_set():
                    break
            except Exception as exc:  # network errors, 401/403 ...
                message = str(exc)
                status = getattr(exc, "status", None)
                if status in (401, 403):
                    self.status["radio_push"] = "abgelehnt"
                    self.status["push_error"] = (
                        message + " · Das API-v2-Token braucht die Berechtigung radio:write."
                        if "scope" in message.lower() or status == 403 else message
                    )
                    backoff_until = now + 300
                else:
                    self.status["radio_push"] = "Wavelog nicht erreichbar"
                    self.status["push_error"] = message
                    backoff_until = now + 30
                self._emit_status()
                continue
            last_sent_key = pending.key()
            last_sent_at = now
            self.status["radio_push"] = "aktiv"
            self.status["push_error"] = ""
            self.status["last_push"] = time.strftime("%H:%M:%S")
            self._emit_status()


def _number(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number != number:  # NaN
        return None
    return number
