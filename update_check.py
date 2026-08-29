from __future__ import annotations

import json
import hashlib
import os
import platform
import re
import sys
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from logger_core import secure_urlopen


RELEASES_API_URL = "https://api.github.com/repos/DA6IT/Wavelog-Offline-Logger/releases?per_page=20"
RELEASES_PAGE_URL = "https://github.com/DA6IT/Wavelog-Offline-Logger/releases"

_VERSION_RE = re.compile(
    r"^[vV]?(\d+)\.(\d+)\.(\d+)(?:[-.]?(dev|alpha|a|beta|b|rc)[.-]?(\d*)?)?(?:\+.*)?$",
    re.IGNORECASE,
)
_STAGE_RANK = {"dev": 0, "alpha": 1, "a": 1, "beta": 2, "b": 2, "rc": 3}


@dataclass(frozen=True)
class ReleaseAsset:
    name: str
    url: str
    size: int = 0


@dataclass(frozen=True)
class ReleaseInfo:
    version: str
    name: str
    url: str
    prerelease: bool
    assets: tuple[ReleaseAsset, ...] = ()


def version_key(version: str) -> tuple[int, int, int, int, int] | None:
    """Return a sortable key for the version format used by this project."""
    match = _VERSION_RE.fullmatch((version or "").strip())
    if not match:
        return None
    major, minor, patch = (int(match.group(i)) for i in range(1, 4))
    stage = (match.group(4) or "").lower()
    stage_rank = 4 if not stage else _STAGE_RANK[stage]
    stage_number = int(match.group(5) or 0)
    return major, minor, patch, stage_rank, stage_number


def is_prerelease(version: str) -> bool:
    key = version_key(version)
    return bool(key and key[3] < 4)


def find_newer_release(
    current_version: str,
    *,
    timeout: float = 4.0,
    opener: Callable | None = None,
) -> ReleaseInfo | None:
    """Return a newer applicable GitHub release, or silently return None.

    Network, HTTP, JSON and schema errors are intentionally swallowed: update
    discovery must never disturb offline logging or delay application startup.
    """
    current_key = version_key(current_version)
    if current_key is None:
        return None

    request = urllib.request.Request(
        RELEASES_API_URL,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": f"DA6IT.de-Wavelog-Offline-Logger/{current_version}",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    try:
        open_request = opener or secure_urlopen
        with open_request(request, timeout=timeout) as response:
            releases = json.loads(response.read().decode("utf-8"))
    except Exception:
        return None

    if not isinstance(releases, list):
        return None

    allow_prereleases = is_prerelease(current_version)
    candidates: list[tuple[tuple[int, int, int, int, int], ReleaseInfo]] = []
    for item in releases:
        if not isinstance(item, dict) or item.get("draft"):
            continue
        prerelease = bool(item.get("prerelease"))
        if prerelease and not allow_prereleases:
            continue
        tag = str(item.get("tag_name") or "").strip()
        key = version_key(tag)
        if key is None or key <= current_key:
            continue
        version = tag[1:] if tag.lower().startswith("v") else tag
        url = str(item.get("html_url") or RELEASES_PAGE_URL)
        name = str(item.get("name") or tag)
        assets = []
        for raw_asset in item.get("assets") or []:
            if not isinstance(raw_asset, dict):
                continue
            asset_name = str(raw_asset.get("name") or "").strip()
            asset_url = str(raw_asset.get("browser_download_url") or "").strip()
            if asset_name and asset_url:
                assets.append(ReleaseAsset(asset_name, asset_url, int(raw_asset.get("size") or 0)))
        candidates.append((key, ReleaseInfo(version, name, url, prerelease, tuple(assets))))

    return max(candidates, key=lambda candidate: candidate[0])[1] if candidates else None


def select_update_asset(
    release: ReleaseInfo, *, system: str | None = None, machine: str | None = None,
) -> ReleaseAsset | None:
    """Choose the native package matching this operating system and CPU."""
    system_name = (system or sys.platform).lower()
    machine_name = (machine or platform.machine()).lower()
    arm = machine_name in {"arm64", "aarch64"}
    if system_name.startswith("win"):
        suffix = f"v{release.version}-windows-x64.exe"
    elif system_name == "darwin":
        suffix = f"v{release.version}-macos-{'arm64' if arm else 'x64'}.zip"
    elif system_name.startswith("linux"):
        architecture = "arm64" if arm else "x64"
        suffix = f"v{release.version}-linux-{architecture}.AppImage" if os.environ.get("APPIMAGE") else f"v{release.version}-linux-{architecture}.deb"
    else:
        return None
    return next((asset for asset in release.assets if asset.name.endswith(suffix)), None)


def _parse_checksums(payload: str) -> dict[str, str]:
    checksums: dict[str, str] = {}
    for line in payload.splitlines():
        match = re.match(r"^\s*([0-9a-fA-F]{64})\s+[*]?(.+?)\s*$", line)
        if match:
            checksums[Path(match.group(2)).name] = match.group(1).lower()
    return checksums


def _read_url(url: str, *, timeout: float, opener: Callable | None = None) -> bytes:
    if urllib.parse.urlparse(url).scheme != "https":
        raise RuntimeError("Update-Downloads sind ausschließlich über HTTPS erlaubt.")
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "DA6IT.de-Wavelog-Offline-Logger-Updater", "Accept": "application/octet-stream"},
    )
    open_request = opener or secure_urlopen
    with open_request(request, timeout=timeout) as response:
        return response.read()


def download_verified_asset(
    release: ReleaseInfo,
    asset: ReleaseAsset,
    destination_dir: Path,
    *,
    timeout: float = 45.0,
    opener: Callable | None = None,
    progress: Callable[[int, int], None] | None = None,
) -> tuple[Path, str]:
    """Download one release asset and require a matching published SHA-256."""
    # Platform jobs publish a checksum beside their own artifact. Prefer that
    # exact file; the Windows-wide SHA256SUMS.txt is only the fallback.
    checksum_asset = next((row for row in release.assets if row.name == asset.name + ".sha256"), None)
    if checksum_asset is None:
        checksum_asset = next((row for row in release.assets if row.name == "SHA256SUMS.txt"), None)
    if checksum_asset is None:
        raise RuntimeError("Für dieses Update wurde keine SHA-256-Prüfsumme veröffentlicht.")
    checksum_payload = _read_url(checksum_asset.url, timeout=timeout, opener=opener).decode("utf-8-sig", errors="replace")
    checksums = _parse_checksums(checksum_payload)
    expected = checksums.get(asset.name)
    if expected is None:
        # Per-platform .sha256 files occasionally contain only the digest.
        bare = re.search(r"\b([0-9a-fA-F]{64})\b", checksum_payload)
        expected = bare.group(1).lower() if bare else None
    if not expected:
        raise RuntimeError(f"Die veröffentlichte Prüfsumme für {asset.name} fehlt.")

    destination_dir = Path(destination_dir)
    destination_dir.mkdir(parents=True, exist_ok=True)
    destination = destination_dir / Path(asset.name).name
    partial = destination.with_suffix(destination.suffix + ".part")
    if urllib.parse.urlparse(asset.url).scheme != "https":
        raise RuntimeError("Update-Downloads sind ausschließlich über HTTPS erlaubt.")
    request = urllib.request.Request(
        asset.url,
        headers={"User-Agent": f"DA6IT.de-Wavelog-Offline-Logger/{release.version}", "Accept": "application/octet-stream"},
    )
    digest = hashlib.sha256()
    received = 0
    try:
        open_request = opener or secure_urlopen
        with open_request(request, timeout=timeout) as response, partial.open("wb") as output:
            total = int(getattr(response, "headers", {}).get("Content-Length") or asset.size or 0)
            while True:
                chunk = response.read(1024 * 256)
                if not chunk:
                    break
                received += len(chunk)
                if received > 1024 * 1024 * 1024:
                    raise RuntimeError("Das Update-Paket ist unerwartet größer als 1 GiB.")
                digest.update(chunk)
                output.write(chunk)
                if progress:
                    progress(received, total)
            output.flush()
            os.fsync(output.fileno())
        actual = digest.hexdigest().lower()
        if actual != expected:
            raise RuntimeError("Die SHA-256-Prüfung des heruntergeladenen Updates ist fehlgeschlagen.")
        os.replace(partial, destination)
        return destination, actual
    finally:
        partial.unlink(missing_ok=True)
