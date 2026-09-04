from __future__ import annotations

import os
import http.client
import ipaddress
import re
import shutil
import socket
import subprocess
import sys
import threading
import time
import xmlrpc.client
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Callable


HAMLIB_VERSION = "4.7.2"
FLRIG_MODEL_ID = 4
FTX1_MODEL_ID = 1051
DEFAULT_FLRIG_ENDPOINT = "127.0.0.1:12345"
FLRIG_DISCOVERY_PORTS = tuple(range(12345, 12356))
CAT_BAUD_RATES = (300, 1200, 2400, 4800, 9600, 19200, 38400, 57600, 115200)
CAT_DATA_BITS = (7, 8)
CAT_STOP_BITS = (1, 2)
CAT_PARITIES = ("None", "Odd", "Even", "Mark", "Space")
CAT_HANDSHAKES = ("None", "XONXOFF", "Hardware")
CAT_LINE_STATES = ("Unset", "ON", "OFF")


class CatError(RuntimeError):
    pass


class _RigctldResponseTimeout(CatError):
    """The command was delivered locally, but rigctld produced no reply."""


@dataclass(frozen=True)
class RigModel:
    model_id: int
    manufacturer: str
    model: str
    version: str = ""
    status: str = ""

    @property
    def label(self) -> str:
        maker = self.manufacturer.strip()
        name = self.model.strip()
        prefix = f"{maker} · " if maker else ""
        return f"{prefix}{name} [ID {self.model_id}]"


@dataclass(frozen=True)
class CatConfig:
    enabled: bool = False
    model_id: int = 0
    device: str = ""
    baud: int = 9600
    data_bits: int = 8
    stop_bits: int = 1
    parity: str = "None"
    handshake: str = "None"
    dtr_state: str = "Unset"
    rts_state: str = "Unset"
    port: int = 4532
    poll_interval_ms: int = 1000

    @classmethod
    def from_getter(cls, getter: Callable[[str, str], str]) -> "CatConfig":
        def integer(key: str, default: int) -> int:
            try:
                return int(str(getter(key, str(default))).strip())
            except (TypeError, ValueError):
                return default

        enabled = str(getter("cat_enabled", "0")).strip().lower() in {"1", "true", "yes", "on"}
        model_id = integer("cat_model_id", 0)
        device = (
            str(getter("cat_flrig_endpoint", DEFAULT_FLRIG_ENDPOINT) or DEFAULT_FLRIG_ENDPOINT).strip()
            if model_id == FLRIG_MODEL_ID else
            str(getter("cat_device", "")).strip()
        )
        return cls(
            enabled=enabled,
            model_id=model_id,
            device=device,
            baud=integer("cat_baud", 9600),
            data_bits=integer("cat_data_bits", 8),
            stop_bits=integer("cat_stop_bits", 1),
            parity=str(getter("cat_parity", "None") or "None"),
            handshake=str(getter("cat_handshake", "None") or "None"),
            dtr_state=str(getter("cat_dtr_state", "Unset") or "Unset"),
            rts_state=str(getter("cat_rts_state", "Unset") or "Unset"),
            port=integer("cat_port", 4532),
            poll_interval_ms=integer("cat_poll_interval_ms", 1000),
        )

    def settings(self) -> dict[str, str]:
        settings = {
            "cat_enabled": "1" if self.enabled else "0",
            "cat_model_id": str(self.model_id),
            "cat_baud": str(self.baud),
            "cat_data_bits": str(self.data_bits),
            "cat_stop_bits": str(self.stop_bits),
            "cat_parity": self.parity,
            "cat_handshake": self.handshake,
            "cat_dtr_state": self.dtr_state,
            "cat_rts_state": self.rts_state,
            "cat_port": str(self.port),
            "cat_poll_interval_ms": str(self.poll_interval_ms),
        }
        settings["cat_flrig_endpoint" if self.model_id == FLRIG_MODEL_ID else "cat_device"] = self.device
        return settings

    def validate(self) -> None:
        if self.model_id <= 0:
            raise CatError("Bitte ein Funkgerät aus der Hamlib-Liste auswählen")
        if not self.device and self.model_id not in {1, 6}:
            raise CatError("Bitte eine CAT-/COM-Schnittstelle auswählen")
        if self.model_id == FLRIG_MODEL_ID:
            parse_network_endpoint(self.device)
        if not 300 <= self.baud <= 115200:
            raise CatError("Die CAT-Baudrate muss zwischen 300 und 115200 liegen")
        if self.data_bits not in CAT_DATA_BITS:
            raise CatError("Datenbits müssen 7 oder 8 sein")
        if self.stop_bits not in CAT_STOP_BITS:
            raise CatError("Stoppbits müssen 1 oder 2 sein")
        if self.parity not in CAT_PARITIES:
            raise CatError("Ungültige Parität")
        if self.handshake not in CAT_HANDSHAKES:
            raise CatError("Ungültige Flusssteuerung")
        if self.dtr_state not in CAT_LINE_STATES or self.rts_state not in CAT_LINE_STATES:
            raise CatError("Ungültiger DTR-/RTS-Zustand")
        if not 1 <= self.port <= 65535:
            raise CatError("Der lokale rigctld-Port muss zwischen 1 und 65535 liegen")
        if not 250 <= self.poll_interval_ms <= 5000:
            raise CatError("Das CAT-Abfrageintervall muss zwischen 250 und 5000 ms liegen")


@dataclass(frozen=True)
class CatReading:
    frequency_hz: int
    raw_mode: str
    logger_mode: str


def parse_network_endpoint(endpoint: str) -> tuple[str, int]:
    """Validate and split a Hamlib network device in host:port form."""
    value = str(endpoint or "").strip()
    match = re.fullmatch(r"\[([^\]]+)\]:(\d+)", value)
    if match:
        host, port_text = match.group(1), match.group(2)
    else:
        host, separator, port_text = value.rpartition(":")
        if not separator or ":" in host:
            raise CatError("Bitte die FLRig-Adresse als IP/Hostname:Port eingeben")
    host = host.strip()
    if (
        not host or len(host) > 253 or any(ch.isspace() for ch in host)
        or any(ch in host for ch in "/\\?#@")
    ):
        raise CatError("Bitte eine gültige FLRig-IP oder einen Hostnamen eingeben")
    try:
        port = int(port_text)
    except ValueError as exc:
        raise CatError("Bitte einen gültigen FLRig-Port eingeben") from exc
    if not 1 <= port <= 65535:
        raise CatError("Der FLRig-Port muss zwischen 1 und 65535 liegen")
    return host, port


def probe_flrig(endpoint: str, timeout: float = 0.35) -> str | None:
    """Return the FLRig version only when its XML-RPC service answers."""
    host, port = parse_network_endpoint(endpoint)
    body = xmlrpc.client.dumps((), methodname="main.get_version").encode("utf-8")
    connection = http.client.HTTPConnection(host, port, timeout=max(0.05, float(timeout)))
    try:
        connection.request(
            "POST", "/RPC2", body=body,
            headers={"Content-Type": "text/xml", "User-Agent": "Wavelog-Offline-Logger"},
        )
        response = connection.getresponse()
        if response.status != 200:
            return None
        values, _method = xmlrpc.client.loads(response.read(65536))
        version = str(values[0] if values else "").strip()
        return version or "FLRig"
    except (OSError, http.client.HTTPException, ValueError, xmlrpc.client.Error):
        return None
    finally:
        connection.close()


def local_ipv4_addresses() -> list[str]:
    """Return usable local IPv4 addresses without external network traffic."""
    addresses: set[str] = set()
    try:
        for item in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET, socket.SOCK_STREAM):
            address = str(item[4][0])
            parsed = ipaddress.ip_address(address)
            if not parsed.is_loopback and not parsed.is_link_local:
                addresses.add(address)
    except (OSError, ValueError):
        pass
    return sorted(addresses)


def flrig_discovery_targets(
    current_endpoint: str = "", local_addresses: list[str] | None = None,
) -> list[str]:
    """Build a bounded list of local FLRig XML-RPC candidates."""
    targets: list[str] = []

    def add(endpoint: str) -> None:
        if endpoint and endpoint not in targets:
            targets.append(endpoint)

    current_port = 12345
    if current_endpoint:
        try:
            current_host, current_port = parse_network_endpoint(current_endpoint)
            formatted_host = f"[{current_host}]" if ":" in current_host else current_host
            add(f"{formatted_host}:{current_port}")
        except CatError:
            pass
    for port in FLRIG_DISCOVERY_PORTS:
        add(f"127.0.0.1:{port}")

    addresses = local_ipv4_addresses() if local_addresses is None else list(local_addresses)
    scan_ports = sorted({12345, current_port})
    networks: list[ipaddress.IPv4Network] = []
    for value in addresses:
        try:
            address = ipaddress.ip_address(value)
            if not isinstance(address, ipaddress.IPv4Address) or not address.is_private:
                continue
            network = ipaddress.ip_network(f"{address}/24", strict=False)
            if network not in networks:
                networks.append(network)
        except ValueError:
            continue
        if len(networks) >= 4:
            break
    for network in networks:
        for address in network.hosts():
            for port in scan_ports:
                add(f"{address}:{port}")
    return targets


def discover_flrig(
    current_endpoint: str = "", *, timeout: float = 0.25,
    local_addresses: list[str] | None = None,
    probe: Callable[[str, float], str | None] = probe_flrig,
) -> list[tuple[str, str]]:
    """Find FLRig servers on loopback and bounded private /24 networks."""
    targets = flrig_discovery_targets(current_endpoint, local_addresses)
    found: list[tuple[str, str]] = []
    if not targets:
        return found
    with ThreadPoolExecutor(max_workers=min(48, len(targets))) as executor:
        futures = {executor.submit(probe, endpoint, timeout): endpoint for endpoint in targets}
        for future in as_completed(futures):
            try:
                version = future.result()
            except Exception:
                version = None
            if version:
                found.append((futures[future], str(version)))
    order = {endpoint: index for index, endpoint in enumerate(targets)}
    return sorted(found, key=lambda item: order.get(item[0], len(order)))


def _windows_creation_flags() -> int:
    if sys.platform != "win32":
        return 0
    return int(getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000))


def find_hamlib_dir() -> Path:
    override = os.environ.get("WAVELOG_HAMLIB_DIR", "").strip()
    candidates = []
    if override:
        candidates.append(Path(override))
    here = Path(__file__).resolve().parent
    bundle_root = Path(getattr(sys, "_MEIPASS", here))
    if sys.platform == "win32":
        local_app_data = Path(os.environ.get("LOCALAPPDATA", Path.home()))
        candidates.append(
            local_app_data / "AFU-Tools" / "WavelogOfflineLogger"
            / "hamlib-runtime" / "windows-x64" / "current"
        )
    candidates.extend(
        [
            bundle_root / "hamlib",
            here / "hamlib",
            here / "build" / "embedded" / "hamlib" / "windows-x64",
        ]
    )
    executable = "rigctld.exe" if sys.platform == "win32" else "rigctld"
    for candidate in candidates:
        if (candidate / executable).is_file():
            return candidate
    system_rigctld = shutil.which(executable)
    if system_rigctld:
        return Path(system_rigctld).resolve().parent
    raise CatError(
        "Die gebündelte Hamlib-Laufzeit wurde nicht gefunden. "
        "Bitte das passende Windows-, macOS- oder Linux-Release-Paket verwenden."
    )


def find_rigctld() -> Path:
    executable = "rigctld.exe" if sys.platform == "win32" else "rigctld"
    return find_hamlib_dir() / executable


_MODEL_RE = re.compile(
    r"^\s*(?P<id>\d+)\s{2,}(?P<mfg>.*?)\s{2,}(?P<model>.*?)\s{2,}"
    r"(?P<version>\S+)\s{2,}(?P<status>\S+)\s{2,}\S+\s*$"
)


def parse_rigctld_models(output: str) -> list[RigModel]:
    models: list[RigModel] = []
    for raw_line in output.splitlines():
        match = _MODEL_RE.match(raw_line.rstrip())
        if not match:
            continue
        models.append(
            RigModel(
                model_id=int(match.group("id")),
                manufacturer=match.group("mfg").strip(),
                model=match.group("model").strip(),
                version=match.group("version").strip(),
                status=match.group("status").strip(),
            )
        )
    return models


def list_rig_models(rigctld: Path | None = None) -> list[RigModel]:
    executable = Path(rigctld) if rigctld else find_rigctld()
    try:
        result = subprocess.run(
            [str(executable), "--list"],
            cwd=str(executable.parent),
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=15,
            creationflags=_windows_creation_flags(),
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise CatError(f"Hamlib-Modellliste konnte nicht geladen werden: {exc}") from exc
    models = parse_rigctld_models(result.stdout)
    if not models:
        detail = (result.stderr or result.stdout or f"Exit-Code {result.returncode}").strip()
        raise CatError(f"Hamlib hat keine Funkgerätemodelle geliefert: {detail}")
    return models


def hamlib_version(rigctld: Path | None = None) -> str:
    executable = Path(rigctld) if rigctld else find_rigctld()
    try:
        result = subprocess.run(
            [str(executable), "--version"],
            cwd=str(executable.parent),
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=10,
            creationflags=_windows_creation_flags(),
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise CatError(f"Hamlib-Version konnte nicht gelesen werden: {exc}") from exc
    line = (result.stdout or result.stderr).strip().splitlines()
    if not line:
        raise CatError("Hamlib hat keine Versionsinformation geliefert")
    return line[0]


def list_serial_ports() -> list[str]:
    if sys.platform == "win32":
        try:
            import winreg

            ports: list[str] = []
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"HARDWARE\DEVICEMAP\SERIALCOMM") as key:
                index = 0
                while True:
                    try:
                        _name, value, _kind = winreg.EnumValue(key, index)
                    except OSError:
                        break
                    if str(value).upper().startswith("COM"):
                        ports.append(str(value).upper())
                    index += 1
            return sorted(set(ports), key=_natural_port_key)
        except OSError:
            return []

    import glob

    ports = glob.glob("/dev/ttyUSB*") + glob.glob("/dev/ttyACM*") + glob.glob("/dev/cu.*")
    return sorted(set(ports))


def _natural_port_key(value: str) -> tuple[str, int]:
    match = re.match(r"^(.*?)(\d+)$", value)
    return (match.group(1), int(match.group(2))) if match else (value, 0)


def build_rigctld_args(config: CatConfig) -> list[str]:
    config.validate()
    args = ["-m", str(config.model_id)]
    if config.model_id in {1, 6}:
        return [*args, "-T", "127.0.0.1", "-t", str(config.port)]
    if config.model_id == FLRIG_MODEL_ID:
        return [*args, "-r", config.device, "-T", "127.0.0.1", "-t", str(config.port)]

    serial_settings = [
        f"data_bits={config.data_bits}",
        f"stop_bits={config.stop_bits}",
        f"serial_parity={config.parity}",
        f"serial_handshake={config.handshake}",
    ]
    if config.dtr_state != "Unset":
        serial_settings.append(f"dtr_state={config.dtr_state}")
    if config.rts_state != "Unset":
        serial_settings.append(f"rts_state={config.rts_state}")
    return [
        *args,
        "-r",
        config.device,
        "-s",
        str(config.baud),
        "-T",
        "127.0.0.1",
        "-t",
        str(config.port),
        "-C",
        ",".join(serial_settings),
    ]


def map_hamlib_mode(raw_mode: str, current_mode: str = "") -> str:
    raw = (raw_mode or "").strip().upper()
    current = (current_mode or "").strip().upper()
    digital_modes = {"FT8", "FT4", "JS8", "PSK31", "MFSK", "RTTY"}

    if raw in {"USB", "LSB"}:
        return current if current in digital_modes else raw
    if raw in {"PKTUSB", "PKTLSB", "PKTFM", "DATA", "DATA-U", "DATA-L"}:
        if current in digital_modes:
            return current
        return "FM" if raw == "PKTFM" else ("LSB" if raw in {"PKTLSB", "DATA-L"} else "USB")
    if raw in {"CW", "CWR"}:
        return "CW"
    if raw in {"RTTY", "RTTYR"}:
        return "RTTY"
    # Some Hamlib backends report narrow FM as FMN (for example the
    # Yaesu FTX-1), while others use NFM. Both are normal FM for ADIF.
    if raw in {"FM", "FMN", "NFM", "WFM"}:
        return "FM"
    if raw in {"AM", "SAM", "SAL", "SAH", "AMS"}:
        return "AM"
    if raw in {"DV", "DIGITALVOICE"}:
        return "DIGITALVOICE"
    return raw if raw else current


def hamlib_mode_for_logger(logger_mode: str, frequency_hz: int = 0) -> str:
    mode = (logger_mode or "").strip().upper()
    if mode == "SSB":
        mhz = frequency_hz / 1_000_000
        mode = "LSB" if (1.8 <= mhz <= 2.0 or 3.5 <= mhz <= 4.0 or 7.0 <= mhz <= 7.3) else "USB"
    if mode in {"FT8", "FT4", "JS8", "PSK31", "MFSK"}:
        return "PKTUSB"
    return {
        "USB": "USB", "LSB": "LSB", "CW": "CW", "FM": "FM", "AM": "AM",
        "RTTY": "RTTY", "DIGITALVOICE": "DV",
    }.get(mode, "")


def format_frequency_mhz(frequency_hz: int) -> str:
    if frequency_hz <= 0:
        return ""
    value = f"{frequency_hz / 1_000_000:.6f}".rstrip("0").rstrip(".")
    return value if "." in value else value + ".0"


def _rigctld_command(host: str, port: int, command: str, expected_lines: int) -> list[str]:
    try:
        with socket.create_connection((host, port), timeout=2.0) as connection:
            connection.settimeout(2.0)
            with connection.makefile("rwb", buffering=0) as stream:
                stream.write((command.rstrip("\n") + "\n").encode("ascii"))
                lines = []
                for _ in range(expected_lines):
                    raw = stream.readline(4096)
                    if not raw:
                        raise CatError("rigctld hat die Verbindung unerwartet geschlossen")
                    line = raw.decode("utf-8", errors="replace").strip()
                    if line.startswith("RPRT "):
                        raise CatError(f"rigctld meldet Fehler {line[5:]}")
                    lines.append(line)
                return lines
    except CatError:
        raise
    except OSError as exc:
        raise CatError(f"Keine Verbindung zum lokalen rigctld: {exc}") from exc


def _rigctld_set_command(host: str, port: int, command: str) -> None:
    try:
        with socket.create_connection((host, port), timeout=2.0) as connection:
            connection.settimeout(2.0)
            with connection.makefile("rwb", buffering=0) as stream:
                stream.write((command.rstrip("\n") + "\n").encode("ascii"))
                raw = stream.readline(4096)
                if not raw:
                    raise CatError("rigctld hat die Verbindung unerwartet geschlossen")
                line = raw.decode("utf-8", errors="replace").strip()
                if line != "RPRT 0":
                    if line.startswith("RPRT "):
                        raise CatError(f"rigctld meldet Fehler {line[5:]}")
                    raise CatError(f"Unerwartete Antwort von rigctld: {line!r}")
    except CatError:
        raise
    except OSError as exc:
        raise CatError(f"Keine Verbindung zum lokalen rigctld: {exc}") from exc


def _rigctld_extended_command(host: str, port: int, command: str) -> str:
    """Run an extended-protocol command and consume output through RPRT.

    Raw ``send_cmd`` replies are not line-oriented and may contain a NUL byte
    immediately before rigctld's final status.  Reading only the first line,
    as for ordinary setters, therefore leaves the client waiting forever.
    """
    try:
        with socket.create_connection((host, port), timeout=2.0) as connection:
            connection.settimeout(4.0)
            connection.sendall((command.rstrip("\n") + "\n").encode("ascii"))
            response = bytearray()
            while len(response) < 65536:
                chunk = connection.recv(4096)
                if not chunk:
                    raise CatError("rigctld hat die Verbindung unerwartet geschlossen")
                response.extend(chunk)
                status_match = re.search(rb"(?:^|[\r\n\x00])RPRT (-?\d+)(?:\r?\n|$)", response)
                if status_match:
                    status = int(status_match.group(1))
                    if status != 0:
                        raise CatError(f"rigctld meldet Fehler {status}")
                    return response.decode("ascii", errors="replace")
            raise CatError("Antwort von rigctld war unerwartet lang")
    except CatError:
        raise
    except socket.timeout as exc:
        raise _RigctldResponseTimeout(
            "rigctld hat den TUNE-Befehl nicht rechtzeitig beantwortet"
        ) from exc
    except OSError as exc:
        raise CatError(f"Keine Verbindung zum lokalen rigctld: {exc}") from exc


def _rigctld_extended_set_command(
    host: str, port: int, command: str, *, no_reply_ok: bool = False,
) -> None:
    try:
        _rigctld_extended_command(host, port, command)
    except _RigctldResponseTimeout:
        # Yaesu CAT write commands intentionally have no answer.  Hamlib's raw
        # bridge still waits for one and can therefore time out after the rig
        # has already performed the requested operation.  This exception is
        # safe only after a successful AC query proved the connection below.
        if not no_reply_ok:
            raise


def _ftx1_tuner_command(host: str, port: int) -> None:
    """Start the tuner selected by the FTX-1 itself.

    The three AC parameters select internal/external, tuner/ATAS and the
    requested operation.  Hard-coding ``AC003`` therefore only works for the
    internal tuner of an Optima.  Read the current selection first, preserve
    P1/P2 and then issue the matching ON/START sequence.
    """
    response = _rigctld_extended_command(host, port, "+w AC;")
    matches = re.findall(r"AC([01])([02])([0-3]);", response)
    if not matches:
        raise CatError(
            "Der am FTX-1 ausgewählte Antennentuner konnte nicht ermittelt werden. "
            "Bitte den Tuner am Funkgerät einmal ein- und wieder ausschalten."
        )
    tuner_type, tuner_mode, tuner_state = matches[-1]
    if tuner_mode == "0" and tuner_state == "0":
        _rigctld_extended_set_command(
            host, port, f"+w AC{tuner_type}{tuner_mode}1;", no_reply_ok=True,
        )
    _rigctld_extended_set_command(
        host, port, f"+w AC{tuner_type}{tuner_mode}3;", no_reply_ok=True,
    )


class HamlibManager:
    def __init__(self, rigctld: Path | None = None):
        self.rigctld = Path(rigctld) if rigctld else None
        self._lock = threading.RLock()
        # rigctld and a serial CAT connection must be treated as one ordered
        # command stream.  Polling and user actions (for example TUNE) run in
        # different worker threads, so serialize complete transactions here.
        self._io_lock = threading.RLock()
        self._process: subprocess.Popen[str] | None = None
        self._config: CatConfig | None = None
        self._generation = 0

    @property
    def running(self) -> bool:
        with self._lock:
            return self._process is not None and self._process.poll() is None

    def start(self, config: CatConfig, timeout: float = 12.0) -> None:
        config.validate()
        # Reserve this start atomically. A concurrent stop (for example while
        # the application is closing) invalidates the reservation so that a
        # process which finishes spawning afterwards is terminated at once.
        with self._lock:
            self._generation += 1
            generation = self._generation
            previous = self._process
            self._process = None
            self._config = None
        self._terminate_process(previous)

        executable = self.rigctld or find_rigctld()
        args = build_rigctld_args(config)
        try:
            process = subprocess.Popen(
                [str(executable), *args],
                cwd=str(executable.parent),
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                creationflags=_windows_creation_flags(),
            )
        except OSError as exc:
            raise CatError(f"rigctld konnte nicht gestartet werden: {exc}") from exc

        with self._lock:
            accepted = generation == self._generation
            if accepted:
                self._process = process
                self._config = config

        if not accepted:
            self._terminate_process(process)
            raise CatError("CAT-Start wurde abgebrochen")

        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            with self._lock:
                still_current = generation == self._generation and self._process is process
            if not still_current:
                self._terminate_process(process)
                raise CatError("CAT-Start wurde abgebrochen")
            if process.poll() is not None:
                detail = ""
                if process.stderr:
                    detail = process.stderr.read().strip()
                self._clear_process(process)
                raise CatError(detail or f"rigctld wurde mit Code {process.returncode} beendet")
            try:
                with socket.create_connection(("127.0.0.1", config.port), timeout=0.25):
                    return
            except OSError:
                time.sleep(0.1)

        self._clear_process(process)
        self._terminate_process(process)
        raise CatError(
            "rigctld wurde nicht rechtzeitig bereit. Bitte Funkgerät, COM-Port, "
            "Baudrate und den lokalen Port prüfen."
        )

    def _clear_process(self, process: subprocess.Popen[str]) -> None:
        with self._lock:
            if self._process is process:
                self._process = None
                self._config = None

    @staticmethod
    def _terminate_process(process: subprocess.Popen[str] | None) -> None:
        if process is None:
            return
        try:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=2.0)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=2.0)
        except (OSError, subprocess.TimeoutExpired):
            try:
                if process.poll() is None:
                    process.kill()
                    process.wait(timeout=2.0)
            except (OSError, subprocess.TimeoutExpired):
                pass
        finally:
            try:
                if process.stderr:
                    process.stderr.close()
            except OSError:
                pass

    def stop(self) -> None:
        with self._lock:
            self._generation += 1
            process = self._process
            self._process = None
            self._config = None
        self._terminate_process(process)

    def read(self, current_mode: str = "") -> CatReading:
        with self._lock:
            process = self._process
            config = self._config
        if process is None or config is None or process.poll() is not None:
            raise CatError("CAT ist nicht gestartet")
        with self._io_lock:
            frequency_line = _rigctld_command("127.0.0.1", config.port, "f", 1)[0]
            mode_lines = _rigctld_command("127.0.0.1", config.port, "m", 2)
        try:
            frequency_hz = int(round(float(frequency_line)))
        except ValueError as exc:
            raise CatError(f"Ungültige Frequenz von rigctld: {frequency_line!r}") from exc
        raw_mode = mode_lines[0].upper()
        return CatReading(
            frequency_hz=frequency_hz,
            raw_mode=raw_mode,
            logger_mode=map_hamlib_mode(raw_mode, current_mode),
        )

    def set_frequency(self, frequency_hz: int) -> None:
        try:
            frequency_hz = int(round(frequency_hz))
        except (TypeError, ValueError) as exc:
            raise CatError("Ungültige Frequenz für CAT") from exc
        if frequency_hz <= 0:
            raise CatError("Ungültige Frequenz für CAT")
        with self._lock:
            process = self._process
            config = self._config
        if process is None or config is None or process.poll() is not None:
            raise CatError("CAT ist nicht gestartet")
        with self._io_lock:
            _rigctld_set_command("127.0.0.1", config.port, f"F {frequency_hz}")


    def set_mode(self, logger_mode: str, frequency_hz: int = 0) -> None:
        hamlib_mode = hamlib_mode_for_logger(logger_mode, frequency_hz)
        if not hamlib_mode:
            raise CatError(f"Mode {logger_mode!r} kann nicht sicher über CAT gesetzt werden")
        with self._lock:
            process = self._process
            config = self._config
        if process is None or config is None or process.poll() is not None:
            raise CatError("CAT ist nicht gestartet")
        # Passband 0 asks Hamlib/the backend for the normal filter width.
        with self._io_lock:
            _rigctld_set_command("127.0.0.1", config.port, f"M {hamlib_mode} 0")

    def set_frequency_and_mode(self, frequency_hz: int, logger_mode: str = "") -> None:
        with self._io_lock:
            self.set_frequency(frequency_hz)
            if (logger_mode or "").strip():
                self.set_mode(logger_mode, frequency_hz)

    def start_tuner(self) -> None:
        """Ask Hamlib to run the radio's one-shot automatic tuner operation."""
        with self._lock:
            process = self._process
            config = self._config
        if process is None or config is None or process.poll() is not None:
            raise CatError("CAT ist nicht gestartet")
        # Hamlib's documented vfo_op command delegates the complete,
        # radio-specific tune cycle to the backend and never toggles PTT here.
        # Hamlib 4.7 advertises TUNE for the FTX-1 but its beta backend maps it
        # to AC002.  Yaesu's CAT reference uses all three AC parameters to
        # distinguish the internal tuner, an external tuner and ATAS.  Read
        # that selection from the radio and preserve it for the start command.
        with self._io_lock:
            if config.model_id == FTX1_MODEL_ID:
                _ftx1_tuner_command("127.0.0.1", config.port)
            else:
                _rigctld_set_command("127.0.0.1", config.port, "G TUNE")
