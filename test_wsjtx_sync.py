from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from logger_core import LogStore, MetadataDB, qso_hash, qso_to_adif_record
from wsjtx_sync import (
    QsoMatcher,
    WsjtxSyncSettings,
    load_wsjtx_settings,
    save_wsjtx_settings,
    should_wsjtx_sync_for_reason,
    sync_wsjtx_with_local,
)


def qso(
    call,
    date,
    time_on,
    *,
    freq="14.074",
    band="20m",
    mode="FT8",
    station="DK0GN",
    operator="DA6IT",
):
    return {
        "call": call,
        "qso_date": date,
        "time_on": time_on,
        "freq": freq,
        "band": band,
        "mode": mode,
        "rst_sent": "-10",
        "rst_rcvd": "-12",
        "station_call": station,
        "operator_call": operator,
    }


class WsjtxSyncTests(unittest.TestCase):
    def test_matcher_accepts_small_time_difference(self):
        a = qso("DL1ABC", "2026-09-06", "120000")
        b = qso("DL1ABC", "2026-09-06", "120045")
        self.assertIsNotNone(QsoMatcher([a]).find(b))

    def test_fresh_profile_does_not_enable_wsjtx_implicitly(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            db = MetadataDB(root / "metadata.db")

            try:
                loaded = load_wsjtx_settings(db)

                self.assertFalse(loaded.enabled)
                self.assertIsNone(loaded.log_path)
                self.assertEqual(loaded.profile_name, "")
                self.assertFalse(loaded.sync_on_startup)
                self.assertFalse(loaded.sync_on_shutdown)
                self.assertFalse(loaded.sync_on_manual)
            finally:
                db.close()
    def test_reason_specific_settings(self):
        settings = WsjtxSyncSettings(
            enabled=True,
            log_path=Path("wsjtx_log.adi"),
            profile_name="Club",
            sync_on_startup=True,
            sync_on_shutdown=False,
            sync_on_manual=True,
        )

        self.assertTrue(
            should_wsjtx_sync_for_reason(settings, "startup")
        )
        self.assertFalse(
            should_wsjtx_sync_for_reason(settings, "shutdown")
        )
        self.assertTrue(
            should_wsjtx_sync_for_reason(settings, "manual")
        )
        self.assertFalse(
            should_wsjtx_sync_for_reason(settings, "other")
        )

    def test_reason_settings_are_profile_database_settings(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            db = MetadataDB(root / "metadata.db")

            try:
                original = WsjtxSyncSettings(
                    enabled=True,
                    log_path=root / "WSJT-X - Club" / "wsjtx_log.adi",
                    profile_name="Club",
                    sync_on_startup=False,
                    sync_on_shutdown=True,
                    sync_on_manual=False,
                )

                save_wsjtx_settings(db, original)
                loaded = load_wsjtx_settings(db)

                self.assertFalse(loaded.sync_on_startup)
                self.assertTrue(loaded.sync_on_shutdown)
                self.assertFalse(loaded.sync_on_manual)
                self.assertTrue(loaded.enabled)
                self.assertEqual(
                    loaded.profile_name,
                    "Club",
                )
            finally:
                db.close()

    def test_bidirectional_merge_is_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            store = LogStore(root / "logs", "test")
            db = MetadataDB(root / "metadata.db")

            try:
                db.set_setting("station_call", "DK0GN")
                db.set_setting("operator_call", "DA6IT")

                local_shared = store.add(
                    qso("DL1AAA", "2026-09-06", "100000")
                )
                db.ensure_local(
                    local_shared["local_id"],
                    qso_hash(local_shared),
                )

                local_only = store.add(
                    qso("DL2BBB", "2026-09-06", "101500")
                )
                db.ensure_local(
                    local_only["local_id"],
                    qso_hash(local_only),
                )

                wsjtx = root / "WSJT-X - Club" / "wsjtx_log.adi"
                wsjtx.parent.mkdir(parents=True)
                wsjtx.write_text(
                    qso_to_adif_record(
                        qso("DL1AAA", "2026-09-06", "100030")
                    )
                    + qso_to_adif_record(
                        qso("DL3CCC", "2026-09-06", "103000")
                    ),
                    encoding="utf-8",
                )

                settings = WsjtxSyncSettings(
                    enabled=True,
                    log_path=wsjtx,
                    profile_name="Club",
                    sync_on_manual=True,
                )

                first = sync_wsjtx_with_local(
                    store,
                    db,
                    settings,
                )

                self.assertEqual(first.imported_to_local, 1)
                self.assertEqual(first.appended_to_wsjtx, 1)
                self.assertEqual(first.scope_skipped_from_wsjtx, 0)
                self.assertEqual(len(store.scan()), 3)

                second = sync_wsjtx_with_local(
                    store,
                    db,
                    settings,
                )

                self.assertEqual(second.imported_to_local, 0)
                self.assertEqual(second.appended_to_wsjtx, 0)
                self.assertEqual(second.scope_skipped_from_wsjtx, 0)
                self.assertEqual(len(store.scan()), 3)

            finally:
                db.close()

    def test_other_station_call_is_not_imported(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            store = LogStore(root / "logs", "test")
            db = MetadataDB(root / "metadata.db")

            try:
                db.set_setting("station_call", "DK0GN")
                db.set_setting("operator_call", "DA6IT")

                wsjtx = root / "WSJT-X - Club" / "wsjtx_log.adi"
                wsjtx.parent.mkdir(parents=True)
                wsjtx.write_text(
                    qso_to_adif_record(
                        qso(
                            "DL9XYZ",
                            "2026-09-06",
                            "110000",
                            station="DA6IT",
                        )
                    ),
                    encoding="utf-8",
                )

                settings = WsjtxSyncSettings(
                    enabled=True,
                    log_path=wsjtx,
                    profile_name="Club",
                    sync_on_manual=True,
                )

                result = sync_wsjtx_with_local(
                    store,
                    db,
                    settings,
                )

                self.assertEqual(result.imported_to_local, 0)
                self.assertEqual(result.scope_skipped_from_wsjtx, 1)
                self.assertEqual(store.scan(), [])

            finally:
                db.close()
    def test_missing_station_profile_fields_use_logger_profile_defaults(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            store = LogStore(root / "logs", "test")
            db = MetadataDB(root / "metadata.db")

            try:
                db.set_setting("station_call", "DK0GN")
                db.set_setting("operator_call", "DA6IT")
                db.set_setting("locator", "JO31EJ")
                db.set_setting("qth", "Wachtendonk")
                db.set_setting("my_pota_ref", "DE-0001")
                db.set_setting("my_sota_ref", "DM/NW-001")
                db.set_setting("my_wwff_ref", "DLFF-0001")

                wsjtx = root / "WSJT-X - Club" / "wsjtx_log.adi"
                wsjtx.parent.mkdir(parents=True)
                wsjtx.write_text(
                    qso_to_adif_record(
                        qso(
                            "DL4DDD",
                            "2026-09-06",
                            "111500",
                            station="",
                            operator="",
                        )
                    ),
                    encoding="utf-8",
                )

                settings = WsjtxSyncSettings(
                    enabled=True,
                    log_path=wsjtx,
                    profile_name="Club",
                    sync_on_manual=True,
                )

                result = sync_wsjtx_with_local(store, db, settings)
                self.assertEqual(result.imported_to_local, 1)

                rows = store.scan()
                self.assertEqual(len(rows), 1)
                imported = rows[0]
                self.assertEqual(imported["station_call"], "DK0GN")
                self.assertEqual(imported["operator_call"], "DA6IT")
                self.assertEqual(imported["my_gridsquare"], "JO31EJ")
                self.assertEqual(imported["my_qth"], "Wachtendonk")
                self.assertEqual(imported["my_pota_ref"], "DE-0001")
                self.assertEqual(imported["my_sota_ref"], "DM/NW-001")
                self.assertEqual(imported["my_wwff_ref"], "DLFF-0001")
            finally:
                db.close()

if __name__ == "__main__":
    unittest.main()
