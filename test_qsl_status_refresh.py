from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from logger_core import MetadataDB
from qsl_background import (
    QSL_STATUS_REFRESH_LIMIT,
    status_refresh_candidates,
)
from qsl_storage import QslStorage


def uid(number: int) -> str:
    return (
        "qso_"
        + f"{number:064x}"
    )


class QslStatusRefreshTests(
    unittest.TestCase
):
    def make_storage(
        self,
        root: Path,
    ):
        db = MetadataDB(
            root / "metadata.db"
        )
        return db, QslStorage(
            db
        )

    def test_missing_snapshot_is_refreshed_first(
        self,
    ):
        with tempfile.TemporaryDirectory() as tmp:
            db, storage = self.make_storage(
                Path(tmp)
            )

            try:
                storage.bind_qso_uid(
                    "missing",
                    uid(1),
                )
                storage.bind_qso_uid(
                    "fresh",
                    uid(2),
                )
                storage.set_status_snapshot(
                    uid(2),
                    {
                        "qsoUid": uid(2),
                        "cardStatus": "none",
                        "mailStatus": "not_sent",
                    },
                )

                selected = status_refresh_candidates(
                    storage,
                    now=datetime.now(
                        timezone.utc
                    ),
                )

                self.assertEqual(
                    selected,
                    [uid(1)],
                )
            finally:
                db.close()

    def test_active_status_refreshes_after_30_minutes(
        self,
    ):
        with tempfile.TemporaryDirectory() as tmp:
            db, storage = self.make_storage(
                Path(tmp)
            )

            try:
                storage.bind_qso_uid(
                    "queued",
                    uid(10),
                )
                storage.bind_qso_uid(
                    "stable",
                    uid(11),
                )

                storage.set_status_snapshot(
                    uid(10),
                    {
                        "qsoUid": uid(10),
                        "cardStatus": "generated",
                        "mailStatus": "queued",
                    },
                )
                storage.set_status_snapshot(
                    uid(11),
                    {
                        "qsoUid": uid(11),
                        "cardStatus": "generated",
                        "mailStatus": "sent",
                    },
                )

                future = (
                    datetime.now(
                        timezone.utc
                    )
                    + timedelta(
                        minutes=31
                    )
                )

                selected = status_refresh_candidates(
                    storage,
                    now=future,
                )

                self.assertEqual(
                    selected,
                    [uid(10)],
                )
            finally:
                db.close()

    def test_stable_status_refreshes_after_24_hours(
        self,
    ):
        with tempfile.TemporaryDirectory() as tmp:
            db, storage = self.make_storage(
                Path(tmp)
            )

            try:
                storage.bind_qso_uid(
                    "stable",
                    uid(20),
                )
                storage.set_status_snapshot(
                    uid(20),
                    {
                        "qsoUid": uid(20),
                        "cardStatus": "generated",
                        "mailStatus": "sent",
                    },
                )

                future = (
                    datetime.now(
                        timezone.utc
                    )
                    + timedelta(
                        hours=25
                    )
                )

                selected = status_refresh_candidates(
                    storage,
                    now=future,
                )

                self.assertEqual(
                    selected,
                    [uid(20)],
                )
            finally:
                db.close()

    def test_refresh_set_is_bounded(
        self,
    ):
        with tempfile.TemporaryDirectory() as tmp:
            db, storage = self.make_storage(
                Path(tmp)
            )

            try:
                for number in range(
                    QSL_STATUS_REFRESH_LIMIT
                    + 25
                ):
                    storage.bind_qso_uid(
                        f"local-{number}",
                        uid(
                            1000
                            + number
                        ),
                    )

                selected = status_refresh_candidates(
                    storage
                )

                self.assertEqual(
                    len(selected),
                    QSL_STATUS_REFRESH_LIMIT,
                )
                self.assertEqual(
                    len(set(selected)),
                    len(selected),
                )
            finally:
                db.close()


if __name__ == "__main__":
    unittest.main()
