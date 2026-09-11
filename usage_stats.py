from __future__ import annotations

import json
import platform
import threading
import urllib.error
import urllib.request
import uuid
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable


STATE_FILE = "usage_stats.json"
HEARTBEAT_URL = "https://da6it.de/wp-json/da6it/v1/offline-logger/heartbeat"
FORGET_URL = "https://da6it.de/wp-json/da6it/v1/offline-logger/forget"
HTTP_TIMEOUT_SECONDS = 5


class UsageStatsError(RuntimeError):
    pass


@dataclass(frozen=True)
class UsageStatsState:
    installation_id: str
    enabled: bool = True
    notice_seen: bool = False
    last_successful_heartbeat: str = ""

    def normalized(self) -> "UsageStatsState":
        try:
            installation_id = str(uuid.UUID(str(self.installation_id)))
        except (ValueError, AttributeError, TypeError):
            installation_id = str(uuid.uuid4())
        heartbeat = str(self.last_successful_heartbeat or "").strip()
        if heartbeat:
            try:
                datetime.strptime(heartbeat, "%Y-%m-%d")
            except ValueError:
                heartbeat = ""
        return UsageStatsState(
            installation_id=installation_id,
            enabled=bool(self.enabled),
            notice_seen=bool(self.notice_seen),
            last_successful_heartbeat=heartbeat,
        )


def _utc_day() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _platform_name() -> str:
    name = platform.system().strip().lower()
    if name == "windows":
        return "windows"
    if name == "darwin":
        return "macos"
    if name == "linux":
        return "linux"
    return "other"


class UsageStatsService:
    """Small, app-wide usage heartbeat with no QSO/profile data."""

    def __init__(
        self,
        data_dir: Path,
        *,
        heartbeat_url: str = HEARTBEAT_URL,
        forget_url: str = FORGET_URL,
        post_json: Callable[[str, dict, str], int] | None = None,
    ) -> None:
        self.data_dir = Path(data_dir)
        self.path = self.data_dir / STATE_FILE
        self.heartbeat_url = heartbeat_url
        self.forget_url = forget_url
        self._post_json_override = post_json
        self._lock = threading.RLock()
        self.state = self._load_or_create()

    def _load_or_create(self) -> UsageStatsState:
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(payload, dict):
                raise ValueError("invalid state")
            state = UsageStatsState(
                installation_id=str(payload.get("installation_id") or ""),
                enabled=bool(payload.get("enabled", True)),
                notice_seen=bool(payload.get("notice_seen", False)),
                last_successful_heartbeat=str(payload.get("last_successful_heartbeat") or ""),
            ).normalized()
        except (OSError, ValueError, TypeError):
            state = UsageStatsState(installation_id=str(uuid.uuid4()))
        self._save_state(state)
        return state

    def _save_state(self, state: UsageStatsState) -> None:
        state = state.normalized()
        self.data_dir.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        temporary.write_text(
            json.dumps(
                {
                    "installation_id": state.installation_id,
                    "enabled": state.enabled,
                    "notice_seen": state.notice_seen,
                    "last_successful_heartbeat": state.last_successful_heartbeat,
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        temporary.replace(self.path)

    def _replace_state(self, **changes) -> UsageStatsState:
        with self._lock:
            self.state = replace(self.state, **changes).normalized()
            self._save_state(self.state)
            return self.state

    @property
    def installation_id(self) -> str:
        with self._lock:
            return self.state.installation_id

    @property
    def enabled(self) -> bool:
        with self._lock:
            return self.state.enabled

    @property
    def notice_seen(self) -> bool:
        with self._lock:
            return self.state.notice_seen

    def set_enabled(self, enabled: bool) -> UsageStatsState:
        return self._replace_state(enabled=bool(enabled))

    def mark_notice_seen(self, *, enabled: bool) -> UsageStatsState:
        return self._replace_state(enabled=bool(enabled), notice_seen=True)

    def should_send_today(self) -> bool:
        with self._lock:
            return (
                self.state.enabled
                and self.state.notice_seen
                and self.state.last_successful_heartbeat != _utc_day()
            )

    def _post_json(self, url: str, payload: dict, version: str) -> int:
        if self._post_json_override is not None:
            return int(self._post_json_override(url, payload, version))
        body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        request = urllib.request.Request(
            url,
            data=body,
            method="POST",
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json",
                "User-Agent": f"DA6IT-Wavelog-Offline-Logger/{version}",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=HTTP_TIMEOUT_SECONDS) as response:
                return int(response.status)
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError) as exc:
            raise UsageStatsError(str(exc)) from exc

    def send_heartbeat(self, version: str) -> bool:
        with self._lock:
            state = self.state
        if not (
            state.enabled
            and state.notice_seen
            and state.last_successful_heartbeat != _utc_day()
        ):
            return False

        status = self._post_json(
            self.heartbeat_url,
            {
                "installation_id": state.installation_id,
                "version": str(version),
                "platform": _platform_name(),
            },
            str(version),
        )
        if status not in {200, 201, 202, 204}:
            raise UsageStatsError(f"Heartbeat wurde mit HTTP {status} abgelehnt.")

        with self._lock:
            # Do not overwrite a freshly rotated installation id.
            if self.state.installation_id == state.installation_id:
                self.state = replace(
                    self.state,
                    last_successful_heartbeat=_utc_day(),
                ).normalized()
                self._save_state(self.state)
        return True

    def forget_remote_data(self, version: str) -> str:
        with self._lock:
            previous = self.state

        status = self._post_json(
            self.forget_url,
            {"installation_id": previous.installation_id},
            str(version),
        )
        if status not in {200, 201, 202, 204}:
            raise UsageStatsError(f"Löschanfrage wurde mit HTTP {status} abgelehnt.")

        new_id = str(uuid.uuid4())
        with self._lock:
            if self.state.installation_id == previous.installation_id:
                # Do not immediately recreate a server record on the same day.
                self.state = replace(
                    self.state,
                    installation_id=new_id,
                    last_successful_heartbeat=_utc_day(),
                ).normalized()
                self._save_state(self.state)
                return self.state.installation_id
            return self.state.installation_id
