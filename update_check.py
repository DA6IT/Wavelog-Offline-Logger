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


def current_windows_launcher(environ: dict[str, str] | None = None) -> Path | None:
    """Return the exact user-started Windows EXE passed by the bootstrapper."""
    values = os.environ if environ is None else environ
    raw = str(values.get("WAVELOG_LAUNCHER_PATH") or "").strip()
    if not raw:
        return None
    try:
        # Do not replace this with sys.executable: in the Windows package that
        # is the private pythonw.exe, not the user-named launcher.
        candidate = Path(os.path.abspath(os.path.expandvars(os.path.expanduser(raw))))
    except (OSError, ValueError):
        return None
    if candidate.suffix.lower() != ".exe" or not candidate.is_file():
        return None
    return candidate


def windows_update_helper_script() -> str:
    """PowerShell helper that safely replaces the exact user-started EXE.

    The helper deliberately makes no assumptions about the executable's name
    or location.  It waits for the old Go launcher to exit, verifies that a
    stubborn PID still belongs to the exact target before force-stopping it,
    stages the downloaded package beside the target, verifies SHA-256 before
    and after replacement, rolls back on failure and finally starts the same
    path again.  The script is compatible with Windows PowerShell 5.1.
    """
    return r'''param([int]$ProcessId,[string]$Target,[string]$Package,[string]$Log)
$ErrorActionPreference = 'Stop'

function Write-UpdateLog {
    param([string]$Message)
    if ([string]::IsNullOrWhiteSpace($Log)) { return }
    try {
        $logFull = [System.IO.Path]::GetFullPath($Log)
        $logDir = [System.IO.Path]::GetDirectoryName($logFull)
        if ($logDir -and -not (Test-Path -LiteralPath $logDir)) {
            New-Item -ItemType Directory -Path $logDir -Force | Out-Null
        }
        Add-Content -LiteralPath $logFull -Value ((Get-Date -Format o) + ' ' + $Message) -Encoding UTF8
    } catch {
        # Logging must never prevent the updater from doing its job.
    }
}

try {
    Write-UpdateLog 'Updater started.'

    $targetFull = [System.IO.Path]::GetFullPath($Target)
    $packageFull = [System.IO.Path]::GetFullPath($Package)

    Write-UpdateLog ('Target: ' + $targetFull)
    Write-UpdateLog ('Package: ' + $packageFull)
    Write-UpdateLog ('Old launcher PID: ' + $ProcessId)

    if ([System.IO.Path]::GetExtension($targetFull) -ine '.exe') {
        throw 'Update target is not an EXE.'
    }
    if (-not (Test-Path -LiteralPath $targetFull -PathType Leaf)) {
        throw 'Started EXE no longer exists.'
    }
    if (-not (Test-Path -LiteralPath $packageFull -PathType Leaf)) {
        throw 'Downloaded package is missing.'
    }
    if ($targetFull -ieq $packageFull) {
        throw 'Target and package must be different files.'
    }

    # The Python downloader already verified the published checksum.  Keep a
    # local reference hash as well, so copying/replacing can be verified again
    # without needing another network request or an extra app.py parameter.
    $packageHash = (Get-FileHash -LiteralPath $packageFull -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($packageHash -notmatch '^[0-9a-f]{64}$') {
        throw 'Downloaded package SHA-256 could not be determined.'
    }
    Write-UpdateLog ('Package SHA-256: ' + $packageHash)

    $backup = $targetFull + '.previous'
    $staged = $targetFull + '.update-new'
    $targetDir = [System.IO.Path]::GetDirectoryName($targetFull)
    $packageDir = [System.IO.Path]::GetDirectoryName($packageFull)
    $targetName = [System.IO.Path]::GetFileName($targetFull)
    $archivedBackup = [System.IO.Path]::Combine($packageDir, ($targetName + '.previous'))

    # Do not use Wait-Process -Timeout here.  A simple polling loop works on
    # Windows PowerShell 5.1 and, importantly, lets us log what is happening.
    # The normal app shutdown may include a final Wavelog sync and therefore
    # can legitimately need some time.
    Write-UpdateLog 'Waiting for the old launcher to exit.'
    $deadline = (Get-Date).AddMinutes(10)

    while ($true) {
        $running = Get-Process -Id $ProcessId -ErrorAction SilentlyContinue
        if ($null -eq $running) { break }
        if ((Get-Date) -ge $deadline) { break }
        Start-Sleep -Milliseconds 250
    }

    $running = Get-Process -Id $ProcessId -ErrorAction SilentlyContinue
    if ($null -ne $running) {
        # Never kill a PID merely because its number matches.  Verify that it
        # still belongs to the exact EXE the bootstrapper told us was started.
        $runningPath = $null
        try { $runningPath = $running.Path } catch {}
        if ([string]::IsNullOrWhiteSpace($runningPath)) {
            try { $runningPath = $running.MainModule.FileName } catch {}
        }
        if ([string]::IsNullOrWhiteSpace($runningPath)) {
            throw 'Old launcher did not exit and its executable path could not be verified.'
        }

        $runningFull = [System.IO.Path]::GetFullPath($runningPath)
        if ($runningFull -ine $targetFull) {
            throw 'Old launcher PID now belongs to a different executable. Update aborted.'
        }

        Write-UpdateLog 'Old launcher did not exit normally. Force-stopping the verified target process.'
        Stop-Process -Id $ProcessId -Force -ErrorAction Stop

        $forceDeadline = (Get-Date).AddSeconds(10)
        while ((Get-Date) -lt $forceDeadline) {
            if ($null -eq (Get-Process -Id $ProcessId -ErrorAction SilentlyContinue)) { break }
            Start-Sleep -Milliseconds 200
        }
        if (Get-Process -Id $ProcessId -ErrorAction SilentlyContinue) {
            throw 'Old launcher could not be stopped.'
        }
    }

    Write-UpdateLog 'Old launcher is gone. Starting executable replacement.'

    # Antivirus/indexers can briefly keep an EXE open after the process exits.
    # Retry for roughly 30 seconds and roll back after every failed attempt.
    for ($i = 0; $i -lt 60; $i++) {
        $oldMoved = $false
        try {
            Remove-Item -LiteralPath $staged -Force -ErrorAction SilentlyContinue

            # Stage beside the ORIGINAL target.  The final rename therefore
            # stays on the same filesystem and preserves any arbitrary name.
            Copy-Item -LiteralPath $packageFull -Destination $staged -Force
            $stagedHash = (Get-FileHash -LiteralPath $staged -Algorithm SHA256).Hash.ToLowerInvariant()
            if ($stagedHash -ine $packageHash) {
                throw 'Staged update SHA-256 mismatch.'
            }

            Remove-Item -LiteralPath $backup -Force -ErrorAction SilentlyContinue
            Move-Item -LiteralPath $targetFull -Destination $backup -Force
            $oldMoved = $true

            try {
                Move-Item -LiteralPath $staged -Destination $targetFull -Force
            } catch {
                Move-Item -LiteralPath $backup -Destination $targetFull -Force
                $oldMoved = $false
                throw
            }

            $installedHash = (Get-FileHash -LiteralPath $targetFull -Algorithm SHA256).Hash.ToLowerInvariant()
            if ($installedHash -ine $packageHash) {
                throw 'Installed update SHA-256 mismatch.'
            }

            Write-UpdateLog ('Replacement verified. SHA-256: ' + $installedHash)

            try {
                $newProcess = Start-Process -FilePath $targetFull -WorkingDirectory $targetDir -PassThru
                Start-Sleep -Milliseconds 1500
                if ($newProcess.HasExited) {
                    throw ('New launcher exited immediately with code ' + $newProcess.ExitCode + '.')
                }
            } catch {
                Remove-Item -LiteralPath $targetFull -Force -ErrorAction SilentlyContinue
                Move-Item -LiteralPath $backup -Destination $targetFull -Force
                $oldMoved = $false
                throw
            }

            Write-UpdateLog ('New launcher started. PID: ' + $newProcess.Id)

            # Keep one safety copy internally instead of cluttering whatever
            # folder/name the user chose for the actual launcher.
            Remove-Item -LiteralPath $archivedBackup -Force -ErrorAction SilentlyContinue
            Move-Item -LiteralPath $backup -Destination $archivedBackup -Force -ErrorAction SilentlyContinue
            Remove-Item -LiteralPath $packageFull -Force -ErrorAction SilentlyContinue

            Write-UpdateLog ('SUCCESS: updated and restarted: ' + $targetFull)
            exit 0
        } catch {
            $errorText = $_.Exception.Message

            if ($oldMoved -and (Test-Path -LiteralPath $backup -PathType Leaf)) {
                try {
                    Remove-Item -LiteralPath $targetFull -Force -ErrorAction SilentlyContinue
                    Move-Item -LiteralPath $backup -Destination $targetFull -Force
                    Write-UpdateLog 'Rollback to the previous launcher completed.'
                } catch {
                    Write-UpdateLog ('ROLLBACK FAILED: ' + $_.Exception.Message)
                }
            }

            Write-UpdateLog ('Retry ' + ($i + 1) + '/60: ' + $errorText)
            Start-Sleep -Milliseconds 500
        }
    }

    Remove-Item -LiteralPath $staged -Force -ErrorAction SilentlyContinue
    if (-not (Test-Path -LiteralPath $targetFull) -and (Test-Path -LiteralPath $backup)) {
        Move-Item -LiteralPath $backup -Destination $targetFull -Force
    }
    throw 'Executable replacement failed after 60 attempts.'
} catch {
    Write-UpdateLog ('FATAL: ' + $_.Exception.Message)
    exit 1
}
'''
