from __future__ import annotations

import threading
import unittest
from types import SimpleNamespace
from typing import Any, cast

from feature_lifecycle import LifecycleFeatureMixin
from feature_qso_sync import QsoSyncFeatureMixin
from logger_core import SyncEngine, WavelogOnlineSettings


class _Status:
    def __init__(self):
        self.value = ""

    def set(self, value):
        self.value = value


class _LifecycleProbe(LifecycleFeatureMixin):
    def __init__(self):
        self.closing = False
        self.close_services_stopped = True
        self.sync_busy = False
        self.wavelog_online = True
        self.startup_full_sync_pending = True
        self.status_var = _Status()
        self.delta_started = False
        self.full_started = False

    def _wavelog_online_settings(self):
        return SimpleNamespace(delta_sync_on_exit=True, configured=True)

    def _start_shutdown_delta_sync(self):
        self.delta_started = True

    def _start_sync(self, **_kwargs):
        self.full_started = True

    def _finalize_close(self):
        raise AssertionError("shutdown delta should start before final close")


class _SyncProbe(QsoSyncFeatureMixin):
    def __init__(self):
        self.sync_cancel_event = threading.Event()
        self.sync_busy = True
        self.sync_is_automatic = True
        self.sync_operation = "delta"
        self.status_var = _Status()
        self.finalized = False

    def _finalize_close(self):
        self.finalized = True


class _DeltaStore:
    def scan(self):
        return [{"local_id": "queued", "call": "DL1TEST"}]


class _DeltaDb:
    def list_new_upload_candidates(self):
        return [{"local_id": "queued"}]

    def reconcile_index(self, _qsos):
        raise AssertionError("shutdown delta must not reconcile the local index")

    def xota_station_id_for_qso(self, _local_id):
        return None

    def set_status(self, *_args, **_kwargs):
        pass


class _DeltaClient:
    def create_qso(self, _payload):
        return {"id": 123}


class ShutdownDeltaSyncTests(unittest.TestCase):
    def test_shutdown_uses_delta_and_never_starts_full_sync(self):
        app = _LifecycleProbe()
        app._begin_close_sequence()
        self.assertTrue(app.delta_started)
        self.assertFalse(app.full_started)
        self.assertIn("Delta", app.status_var.value)

    def test_legacy_shutdown_setting_migrates_to_delta_without_overwriting_legacy(self):
        values = {"full_sync_on_exit": "1"}
        writes = []

        def get_setting(key, default=""):
            return values.get(key, default)

        def set_setting(key, value):
            values[key] = value
            writes.append((key, value))

        self.assertTrue(WavelogOnlineSettings.migrate_shutdown_sync_setting(get_setting, set_setting))
        self.assertEqual([("delta_sync_on_exit", "1")], writes)
        self.assertEqual("1", values["full_sync_on_exit"])
        self.assertTrue(WavelogOnlineSettings.from_storage(get_setting, lambda: "token").delta_sync_on_exit)
        self.assertFalse(WavelogOnlineSettings.migrate_shutdown_sync_setting(get_setting, set_setting))

    def test_manual_sync_still_starts_full_reconciliation(self):
        calls = []
        app = object.__new__(QsoSyncFeatureMixin)
        app._start_sync = lambda **kwargs: calls.append(kwargs)
        app.sync_now()
        self.assertEqual([{"automatic": False, "reason": "manual"}], calls)

    def test_cancelled_shutdown_delta_finalizes_close(self):
        app = _SyncProbe()
        app.sync_cancel_event.set()
        app._delta_sync_failed("Synchronisierung wurde abgebrochen", "shutdown")
        self.assertFalse(app.sync_busy)
        self.assertTrue(app.finalized)
        self.assertIn("abgebrochen", app.status_var.value)

    def test_delta_upload_skips_full_integrity_reconciliation(self):
        summary = SyncEngine(
            cast(Any, _DeltaStore()), cast(Any, _DeltaDb()), cast(Any, _DeltaClient()),
        ).push_new_only(1)
        self.assertEqual(1, summary.pushed)


if __name__ == "__main__":
    unittest.main()
