from __future__ import annotations

import os
import re
import shutil
import socket
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable


DEFAULT_ROTCTLD_PORT = 4533
DEFAULT_ROTOR_POLL_MS = 750
DUMMY_ROTOR_MODEL_ID = 1
NET_ROTCTL_MODEL_ID = 2
ROTOR_BAUD_RATES = (300, 1200, 2400, 4800, 9600, 19200, 38400, 57600, 115200)


class RotorError(RuntimeError):
    pass


@dataclass(frozen=True)
class RotorModel:
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
class RotorConfig:
    model_id: int = DUMMY_ROTOR_MODEL_ID
    device: str = ""
    baud: int = 9600
    port: int = DEFAULT_ROTCTLD_PORT
    poll_interval_ms: int = DEFAULT_ROTOR_POLL_MS

    @classmethod
    def from_getter(cls, getter: Callable[[str, str], str]) -> "RotorConfig":
        def integer(key: str, default: int) -> int:
            try:
                return int(str(getter(key, str(default))).strip())
            except (TypeError, ValueError):
                return default

        return cls(
            model_id=integer("rotor_model_id", DUMMY_ROTOR_MODEL_ID),
            device=str(getter("rotor_device", "") or "").strip(),
            baud=integer("rotor_baud", 9600),
            port=integer("rotor_port", DEFAULT_ROTCTLD_PORT),
            poll_interval_ms=integer("rotor_poll_interval_ms", DEFAULT_ROTOR_POLL_MS),
        )

    def settings(self) -> dict[str, str]:
        return {
            "rotor_model_id": str(self.model_id),
            "rotor_device": self.device,
            "rotor_baud": str(self.baud),
            "rotor_port": str(self.port),
            "rotor_poll_interval_ms": str(self.poll_interval_ms),
        }

    def validate(self) -> None:
        if self.model_id <= 0:
            raise RotorError("Bitte ein Rotor-Modell auswählen")
        if self.model_id == NET_ROTCTL_MODEL_ID:
            raise RotorError(
                "Hamlib-Modell 2 (NET rotctl) ist ein Client-Backend und kann nicht direkt mit rotctld gestartet werden"
            )
        if self.model_id != DUMMY_ROTOR_MODEL_ID and not self.device:
            raise RotorError("Bitte die Rotor-/COM-Schnittstelle eintragen")
        if not 300 <= self.baud <= 115200:
            raise RotorError("Die Rotor-Baudrate muss zwischen 300 und 115200 liegen")
        if not 1 <= self.port <= 65535:
            raise RotorError("Der lokale rotctld-Port muss zwischen 1 und 65535 liegen")
        if not 250 <= self.poll_interval_ms <= 5000:
            raise RotorError("Das Rotor-Abfrageintervall muss zwischen 250 und 5000 ms liegen")


@dataclass(frozen=True)
class RotorReading:
    azimuth: float
    elevation: float


def _windows_creation_flags() -> int:
    if sys.platform != "win32":
        return 0
    return int(getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000))


def _candidate_hamlib_dirs() -> list[Path]:
    candidates: list[Path] = []
    override = os.environ.get("WAVELOG_HAMLIB_DIR", "").strip()
    if override:
        candidates.append(Path(override))

    here = Path(__file__).resolve().parent
    bundle_root = Path(getattr(sys, "_MEIPASS", here))
    if sys.platform == "win32":
        local_app_data = Path(os.environ.get("LOCALAPPDATA", Path.home()))
        candidates.append(
            local_app_data
            / "AFU-Tools"
            / "WavelogOfflineLogger"
            / "hamlib-runtime"
            / "windows-x64"
            / "current"
        )

    candidates.extend(
        [
            bundle_root / "hamlib",
            here / "hamlib",
            here / "build" / "embedded" / "hamlib" / "windows-x64",
            here / "build" / "embedded" / "hamlib" / f"linux-{os.uname().machine}" if hasattr(os, "uname") else here,
            here / "build" / "embedded" / "hamlib" / f"macos-{os.uname().machine}" if hasattr(os, "uname") else here,
        ]
    )

    unique: list[Path] = []
    seen: set[str] = set()
    for candidate in candidates:
        key = str(candidate)
        if key not in seen:
            seen.add(key)
            unique.append(candidate)
    return unique


def find_rotctld() -> Path:
    executable = "rotctld.exe" if sys.platform == "win32" else "rotctld"
    for candidate in _candidate_hamlib_dirs():
        if (candidate / executable).is_file():
            return candidate / executable
    system = shutil.which(executable)
    if system:
        return Path(system).resolve()
    raise RotorError(
        "rotctld wurde nicht gefunden. Bitte die Hamlib-Laufzeit für den Logger vorbereiten "
        "oder ein Release-Paket mit Rotor-Unterstützung verwenden."
    )


_MODEL_RE = re.compile(
    r"^\s*(?P<id>\d+)\s{2,}(?P<mfg>.*?)\s{2,}(?P<model>.*?)\s{2,}"
    r"(?P<version>\S+)\s{2,}(?P<status>\S+)(?:\s{2,}.*)?$"
)


def parse_rotctld_models(output: str) -> list[RotorModel]:
    models: list[RotorModel] = []
    for raw_line in output.splitlines():
        match = _MODEL_RE.match(raw_line.rstrip())
        if not match:
            continue
        model_id = int(match.group("id"))
        if model_id == NET_ROTCTL_MODEL_ID:
            continue
        models.append(
            RotorModel(
                model_id=model_id,
                manufacturer=match.group("mfg").strip(),
                model=match.group("model").strip(),
                version=match.group("version").strip(),
                status=match.group("status").strip(),
            )
        )
    return models


def list_rotor_models(rotctld: Path | None = None) -> list[RotorModel]:
    executable = Path(rotctld) if rotctld else find_rotctld()
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
        raise RotorError(f"Hamlib-Rotormodellliste konnte nicht geladen werden: {exc}") from exc
    models = parse_rotctld_models(result.stdout)
    if not models:
        detail = (result.stderr or result.stdout or f"Exit-Code {result.returncode}").strip()
        raise RotorError(f"Hamlib hat keine Rotormodelle geliefert: {detail}")
    return models


def rotctld_version(rotctld: Path | None = None) -> str:
    executable = Path(rotctld) if rotctld else find_rotctld()
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
        raise RotorError(f"rotctld-Version konnte nicht gelesen werden: {exc}") from exc
    lines = (result.stdout or result.stderr).strip().splitlines()
    if result.returncode != 0 or not lines:
        raise RotorError("rotctld hat keine Versionsinformation geliefert")
    return lines[0]


def build_rotctld_args(config: RotorConfig) -> list[str]:
    config.validate()
    args = ["-m", str(config.model_id)]
    if config.model_id != DUMMY_ROTOR_MODEL_ID:
        args.extend(["-r", config.device, "-s", str(config.baud)])
    args.extend(["-T", "127.0.0.1", "-t", str(config.port)])
    return args


def _rotctld_get_position(host: str, port: int) -> RotorReading:
    try:
        with socket.create_connection((host, port), timeout=2.0) as connection:
            connection.settimeout(2.0)
            with connection.makefile("rwb", buffering=0) as stream:
                stream.write(b"p\n")
                values: list[str] = []
                for _ in range(2):
                    raw = stream.readline(4096)
                    if not raw:
                        raise RotorError("rotctld hat die Verbindung unerwartet geschlossen")
                    line = raw.decode("utf-8", errors="replace").strip()
                    if line.startswith("RPRT "):
                        raise RotorError(f"rotctld meldet Fehler {line[5:]}")
                    values.append(line)
        return RotorReading(float(values[0]), float(values[1]))
    except RotorError:
        raise
    except (OSError, ValueError) as exc:
        raise RotorError(f"Rotorposition konnte nicht gelesen werden: {exc}") from exc


def _rotctld_set_command(host: str, port: int, command: str) -> None:
    try:
        with socket.create_connection((host, port), timeout=2.0) as connection:
            connection.settimeout(2.0)
            with connection.makefile("rwb", buffering=0) as stream:
                stream.write((command.rstrip("\n") + "\n").encode("ascii"))
                raw = stream.readline(4096)
                if not raw:
                    raise RotorError("rotctld hat die Verbindung unerwartet geschlossen")
                line = raw.decode("utf-8", errors="replace").strip()
                if line != "RPRT 0":
                    if line.startswith("RPRT "):
                        raise RotorError(f"rotctld meldet Fehler {line[5:]}")
                    raise RotorError(f"Unerwartete Antwort von rotctld: {line!r}")
    except RotorError:
        raise
    except OSError as exc:
        raise RotorError(f"Keine Verbindung zum lokalen rotctld: {exc}") from exc


class RotatorManager:
    def __init__(self, rotctld: Path | None = None):
        self.rotctld = Path(rotctld) if rotctld else None
        self._lock = threading.RLock()
        self._io_lock = threading.RLock()
        self._process: subprocess.Popen[str] | None = None
        self._config: RotorConfig | None = None
        self._generation = 0

    @property
    def running(self) -> bool:
        with self._lock:
            return self._process is not None and self._process.poll() is None

    def start(self, config: RotorConfig, timeout: float = 10.0) -> None:
        config.validate()
        with self._lock:
            self._generation += 1
            generation = self._generation
            previous = self._process
            self._process = None
            self._config = None
        self._terminate_process(previous)

        executable = self.rotctld or find_rotctld()
        try:
            process = subprocess.Popen(
                [str(executable), *build_rotctld_args(config)],
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
            raise RotorError(f"rotctld konnte nicht gestartet werden: {exc}") from exc

        with self._lock:
            accepted = generation == self._generation
            if accepted:
                self._process = process
                self._config = config
        if not accepted:
            self._terminate_process(process)
            raise RotorError("Rotor-Start wurde abgebrochen")

        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            with self._lock:
                still_current = generation == self._generation and self._process is process
            if not still_current:
                self._terminate_process(process)
                raise RotorError("Rotor-Start wurde abgebrochen")
            if process.poll() is not None:
                detail = process.stderr.read().strip() if process.stderr else ""
                self._clear_process(process)
                self._terminate_process(process)
                raise RotorError(detail or f"rotctld wurde mit Code {process.returncode} beendet")
            try:
                with socket.create_connection(("127.0.0.1", config.port), timeout=0.25):
                    return
            except OSError:
                time.sleep(0.1)

        self._clear_process(process)
        self._terminate_process(process)
        raise RotorError(
            "rotctld wurde nicht rechtzeitig bereit. Bitte Rotor-Modell, Schnittstelle, "
            "Baudrate und lokalen Port prüfen."
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
            except OSError:
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

    def _active_config(self) -> RotorConfig:
        with self._lock:
            process = self._process
            config = self._config
        if process is None or config is None or process.poll() is not None:
            raise RotorError("Rotor ist nicht gestartet")
        return config

    def read(self) -> RotorReading:
        config = self._active_config()
        with self._io_lock:
            return _rotctld_get_position("127.0.0.1", config.port)

    def set_position(self, azimuth: float, elevation: float = 0.0) -> None:
        config = self._active_config()
        azimuth = float(azimuth)
        elevation = float(elevation)
        if not -180.0 <= azimuth <= 540.0:
            raise RotorError("Azimut liegt außerhalb des Hamlib-Bereichs")
        if not -20.0 <= elevation <= 210.0:
            raise RotorError("Elevation liegt außerhalb des Hamlib-Bereichs")
        with self._io_lock:
            _rotctld_set_command(
                "127.0.0.1",
                config.port,
                f"P {azimuth:.2f} {elevation:.2f}",
            )

    def stop_motion(self) -> None:
        config = self._active_config()
        with self._io_lock:
            _rotctld_set_command("127.0.0.1", config.port, "S")

    def park(self) -> None:
        config = self._active_config()
        with self._io_lock:
            _rotctld_set_command("127.0.0.1", config.port, "K")
