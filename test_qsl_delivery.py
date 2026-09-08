from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from logger_core import MetadataDB
from qsl_client import QslClientError
from qsl_delivery import (
    QslDeliveryError,
    send_single_qsl,
)
from qsl_storage import QslStorage


UID = "qso_" + ("d" * 64)


def qso():
    return {
        "local_id": "local-1",
        "call": "DL1ABC",
        "qso_date": "20260908",
        "time_on": "180000",
        "band": "20m",
        "mode": "FT8",
        "freq": "14.074",
        "station_call": "DA6IT",
        "rst_sent": "-08",
        "rst_rcvd": "-12",
    }


def template():
    return {
        "id": 10,
        "name": "Community Light",
        "canvas": {
            "width": 1400,
            "height": 900,
            "background": {
                "color": "#ffffff",
                "url": "",
            },
        },
        "fields": [
            {
                "id": "call",
                "source": "qso.call",
                "prefix": "",
                "suffix": "",
                "x": 10,
                "y": 20,
                "width": 80,
                "fontSize": 72,
                "fontFamily": "Arial",
                "fontWeight": 700,
                "color": "#000000",
                "align": "center",
                "rotation": 0,
                "visible": True,
            }
        ],
    }


class FakeClient:
    def __init__(
        self,
        *,
        email="ham@example.org",
        mail_error=None,
    ):
        self.email = email
        self.mail_error = mail_error
        self.uploads = []
        self.mail_calls = []
        self.status_calls = 0

    def qrz_recipient(self, qso_uid):
        return {
            "qsoUid": qso_uid,
            "email": self.email,
            "cached": True,
        }

    def upload_card(
        self,
        qso_uid,
        template_id,
        png_bytes,
    ):
        self.uploads.append(
            (
                qso_uid,
                template_id,
                png_bytes,
            )
        )

        return {
            "qsoUid": qso_uid,
            "status": "generated",
            "expiresAt": "2026-09-09 18:00:00",
        }

    def mail_send(self, qso_uid):
        self.mail_calls.append(
            qso_uid
        )

        if self.mail_error:
            raise self.mail_error

        return {
            "qsoUid": qso_uid,
            "sent": True,
            "recipient": self.email,
            "sentAt": "2026-09-08 18:01:00",
        }

    def qso_status(self, qso_uids):
        self.status_calls += 1

        if self.status_calls == 1:
            payload = {
                "exists": True,
                "qsoUid": UID,
                "cardStatus": "generated",
                "mailStatus": "not_sent",
                "emailSentAt": "",
            }
        else:
            payload = {
                "exists": True,
                "qsoUid": UID,
                "cardStatus": "generated",
                "mailStatus": "sent",
                "emailSentAt": "2026-09-08 18:01:00",
                "emailRecipient": self.email,
            }

        return {
            "statuses": {
                UID: payload,
            }
        }


class QslDeliveryTests(unittest.TestCase):
    def make_storage(
        self,
        root: Path,
    ):
        db = MetadataDB(
            root / "metadata.db"
        )
        storage = QslStorage(
            db
        )
        storage.bind_qso_uid(
            "local-1",
            UID,
        )
        return db, storage

    def test_single_send_generates_uploads_and_sends(self):
        with tempfile.TemporaryDirectory() as tmp:
            db, storage = self.make_storage(
                Path(tmp)
            )

            try:
                client = FakeClient()

                result = send_single_qsl(
                    client,
                    storage,
                    qso(),
                    template(),
                    cache_root=Path(tmp) / "assets",
                )

                self.assertEqual(
                    result.qso_uid,
                    UID,
                )
                self.assertEqual(
                    result.recipient,
                    "ham@example.org",
                )
                self.assertEqual(
                    len(client.uploads),
                    1,
                )
                self.assertTrue(
                    client.uploads[0][2].startswith(
                        b"\x89PNG\r\n\x1a\n"
                    )
                )
                self.assertEqual(
                    client.mail_calls,
                    [UID],
                )

                snapshot = storage.get_status_snapshot(
                    UID
                )
                self.assertEqual(
                    snapshot["payload"]["mailStatus"],
                    "sent",
                )
            finally:
                db.close()

    def test_missing_recipient_does_not_upload(self):
        with tempfile.TemporaryDirectory() as tmp:
            db, storage = self.make_storage(
                Path(tmp)
            )

            try:
                client = FakeClient(
                    email=""
                )

                with self.assertRaisesRegex(
                    QslDeliveryError,
                    "keine nutzbare E-Mail",
                ):
                    send_single_qsl(
                        client,
                        storage,
                        qso(),
                        template(),
                        cache_root=Path(tmp) / "assets",
                    )

                self.assertEqual(
                    client.uploads,
                    [],
                )
                self.assertEqual(
                    client.mail_calls,
                    [],
                )
            finally:
                db.close()

    def test_mail_error_keeps_generated_card_snapshot(self):
        with tempfile.TemporaryDirectory() as tmp:
            db, storage = self.make_storage(
                Path(tmp)
            )

            try:
                client = FakeClient(
                    mail_error=QslClientError(
                        "temporary",
                        status_code=502,
                        error_code="mail_failed",
                    )
                )

                with self.assertRaises(
                    QslClientError
                ):
                    send_single_qsl(
                        client,
                        storage,
                        qso(),
                        template(),
                        cache_root=Path(tmp) / "assets",
                    )

                snapshot = storage.get_status_snapshot(
                    UID
                )
                self.assertEqual(
                    snapshot["payload"]["cardStatus"],
                    "generated",
                )
                self.assertEqual(
                    snapshot["payload"]["mailStatus"],
                    "not_sent",
                )
            finally:
                db.close()

    def test_missing_mapping_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = MetadataDB(
                Path(tmp) / "metadata.db"
            )

            try:
                storage = QslStorage(
                    db
                )

                with self.assertRaisesRegex(
                    QslDeliveryError,
                    "keine qsoUid",
                ):
                    send_single_qsl(
                        FakeClient(),
                        storage,
                        qso(),
                        template(),
                        cache_root=Path(tmp) / "assets",
                    )
            finally:
                db.close()


if __name__ == "__main__":
    unittest.main()
