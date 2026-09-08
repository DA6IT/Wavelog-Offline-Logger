from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from logger_core import MetadataDB
from qsl_background import run_qsl_background_sync, unmapped_qsos
from qsl_recipient import queue_recipient_check
from qsl_storage import QslStorage


OLD_UID = "qso_" + ("a" * 64)
NEW_UID = "qso_" + ("b" * 64)


def qso(local_id: str, call: str):
    return {
        "local_id": local_id,
        "call": call,
        "qso_date": "20260908",
        "time_on": "200000",
        "band": "20m",
        "freq": "14.074",
        "mode": "FT8",
        "station_call": "DA6IT",
        "rst_sent": "-08",
        "rst_rcvd": "-10",
    }


class FakeClient:
    def __init__(self):
        self.upserts = []
        self.qrz_calls = []
        self.status_calls = []
        self.template_calls = []

    def bootstrap(self):
        return {
            "contract": "da6it-qsl-client-v1",
            "apiVersion": "1.0",
            "mailUsage": {"queueBatchMax": 500},
        }

    def upsert_qsos(self, records):
        self.upserts.append(list(records))
        return {
            "records": [
                {
                    "action": "created",
                    "qsoUid": NEW_UID,
                    "qso": {"qsoUid": NEW_UID},
                }
            ],
            "stats": {
                "created": 1,
                "updated": 0,
                "unchanged": 0,
                "ignored": 0,
            },
            "syncedAt": "2026-09-08T20:00:00+00:00",
        }

    def qrz_recipient(self, qso_uid):
        self.qrz_calls.append(qso_uid)
        return {
            "qsoUid": qso_uid,
            "email": "ham@example.org",
            "cached": True,
        }

    def qso_status(self, qso_uids):
        self.status_calls.append(list(qso_uids))
        return {
            "statuses": {
                uid: {
                    "exists": True,
                    "qsoUid": uid,
                    "cardStatus": "none",
                    "mailStatus": "not_sent",
                    "emailSentAt": "",
                }
                for uid in qso_uids
            }
        }

    def templates(self, profile):
        self.template_calls.append(profile)
        return {
            "stationProfile": profile,
            "templates": [],
        }

    def mail_send(self, *_args, **_kwargs):
        raise AssertionError("Background-Sync darf keine Mail versenden")

    def mail_queue(self, *_args, **_kwargs):
        raise AssertionError("Background-Sync darf keine Mail einreihen")


class QslBackgroundTests(unittest.TestCase):
    def test_only_unmapped_qsos_are_selected(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = MetadataDB(Path(tmp) / "metadata.db")
            try:
                storage = QslStorage(db)
                storage.bind_qso_uid("old-local", OLD_UID)
                rows = unmapped_qsos(
                    storage,
                    [
                        qso("old-local", "DL1OLD"),
                        qso("new-local", "DL1NEW"),
                    ],
                )
                self.assertEqual(
                    [item["local_id"] for item in rows],
                    ["new-local"],
                )
            finally:
                db.close()

    def test_background_maps_new_qso_and_resolves_pending_recipient(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = MetadataDB(Path(tmp) / "metadata.db")
            try:
                storage = QslStorage(db)
                storage.bind_qso_uid("old-local", OLD_UID)
                queue_recipient_check(storage, "new-local")
                client = FakeClient()

                result = run_qsl_background_sync(
                    client,
                    storage,
                    db,
                    [
                        qso("old-local", "DL1OLD"),
                        qso("new-local", "DL1NEW"),
                    ],
                    template_candidates=["DA6IT"],
                )

                self.assertEqual(result.sync.total, 1)
                self.assertEqual(result.sync.created, 1)
                self.assertEqual(
                    storage.qso_uid_for_local("new-local"),
                    NEW_UID,
                )
                self.assertEqual(result.recipient.processed, 1)
                self.assertEqual(result.recipient.pending_after, 0)
                self.assertEqual(client.qrz_calls, [NEW_UID])
                self.assertEqual(len(client.upserts), 1)
                self.assertEqual(len(client.upserts[0]), 1)
                self.assertEqual(result.template_profile, "DA6IT")
                self.assertGreaterEqual(result.statuses_refreshed, 2)
                self.assertEqual(result.errors, ())
            finally:
                db.close()


if __name__ == "__main__":
    unittest.main()
