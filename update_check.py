from __future__ import annotations

import json
import re
import urllib.request
from dataclasses import dataclass
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
class ReleaseInfo:
    version: str
    name: str
    url: str
    prerelease: bool


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
        candidates.append((key, ReleaseInfo(version, name, url, prerelease)))

    return max(candidates, key=lambda candidate: candidate[0])[1] if candidates else None
