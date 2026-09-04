from __future__ import annotations

import hashlib
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.request
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Callable


HAMLIB_RELEASES_API = "https://api.github.com/repos/Hamlib/Hamlib/releases?per_page=30"
MAX_DOWNLOAD_BYTES = 120 * 1024 * 1024
MAX_ARCHIVE_FILES = 500
MAX_EXTRACTED_BYTES = 250 * 1024 * 1024


class HamlibUpdateError(RuntimeError):
    pass


@dataclass(frozen=True)
class HamlibRelease:
    version: str
    page_url: str
    asset_name: str
    asset_url: str
    sha256: str


def _version_tuple(value: str) -> tuple[int, ...]:
    match = re.search(r"(?<!\d)(\d+(?:\.\d+){1,3})(?!\d)", str(value or ""))
    return tuple(int(part) for part in match.group(1).split(".")) if match else ()


def version_from_output(value: str) -> str:
    parts = _version_tuple(value)
    return ".".join(str(part) for part in parts)


def _read_limited(response, limit: int) -> bytes:
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = response.read(min(1024 * 1024, limit + 1 - total))
        if not chunk:
            break
        total += len(chunk)
        if total > limit:
            raise HamlibUpdateError("Der Hamlib-Download ist unerwartet groß und wurde abgebrochen")
        chunks.append(chunk)
    return b"".join(chunks)


def find_latest_windows_release(
    current_version: str,
    *,
    opener: Callable = urllib.request.urlopen,
) -> HamlibRelease | None:
    """Return the newest stable official Windows Hamlib release."""
    current = _version_tuple(current_version)
    if not current:
        raise HamlibUpdateError("Die installierte Hamlib-Version konnte nicht ermittelt werden")
    request = urllib.request.Request(
        HAMLIB_RELEASES_API,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "DA6IT-Wavelog-Offline-Logger",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    try:
        with opener(request, timeout=20) as response:
            payload = json.loads(_read_limited(response, 4 * 1024 * 1024).decode("utf-8"))
    except HamlibUpdateError:
        raise
    except Exception as exc:
        raise HamlibUpdateError(f"Hamlib-Versionen konnten nicht abgerufen werden: {exc}") from exc
    if not isinstance(payload, list):
        raise HamlibUpdateError("GitHub hat keine gültige Hamlib-Versionsliste geliefert")

    candidates: list[tuple[tuple[int, ...], HamlibRelease]] = []
    for release in payload:
        if not isinstance(release, dict) or release.get("draft") or release.get("prerelease"):
            continue
        version = str(release.get("tag_name") or release.get("name") or "").lstrip("v")
        parsed = _version_tuple(version)
        if not parsed or parsed <= current:
            continue
        expected_name = f"hamlib-w64-{version}.zip".lower()
        for asset in release.get("assets") or ():
            if not isinstance(asset, dict) or str(asset.get("name", "")).lower() != expected_name:
                continue
            url = str(asset.get("browser_download_url") or "")
            digest = str(asset.get("digest") or "")
            digest_match = re.fullmatch(r"sha256:([0-9a-fA-F]{64})", digest)
            if not url.startswith("https://github.com/Hamlib/Hamlib/releases/download/"):
                continue
            if not digest_match:
                raise HamlibUpdateError(
                    f"Für {asset.get('name')} stellt GitHub keine prüfbare SHA-256-Summe bereit"
                )
            candidates.append((parsed, HamlibRelease(
                version=version,
                page_url=str(release.get("html_url") or "https://github.com/Hamlib/Hamlib/releases"),
                asset_name=str(asset.get("name")),
                asset_url=url,
                sha256=digest_match.group(1).lower(),
            )))
            break
    return max(candidates, key=lambda item: item[0])[1] if candidates else None


def hamlib_runtime_root(data_dir: Path) -> Path:
    return Path(data_dir) / "hamlib-runtime" / "windows-x64"


def user_hamlib_dir(data_dir: Path) -> Path:
    return hamlib_runtime_root(data_dir) / "current"


def backup_hamlib_dir(data_dir: Path) -> Path:
    return hamlib_runtime_root(data_dir) / "backup"


def _rigctld_path(directory: Path) -> Path:
    return Path(directory) / ("rigctld.exe" if sys.platform == "win32" else "rigctld")


def usable_hamlib_dir(directory: Path) -> bool:
    try:
        path = _rigctld_path(directory)
        return path.is_file() and path.stat().st_size > 0
    except OSError:
        return False


def _ensure_child(path: Path, parent: Path) -> Path:
    resolved = path.resolve()
    root = parent.resolve()
    if resolved == root or root not in resolved.parents:
        raise HamlibUpdateError("Unsicherer Hamlib-Zielpfad")
    return resolved


def _remove_tree(path: Path, root: Path) -> None:
    target = _ensure_child(path, root)
    if target.exists():
        shutil.rmtree(target)


def _safe_extract_runtime(archive_bytes: bytes, target: Path) -> None:
    try:
        archive = zipfile.ZipFile(io.BytesIO(archive_bytes))
    except (OSError, zipfile.BadZipFile) as exc:
        raise HamlibUpdateError("Das Hamlib-Paket ist kein gültiges ZIP-Archiv") from exc
    with archive:
        files = [info for info in archive.infolist() if not info.is_dir()]
        if len(files) > MAX_ARCHIVE_FILES or sum(info.file_size for info in files) > MAX_EXTRACTED_BYTES:
            raise HamlibUpdateError("Das Hamlib-Paket überschreitet die Sicherheitsgrenzen")
        bin_files: list[tuple[zipfile.ZipInfo, str]] = []
        docs: list[tuple[zipfile.ZipInfo, str]] = []
        for info in files:
            parts = PurePosixPath(info.filename).parts
            if not parts or any(part in {"", ".", ".."} for part in parts):
                raise HamlibUpdateError("Das Hamlib-Paket enthält einen unsicheren Dateipfad")
            if info.external_attr >> 16 & 0o170000 == 0o120000:
                raise HamlibUpdateError("Das Hamlib-Paket enthält nicht unterstützte Verknüpfungen")
            if len(parts) >= 3 and parts[-2].lower() == "bin":
                bin_files.append((info, parts[-1]))
            elif len(parts) == 2 and parts[-1].lower().startswith(("copying", "license", "authors", "readme")):
                docs.append((info, parts[-1]))
        if not any(name.lower() == "rigctld.exe" for _info, name in bin_files):
            raise HamlibUpdateError("Im Hamlib-Paket fehlt rigctld.exe")
        target.mkdir(parents=True, exist_ok=False)
        seen: set[str] = set()
        for info, name in [*bin_files, *docs]:
            key = name.casefold()
            if key in seen:
                continue
            seen.add(key)
            destination = _ensure_child(target / name, target)
            with archive.open(info) as source, destination.open("wb") as output:
                shutil.copyfileobj(source, output)


def runtime_version(directory: Path) -> str:
    executable = _rigctld_path(directory)
    if not executable.is_file():
        raise HamlibUpdateError("rigctld wurde nicht gefunden")
    try:
        result = subprocess.run(
            [str(executable), "--version"], cwd=str(executable.parent),
            stdin=subprocess.DEVNULL, capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=15,
            creationflags=int(getattr(subprocess, "CREATE_NO_WINDOW", 0)) if sys.platform == "win32" else 0,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise HamlibUpdateError(f"Die neue Hamlib-Version konnte nicht gestartet werden: {exc}") from exc
    version = version_from_output(result.stdout or result.stderr)
    if result.returncode != 0 or not version:
        raise HamlibUpdateError("Die neue Hamlib-Version hat den Funktionstest nicht bestanden")
    return version


def install_windows_release(
    release: HamlibRelease,
    data_dir: Path,
    active_runtime: Path,
    *,
    opener: Callable = urllib.request.urlopen,
) -> str:
    if sys.platform != "win32":
        raise HamlibUpdateError("Der direkte Hamlib-Download ist nur unter Windows verfügbar")
    request = urllib.request.Request(
        release.asset_url,
        headers={"Accept": "application/octet-stream", "User-Agent": "DA6IT-Wavelog-Offline-Logger"},
    )
    try:
        with opener(request, timeout=180) as response:
            archive_bytes = _read_limited(response, MAX_DOWNLOAD_BYTES)
    except HamlibUpdateError:
        raise
    except Exception as exc:
        raise HamlibUpdateError(f"Hamlib konnte nicht heruntergeladen werden: {exc}") from exc
    digest = hashlib.sha256(archive_bytes).hexdigest()
    if digest.lower() != release.sha256.lower():
        raise HamlibUpdateError("Die SHA-256-Prüfsumme des Hamlib-Pakets stimmt nicht")

    root = hamlib_runtime_root(data_dir)
    root.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix="install-", dir=root))
    current = user_hamlib_dir(data_dir)
    backup = backup_hamlib_dir(data_dir)
    staged_runtime = stage / "runtime"
    try:
        _safe_extract_runtime(archive_bytes, staged_runtime)
        installed_version = runtime_version(staged_runtime)
        if _version_tuple(installed_version) != _version_tuple(release.version):
            raise HamlibUpdateError(
                f"Geladen wurde Hamlib {installed_version} statt der erwarteten Version {release.version}"
            )
        (staged_runtime / "WAVELOG_HAMLIB_UPDATE.json").write_text(json.dumps({
            "version": installed_version,
            "source": release.page_url,
            "asset": release.asset_name,
            "sha256": digest,
        }, indent=2) + "\n", encoding="utf-8")
        _remove_tree(backup, root)
        if usable_hamlib_dir(current):
            os.replace(current, backup)
        elif usable_hamlib_dir(active_runtime):
            shutil.copytree(active_runtime, backup)
        elif current.exists():
            _remove_tree(current, root)
        os.replace(staged_runtime, current)
        return installed_version
    except Exception:
        if not usable_hamlib_dir(current) and usable_hamlib_dir(backup):
            if current.exists():
                _remove_tree(current, root)
            shutil.copytree(backup, current)
        raise
    finally:
        _remove_tree(stage, root)


def restore_previous_windows_runtime(data_dir: Path) -> str:
    if sys.platform != "win32":
        raise HamlibUpdateError("Die Hamlib-Wiederherstellung ist nur unter Windows verfügbar")
    root = hamlib_runtime_root(data_dir)
    current = user_hamlib_dir(data_dir)
    backup = backup_hamlib_dir(data_dir)
    if not usable_hamlib_dir(backup):
        raise HamlibUpdateError("Es ist keine vorherige Hamlib-Version gespeichert")
    swap = root / "swap"
    _remove_tree(swap, root)
    try:
        if current.exists():
            os.replace(current, swap)
        os.replace(backup, current)
        version = runtime_version(current)
        if swap.exists():
            os.replace(swap, backup)
        return version
    except Exception:
        if not backup.exists() and current.exists():
            os.replace(current, backup)
        if swap.exists() and not current.exists():
            os.replace(swap, current)
        raise
