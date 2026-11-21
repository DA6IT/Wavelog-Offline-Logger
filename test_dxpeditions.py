from __future__ import annotations

import unittest
from datetime import date, datetime, timezone

from dx_cluster import DxSpot
from feature_dxpeditions import (
    Dxpedition,
    active_slots,
    beam,
    build_worked_index,
    format_age,
    format_distance,
    format_heading,
    format_until,
    format_worked,
    parse_calendar,
    worked_status,
)

NOW = 1_795_267_137.0  # server and local time agree in these fixtures

CALENDAR = {
    "count": 4,
    "items": [
        {"callsign": "VK9XY", "aliases": ["VK9XY", "VK9DS"], "dxcc": "Christmas I", "start": "2026-11-15",
         "end": "2026-11-28", "qsl": "Club Log OQRS", "info": "By the DXpedition team", "bands": ["10m"],
         "modes": ["CW"], "iota": "OC-002", "grid": "", "id": "dx-vk9"},
        {"callsign": "3X4U", "aliases": ["3X4U"], "dxcc": "Guinea", "start": "2026-11-10", "end": "2026-11-30",
         "qsl": "LoTW", "info": "", "iota": "", "grid": "IK21", "id": "dx-3x"},
        {"callsign": "TZ4AM", "aliases": ["TZ4AM"], "dxcc": "Mali", "start": "2026-10-25", "end": "2026-12-20",
         "id": "dx-tz"},
        {"callsign": "", "id": "broken"},
        "kaputt",
    ],
}


def band_entry(call, band, mode, khz, minutes_ago, spotter="DL1AAA"):
    return {"band": band, "mode": mode, "frequency_khz": khz, "call": call, "spotter": spotter,
            "last_ts": NOW - minutes_ago * 60, "spots": 3}


SPOTS = {
    "available": True,
    "server_time": NOW,
    "collector_stale": False,
    "items": {
        "dx-vk9": {"call": "VK9XY", "last_ts": NOW - 4 * 60, "frequency_khz": 28180, "band": "10m", "mode": "FT4",
                   "spotter": "EA1AHP", "bands_60m": [
                       band_entry("VK9XY", "10m", "FT4", 28180, 4),
                       band_entry("VK9XY", "17m", "SSB", 18130, 4),
                       band_entry("VK9XY", "15m", "CW", 21000, 12),
                       band_entry("VK9XY", "80m", "FT8", 3579, 35),  # older than 30 min
                   ]},
        "dx-3x": {"call": "3X4U", "last_ts": NOW - 10 * 60, "frequency_khz": 14090, "band": "20m", "mode": "FT8",
                  "spotter": "OK2LI", "bands_60m": []},
        "dx-tz": {"call": "TZ4AM", "last_ts": NOW - 474 * 60, "frequency_khz": 7027, "band": "40m", "mode": "CW",
                  "spotter": "OE1TOA", "bands_60m": []},
        "unknown-id": {"call": "XX0XX", "last_ts": NOW, "frequency_khz": 14000, "band": "20m", "mode": "CW"},
    },
}


def slots_by_key(slots):
    return {slot.key: slot for slot in slots}


class CalendarTests(unittest.TestCase):
    def test_parse_skips_invalid_entries(self):
        calendar = parse_calendar(CALENDAR)
        self.assertEqual([d.callsign for d in calendar], ["VK9XY", "3X4U", "TZ4AM"])
        self.assertEqual(calendar[0].calls, frozenset({"VK9XY", "VK9DS"}))
        self.assertEqual(calendar[1].grid, "IK21")
        self.assertEqual(parse_calendar(None), [])
        self.assertEqual(parse_calendar({"items": "x"}), [])


class ActiveSlotTests(unittest.TestCase):
    def setUp(self):
        self.calendar = parse_calendar(CALENDAR)

    def test_only_spots_within_30_minutes(self):
        keys = set(slots_by_key(active_slots(self.calendar, SPOTS, now=NOW)))
        self.assertEqual(keys, {"dx-vk9|10m|FT4", "dx-vk9|17m|SSB", "dx-vk9|15m|CW", "dx-3x|20m|FT8"})

    def test_server_time_is_used_for_the_window(self):
        # Local clock 2 hours ahead: still active, ages are relative to the server.
        slots = slots_by_key(active_slots(self.calendar, SPOTS, now=NOW + 7200))
        self.assertIn("dx-3x|20m|FT8", slots)
        self.assertAlmostEqual(NOW + 7200 - slots["dx-3x|20m|FT8"].spotted_ts, 600, delta=1)

    def test_spots_age_out_without_new_download(self):
        # Downloaded at NOW (skew 0); 25 minutes later only spots younger than
        # 5 minutes at download time are still active.
        later = active_slots(self.calendar, SPOTS, now=NOW + 25 * 60, skew=0.0)
        self.assertEqual({slot.key for slot in later}, {"dx-vk9|10m|FT4", "dx-vk9|17m|SSB"})
        self.assertEqual(active_slots(self.calendar, SPOTS, now=NOW + 7200, skew=0.0), [])
        # Local clock 1 h behind the server: skew from the download keeps ages right.
        shifted = slots_by_key(active_slots(self.calendar, SPOTS, now=NOW - 3600 + 60, skew=-3600.0))
        self.assertAlmostEqual(NOW - 3600 + 60 - shifted["dx-3x|20m|FT8"].spotted_ts, 660, delta=1)

    def test_missing_mode_is_guessed_or_marked(self):
        payload = {"server_time": NOW, "items": {"dx-3x": {"call": "3X4U", "last_ts": NOW - 60, "frequency_khz": 14074,
                                                            "band": "20m", "mode": "", "bands_60m": [
                                                                {"call": "3X4U", "last_ts": NOW - 60, "frequency_khz": 50313.5,
                                                                 "band": "6m", "mode": ""}]}}}
        keys = {slot.key for slot in active_slots(self.calendar, payload, now=NOW)}
        self.assertIn("dx-3x|20m|FT8", keys)
        self.assertEqual(len(keys), 2)

    def test_local_cluster_spot_adds_and_refreshes(self):
        spotted = datetime.fromtimestamp(NOW - 60, timezone.utc)
        local = [
            DxSpot("DK0XX", "VK9DS", 7_025_000, "40m", "CW", "", "1234", spotted),  # alias, new band
            DxSpot("DK0XX", "TZ4AM", 7_027_000, "40m", "CW", "", "1234", spotted),  # API says 8 h ago
            DxSpot("DK0XX", "3X4U", 14_090_000, "20m", "FT8", "", "1234", spotted),  # newer than API
            DxSpot("DK0XX", "DL1ABC", 14_074_000, "20m", "FT8", "", "1234", spotted),  # no DXpedition
            DxSpot("DK0XX", "TZ4AM", 14_200_000, "20m", "SSB", "", "1234",
                   datetime.fromtimestamp(NOW - 3600, timezone.utc)),  # too old
        ]
        slots = slots_by_key(active_slots(self.calendar, SPOTS, local, now=NOW))
        self.assertEqual(slots["dx-vk9|40m|CW"].source, "cluster")
        self.assertEqual(slots["dx-vk9|40m|CW"].call, "VK9DS")
        self.assertIn("dx-tz|40m|CW", slots)
        self.assertNotIn("dx-tz|20m|SSB", slots)
        self.assertEqual(slots["dx-3x|20m|FT8"].source, "cluster")
        self.assertFalse(any(key.startswith("XX") for key in slots))

    def test_cluster_ssb_is_one_slot(self):
        spotted = datetime.fromtimestamp(NOW - 30, timezone.utc)
        local = [DxSpot("DK0XX", "VK9XY", 18_130_000, "17m", "USB", "", "1234", spotted)]
        slots = slots_by_key(active_slots(self.calendar, SPOTS, local, now=NOW))
        self.assertEqual(slots["dx-vk9|17m|SSB"].source, "cluster")
        self.assertEqual(len([k for k in slots if k.startswith("dx-vk9|17m")]), 1)

    def test_garbage_payload(self):
        self.assertEqual(active_slots(self.calendar, None, now=NOW), [])
        self.assertEqual(active_slots(self.calendar, {"items": []}, now=NOW), [])
        bad = {"server_time": "x", "items": {"dx-3x": {"last_ts": "nope"}, "dx-vk9": "x"}}
        self.assertEqual(active_slots(self.calendar, bad, now=NOW), [])


class WorkedTests(unittest.TestCase):
    def setUp(self):
        calendar = parse_calendar(CALENDAR)
        self.slots = slots_by_key(active_slots(calendar, SPOTS, now=NOW))
        self.call_index, self.country_index = build_worked_index(
            {("VK9DS", "10m", "FT4"), ("VK9XY", "15m", "CW"), ("DL1ABC", "20m", "FT8")},
            {("Christmas Island", "10m", "FT4"), ("Christmas Island", "15m", "CW"),
             ("Christmas Island", "17m", "USB"), ("Fed. Rep. of Germany", "20m", "FT8")},
        )

    def status(self, key, country):
        return worked_status(self.slots[key], country, self.call_index, self.country_index)

    def test_statuses(self):
        self.assertEqual(self.status("dx-vk9|10m|FT4", "Christmas Island")[0], "worked")  # via alias VK9DS
        self.assertEqual(self.status("dx-vk9|17m|SSB", "Christmas Island")[0], "new_call")  # entity has 17m USB
        self.assertEqual(self.status("dx-3x|20m|FT8", "Guinea")[0], "new_country")
        self.assertEqual(self.status("dx-3x|20m|FT8", "")[0], "new_slot")
        status, worked = self.status("dx-vk9|15m|CW", "Christmas Island")
        self.assertEqual(status, "worked")
        self.assertEqual(worked, [("15m", "CW"), ("10m", "FT4")])
        self.assertEqual(format_worked(worked), "15m CW · 10m FT4")
        self.assertEqual(format_worked([]), "—")

    def test_worked_wins_over_unknown_country_index(self):
        call_index, country_index = build_worked_index({("3X4U", "20m", "FT8")}, set())
        status, worked = worked_status(self.slots["dx-3x|20m|FT8"], "Guinea", call_index, country_index)
        self.assertEqual(status, "worked")
        self.assertEqual(worked, [("20m", "FT8")])
        self.assertEqual(format_worked([("17m", "USB"), ("40m", "LSB")]), "17m SSB · 40m SSB")

    def test_new_slot_when_entity_not_on_band(self):
        call_index, country_index = build_worked_index(set(), {("Christmas Island", "40m", "CW")})
        self.assertEqual(worked_status(self.slots["dx-vk9|15m|CW"], "Christmas Island", call_index, country_index)[0], "new_slot")


class FormatTests(unittest.TestCase):
    def test_beam_from_grid_and_cty(self):
        vk9 = Dxpedition(id="a", callsign="VK9XY")
        result = beam("JO31", vk9, (-10.48, 105.63))
        assert result is not None
        bearing, km, approx = result
        self.assertTrue(approx)
        self.assertTrue(60 < bearing < 110, bearing)
        self.assertTrue(10_000 < km < 12_000, km)
        guinea = Dxpedition(id="b", callsign="3X4U", grid="IK21")
        result = beam("JO31", guinea, None)
        assert result is not None
        self.assertFalse(result[2])
        self.assertIsNone(beam("", vk9, (-10.48, 105.63)))
        self.assertIsNone(beam("JO31", vk9, None))
        self.assertIsNone(beam("JO31", Dxpedition(id="c", callsign="X", grid="ZZ99"), None))

    def test_texts(self):
        self.assertEqual(format_heading(90, False), "90° O")
        self.assertEqual(format_heading(90, True, "en"), "~90° E")
        self.assertEqual(format_distance(10871.4, True), "ca. 10.871 km")
        self.assertEqual(format_distance(10871.4, False, "en"), "10,871 km")
        self.assertEqual(format_age(30), "jetzt")
        self.assertEqual(format_age(12 * 60 + 5), "12 Min.")
        self.assertEqual(format_until("2026-11-28"), "28.11.")
        self.assertEqual(format_until(""), "—")
        self.assertEqual(format_until("2026-11-28", language="en"), "Nov 28")


class SlashCallCountryTests(unittest.TestCase):
    def test_prefix_after_slash(self):
        from pathlib import Path

        from logger_core import CountryDB

        db = CountryDB(Path(__file__).resolve().parent / "cty.dat")
        expected = {
            "DL1ABC/P": "Fed. Rep. of Germany", "EA8/DL1ABC": "Canary Islands", "K6VHF/HR9": "Honduras",
            "W1AW/KH6": "Hawaii", "VP2V/NY9K": "British Virgin Islands", "W1AW/4": "United States",
            "DL1ABC/P/QRP": "Fed. Rep. of Germany", "DL1ABC": "Fed. Rep. of Germany",
            "VP8/G4ABC": "South Georgia Island", "3Y/P1XYZ": "Peter 1 Island", "FK/C1XYZ": "Chesterfield Islands",
        }
        for call, country in expected.items():
            info = db.lookup(call)
            self.assertEqual(info.country if info else None, country, call)
        self.assertIsNone(db.lookup("DL1ABC/MM"))
        self.assertIsNone(db.lookup("/P"))


class WorkedCacheBandCaseTests(unittest.TestCase):
    def test_upper_case_band_counts_as_worked(self):
        from pathlib import Path
        from types import SimpleNamespace

        from feature_dxcluster import DxClusterFeatureMixin
        from logger_core import CountryDB

        fake = SimpleNamespace(country_db=CountryDB(Path(__file__).resolve().parent / "cty.dat"))
        data = DxClusterFeatureMixin._compute_dx_cluster_worked_cache(
            fake, [{"call": "3X4U", "band": "20M", "mode": "FT8", "country": "GUINEA"}],
        )
        self.assertIn(("3X4U", "20m", "FT8"), data["calls"])
        self.assertIn(("Guinea", "20m", "FT8"), data["countries"])


if __name__ == "__main__":
    unittest.main()
