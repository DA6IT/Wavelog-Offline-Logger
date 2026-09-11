from __future__ import annotations

import calendar
import csv
import io
import re
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Mapping


EQSL_MEMBER_LIST_URL = "https://www.eqsl.cc/DownloadedFiles/eQSLMemberList.csv"
EQSL_CACHE_MAX_AGE = timedelta(hours=24)
EQSL_INACTIVE_MONTHS = 6
MAX_DOWNLOAD_BYTES = 20 * 1024 * 1024
MIN_EXPECTED_MEMBERS = 1000
_EQSL_ALLOWED_HOSTS = frozenset({"eqsl.cc", "www.eqsl.cc"})

_CALL_RE = re.compile(r"^[A-Z0-9][A-Z0-9/.\-]{1,31}$")
_CALL_HEADERS = {
    "call",
    "callsign",
    "callsignid",
    "callssid",
}
_DATE_HEADERS = {
    "lastlogupdate",
    "lastlogdate",
    "lastupload",
    "lastuploaddate",
    "lastadifupload",
    "lastadifdate",
    "lastqso",
    "lastqsodate",
}


class EqslMemberListError(RuntimeError):
    pass


def _validate_eqsl_https_url(value: str) -> str:
    url = str(value or "").strip()

    try:
        parsed = urllib.parse.urlsplit(url)
        port = parsed.port
    except ValueError as exc:
        raise EqslMemberListError(
            "eQSL-Mitgliederliste verwendet eine ungültige URL"
        ) from exc

    host = (parsed.hostname or "").lower()

    if (
        parsed.scheme.lower() != "https"
        or host not in _EQSL_ALLOWED_HOSTS
        or port not in {None, 443}
        or parsed.username is not None
        or parsed.password is not None
    ):
        raise EqslMemberListError(
            "eQSL-Mitgliederliste darf nur von den freigegebenen HTTPS-Hosts geladen werden"
        )

    return url


class _EqslHttpsRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(
        self,
        req,
        fp,
        code,
        msg,
        headers,
        newurl,
    ):
        _validate_eqsl_https_url(newurl)
        return super().redirect_request(
            req,
            fp,
            code,
            msg,
            headers,
            newurl,
        )


@dataclass(frozen=True)
class EqslMemberIndex:
    members: Mapping[str, date | None]

    def classify(
        self,
        callsign: str,
        *,
        today: date | None = None,
    ) -> tuple[str, date | None]:
        call = normalize_callsign(callsign)

        if not call or call not in self.members:
            return "missing", None

        last_upload = self.members[call]

        if last_upload is None:
            return "inactive", None

        reference = today or datetime.now(timezone.utc).date()
        cutoff = subtract_months(reference, EQSL_INACTIVE_MONTHS)

        if last_upload < cutoff:
            return "inactive", last_upload

        return "active", last_upload


@dataclass(frozen=True)
class EqslLoadResult:
    index: EqslMemberIndex
    cache_time: datetime
    downloaded: bool
    stale_fallback: bool
    error: str = ""


def normalize_callsign(value: object) -> str:
    call = str(value or "").strip().upper()
    if not _CALL_RE.fullmatch(call):
        return ""
    return call


def subtract_months(value: date, months: int) -> date:
    months = max(0, int(months))
    month_index = value.year * 12 + (value.month - 1) - months
    year, month_zero = divmod(month_index, 12)
    month = month_zero + 1
    day = min(value.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def parse_member_date(value: object) -> date | None:
    raw = str(value or "").strip()

    if not raw or raw in {"0000-00-00", "00000000", "0"}:
        return None

    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y%m%d"):
        try:
            return datetime.strptime(raw[:10], fmt).date()
        except ValueError:
            continue

    return None


def _header_key(value: object) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value or "").strip().lower())


def _decode_csv(data: bytes) -> str:
    if not isinstance(data, (bytes, bytearray)):
        raise EqslMemberListError("eQSL-Mitgliederliste enthält keine Bytes")

    raw = bytes(data)

    if len(raw) > MAX_DOWNLOAD_BYTES:
        raise EqslMemberListError("eQSL-Mitgliederliste ist unerwartet groß")

    for encoding in ("utf-8-sig", "cp1252"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue

    raise EqslMemberListError("eQSL-Mitgliederliste hat eine unbekannte Zeichenkodierung")


def parse_member_csv(data: bytes) -> EqslMemberIndex:
    text = _decode_csv(data)
    rows = csv.reader(io.StringIO(text))

    try:
        first = next(rows)
    except StopIteration as exc:
        raise EqslMemberListError("eQSL-Mitgliederliste ist leer") from exc

    if not first:
        raise EqslMemberListError("eQSL-Mitgliederliste enthält keine Spalten")

    header = [_header_key(value) for value in first]
    call_index = next(
        (index for index, value in enumerate(header) if value in _CALL_HEADERS),
        None,
    )
    date_index = next(
        (index for index, value in enumerate(header) if value in _DATE_HEADERS),
        None,
    )

    has_header = call_index is not None

    if not has_header:
        call_index = 0
        date_index = len(first) - 1
        iterable = [first]
        iterable.extend(rows)
    else:
        if date_index is None:
            date_index = len(first) - 1
        iterable = rows

    members: dict[str, date | None] = {}

    for row in iterable:
        if not row or call_index >= len(row):
            continue

        call = normalize_callsign(row[call_index])
        if not call:
            continue

        raw_date = row[date_index] if date_index < len(row) else ""
        last_upload = parse_member_date(raw_date)

        if call not in members:
            members[call] = last_upload
            continue

        previous = members[call]
        if previous is None or (
            last_upload is not None and last_upload > previous
        ):
            members[call] = last_upload

    if not members:
        raise EqslMemberListError("eQSL-Mitgliederliste enthält keine gültigen Rufzeichen")

    return EqslMemberIndex(members)


class EqslMemberCache:
    def __init__(self, data_dir: Path):
        self.cache_dir = Path(data_dir) / "qsl-cache" / "eqsl"
        self.path = self.cache_dir / "eQSLMemberList.csv"

    def _cache_time(self) -> datetime:
        try:
            return datetime.fromtimestamp(
                self.path.stat().st_mtime,
                tz=timezone.utc,
            )
        except OSError:
            return datetime.fromtimestamp(0, tz=timezone.utc)

    def _load_cached(self) -> EqslMemberIndex:
        try:
            data = self.path.read_bytes()
        except OSError as exc:
            raise EqslMemberListError(
                "Lokale eQSL-Mitgliederliste konnte nicht gelesen werden"
            ) from exc

        return parse_member_csv(data)

    def _cache_is_fresh(self, now: datetime) -> bool:
        if not self.path.is_file():
            return False

        age = now - self._cache_time()
        return timedelta(0) <= age <= EQSL_CACHE_MAX_AGE

    def _download(self) -> bytes:
        url = _validate_eqsl_https_url(EQSL_MEMBER_LIST_URL)
        request = urllib.request.Request(
            url,
            headers={
                "User-Agent": "DA6IT-Wavelog-Offline-Logger/eQSL-member-cache",
                "Accept": "text/csv,text/plain,application/octet-stream,*/*;q=0.5",
            },
            method="GET",
        )
        opener = urllib.request.build_opener(
            _EqslHttpsRedirectHandler(),
        )

        with opener.open(request, timeout=15) as response:
            # Defense in depth: the redirect handler validates every redirect
            # before it is followed; verify the final URL once more as well.
            _validate_eqsl_https_url(response.geturl())

            length = response.headers.get("Content-Length")
            if length:
                try:
                    if int(length) > MAX_DOWNLOAD_BYTES:
                        raise EqslMemberListError(
                            "eQSL-Mitgliederliste ist unerwartet groß"
                        )
                except ValueError:
                    pass

            data = response.read(MAX_DOWNLOAD_BYTES + 1)

        if len(data) > MAX_DOWNLOAD_BYTES:
            raise EqslMemberListError("eQSL-Mitgliederliste ist unerwartet groß")

        return data

    def refresh(self, *, force: bool = False) -> EqslLoadResult:
        now = datetime.now(timezone.utc)

        if not force and self._cache_is_fresh(now):
            return EqslLoadResult(
                index=self._load_cached(),
                cache_time=self._cache_time(),
                downloaded=False,
                stale_fallback=False,
            )

        old_available = self.path.is_file()

        try:
            data = self._download()
            index = parse_member_csv(data)

            if len(index.members) < MIN_EXPECTED_MEMBERS:
                raise EqslMemberListError(
                    "eQSL-Mitgliederliste enthält unerwartet wenige Einträge"
                )

            self.cache_dir.mkdir(parents=True, exist_ok=True)
            temporary = self.path.with_suffix(".csv.tmp")
            temporary.write_bytes(data)
            temporary.replace(self.path)

            return EqslLoadResult(
                index=index,
                cache_time=self._cache_time(),
                downloaded=True,
                stale_fallback=False,
            )
        except Exception as exc:
            if not old_available:
                if isinstance(exc, EqslMemberListError):
                    raise
                raise EqslMemberListError(str(exc)) from exc

            try:
                index = self._load_cached()
            except Exception:
                if isinstance(exc, EqslMemberListError):
                    raise
                raise EqslMemberListError(str(exc)) from exc

            return EqslLoadResult(
                index=index,
                cache_time=self._cache_time(),
                downloaded=False,
                stale_fallback=True,
                error=str(exc),
            )
