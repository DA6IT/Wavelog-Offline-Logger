from __future__ import annotations

import unittest

from logger_core import WavelogOnlineSettings


class WavelogOnlineSettingsTests(unittest.TestCase):
    def _load(self, values):
        def get_setting(key, default=""):
            return values.get(key, default)

        return WavelogOnlineSettings.from_storage(
            get_setting,
            lambda: "wl2_test_token",
        )

    def test_default_auto_sync_delay_is_five_minutes(self):
        settings = self._load({
            "wavelog_url": "https://example.invalid",
            "station_profile_id": "1",
            "auto_sync_online": "1",
        })
        self.assertEqual(settings.auto_sync_delay_seconds, 300)

    def test_auto_sync_delay_is_profile_setting(self):
        settings = self._load({
            "wavelog_url": "https://example.invalid",
            "station_profile_id": "1",
            "auto_sync_delay_seconds": "900",
        })
        self.assertEqual(settings.auto_sync_delay_seconds, 900)

    def test_auto_sync_delay_is_safely_clamped(self):
        low = self._load({
            "wavelog_url": "https://example.invalid",
            "station_profile_id": "1",
            "auto_sync_delay_seconds": "5",
        })
        high = self._load({
            "wavelog_url": "https://example.invalid",
            "station_profile_id": "1",
            "auto_sync_delay_seconds": "99999",
        })
        invalid = self._load({
            "wavelog_url": "https://example.invalid",
            "station_profile_id": "1",
            "auto_sync_delay_seconds": "nope",
        })
        self.assertEqual(low.auto_sync_delay_seconds, 60)
        self.assertEqual(high.auto_sync_delay_seconds, 3600)
        self.assertEqual(invalid.auto_sync_delay_seconds, 300)


if __name__ == "__main__":
    unittest.main()
