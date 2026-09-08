from __future__ import annotations

import json
import secrets
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from logger_core import USER_AGENT, secure_urlopen


QSL_API_BASE = "https://da6it.de/wp-json/da6it/v1/qsl/client/v1/"
QSL_CONTRACT = "da6it-qsl-client-v1"

MAX_RESPONSE_BYTES = 2 * 1024 * 1024
MAX_ERROR_BYTES = 16 * 1024
MAX_QSO_BATCH = 1000


class QslClientError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        error_code: str = "",
    ):
        super().__init__(message)
        self.status_code = status_code
        self.error_code = str(error_code or "").strip()


class QslClient:
    """Client for the fixed DA6IT.de QSL Card Manager API."""

    def __init__(self, connection_key: str, *, timeout: int = 15):
        self.connection_key = (connection_key or "").strip()
        self.timeout = max(1, int(timeout))

    @staticmethod
    def _endpoint_url(endpoint: str) -> str:
        endpoint = (endpoint or "").strip().lstrip("/")

        if (
            not endpoint
            or endpoint.startswith("../")
            or "://" in endpoint
            or "?" in endpoint
            or "#" in endpoint
        ):
            raise QslClientError("Ungültiger QSL-API-Endpunkt")

        return QSL_API_BASE + endpoint

    @staticmethod
    def _validate_final_url(url: str) -> None:
        base = urllib.parse.urlsplit(QSL_API_BASE)
        final = urllib.parse.urlsplit(url)

        def origin(parts: urllib.parse.SplitResult) -> tuple[str, str, int]:
            scheme = (parts.scheme or "").lower()
            host = (parts.hostname or "").lower().rstrip(".")

            try:
                port = parts.port
            except ValueError as exc:
                raise QslClientError(
                    "Ungültige Antwort-URL der QSL API"
                ) from exc

            if port is None:
                port = 443 if scheme == "https" else 80

            return scheme, host, port

        if (
            origin(final) != origin(base)
            or not final.path.startswith(base.path)
        ):
            raise QslClientError(
                "QSL API hat auf ein unerwartetes Ziel umgeleitet"
            )

    def _safe_message(self, value: object) -> str:
        text = " ".join(str(value or "").split())

        if self.connection_key:
            text = text.replace(self.connection_key, "[redacted]")

        return text[:400]

    def _http_error(
        self,
        exc: urllib.error.HTTPError,
    ) -> QslClientError:
        try:
            raw = exc.read(MAX_ERROR_BYTES + 1)
        except Exception:
            raw = b""

        message = ""
        error_code = ""

        if raw:
            try:
                payload = json.loads(
                    raw[:MAX_ERROR_BYTES].decode(
                        "utf-8",
                        errors="replace",
                    )
                )

                if isinstance(payload, dict):
                    error_code = str(
                        payload.get("code")
                        or ""
                    ).strip()
                    message = str(
                        payload.get("message")
                        or error_code
                        or ""
                    )

            except (ValueError, TypeError):
                message = raw[:MAX_ERROR_BYTES].decode(
                    "utf-8",
                    errors="replace",
                )

        message = self._safe_message(message)
        suffix = f": {message}" if message else ""

        return QslClientError(
            f"QSL API HTTP {exc.code}{suffix}",
            status_code=int(exc.code),
            error_code=error_code,
        )

    def _request_once(
        self,
        endpoint: str,
        *,
        fallback_header: bool,
        method: str = "GET",
        payload: dict[str, Any] | None = None,
        query: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if not self.connection_key:
            raise QslClientError("Connection Key fehlt")

        method = str(method or "GET").strip().upper()

        if method not in {"GET", "POST", "DELETE"}:
            raise QslClientError("Nicht unterstützte QSL-API-Methode")

        url = self._endpoint_url(endpoint)

        if query:
            encoded_query = urllib.parse.urlencode(
                {
                    str(key): value
                    for key, value in query.items()
                    if value not in (None, "")
                }
            )
            if encoded_query:
                url += "?" + encoded_query

        headers = {
            "Accept": "application/json",
            "User-Agent": USER_AGENT,
        }

        if fallback_header:
            headers["X-DA6IT-QSL-Token"] = self.connection_key
        else:
            headers["Authorization"] = f"Bearer {self.connection_key}"

        body = None

        if payload is not None:
            try:
                body = json.dumps(
                    payload,
                    ensure_ascii=False,
                    separators=(",", ":"),
                ).encode("utf-8")
            except (TypeError, ValueError) as exc:
                raise QslClientError(
                    "QSL-API-Payload kann nicht als JSON gesendet werden"
                ) from exc

            headers["Content-Type"] = "application/json; charset=utf-8"

        request = urllib.request.Request(
            url,
            data=body,
            headers=headers,
            method=method,
        )

        try:
            with secure_urlopen(
                request,
                timeout=self.timeout,
            ) as response:
                self._validate_final_url(response.geturl())
                raw = response.read(MAX_RESPONSE_BYTES + 1)

        except urllib.error.HTTPError as exc:
            raise self._http_error(exc) from exc

        except urllib.error.URLError as exc:
            reason = self._safe_message(
                getattr(exc, "reason", exc)
            )

            raise QslClientError(
                f"QSL API nicht erreichbar: {reason}"
            ) from exc

        except (OSError, TimeoutError, ValueError) as exc:
            raise QslClientError(
                "QSL API nicht erreichbar: "
                f"{self._safe_message(exc)}"
            ) from exc

        if len(raw) > MAX_RESPONSE_BYTES:
            raise QslClientError(
                "Antwort der QSL API ist unerwartet groß"
            )

        try:
            decoded = raw.decode("utf-8")
            parsed = json.loads(decoded) if decoded.strip() else {}

        except (UnicodeDecodeError, ValueError) as exc:
            raise QslClientError(
                "QSL API hat keine gültige JSON-Antwort geliefert"
            ) from exc

        if not isinstance(parsed, dict):
            raise QslClientError(
                "QSL API hat ein ungültiges Antwortformat geliefert"
            )

        return parsed

    def _request_json(
        self,
        endpoint: str,
        *,
        method: str = "GET",
        payload: dict[str, Any] | None = None,
        query: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        try:
            return self._request_once(
                endpoint,
                fallback_header=False,
                method=method,
                payload=payload,
                query=query,
            )

        except QslClientError as exc:
            if exc.status_code not in {401, 403}:
                raise

        return self._request_once(
            endpoint,
            fallback_header=True,
            method=method,
            payload=payload,
            query=query,
        )

    def bootstrap(self) -> dict[str, Any]:
        payload = self._request_json("bootstrap")

        contract = str(
            payload.get("contract") or ""
        ).strip()

        if contract != QSL_CONTRACT:
            raise QslClientError(
                "QSL API Contract stimmt nicht: "
                f"erwartet {QSL_CONTRACT}, "
                f"erhalten {contract or '—'}"
            )

        return payload

    def list_qsos(
        self,
        *,
        page: int = 1,
        per_page: int = 100,
        status: str = "",
        search: str = "",
        band: str = "",
        mode: str = "",
        date_from: str = "",
        date_to: str = "",
        recent: int | str | None = None,
    ) -> dict[str, Any]:
        page = max(1, int(page))
        per_page = max(10, min(int(per_page), 500))

        return self._request_json(
            "qsos",
            query={
                "page": page,
                "per_page": per_page,
                "status": str(status or "").strip(),
                "search": str(search or "").strip(),
                "band": str(band or "").strip(),
                "mode": str(mode or "").strip(),
                "date_from": str(date_from or "").strip(),
                "date_to": str(date_to or "").strip(),
                "recent": recent,
            },
        )

    def upsert_qsos(
        self,
        records: list[dict[str, Any]],
    ) -> dict[str, Any]:
        if not isinstance(records, list) or not records:
            raise QslClientError(
                "Für qsos/upsert wird mindestens ein QSO benötigt"
            )

        if len(records) > MAX_QSO_BATCH:
            raise QslClientError(
                f"qsos/upsert erlaubt maximal {MAX_QSO_BATCH} QSOs pro Request"
            )

        if any(not isinstance(record, dict) for record in records):
            raise QslClientError(
                "Jeder QSO-Upsert-Datensatz muss ein Objekt sein"
            )

        return self._request_json(
            "qsos/upsert",
            method="POST",
            payload={"records": records},
        )

    def qso_status(
        self,
        qso_uids: list[str],
    ) -> dict[str, Any]:
        if not isinstance(qso_uids, list) or not qso_uids:
            raise QslClientError(
                "Für qsos/status wird mindestens eine qsoUid benötigt"
            )

        if len(qso_uids) > MAX_QSO_BATCH:
            raise QslClientError(
                f"qsos/status erlaubt maximal {MAX_QSO_BATCH} qsoUids pro Request"
            )

        normalized = []

        for value in qso_uids:
            qso_uid = str(value or "").strip()

            if not qso_uid:
                raise QslClientError(
                    "Leere qsoUid in qsos/status"
                )

            normalized.append(qso_uid)

        return self._request_json(
            "qsos/status",
            method="POST",
            payload={"qso_uids": normalized},
        )

    def _request_multipart_once(
        self,
        endpoint: str,
        fallback_header: bool,
        *,
        fields: dict[str, str],
        file_name: str,
        file_bytes: bytes,
    ) -> dict[str, Any]:
        url = self._endpoint_url(
            endpoint
        )

        boundary = (
            "----DA6ITQSL"
            + secrets.token_hex(16)
        )

        chunks: list[bytes] = []

        for name, value in fields.items():
            chunks.extend(
                [
                    (
                        f"--{boundary}\r\n"
                        f'Content-Disposition: form-data; name="{name}"\r\n'
                        "\r\n"
                    ).encode("utf-8"),
                    str(value).encode("utf-8"),
                    b"\r\n",
                ]
            )

        chunks.extend(
            [
                (
                    f"--{boundary}\r\n"
                    f'Content-Disposition: form-data; name="file"; '
                    f'filename="{file_name}"\r\n'
                    "Content-Type: image/png\r\n"
                    "\r\n"
                ).encode("utf-8"),
                bytes(file_bytes),
                b"\r\n",
                (
                    f"--{boundary}--\r\n"
                ).encode("utf-8"),
            ]
        )

        body = b"".join(
            chunks
        )

        headers = {
            "Accept": "application/json",
            "User-Agent": USER_AGENT,
            "Content-Type": (
                "multipart/form-data; "
                f"boundary={boundary}"
            ),
        }

        if fallback_header:
            headers[
                "X-DA6IT-QSL-Token"
            ] = self.connection_key
        else:
            headers[
                "Authorization"
            ] = (
                "Bearer "
                + self.connection_key
            )

        request = urllib.request.Request(
            url,
            data=body,
            headers=headers,
            method="POST",
        )

        try:
            with secure_urlopen(
                request,
                timeout=self.timeout,
            ) as response:
                self._validate_final_url(
                    response.geturl()
                )

                raw = response.read(
                    MAX_RESPONSE_BYTES + 1
                )

                if len(raw) > MAX_RESPONSE_BYTES:
                    raise QslClientError(
                        "QSL API Antwort ist zu groß"
                    )

        except urllib.error.HTTPError as exc:
            raise self._http_error(
                exc
            ) from exc
        except urllib.error.URLError as exc:
            raise QslClientError(
                "QSL API ist nicht erreichbar"
            ) from exc

        try:
            payload = json.loads(
                raw.decode("utf-8")
            )
        except (
            UnicodeDecodeError,
            json.JSONDecodeError,
        ) as exc:
            raise QslClientError(
                "QSL API liefert ungültiges JSON"
            ) from exc

        if not isinstance(
            payload,
            dict,
        ):
            raise QslClientError(
                "QSL API Antwort muss ein Objekt sein"
            )

        return payload

    def _request_multipart(
        self,
        endpoint: str,
        *,
        fields: dict[str, str],
        file_name: str,
        file_bytes: bytes,
    ) -> dict[str, Any]:
        try:
            return self._request_multipart_once(
                endpoint,
                False,
                fields=fields,
                file_name=file_name,
                file_bytes=file_bytes,
            )
        except QslClientError as exc:
            if exc.status_code not in (
                401,
                403,
            ):
                raise

        return self._request_multipart_once(
            endpoint,
            True,
            fields=fields,
            file_name=file_name,
            file_bytes=file_bytes,
        )

    def templates(
        self,
        station_profile: str,
    ) -> dict[str, Any]:
        station_profile = str(
            station_profile or ""
        ).strip().upper()

        if not station_profile:
            raise QslClientError(
                "Für templates wird ein Stationsprofil benötigt"
            )

        if len(station_profile) > 40:
            raise QslClientError(
                "Stationsprofil ist zu lang"
            )

        return self._request_json(
            "templates",
            method="GET",
            query={
                "station_profile": station_profile,
            },
        )

    def upload_card(
        self,
        qso_uid: str,
        template_id: int,
        png_bytes: bytes,
    ) -> dict[str, Any]:
        qso_uid = str(
            qso_uid or ""
        ).strip()

        if not qso_uid:
            raise QslClientError(
                "Für cards wird eine qsoUid benötigt"
            )

        try:
            template_id = int(
                template_id
            )
        except (
            TypeError,
            ValueError,
        ) as exc:
            raise QslClientError(
                "Ungültige Template-ID"
            ) from exc

        if template_id < 1:
            raise QslClientError(
                "Ungültige Template-ID"
            )

        png_bytes = bytes(
            png_bytes
        )

        if (
            not png_bytes.startswith(
                b"\x89PNG\r\n\x1a\n"
            )
            or len(png_bytes)
            > 15 * 1024 * 1024
        ):
            raise QslClientError(
                "Ungültige oder zu große QSL-PNG-Datei"
            )

        return self._request_multipart(
            "cards",
            fields={
                "qso_uid": qso_uid,
                "template_id": str(
                    template_id
                ),
            },
            file_name="qsl.png",
            file_bytes=png_bytes,
        )

    def mail_send(
        self,
        qso_uid: str,
    ) -> dict[str, Any]:
        qso_uid = str(
            qso_uid or ""
        ).strip()

        if not qso_uid:
            raise QslClientError(
                "Für mail/send wird eine qsoUid benötigt"
            )

        return self._request_json(
            "mail/send",
            method="POST",
            payload={
                "qso_uid": qso_uid,
            },
        )

    def mail_queue(
        self,
        qso_uids: list[str],
    ) -> dict[str, Any]:
        normalized: list[str] = []

        for raw in qso_uids:
            uid = str(raw or "").strip()
            if not uid or uid in normalized:
                continue
            normalized.append(uid)

        if not normalized:
            raise QslClientError(
                "Für mail/queue wird mindestens eine qsoUid benötigt"
            )

        return self._request_json(
            "mail/queue",
            method="POST",
            payload={
                "qso_uids": normalized,
            },
        )

    def queue_status(
        self,
        *,
        job_id: str = "",
        limit: int = 100,
    ) -> dict[str, Any]:
        limit = max(1, min(int(limit), 500))
        query: dict[str, Any] = {
            "limit": limit,
        }

        job_id = str(job_id or "").strip()
        if job_id:
            query["job_id"] = job_id

        return self._request_json(
            "mail/queue",
            method="GET",
            query=query,
        )

    def control_copy(
        self,
    ) -> dict[str, Any]:
        return self._request_json(
            "mail/copy",
            method="GET",
        )

    def set_control_copy(
        self,
        enabled: bool,
        email: str,
    ) -> dict[str, Any]:
        email = str(email or "").strip()
        return self._request_json(
            "mail/copy",
            method="POST",
            payload={
                "enabled": bool(enabled),
                "email": email,
            },
        )

    def qrz_recipient(
        self,
        qso_uid: str,
    ) -> dict[str, Any]:
        qso_uid = str(qso_uid or "").strip()

        if not qso_uid:
            raise QslClientError(
                "Für qrz wird eine qsoUid benötigt"
            )

        return self._request_json(
            "qrz",
            method="POST",
            payload={"qso_uid": qso_uid},
        )
