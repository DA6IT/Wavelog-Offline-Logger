from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from logger_core import LogStore, MetadataDB, qso_hash


def qso(call: str, time_on: str) -> dict:
    return {
        "call": call,
        "qso_date": "2026-09-10",
        "time_on": time_on,
        "band": "20m",
        "mode": "FT8",
        "freq": "14.074",
        "station_call": "DA6IT",
        "operator_call": "DA6IT",
    }


class LogStoreDeleteManyTests(unittest.TestCase):
    def test_delete_many_removes_selected_records(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = LogStore(Path(tmp) / "logs", "test")
            first = store.add(qso("DL1AAA", "120000"))
            second = store.add(qso("DL2BBB", "120100"))
            third = store.add(qso("DL3CCC", "120200"))

            deleted = store.delete_many(
                [first["local_id"], third["local_id"]]
            )

            self.assertEqual(
                deleted,
                [first["local_id"], third["local_id"]],
            )
            remaining = store.scan()
            self.assertEqual(len(remaining), 1)
            self.assertEqual(remaining[0]["local_id"], second["local_id"])

    def test_batch_pending_delete_only_keeps_linked_remote_intent(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            store = LogStore(root / "logs", "test")
            db = MetadataDB(root / "metadata.db")
            try:
                local_only = store.add(qso("DL1AAA", "120000"))
                linked = store.add(qso("DL2BBB", "120100"))
                db.ensure_local(local_only["local_id"], qso_hash(local_only))
                db.ensure_local(linked["local_id"], qso_hash(linked))
                db.set_status(
                    linked["local_id"],
                    "synced",
                    wavelog_id=123,
                    last_synced_hash=qso_hash(linked),
                    remote_hash=qso_hash(linked),
                )

                db.mark_pending_delete_many(
                    [local_only["local_id"], linked["local_id"]]
                )

                self.assertIsNone(db.get_meta(local_only["local_id"]))
                linked_meta = db.get_meta(linked["local_id"])
                self.assertIsNotNone(linked_meta)
                self.assertEqual(linked_meta["status"], "pending_delete")
                self.assertEqual(linked_meta["wavelog_id"], 123)
            finally:
                db.close()


if __name__ == "__main__":
    unittest.main()
