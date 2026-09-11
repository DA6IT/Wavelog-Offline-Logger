from __future__ import annotations

import json
import tempfile
import unittest
import uuid
from pathlib import Path

from usage_stats import UsageStatsService


class UsageStatsTests(unittest.TestCase):
    def test_new_state_defaults_to_enabled_but_not_acknowledged(self):
        with tempfile.TemporaryDirectory() as temporary:
            service = UsageStatsService(Path(temporary))
            uuid.UUID(service.installation_id)
            self.assertTrue(service.enabled)
            self.assertFalse(service.notice_seen)
            self.assertFalse(service.should_send_today())

    def test_heartbeat_is_sent_only_after_notice_and_once_per_day(self):
        calls = []

        def post_json(url, payload, version):
            calls.append((url, payload, version))
            return 204

        with tempfile.TemporaryDirectory() as temporary:
            service = UsageStatsService(Path(temporary), post_json=post_json)
            service.mark_notice_seen(enabled=True)
            self.assertTrue(service.should_send_today())
            self.assertTrue(service.send_heartbeat("0.20.2"))
            self.assertFalse(service.should_send_today())
            self.assertFalse(service.send_heartbeat("0.20.2"))
            self.assertEqual(len(calls), 1)
            self.assertEqual(calls[0][1]["installation_id"], service.installation_id)
            self.assertEqual(calls[0][1]["version"], "0.20.2")
            self.assertIn(calls[0][1]["platform"], {"windows", "macos", "linux", "other"})

    def test_disabled_stats_never_send(self):
        calls = []

        def post_json(url, payload, version):
            calls.append(payload)
            return 204

        with tempfile.TemporaryDirectory() as temporary:
            service = UsageStatsService(Path(temporary), post_json=post_json)
            service.mark_notice_seen(enabled=False)
            self.assertFalse(service.send_heartbeat("0.20.2"))
            self.assertEqual(calls, [])

    def test_forget_rotates_installation_id(self):
        calls = []

        def post_json(url, payload, version):
            calls.append((url, payload))
            return 200

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            service = UsageStatsService(root, post_json=post_json)
            old_id = service.installation_id
            service.mark_notice_seen(enabled=True)
            new_id = service.forget_remote_data("0.20.2")
            self.assertNotEqual(old_id, new_id)
            uuid.UUID(new_id)
            self.assertEqual(calls[0][1]["installation_id"], old_id)

            payload = json.loads((root / "usage_stats.json").read_text(encoding="utf-8"))
            self.assertEqual(payload["installation_id"], new_id)
            self.assertTrue(payload["enabled"])
            self.assertTrue(payload["notice_seen"])
            self.assertTrue(payload["last_successful_heartbeat"])


if __name__ == "__main__":
    unittest.main()
