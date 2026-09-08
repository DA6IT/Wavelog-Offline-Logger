from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from qsl_client import QslClientError
from qsl_renderer import (
    QslAssetCache,
    qso_designer_values,
    render_qsl_png,
)
from qsl_storage import (
    QslStorage,
    QslStorageError,
    normalize_qso_uid,
)
from qsl_sync import sync_qsos


class QslDeliveryError(RuntimeError):
    pass


@dataclass(frozen=True)
class QslDeliveryResult:
    qso_uid: str
    template_id: int
    template_name: str
    recipient: str
    sent_at: str
    card_expires_at: str


class QslQueueError(QslDeliveryError):
    pass


@dataclass(frozen=True)
class QslQueueResult:
    requested: int
    prepared: int
    failed: int
    job_id: str
    queued: int
    skipped: int
    no_email: int
    recipient_pending: int
    cooldown: int
    missing_card: int
    failures: tuple[str, ...]
    qso_uids: tuple[str, ...]


def _same_uid(
    value: Any,
    expected: str,
    *,
    source: str,
) -> str:
    raw = str(
        value or expected
    ).strip()

    try:
        normalized = normalize_qso_uid(
            raw
        )
    except QslStorageError as exc:
        raise QslDeliveryError(
            f"{source} liefert eine ungültige qsoUid"
        ) from exc

    if normalized != expected:
        raise QslDeliveryError(
            f"{source} liefert eine fremde qsoUid"
        )

    return normalized


def ensure_qso_uid(
    client,
    storage: QslStorage,
    qso: dict[str, Any],
) -> str:
    local_id = str(
        qso.get("local_id")
        or ""
    ).strip()

    if not local_id:
        raise QslDeliveryError(
            "Lokales QSO hat keine local_id"
        )

    existing = storage.qso_uid_for_local(
        local_id
    )

    if existing:
        return normalize_qso_uid(
            existing
        )

    try:
        sync_qsos(
            client,
            storage,
            [qso],
        )
    except Exception as exc:
        raise QslDeliveryError(
            "QSO hat noch keine qsoUid und konnte "
            "nicht automatisch synchronisiert werden: "
            + str(exc)
        ) from exc

    qso_uid = storage.qso_uid_for_local(
        local_id
    )

    if not qso_uid:
        raise QslDeliveryError(
            "QSO hat noch keine qsoUid und der Server "
            "hat nach der automatischen Synchronisierung "
            "keine Zuordnung geliefert."
        )

    return normalize_qso_uid(
        qso_uid
    )


def refresh_qsl_status(
    client,
    storage: QslStorage,
    qso_uid: str,
) -> dict[str, Any]:
    qso_uid = normalize_qso_uid(
        qso_uid
    )

    response = client.qso_status(
        [qso_uid]
    )

    if not isinstance(
        response,
        dict,
    ):
        raise QslDeliveryError(
            "qsos/status hat kein Objekt geliefert"
        )

    statuses = response.get(
        "statuses"
    )

    if not isinstance(
        statuses,
        dict,
    ):
        raise QslDeliveryError(
            "qsos/status enthält keine statuses-Map"
        )

    status = statuses.get(
        qso_uid
    )

    if not isinstance(
        status,
        dict,
    ):
        raise QslDeliveryError(
            "qsos/status enthält keinen Zustand für die qsoUid"
        )

    _same_uid(
        status.get("qsoUid"),
        qso_uid,
        source="qsos/status",
    )

    storage.set_status_snapshot(
        qso_uid,
        status,
    )

    return status


def render_selected_qsl(
    template: dict[str, Any],
    qso: dict[str, Any],
    *,
    cache_root: Path,
) -> bytes:
    canvas = template.get(
        "canvas"
    )

    canvas = (
        canvas
        if isinstance(
            canvas,
            dict,
        )
        else {}
    )

    background = canvas.get(
        "background"
    )

    background = (
        background
        if isinstance(
            background,
            dict,
        )
        else {}
    )

    background_url = str(
        background.get(
            "url",
            "",
        )
        or ""
    ).strip()

    background_bytes = None

    if background_url:
        background_bytes = (
            QslAssetCache(
                cache_root
            ).get_background_bytes(
                background_url
            )
        )

    return render_qsl_png(
        template,
        qso_designer_values(
            qso
        ),
        background_bytes=background_bytes,
    )


def _prepare_qsl_card_for_queue(
    client,
    storage: QslStorage,
    qso: dict[str, Any],
    template: dict[str, Any],
    *,
    cache_root: Path,
) -> str:
    local_id = str(
        qso.get("local_id") or ""
    ).strip()

    if not local_id:
        raise QslQueueError(
            "Lokales QSO hat keine local_id"
        )

    try:
        qso_uid = ensure_qso_uid(
            client,
            storage,
            qso,
        )
    except QslDeliveryError as exc:
        raise QslQueueError(
            str(exc)
        ) from exc

    try:
        template_id = int(
            template.get("id", 0)
        )
    except (TypeError, ValueError) as exc:
        raise QslQueueError(
            "Ungültige Template-ID"
        ) from exc

    if template_id < 1:
        raise QslQueueError(
            "Ungültige Template-ID"
        )

    png_bytes = render_selected_qsl(
        template,
        qso,
        cache_root=cache_root,
    )

    result = client.upload_card(
        qso_uid,
        template_id,
        png_bytes,
    )

    if not isinstance(result, dict):
        raise QslQueueError(
            "QSL-Karten-Upload hat kein Objekt geliefert"
        )

    _same_uid(
        result.get("qsoUid"),
        qso_uid,
        source="POST cards",
    )

    if str(
        result.get("status", "")
    ).strip().lower() != "generated":
        raise QslQueueError(
            "Server hat QSL-Karte nicht als generated bestätigt"
        )

    try:
        refresh_qsl_status(
            client,
            storage,
            qso_uid,
        )
    except Exception:
        # Card upload already succeeded. Queue creation is still allowed;
        # status refresh is only local convenience.
        pass

    return qso_uid


def queue_qsl_batch(
    client,
    storage: QslStorage,
    qsos: list[dict[str, Any]],
    template: dict[str, Any],
    *,
    cache_root: Path,
    max_batch: int,
) -> QslQueueResult:
    requested = len(qsos)
    max_batch = max(1, int(max_batch))

    if requested < 2:
        raise QslQueueError(
            "Batch-Queue benötigt mindestens zwei QSOs"
        )

    if requested > max_batch:
        raise QslQueueError(
            f"Auswahl überschreitet das Server-Queue-Limit von {max_batch} QSOs"
        )

    prepared_uids: list[str] = []
    failures: list[str] = []

    for qso in qsos:
        call = str(
            qso.get("call") or "—"
        ).strip().upper()

        try:
            uid = _prepare_qsl_card_for_queue(
                client,
                storage,
                qso,
                template,
                cache_root=cache_root,
            )
            prepared_uids.append(uid)
        except Exception as exc:
            failures.append(
                f"{call}: {exc}"
            )

    if not prepared_uids:
        raise QslQueueError(
            "Für keines der ausgewählten QSOs konnte eine QSL-Karte vorbereitet werden"
        )

    response = client.mail_queue(
        prepared_uids
    )

    if not isinstance(response, dict):
        raise QslQueueError(
            "mail/queue hat kein Objekt geliefert"
        )

    job_id = str(
        response.get("jobId") or ""
    ).strip()

    if not job_id:
        raise QslQueueError(
            "Server hat keine Queue-Job-ID geliefert"
        )

    def number(name: str) -> int:
        try:
            return max(0, int(response.get(name, 0)))
        except (TypeError, ValueError):
            return 0

    return QslQueueResult(
        requested=requested,
        prepared=len(prepared_uids),
        failed=len(failures),
        job_id=job_id,
        queued=number("queued"),
        skipped=number("skipped"),
        no_email=number("no_email"),
        recipient_pending=number("recipient_pending"),
        cooldown=number("cooldown"),
        missing_card=number("missing_card"),
        failures=tuple(failures),
        qso_uids=tuple(prepared_uids),
    )


def send_single_qsl(
    client,
    storage: QslStorage,
    qso: dict[str, Any],
    template: dict[str, Any],
    *,
    cache_root: Path,
) -> QslDeliveryResult:
    local_id = str(
        qso.get("local_id")
        or ""
    ).strip()

    if not local_id:
        raise QslDeliveryError(
            "Lokales QSO hat keine local_id"
        )

    qso_uid = ensure_qso_uid(
        client,
        storage,
        qso,
    )

    try:
        template_id = int(
            template.get(
                "id",
                0,
            )
        )
    except (
        TypeError,
        ValueError,
    ) as exc:
        raise QslDeliveryError(
            "Das ausgewählte QSL-Motiv hat keine gültige Template-ID"
        ) from exc

    if template_id < 1:
        raise QslDeliveryError(
            "Das ausgewählte QSL-Motiv hat keine gültige Template-ID"
        )

    template_name = str(
        template.get(
            "name",
            "QSL Template",
        )
        or "QSL Template"
    ).strip()[:80]

    # Check the server-authoritative recipient before spending time rendering
    # and uploading a card. The server may reuse its fresh QRZ cache.
    recipient_result = client.qrz_recipient(
        qso_uid
    )

    if not isinstance(
        recipient_result,
        dict,
    ):
        raise QslDeliveryError(
            "QRZ-Empfängerprüfung hat kein Objekt geliefert"
        )

    _same_uid(
        recipient_result.get(
            "qsoUid"
        ),
        qso_uid,
        source="POST qrz",
    )

    recipient = str(
        recipient_result.get(
            "email",
            "",
        )
        or ""
    ).strip()

    if not recipient:
        raise QslDeliveryError(
            "Für dieses Rufzeichen ist bei QRZ.com "
            "keine nutzbare E-Mail-Adresse hinterlegt."
        )

    png_bytes = render_selected_qsl(
        template,
        qso,
        cache_root=cache_root,
    )

    card_result = client.upload_card(
        qso_uid,
        template_id,
        png_bytes,
    )

    if not isinstance(
        card_result,
        dict,
    ):
        raise QslDeliveryError(
            "QSL-Karten-Upload hat kein Objekt geliefert"
        )

    _same_uid(
        card_result.get(
            "qsoUid"
        ),
        qso_uid,
        source="POST cards",
    )

    if (
        str(
            card_result.get(
                "status",
                "",
            )
        ).strip().lower()
        != "generated"
    ):
        raise QslDeliveryError(
            "Der Server hat die QSL-Karte nicht als generated bestätigt"
        )

    card_expires_at = str(
        card_result.get(
            "expiresAt",
            "",
        )
        or ""
    ).strip()

    # Preserve the successfully generated card state locally even when the
    # following mail handoff fails for a transient reason.
    refresh_qsl_status(
        client,
        storage,
        qso_uid,
    )

    mail_result = client.mail_send(
        qso_uid
    )

    if not isinstance(
        mail_result,
        dict,
    ):
        raise QslDeliveryError(
            "QSL-Mailversand hat kein Objekt geliefert"
        )

    _same_uid(
        mail_result.get(
            "qsoUid"
        ),
        qso_uid,
        source="POST mail/send",
    )

    if not bool(
        mail_result.get(
            "sent",
            False,
        )
    ):
        raise QslDeliveryError(
            "Der Server hat den QSL-Mailversand nicht bestätigt"
        )

    sent_recipient = str(
        mail_result.get(
            "recipient",
            "",
        )
        or ""
    ).strip()

    if sent_recipient:
        recipient = sent_recipient

    sent_at = str(
        mail_result.get(
            "sentAt",
            "",
        )
        or ""
    ).strip()

    refresh_qsl_status(
        client,
        storage,
        qso_uid,
    )

    return QslDeliveryResult(
        qso_uid=qso_uid,
        template_id=template_id,
        template_name=template_name,
        recipient=recipient,
        sent_at=sent_at,
        card_expires_at=card_expires_at,
    )
