from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from logger_core import MetadataDB
from qsl_client import QslClientError
from qsl_recipient import (
    RECIPIENT_ACTION,
    queue_recipient_check,
    resolve_pending_recipients,
)
from qsl_storage import QslStorage


UID_A = "qso_" + ("a" * 64)
UID_B = "qso_" + ("b" * 64)


class FakeClient:
    def __init__(
        self,
        qrz_responses=None,
        status_responses=None,
    ):
        self.qrz_responses = list(
            qrz_responses or []
        )
        self.status_responses = list(
            status_responses or []
        )
        self.qrz_calls = []
        self.status_calls = []

    def qrz_recipient(self, qso_uid):
        self.qrz_calls.append(qso_uid)
        value = self.qrz_responses.pop(0)

        if isinstance(value, Exception):
            raise value

        return value

    def qso_status(self, qso_uids):
        self.status_calls.append(list(qso_uids))
        return self.status_responses.pop(0)


class QslRecipientTests(unittest.TestCase):
    def make_storage(self, root: Path):
        db = MetadataDB(
            root / "metadata.db"
        )
        return db, QslStorage(db)

    def test_queue_is_idempotent_per_local_qso(self):
        with tempfile.TemporaryDirectory() as tmp:
            db, storage = self.make_storage(
                Path(tmp)
            )

            try:
                first = queue_recipient_check(
                    storage,
                    "local-1",
                )
                second = queue_recipient_check(
                    storage,
                    "local-1",
                )

                self.assertEqual(
                    first,
                    second,
                )

                actions = storage.list_pending_actions(
                    ready_only=False,
                    limit=5000,
                )

                self.assertEqual(
                    len(actions),
                    1,
                )
                self.assertEqual(
                    actions[0]["action_type"],
                    RECIPIENT_ACTION,
                )
            finally:
                db.close()

    def test_action_waits_until_qso_uid_exists(self):
        with tempfile.TemporaryDirectory() as tmp:
            db, storage = self.make_storage(
                Path(tmp)
            )

            try:
                queue_recipient_check(
                    storage,
                    "local-1",
                )

                client = FakeClient()

                result = resolve_pending_recipients(
                    client,
                    storage,
                )

                self.assertEqual(
                    result.processed,
                    0,
                )
                self.assertEqual(
                    result.pending_after,
                    1,
                )
                self.assertEqual(
                    client.qrz_calls,
                    [],
                )
            finally:
                db.close()

    def test_success_resolves_and_caches_status(self):
        with tempfile.TemporaryDirectory() as tmp:
            db, storage = self.make_storage(
                Path(tmp)
            )

            try:
                queue_recipient_check(
                    storage,
                    "local-1",
                )
                storage.bind_qso_uid(
                    "local-1",
                    UID_A,
                )

                client = FakeClient(
                    qrz_responses=[
                        {
                            "qsoUid": UID_A,
                            "email": "ham@example.org",
                            "cached": True,
                        }
                    ],
                    status_responses=[
                        {
                            "statuses": {
                                UID_A: {
                                    "exists": True,
                                    "qsoUid": UID_A,
                                    "qrzStatus": "email",
                                    "qrzEmail": "ham@example.org",
                                }
                            }
                        }
                    ],
                )

                result = resolve_pending_recipients(
                    client,
                    storage,
                )

                self.assertEqual(
                    result.processed,
                    1,
                )
                self.assertEqual(
                    result.email,
                    1,
                )
                self.assertEqual(
                    result.cached,
                    1,
                )
                self.assertEqual(
                    result.pending_after,
                    0,
                )

                snapshot = storage.get_status_snapshot(
                    UID_A
                )
                self.assertIsNotNone(snapshot)
                self.assertEqual(
                    snapshot["payload"]["qrzStatus"],
                    "email",
                )
            finally:
                db.close()

    def test_qrz_not_found_is_terminal(self):
        with tempfile.TemporaryDirectory() as tmp:
            db, storage = self.make_storage(
                Path(tmp)
            )

            try:
                queue_recipient_check(
                    storage,
                    "local-1",
                )
                storage.bind_qso_uid(
                    "local-1",
                    UID_A,
                )

                client = FakeClient(
                    qrz_responses=[
                        QslClientError(
                            "QRZ not found",
                            status_code=404,
                            error_code="qrz_not_found",
                        )
                    ],
                    status_responses=[
                        {
                            "statuses": {
                                UID_A: {
                                    "exists": True,
                                    "qsoUid": UID_A,
                                    "qrzStatus": "not_found",
                                    "qrzEmail": "",
                                }
                            }
                        }
                    ],
                )

                result = resolve_pending_recipients(
                    client,
                    storage,
                )

                self.assertEqual(
                    result.not_found,
                    1,
                )
                self.assertEqual(
                    result.pending_after,
                    0,
                )
            finally:
                db.close()

    def test_temporary_error_remains_pending(self):
        with tempfile.TemporaryDirectory() as tmp:
            db, storage = self.make_storage(
                Path(tmp)
            )

            try:
                queue_recipient_check(
                    storage,
                    "local-1",
                )
                storage.bind_qso_uid(
                    "local-1",
                    UID_A,
                )

                client = FakeClient(
                    qrz_responses=[
                        QslClientError(
                            "temporary",
                            status_code=502,
                            error_code="qrz_http",
                        )
                    ],
                )

                result = resolve_pending_recipients(
                    client,
                    storage,
                )

                self.assertEqual(
                    result.failed,
                    1,
                )
                self.assertEqual(
                    result.pending_after,
                    1,
                )

                actions = storage.list_pending_actions(
                    ready_only=False,
                    limit=5000,
                )
                self.assertTrue(
                    actions[0]["last_error"]
                )
            finally:
                db.close()

    def test_limit_prevents_large_lookup_burst(self):
        with tempfile.TemporaryDirectory() as tmp:
            db, storage = self.make_storage(
                Path(tmp)
            )

            try:
                for index, uid in enumerate(
                    (UID_A, UID_B),
                    start=1,
                ):
                    local_id = f"local-{index}"
                    queue_recipient_check(
                        storage,
                        local_id,
                    )
                    storage.bind_qso_uid(
                        local_id,
                        uid,
                    )

                client = FakeClient(
                    qrz_responses=[
                        {
                            "qsoUid": UID_A,
                            "email": "",
                            "cached": False,
                        }
                    ],
                    status_responses=[
                        {
                            "statuses": {
                                UID_A: {
                                    "exists": True,
                                    "qsoUid": UID_A,
                                    "qrzStatus": "no_email",
                                }
                            }
                        }
                    ],
                )

                result = resolve_pending_recipients(
                    client,
                    storage,
                    limit=1,
                )

                self.assertEqual(
                    result.processed,
                    1,
                )
                self.assertEqual(
                    result.pending_after,
                    1,
                )
                self.assertEqual(
                    len(client.qrz_calls),
                    1,
                )
            finally:
                db.close()


if __name__ == "__main__":
    unittest.main()
