from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from logger_core import MetadataDB
from qsl_delivery import (
    QslQueueError,
    queue_qsl_batch,
)
from qsl_storage import QslStorage


UID_A = "qso_" + ("a" * 64)
UID_B = "qso_" + ("b" * 64)


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


def qso(local_id, call):
    return {
        "local_id": local_id,
        "call": call,
        "qso_date": "20260908",
        "time_on": "180000",
        "band": "20m",
        "mode": "FT8",
        "freq": "14.074",
        "station_call": "DA6IT",
    }


class FakeClient:
    def __init__(self):
        self.uploads = []
        self.queued = []
        self.status_calls = []

    def upload_card(
        self,
        qso_uid,
        template_id,
        png_bytes,
    ):
        self.uploads.append(
            (qso_uid, template_id, png_bytes)
        )
        return {
            "qsoUid": qso_uid,
            "status": "generated",
            "expiresAt": "2026-09-09 18:00:00",
        }

    def mail_queue(self, qso_uids):
        self.queued.append(list(qso_uids))
        return {
            "jobId": "job123",
            "queued": len(qso_uids),
            "skipped": 0,
            "no_email": 0,
            "recipient_pending": len(qso_uids),
            "cooldown": 0,
            "missing_card": 0,
            "missingQsoUids": [],
        }

    def qso_status(self, qso_uids):
        self.status_calls.append(list(qso_uids))
        return {
            "statuses": {
                uid: {
                    "exists": True,
                    "qsoUid": uid,
                    "cardStatus": "generated",
                    "mailStatus": "not_sent",
                }
                for uid in qso_uids
            }
        }


class QslBatchQueueTests(unittest.TestCase):
    def make_storage(self, root: Path):
        db = MetadataDB(root / "metadata.db")
        storage = QslStorage(db)
        storage.bind_qso_uid("local-a", UID_A)
        storage.bind_qso_uid("local-b", UID_B)
        return db, storage

    def test_two_cards_are_prepared_and_queued_as_one_job(self):
        with tempfile.TemporaryDirectory() as tmp:
            db, storage = self.make_storage(Path(tmp))

            try:
                client = FakeClient()

                result = queue_qsl_batch(
                    client,
                    storage,
                    [
                        qso("local-a", "DL1AAA"),
                        qso("local-b", "DL1BBB"),
                    ],
                    template(),
                    cache_root=Path(tmp) / "assets",
                    max_batch=50,
                )

                self.assertEqual(result.requested, 2)
                self.assertEqual(result.prepared, 2)
                self.assertEqual(result.failed, 0)
                self.assertEqual(result.job_id, "job123")
                self.assertEqual(result.queued, 2)
                self.assertEqual(
                    client.queued,
                    [[UID_A, UID_B]],
                )
                self.assertEqual(len(client.uploads), 2)
            finally:
                db.close()

    def test_missing_mapping_does_not_block_other_qso(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = MetadataDB(Path(tmp) / "metadata.db")
            storage = QslStorage(db)
            storage.bind_qso_uid("local-a", UID_A)

            try:
                client = FakeClient()

                result = queue_qsl_batch(
                    client,
                    storage,
                    [
                        qso("local-a", "DL1AAA"),
                        qso("local-missing", "DL1XXX"),
                    ],
                    template(),
                    cache_root=Path(tmp) / "assets",
                    max_batch=50,
                )

                self.assertEqual(result.prepared, 1)
                self.assertEqual(result.failed, 1)
                self.assertEqual(result.queued, 1)
                self.assertEqual(
                    client.queued,
                    [[UID_A]],
                )
                self.assertIn("DL1XXX", result.failures[0])
            finally:
                db.close()

    def test_server_batch_limit_is_enforced_before_rendering(self):
        with tempfile.TemporaryDirectory() as tmp:
            db, storage = self.make_storage(Path(tmp))

            try:
                client = FakeClient()

                with self.assertRaisesRegex(
                    QslQueueError,
                    "Queue-Limit",
                ):
                    queue_qsl_batch(
                        client,
                        storage,
                        [
                            qso("local-a", "DL1AAA"),
                            qso("local-b", "DL1BBB"),
                        ],
                        template(),
                        cache_root=Path(tmp) / "assets",
                        max_batch=1,
                    )

                self.assertEqual(client.uploads, [])
                self.assertEqual(client.queued, [])
            finally:
                db.close()


if __name__ == "__main__":
    unittest.main()
