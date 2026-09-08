from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from logger_core import MetadataDB
from qsl_delivery import send_single_qsl
from qsl_storage import QslStorage


UID = "qso_" + ("f" * 64)


def qso():
    return {
        "local_id": "local-auto",
        "call": "DL1AUTO",
        "qso_date": "20260908",
        "time_on": "190000",
        "band": "20m",
        "mode": "FT8",
        "freq": "14.074",
        "station_call": "DA6IT",
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
        "fields": [],
    }


class AutoSyncClient:
    def __init__(self):
        self.upsert_calls = 0
        self.upload_calls = 0

    def upsert_qsos(self, records):
        self.upsert_calls += 1

        return {
            "records": [
                {
                    "action": "created",
                    "qsoUid": UID,
                    "qso": {
                        "qsoUid": UID,
                    },
                }
            ],
            "stats": {
                "created": 1,
                "updated": 0,
                "unchanged": 0,
                "ignored": 0,
            },
            "syncedAt": "2026-09-08T19:00:00+00:00",
        }

    def qrz_recipient(self, qso_uid):
        return {
            "qsoUid": qso_uid,
            "email": "ham@example.org",
            "cached": True,
        }

    def upload_card(self, qso_uid, template_id, png_bytes):
        self.upload_calls += 1

        return {
            "qsoUid": qso_uid,
            "status": "generated",
            "expiresAt": "2026-09-09 19:00:00",
        }

    def mail_send(self, qso_uid):
        return {
            "qsoUid": qso_uid,
            "sent": True,
            "recipient": "ham@example.org",
            "sentAt": "2026-09-08 19:01:00",
        }

    def qso_status(self, qso_uids):
        return {
            "statuses": {
                UID: {
                    "exists": True,
                    "qsoUid": UID,
                    "cardStatus": "generated",
                    "mailStatus": "sent",
                    "emailSentAt": "2026-09-08 19:01:00",
                }
            }
        }


class QslDeliveryAutoSyncTests(unittest.TestCase):
    def test_send_auto_syncs_unmapped_qso_first(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = MetadataDB(
                Path(tmp) / "metadata.db"
            )

            try:
                storage = QslStorage(db)
                client = AutoSyncClient()

                self.assertIsNone(
                    storage.qso_uid_for_local(
                        "local-auto"
                    )
                )

                result = send_single_qsl(
                    client,
                    storage,
                    qso(),
                    template(),
                    cache_root=Path(tmp) / "assets",
                )

                self.assertEqual(
                    client.upsert_calls,
                    1,
                )
                self.assertEqual(
                    client.upload_calls,
                    1,
                )
                self.assertEqual(
                    result.qso_uid,
                    UID,
                )
                self.assertEqual(
                    storage.qso_uid_for_local(
                        "local-auto"
                    ),
                    UID,
                )
            finally:
                db.close()


if __name__ == "__main__":
    unittest.main()
