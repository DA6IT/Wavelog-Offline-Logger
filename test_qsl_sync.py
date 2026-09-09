from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from logger_core import MetadataDB
from qsl_qso import qsl_upsert_fingerprint, qso_to_upsert_record
from qsl_storage import QslStorage
from qsl_sync import (
    QslSyncError,
    map_upsert_response,
    sync_qsos,
)


UID_A = "qso_" + ("a" * 64)
UID_B = "qso_" + ("b" * 64)


def qso(
    local_id: str,
    call: str = "DL1ABC",
) -> dict:
    return {
        "local_id": local_id,
        "call": call,
        "qso_date": "2026-09-08",
        "time_on": "18:42:00",
        "band": "20m",
        "freq": "14.074",
        "mode": "FT8",
        "station_call": "DA6IT",
        "rst_sent": "-08",
        "rst_rcvd": "-12",
    }


class FakeClient:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def upsert_qsos(self, records):
        self.calls.append(records)
        return self.responses.pop(0)


class QslSyncTests(unittest.TestCase):
    def make_storage(self, root: Path):
        db = MetadataDB(root / "metadata.db")
        return db, QslStorage(db)

    def test_real_prod_shape_maps_qso_uid(self):
        with tempfile.TemporaryDirectory() as tmp:
            db, storage = self.make_storage(Path(tmp))

            try:
                prepared = [
                    qso_to_upsert_record(
                        qso("local-1", "DL7HS")
                    )
                ]

                response = {
                    "records": [
                        {
                            "action": "created",
                            "qsoUid": UID_A,
                            "qso": {
                                "qsoUid": UID_A,
                                "call": "DL7HS",
                                "cardStatus": "none",
                                "mailStatus": "not_sent",
                            },
                        }
                    ],
                    "stats": {
                        "created": 1,
                        "ignored": 0,
                        "unchanged": 0,
                        "updated": 0,
                    },
                    "syncedAt": "2026-09-08 16:01:45",
                }

                result = map_upsert_response(
                    storage,
                    prepared,
                    response,
                )

                self.assertEqual(result.created, 1)
                self.assertEqual(result.mapped, 1)
                self.assertEqual(
                    storage.qso_uid_for_local("local-1"),
                    UID_A,
                )
                self.assertEqual(
                    result.records[0].qso["mailStatus"],
                    "not_sent",
                )

                self.assertEqual(
                    storage.sync_fingerprint_for_local(
                        "local-1"
                    ),
                    qsl_upsert_fingerprint(
                        prepared[0]
                    ),
                )

                snapshot = storage.get_status_snapshot(
                    UID_A
                )
                self.assertIsNotNone(snapshot)
                self.assertEqual(
                    snapshot["payload"]["cardStatus"],
                    "none",
                )
                self.assertEqual(
                    snapshot["payload"]["mailStatus"],
                    "not_sent",
                )
            finally:
                db.close()

    def test_unchanged_is_mapped_too(self):
        with tempfile.TemporaryDirectory() as tmp:
            db, storage = self.make_storage(Path(tmp))

            try:
                prepared = [
                    qso_to_upsert_record(
                        qso("local-1")
                    )
                ]

                response = {
                    "records": [
                        {
                            "action": "unchanged",
                            "qsoUid": UID_A,
                            "qso": {"qsoUid": UID_A},
                        }
                    ],
                    "stats": {
                        "created": 0,
                        "ignored": 0,
                        "unchanged": 1,
                        "updated": 0,
                    },
                }

                result = map_upsert_response(
                    storage,
                    prepared,
                    response,
                )

                self.assertEqual(result.unchanged, 1)
                self.assertEqual(result.mapped, 1)
            finally:
                db.close()

    def test_ignored_without_uid_is_not_mapped(self):
        with tempfile.TemporaryDirectory() as tmp:
            db, storage = self.make_storage(Path(tmp))

            try:
                prepared = [
                    qso_to_upsert_record(
                        qso("local-1")
                    )
                ]

                response = {
                    "records": [
                        {
                            "action": "ignored",
                            "qso": {},
                        }
                    ],
                    "stats": {
                        "created": 0,
                        "ignored": 1,
                        "unchanged": 0,
                        "updated": 0,
                    },
                }

                result = map_upsert_response(
                    storage,
                    prepared,
                    response,
                )

                self.assertEqual(result.ignored, 1)
                self.assertEqual(result.mapped, 0)
                self.assertIsNone(
                    storage.qso_uid_for_local("local-1")
                )
            finally:
                db.close()

    def test_mismatched_record_count_does_not_write_mapping(self):
        with tempfile.TemporaryDirectory() as tmp:
            db, storage = self.make_storage(Path(tmp))

            try:
                prepared = [
                    qso_to_upsert_record(qso("local-1")),
                    qso_to_upsert_record(qso("local-2", "DL2XYZ")),
                ]

                response = {
                    "records": [
                        {
                            "action": "created",
                            "qsoUid": UID_A,
                            "qso": {"qsoUid": UID_A},
                        }
                    ]
                }

                with self.assertRaisesRegex(
                    QslSyncError,
                    "unerwartete Anzahl",
                ):
                    map_upsert_response(
                        storage,
                        prepared,
                        response,
                    )

                self.assertEqual(
                    storage.list_mappings(),
                    [],
                )
            finally:
                db.close()

    def test_conflicting_uid_fields_are_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            db, storage = self.make_storage(Path(tmp))

            try:
                prepared = [
                    qso_to_upsert_record(qso("local-1"))
                ]

                response = {
                    "records": [
                        {
                            "action": "created",
                            "qsoUid": UID_A,
                            "qso": {"qsoUid": UID_B},
                        }
                    ]
                }

                with self.assertRaisesRegex(
                    QslSyncError,
                    "widersprüchliche",
                ):
                    map_upsert_response(
                        storage,
                        prepared,
                        response,
                    )

                self.assertEqual(
                    storage.list_mappings(),
                    [],
                )
            finally:
                db.close()

    def test_stats_mismatch_is_rejected_before_mapping(self):
        with tempfile.TemporaryDirectory() as tmp:
            db, storage = self.make_storage(Path(tmp))

            try:
                prepared = [
                    qso_to_upsert_record(qso("local-1"))
                ]

                response = {
                    "records": [
                        {
                            "action": "created",
                            "qsoUid": UID_A,
                            "qso": {"qsoUid": UID_A},
                        }
                    ],
                    "stats": {
                        "created": 0,
                        "ignored": 0,
                        "unchanged": 1,
                        "updated": 0,
                    },
                }

                with self.assertRaisesRegex(
                    QslSyncError,
                    "Statistik",
                ):
                    map_upsert_response(
                        storage,
                        prepared,
                        response,
                    )

                self.assertEqual(
                    storage.list_mappings(),
                    [],
                )
            finally:
                db.close()

    def test_sync_qsos_combines_multiple_batches(self):
        with tempfile.TemporaryDirectory() as tmp:
            db, storage = self.make_storage(Path(tmp))

            try:
                client = FakeClient(
                    [
                        {
                            "records": [
                                {
                                    "action": "created",
                                    "qsoUid": UID_A,
                                    "qso": {"qsoUid": UID_A},
                                }
                            ],
                            "stats": {
                                "created": 1,
                                "ignored": 0,
                                "unchanged": 0,
                                "updated": 0,
                            },
                        },
                        {
                            "records": [
                                {
                                    "action": "unchanged",
                                    "qsoUid": UID_B,
                                    "qso": {"qsoUid": UID_B},
                                }
                            ],
                            "stats": {
                                "created": 0,
                                "ignored": 0,
                                "unchanged": 1,
                                "updated": 0,
                            },
                        },
                    ]
                )

                result = sync_qsos(
                    client,
                    storage,
                    [
                        qso("local-1"),
                        qso("local-2", "DL2XYZ"),
                    ],
                    batch_size=1,
                )

                self.assertEqual(result.total, 2)
                self.assertEqual(result.created, 1)
                self.assertEqual(result.unchanged, 1)
                self.assertEqual(result.mapped, 2)
                self.assertEqual(len(client.calls), 2)
            finally:
                db.close()


if __name__ == "__main__":
    unittest.main()
