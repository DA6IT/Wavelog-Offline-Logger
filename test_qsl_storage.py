from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from logger_core import MetadataDB
from qsl_storage import (
    QslStorage,
    QslStorageError,
    normalize_qso_uid,
)


UID_A = "qso_" + ("a" * 64)
UID_B = "qso_" + ("b" * 64)


class QslStorageTests(unittest.TestCase):
    def make_db(self, root: Path) -> MetadataDB:
        return MetadataDB(root / "metadata.db")

    def test_fresh_storage_is_empty(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = self.make_db(Path(tmp))

            try:
                storage = QslStorage(db)
                self.assertEqual(storage.list_mappings(), [])
                self.assertEqual(storage.list_pending_actions(), [])
                self.assertIsNone(storage.get_status_snapshot(UID_A))
            finally:
                db.close()

    def test_qso_uid_is_validated_and_normalized(self):
        self.assertEqual(
            normalize_qso_uid("qso_" + ("A" * 64)),
            UID_A,
        )

        with self.assertRaises(QslStorageError):
            normalize_qso_uid("123")

    def test_mapping_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = self.make_db(Path(tmp))

            try:
                storage = QslStorage(db)
                storage.bind_qso_uid("local-1", UID_A)

                self.assertEqual(
                    storage.qso_uid_for_local("local-1"),
                    UID_A,
                )
                self.assertEqual(
                    storage.local_id_for_qso_uid(UID_A),
                    "local-1",
                )
            finally:
                db.close()

    def test_same_qso_uid_can_reassociate_to_new_local_id(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = self.make_db(Path(tmp))

            try:
                storage = QslStorage(db)
                storage.bind_qso_uid("old-local", UID_A)
                storage.bind_qso_uid("new-local", UID_A)

                self.assertIsNone(
                    storage.qso_uid_for_local("old-local")
                )
                self.assertEqual(
                    storage.qso_uid_for_local("new-local"),
                    UID_A,
                )
                self.assertEqual(
                    storage.local_id_for_qso_uid(UID_A),
                    "new-local",
                )
            finally:
                db.close()

    def test_local_id_can_move_to_new_server_identity(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = self.make_db(Path(tmp))

            try:
                storage = QslStorage(db)
                storage.bind_qso_uid("local-1", UID_A)
                storage.bind_qso_uid("local-1", UID_B)

                self.assertIsNone(
                    storage.local_id_for_qso_uid(UID_A)
                )
                self.assertEqual(
                    storage.qso_uid_for_local("local-1"),
                    UID_B,
                )
            finally:
                db.close()

    def test_offline_action_gets_uid_after_mapping(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = self.make_db(Path(tmp))

            try:
                storage = QslStorage(db)

                action_id = storage.queue_action(
                    "local-1",
                    "mail.queue",
                    {"template_id": 12},
                )

                pending = storage.list_pending_actions()
                self.assertEqual(len(pending), 1)
                self.assertEqual(pending[0]["id"], action_id)
                self.assertIsNone(pending[0]["qso_uid"])

                storage.bind_qso_uid("local-1", UID_A)

                ready = storage.list_pending_actions(
                    ready_only=True
                )
                self.assertEqual(len(ready), 1)
                self.assertEqual(ready[0]["qso_uid"], UID_A)
                self.assertEqual(
                    ready[0]["payload"]["template_id"],
                    12,
                )

                storage.complete_action(action_id)
                self.assertEqual(
                    storage.list_pending_actions(),
                    [],
                )
            finally:
                db.close()

    def test_action_error_is_persisted(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = self.make_db(Path(tmp))

            try:
                storage = QslStorage(db)
                action_id = storage.queue_action(
                    "local-1",
                    "cards.create",
                )

                storage.mark_action_error(
                    action_id,
                    "temporarily unavailable",
                )

                pending = storage.list_pending_actions()
                self.assertEqual(
                    pending[0]["last_error"],
                    "temporarily unavailable",
                )
            finally:
                db.close()

    def test_status_snapshot_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = self.make_db(Path(tmp))

            try:
                storage = QslStorage(db)
                payload = {
                    "exists": True,
                    "card": {"exists": False},
                    "mail": {"lastSentAt": None},
                }

                storage.set_status_snapshot(
                    UID_A,
                    payload,
                )

                snapshot = storage.get_status_snapshot(
                    UID_A
                )

                self.assertIsNotNone(snapshot)
                self.assertEqual(
                    snapshot["payload"],
                    payload,
                )
                self.assertTrue(
                    snapshot["fetched_at"]
                )

                storage.clear_status_snapshot(UID_A)
                self.assertIsNone(
                    storage.get_status_snapshot(UID_A)
                )
            finally:
                db.close()

    def test_storage_survives_database_reopen(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            db = self.make_db(root)

            storage = QslStorage(db)
            storage.bind_qso_uid("local-1", UID_A)
            storage.queue_action(
                "local-1",
                "mail.send",
                {"template_id": 7},
            )
            db.close()

            reopened = self.make_db(root)

            try:
                storage = QslStorage(reopened)

                self.assertEqual(
                    storage.qso_uid_for_local("local-1"),
                    UID_A,
                )

                actions = storage.list_pending_actions(
                    ready_only=True
                )

                self.assertEqual(len(actions), 1)
                self.assertEqual(
                    actions[0]["qso_uid"],
                    UID_A,
                )
            finally:
                reopened.close()

    def test_existing_wavelog_qsl_meta_table_is_not_repurposed(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = self.make_db(Path(tmp))

            try:
                QslStorage(db)

                with db.lock:
                    columns = {
                        str(row[1])
                        for row in db.conn.execute(
                            "PRAGMA table_info(qsl_meta)"
                        )
                    }

                self.assertIn("wavelog_id", columns)
                self.assertNotIn("qso_uid", columns)
            finally:
                db.close()


if __name__ == "__main__":
    unittest.main()
