from __future__ import annotations

import json
import re
import threading
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass, fields
from typing import Any, Callable


QRZ_XML_URL = "https://xmldata.qrz.com/xml/current/"
CALLBOOK_SOURCE_WAVELOG = "wavelog"
CALLBOOK_SOURCE_QRZ = "qrz"
CALLBOOK_SOURCE_DISABLED = "disabled"


class CallbookError(RuntimeError):
    pass


@dataclass(slots=True)
class CallbookResult:
    callsign: str = ""
    name: str = ""
    qth: str = ""
    grid: str = ""
    country: str = ""
    state: str = ""
    county: str = ""
    image_url: str = ""
    profile_url: str = ""
    latitude: str = ""
    longitude: str = ""
    cq_zone: str = ""
    itu_zone: str = ""
    source: str = ""
    cached: bool = False

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False, separators=(",", ":"))

    @classmethod
    def from_json(cls, value: str) -> "CallbookResult":
        raw = json.loads(value)
        allowed = {item.name for item in fields(cls)}
        return cls(**{key: raw.get(key, "") for key in allowed})


def normalized_callsign(value: str) -> str:
    return re.sub(r"\s+", "", (value or "").upper())


def lookup_candidate(value: str) -> bool:
    call = normalized_callsign(value)
    return bool(
        3 <= len(call) <= 24
        and not call.endswith("/")
        and re.fullmatch(r"[A-Z0-9]+(?:/[A-Z0-9]+)*", call)
        and any(ch.isalpha() for ch in call)
        and any(ch.isdigit() for ch in call)
    )


def _text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (list, tuple)):
        for item in value:
            result = _text(item)
            if result:
                return result
        return ""
    return str(value).strip()


def _first(mapping: dict[str, Any], *names: str) -> str:
    lowered = {str(key).lower(): value for key, value in mapping.items()}
    for name in names:
        value = _text(lowered.get(name.lower()))
        if value:
            return value
    return ""


def normalize_wavelog_result(payload: dict[str, Any], requested_call: str = "") -> CallbookResult:
    data = payload.get("data") if isinstance(payload, dict) else {}
    if not isinstance(data, dict):
        data = {}
    callbook = data.get("callbook")
    if not isinstance(callbook, dict):
        callbook = {}

    # Wavelog's callbook providers use a largely common structure, but older
    # releases and different providers do not always expose identical keys.
    combined = dict(data)
    combined.update({key: value for key, value in callbook.items() if value not in (None, "")})
    first_name = _first(combined, "nickname", "fname", "first_name")
    last_name = _first(combined, "name_last", "last_name")
    display_name = _first(combined, "name_fmt")
    if not display_name:
        display_name = _first(combined, "name")
    if not display_name:
        display_name = " ".join(part for part in (first_name, last_name) if part).strip()

    return CallbookResult(
        callsign=normalized_callsign(_first(combined, "callsign", "call") or requested_call),
        name=display_name,
        qth=_first(combined, "city", "location", "addr2", "qth"),
        grid=_first(combined, "gridsquare", "grid")[:8].upper(),
        country=_first(combined, "land", "country", "dxcc"),
        state=_first(combined, "state"),
        county=_first(combined, "us_county", "county"),
        image_url=_first(combined, "image", "image_url", "picture"),
        profile_url=_first(combined, "url", "profile_url"),
        latitude=_first(combined, "lat", "latitude"),
        longitude=_first(combined, "lon", "long", "longitude"),
        cq_zone=_first(combined, "cqz", "cqzone", "dxcc_cqz"),
        itu_zone=_first(combined, "ituz", "ituzone", "dxcc_ituz"),
        source="Wavelog" + (f" / {_first(callbook, 'source')}" if _first(callbook, "source") else ""),
    )


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _children(element: ET.Element | None) -> dict[str, str]:
    if element is None:
        return {}
    return {_local_name(child.tag).lower(): (child.text or "").strip() for child in element}


def parse_qrz_xml(xml_bytes: bytes, requested_call: str = "") -> tuple[CallbookResult | None, dict[str, str]]:
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError as exc:
        raise CallbookError("QRZ.com hat keine gültige XML-Antwort geliefert") from exc
    callsign_node = next((node for node in root.iter() if _local_name(node.tag).lower() == "callsign"), None)
    session_node = next((node for node in root.iter() if _local_name(node.tag).lower() == "session"), None)
    session = _children(session_node)
    if callsign_node is None:
        return None, session
    row = _children(callsign_node)
    name = row.get("nickname") or row.get("fname") or row.get("name_fmt") or row.get("name") or ""
    result = CallbookResult(
        callsign=normalized_callsign(row.get("call") or requested_call),
        name=name.strip(),
        qth=(row.get("addr2") or "").strip(),
        grid=(row.get("grid") or "")[:8].upper(),
        country=(row.get("land") or row.get("country") or "").strip(),
        state=(row.get("state") or "").strip(),
        county=(row.get("county") or "").strip(),
        image_url=(row.get("image") or "").strip(),
        profile_url=(row.get("url") or "").strip(),
        latitude=(row.get("lat") or "").strip(),
        longitude=(row.get("lon") or "").strip(),
        cq_zone=(row.get("cqzone") or "").strip(),
        itu_zone=(row.get("ituzone") or "").strip(),
        source="QRZ.com",
    )
    return result, session


class QrzClient:
    def __init__(
        self,
        username: str,
        password: str,
        *,
        timeout: int = 8,
        opener: Callable[..., Any] | None = None,
        agent: str = "DA6IT.de-Wavelog-Offline-Logger",
    ):
        self.username = (username or "").strip()
        self.password = password or ""
        self.timeout = timeout
        self.opener = opener or urllib.request.urlopen
        self.agent = agent
        self.session_key = ""
        self._lock = threading.Lock()

    def _request(self, params: dict[str, str], *, post: bool = False) -> bytes:
        encoded = urllib.parse.urlencode(params).encode("utf-8")
        url = QRZ_XML_URL if post else QRZ_XML_URL + "?" + encoded.decode("ascii")
        request = urllib.request.Request(
            url,
            data=encoded if post else None,
            headers={"User-Agent": self.agent, "Accept": "application/xml"},
            method="POST" if post else "GET",
        )
        try:
            with self.opener(request, timeout=self.timeout) as response:
                return response.read()
        except urllib.error.HTTPError as exc:
            raise CallbookError(f"QRZ.com HTTP {exc.code}") from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            reason = getattr(exc, "reason", exc)
            raise CallbookError(f"QRZ.com ist nicht erreichbar: {reason}") from exc

    def login(self) -> str:
        if not self.username or not self.password:
            raise CallbookError("QRZ.com Benutzername und Passwort fehlen")
        raw = self._request(
            {"username": self.username, "password": self.password, "agent": self.agent},
            post=True,
        )
        _result, session = parse_qrz_xml(raw)
        key = session.get("key", "")
        if not key:
            raise CallbookError(session.get("error") or session.get("message") or "QRZ.com Anmeldung fehlgeschlagen")
        self.session_key = key
        return key

    def lookup(self, callsign: str) -> CallbookResult:
        with self._lock:
            return self._lookup_locked(callsign)

    def _lookup_locked(self, callsign: str) -> CallbookResult:
        call = normalized_callsign(callsign)
        if not lookup_candidate(call):
            raise CallbookError("Ungültiges oder unvollständiges Rufzeichen")
        for attempt in range(2):
            if not self.session_key:
                self.login()
            raw = self._request({"s": self.session_key, "callsign": call, "agent": self.agent})
            result, session = parse_qrz_xml(raw, call)
            if result is not None:
                return result
            error = session.get("error") or session.get("message") or "Rufzeichen bei QRZ.com nicht gefunden"
            if attempt == 0 and any(word in error.lower() for word in ("session", "timeout", "key", "expired")):
                self.session_key = ""
                continue
            raise CallbookError(error)
        raise CallbookError("QRZ.com Sitzung konnte nicht erneuert werden")
