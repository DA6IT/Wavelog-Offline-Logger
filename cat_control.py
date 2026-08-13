from __future__ import annotations

import os
import re
import socket
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable


HAMLIB_VERSION = "4.7.2"
CAT_BAUD_RATES = (300, 1200, 2400, 4800, 9600, 19200, 38400, 57600, 115200)
CAT_DATA_BITS = (7, 8)
CAT_STOP_BITS = (1, 2)
CAT_PARITIES = ("None", "Odd", "Even", "Mark", "Space")
CAT_HANDSHAKES = ("None", "XONXOFF", "Hardware")
CAT_LINE_STATES = ("Unset", "ON", "OFF")


class CatError(RuntimeError):
    pass


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
        return cls(
            enabled=enabled,
            model_id=integer("cat_model_id", 0),
            device=str(getter("cat_device", "")).strip(),
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
        return {
            "cat_enabled": "1" if self.enabled else "0",
            "cat_model_id": str(self.model_id),
            "cat_device": self.device,
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

    def validate(self) -> None:
        if self.model_id <= 0:
            raise CatError("Bitte ein Funkgerät aus der Hamlib-Liste auswählen")
        if not self.device and self.model_id not in {1, 6}:
            raise CatError("Bitte eine CAT-/COM-Schnittstelle auswählen")
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
    raise CatError(
        "Die gebündelte Hamlib-Laufzeit wurde nicht gefunden. "
        "Bitte das passende Windows- oder macOS-Release-Paket verwenden."
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


class HamlibManager:
    def __init__(self, rigctld: Path | None = None):
        self.rigctld = Path(rigctld) if rigctld else None
        self._lock = threading.RLock()
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
        _rigctld_set_command("127.0.0.1", config.port, f"M {hamlib_mode} 0")

    def set_frequency_and_mode(self, frequency_hz: int, logger_mode: str = "") -> None:
        self.set_frequency(frequency_hz)
        if (logger_mode or "").strip():
            self.set_mode(logger_mode, frequency_hz)
