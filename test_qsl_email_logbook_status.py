from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from feature_qso_sync import QsoSyncFeatureMixin
from logger_core import MetadataDB
from qsl_storage import QslStorage


UID = "qso_" + ("c" * 64)


class QslEmailLogbookStatusTests(unittest.TestCase):
    def test_sent_mail_is_green_check_symbol(self):
        self.assertEqual(
            QsoSyncFeatureMixin._display_email_qsl_status(
                {
                    "mailStatus": "sent",
                    "emailSentAt": "2026-09-08 17:30:00",
                }
            ),
            "✅",
        )

    def test_not_sent_is_dash(self):
        self.assertEqual(
            QsoSyncFeatureMixin._display_email_qsl_status(
                {
                    "mailStatus": "not_sent",
                    "emailSentAt": "",
                }
            ),
            "—",
        )

    def test_historical_sent_at_is_still_shown_as_sent(self):
        self.assertEqual(
            QsoSyncFeatureMixin._display_email_qsl_status(
                {
                    "mailStatus": "not_sent",
                    "emailSentAt": "2026-09-08 17:30:00",
                }
            ),
            "✅",
        )

    def test_missing_snapshot_is_dash(self):
        self.assertEqual(
            QsoSyncFeatureMixin._display_email_qsl_status(None),
            "—",
        )

    def test_bulk_status_lookup_uses_local_id_mapping(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = MetadataDB(
                Path(tmp) / "metadata.db"
            )

            try:
                storage = QslStorage(db)
                storage.bind_qso_uid(
                    "local-1",
                    UID,
                )
                storage.set_status_snapshot(
                    UID,
                    {
                        "qsoUid": UID,
                        "mailStatus": "sent",
                        "emailSentAt": "2026-09-08 17:30:00",
                    },
                )

                snapshots = (
                    storage.list_status_snapshots_by_local()
                )

                self.assertIn(
                    "local-1",
                    snapshots,
                )
                self.assertEqual(
                    snapshots["local-1"]["qso_uid"],
                    UID,
                )
                self.assertEqual(
                    snapshots["local-1"]["payload"]["mailStatus"],
                    "sent",
                )
            finally:
                db.close()


if __name__ == "__main__":
    unittest.main()
