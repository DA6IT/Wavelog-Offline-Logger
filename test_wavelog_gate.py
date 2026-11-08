"""Tests for the built-in WaveLogGate replacement (wavelog_gate.py)."""
from __future__ import annotations

import base64
import json
import os
import socket
import struct
import threading
import time
import urllib.error
import urllib.request
from unittest import TestCase, main

import wavelog_gate
from wavelog_gate import (
    GateConfig, GateError, RadioState, WavelogGate, encode_ws_frame, parse_origins, url_origin,
    wavelog_qsy_mode, websocket_accept,
)

ORIGIN = "https://log.example.org"


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def wait_for(predicate, timeout=3.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.02)
    return predicate()


class WsTestClient:
    def __init__(self, port: int, origin: str | None = ORIGIN):
        self.sock = socket.create_connection(("127.0.0.1", port), timeout=3)
        key = base64.b64encode(os.urandom(16)).decode()
        lines = [
            "GET / HTTP/1.1", f"Host: 127.0.0.1:{port}", "Upgrade: websocket", "Connection: Upgrade",
            f"Sec-WebSocket-Key: {key}", "Sec-WebSocket-Version: 13",
        ]
        if origin:
            lines.append(f"Origin: {origin}")
        self.sock.sendall(("\r\n".join(lines) + "\r\n\r\n").encode())
        response = b""
        while b"\r\n\r\n" not in response:
            chunk = self.sock.recv(1024)
            if not chunk:
                break
            response += chunk
        self.status_line = response.split(b"\r\n", 1)[0].decode()
        self.accept_ok = f"Sec-WebSocket-Accept: {websocket_accept(key)}".encode() in response
        self.buffer = response.split(b"\r\n\r\n", 1)[1] if b"\r\n\r\n" in response else b""

    def _read(self, n):
        while len(self.buffer) < n:
            chunk = self.sock.recv(4096)
            if not chunk:
                raise ConnectionError("closed")
            self.buffer += chunk
        data, self.buffer = self.buffer[:n], self.buffer[n:]
        return data

    def recv_json(self):
        b1, b2 = self._read(2)
        length = b2 & 0x7F
        if length == 126:
            length = struct.unpack("!H", self._read(2))[0]
        payload = self._read(length)
        return json.loads(payload.decode())

    def send_json(self, obj):
        payload = json.dumps(obj).encode()
        mask = os.urandom(4)
        masked = bytes(b ^ mask[i % 4] for i, b in enumerate(payload))
        header = bytes([0x81, 0x80 | len(payload)]) if len(payload) < 126 else \
            bytes([0x81, 0x80 | 126]) + struct.pack("!H", len(payload))
        self.sock.sendall(header + mask + masked)

    def close(self):
        self.sock.close()


class HelperTests(TestCase):
    def test_origins(self):
        self.assertEqual(url_origin("https://Log.Example.org/index.php/api"), ORIGIN)
        self.assertEqual(url_origin("http://192.168.1.5:8080/x"), "http://192.168.1.5:8080")
        self.assertEqual(url_origin("https://h:443/"), "https://h")
        self.assertEqual(url_origin("ftp://h"), "")
        self.assertEqual(parse_origins("https://a.de, http://b.de:81/x ; junk"), ("https://a.de", "http://b.de:81"))

    def test_qsy_modes(self):
        self.assertEqual(wavelog_qsy_mode("usb", 7_074_000), "USB")  # Wavelog decides the sideband
        self.assertEqual(wavelog_qsy_mode("LSB", 7_150_000), "LSB")
        self.assertEqual(wavelog_qsy_mode("cw", 7_010_000), "CW")
        self.assertEqual(wavelog_qsy_mode("pkt", 14_074_000), "PKTUSB")
        self.assertEqual(wavelog_qsy_mode("pktfm", 145_500_000), "PKTFM")
        self.assertEqual(wavelog_qsy_mode("bogus", 14_000_000), "")

    def test_config_roundtrip_and_validation(self):
        config = GateConfig(radio_push=True, qsy=True, websocket=True, qsy_port=50001, ws_port=50002,
                            allowed_origins=(ORIGIN,))
        store = config.settings("http://lan.local")
        loaded = GateConfig.from_getter(lambda k, d="": store.get(k, d), "https://log.example.org/index.php")
        self.assertEqual(loaded.allowed_origins, (ORIGIN, "http://lan.local"))
        self.assertTrue(loaded.radio_push and loaded.qsy and loaded.websocket)
        with self.assertRaises(GateError):
            GateConfig(qsy=True).validate()  # no Wavelog origin
        with self.assertRaises(GateError):
            GateConfig(qsy=True, websocket=True, qsy_port=50000, ws_port=50000, allowed_origins=(ORIGIN,)).validate()

    def test_frame_encoding_lengths(self):
        self.assertEqual(encode_ws_frame(b"x" * 10)[:2], b"\x81\x0a")
        self.assertEqual(encode_ws_frame(b"x" * 300)[:4], b"\x81\x7e\x01\x2c")


class GateServerTests(TestCase):
    def setUp(self):
        self.qsy_calls = []
        self.bearings = []
        self.pushed = []
        self.push_error = None
        gate_self = self

        class Client:
            def post_radio(self, payload):
                if gate_self.push_error is not None:
                    raise gate_self.push_error
                gate_self.pushed.append(payload)
                return {}

        self.gate = WavelogGate(
            on_qsy=lambda hz, mode: self.qsy_calls.append((hz, mode)),
            on_bearing=lambda az, el: self.bearings.append((az, el)),
            client_factory=lambda: Client(),
        )
        self.addCleanup(self.gate.stop)
        self.qsy_port, self.ws_port = free_port(), free_port()

    def start(self, **overrides):
        values = dict(radio_push=False, qsy=True, websocket=True, qsy_port=self.qsy_port, ws_port=self.ws_port,
                      rotor_follow=True, allowed_origins=(ORIGIN,))
        values.update(overrides)
        self.gate.start(GateConfig(**values))

    def http(self, path, origin=ORIGIN, method="GET"):
        req = urllib.request.Request(f"http://127.0.0.1:{self.qsy_port}{path}", method=method)
        if origin:
            req.add_header("Origin", origin)
        try:
            with urllib.request.urlopen(req, timeout=3) as resp:  # nosec B310 - loopback test server
                return resp.status, dict(resp.headers), resp.read().decode()
        except urllib.error.HTTPError as exc:
            return exc.code, dict(exc.headers), exc.read().decode()

    def test_qsy_from_wavelog_origin(self):
        self.start()
        status, headers, body = self.http("/14074000/pkt")
        self.assertEqual((status, body), (200, "OK"))
        self.assertEqual(headers.get("Access-Control-Allow-Origin"), ORIGIN)
        self.assertEqual(self.qsy_calls, [(14074000, "PKTUSB")])

    def test_qsy_rejects_foreign_or_missing_origin(self):
        self.start()
        self.assertEqual(self.http("/14074000/usb", origin="https://evil.example")[0], 403)
        self.assertEqual(self.http("/14074000/usb", origin=None)[0], 403)
        self.assertEqual(self.http("/abc/usb")[0], 400)
        self.assertEqual(self.qsy_calls, [])

    def test_qsy_preflight_allows_private_network(self):
        self.start()
        status, headers, _ = self.http("/14074000/usb", method="OPTIONS")
        self.assertEqual(status, 204)
        self.assertEqual(headers.get("Access-Control-Allow-Private-Network"), "true")

    def test_qsy_error_is_reported(self):
        self.gate.on_qsy = lambda hz, mode: (_ for _ in ()).throw(GateError("CAT ist nicht gestartet"))
        self.start()
        status, _, body = self.http("/7010000/cw")
        self.assertEqual(status, 500)
        self.assertIn("CAT", body)

    def test_qsy_without_mode_setting(self):
        self.start(qsy_set_mode=False)
        self.http("/7010000/cw")
        self.assertEqual(self.qsy_calls, [(7010000, "")])

    def test_websocket_status_and_rotor_follow(self):
        self.start()
        self.gate.update_radio(RadioState(frequency_hz=14_250_000, mode="USB", power_w=100))
        client = WsTestClient(self.ws_port)
        self.addCleanup(client.close)
        self.assertIn("101", client.status_line)
        self.assertTrue(client.accept_ok)
        self.assertEqual(client.recv_json()["type"], "welcome")
        last = client.recv_json()
        self.assertEqual((last["type"], last["frequency"], last["mode"], last["radio"]),
                         ("radio_status", 14250000, "USB", "Offline Logger"))
        self.gate.update_radio(RadioState(frequency_hz=7_074_000, mode="PKTUSB"))
        self.assertEqual(client.recv_json()["frequency"], 7074000)
        client.send_json({"type": "lookup_result", "payload": {"callsign": "K1ABC", "azimuth": 293}})
        client.send_json({"type": "satellite_position", "data": {"sat_name": "SO-50", "azimuth": 120.5, "elevation": 33}})
        self.assertTrue(wait_for(lambda: len(self.bearings) == 2))
        self.assertEqual(self.bearings, [(293.0, None), (120.5, 33.0)])

    def test_websocket_rejects_foreign_origin(self):
        self.start()
        client = WsTestClient(self.ws_port, origin="https://evil.example")
        self.addCleanup(client.close)
        self.assertIn("403", client.status_line)

    def test_rotor_follow_off_ignores_bearing(self):
        self.start(rotor_follow=False)
        client = WsTestClient(self.ws_port)
        self.addCleanup(client.close)
        client.recv_json()
        client.send_json({"type": "lookup_result", "payload": {"azimuth": 10}})
        time.sleep(0.2)
        self.assertEqual(self.bearings, [])

    def test_radio_push_on_change_only(self):
        self.start(radio_push=True, qsy=False, websocket=False)
        state = RadioState(frequency_hz=14_250_000, mode="USB")
        for _ in range(5):
            self.gate.update_radio(state)
        self.assertTrue(wait_for(lambda: len(self.pushed) == 1))
        time.sleep(0.3)
        self.assertEqual(self.pushed, [{"radio": "Offline Logger", "frequency": 14250000, "mode": "USB"}])
        self.gate.update_radio(RadioState(frequency_hz=7_010_000, mode="CW"))
        self.assertTrue(wait_for(lambda: len(self.pushed) == 2, timeout=4))
        self.assertEqual(self.pushed[-1]["mode"], "CW")
        self.assertTrue(wait_for(lambda: self.gate.status["radio_push"] == "aktiv"))

    def test_radio_push_scope_error_is_visible(self):
        class Denied(Exception):
            status = 403

        self.push_error = Denied("HTTP 403: insufficient_scope: Token is missing the required scope: radio:write")
        self.start(radio_push=True, qsy=False, websocket=False)
        self.gate.update_radio(RadioState(frequency_hz=14_250_000, mode="USB"))
        self.assertTrue(wait_for(lambda: self.gate.status["radio_push"] == "abgelehnt"))
        self.assertIn("radio:write", self.gate.status["push_error"])

    def test_port_in_use_raises_and_stop_releases_ports(self):
        blocker = socket.socket()
        blocker.bind(("127.0.0.1", self.qsy_port))
        blocker.listen(1)
        self.addCleanup(blocker.close)
        with self.assertRaises(GateError):
            self.start()
        self.assertIn("aktiv", self.gate.status["websocket"])
        self.gate.stop()
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", self.ws_port))  # released again


class QsyToRigctldTests(TestCase):
    """End to end: Wavelog QSY request -> gate -> HamlibManager -> rigctld."""

    def test_qsy_reaches_rigctld(self):
        from cat_control import CatConfig, CatError, HamlibManager

        received = []
        server = socket.socket()
        server.bind(("127.0.0.1", 0))
        server.listen(8)
        self.addCleanup(server.close)
        rig_port = server.getsockname()[1]

        def fake_rigctld():
            while True:
                try:
                    conn, _ = server.accept()
                except OSError:
                    return
                with conn:
                    line = conn.makefile("rb").readline().decode().strip()
                    received.append(line)
                    conn.sendall(b"RPRT 0\n")

        threading.Thread(target=fake_rigctld, daemon=True).start()

        class Running:
            def poll(self):
                return None

        manager = HamlibManager.__new__(HamlibManager)
        manager._lock = threading.RLock()
        manager._io_lock = threading.RLock()
        manager._process = Running()
        manager._config = CatConfig(port=rig_port)
        with self.assertRaises(CatError):
            manager.set_frequency_and_raw_mode(7_010_000, "XYZ")

        gate = WavelogGate(on_qsy=manager.set_frequency_and_raw_mode)
        self.addCleanup(gate.stop)
        port = free_port()
        gate.start(GateConfig(qsy=True, qsy_port=port, allowed_origins=(ORIGIN,)))
        req = urllib.request.Request(f"http://127.0.0.1:{port}/7074000/usb", headers={"Origin": ORIGIN})
        with urllib.request.urlopen(req, timeout=3) as resp:  # nosec B310 - loopback test server
            self.assertEqual(resp.status, 200)
        self.assertTrue(wait_for(lambda: len(received) == 2))
        self.assertEqual(received, ["F 7074000", "M USB 0"])


class GateRobustnessTests(TestCase):
    def test_non_reading_client_never_blocks_update_radio(self):
        gate = WavelogGate()
        self.addCleanup(gate.stop)
        port = free_port()
        gate.start(GateConfig(websocket=True, ws_port=port, allowed_origins=(ORIGIN,)))
        client = WsTestClient(port)  # never reads again
        self.addCleanup(client.close)
        client.sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 4096)
        started = time.monotonic()
        for index in range(20000):
            gate._last_broadcast_at = 0.0  # force a broadcast every time
            gate.update_radio(RadioState(frequency_hz=14_000_000 + index, mode="USB"))
        self.assertLess(time.monotonic() - started, 5.0)

    def test_stale_or_cleared_cat_state_stops_heartbeats(self):
        posts = []

        class Client:
            def post_radio(self, payload):
                posts.append(payload["frequency"])

        old = wavelog_gate.RADIO_PUSH_HEARTBEAT
        wavelog_gate.RADIO_PUSH_HEARTBEAT = 0.5
        self.addCleanup(setattr, wavelog_gate, "RADIO_PUSH_HEARTBEAT", old)
        gate = WavelogGate(client_factory=lambda: Client())
        self.addCleanup(gate.stop)
        gate.start(GateConfig(radio_push=True, allowed_origins=(ORIGIN,)))
        gate.update_radio(RadioState(frequency_hz=14_074_000, mode="PKTUSB"))
        self.assertTrue(wait_for(lambda: len(posts) == 1))
        gate.clear_radio()
        time.sleep(2.5)
        self.assertEqual(posts, [14_074_000])

    def test_replay_uses_fresh_timestamp(self):
        gate = WavelogGate()
        self.addCleanup(gate.stop)
        port = free_port()
        gate.start(GateConfig(websocket=True, ws_port=port, allowed_origins=(ORIGIN,)))
        gate.update_radio(RadioState(frequency_hz=7_010_000, mode="CW"))
        time.sleep(1.2)
        client = WsTestClient(port)
        self.addCleanup(client.close)
        client.recv_json()
        replay = client.recv_json()
        self.assertLess(abs(time.time() * 1000 - replay["timestamp"]), 800)

    def test_restart_never_runs_two_push_threads(self):
        gate_holder = {}
        release = threading.Event()

        class SlowClient:
            def post_radio(self, payload):
                release.wait(3)

        gate = WavelogGate(client_factory=lambda: SlowClient())
        self.addCleanup(gate.stop)
        config = GateConfig(radio_push=True, allowed_origins=(ORIGIN,))
        gate.start(config)
        gate.update_radio(RadioState(frequency_hz=14_074_000, mode="USB"))
        time.sleep(0.3)  # first thread is inside post_radio
        started = time.monotonic()
        gate.start(config)  # restart: stop() must not block the UI thread
        self.assertLess(time.monotonic() - started, 1.0)
        release.set()
        time.sleep(0.5)
        alive = [t for t in threading.enumerate() if t.name == "gate-radio-push" and t.is_alive()]
        self.assertEqual(len(alive), 1)


if __name__ == "__main__":
    main()
