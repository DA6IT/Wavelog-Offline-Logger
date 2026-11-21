from __future__ import annotations

import unittest
from datetime import date

from qso_tree_view import (
    QsoFilter,
    filter_choices,
    filter_rows,
    normalize_qso_date,
    period_bounds,
)


def row(iid, tag, day, call, band, mode, *, email="—", qrz="—", lotw="—", eqsl="—", clublog="—", dcl="—"):
    return (
        iid,
        tag,
        (day, "12:00:00", call, "DA6IT", "—", band, mode, "14.074", "-10/-12", "X", email, qrz, lotw, eqsl, clublog, dcl),
    )


ROWS = [
    row("a", "wavelog", "2026-11-20", "DL1ABC", "20m", "FT8", lotw="✓"),
    row("b", "local", "2026-11-14", "OE3XYZ", "40m", "SSB", email="✅"),
    row("c", "modified", "2026-01-05", "G4ABC", "20m", "CW", qrz="✓"),
    row("d", "conflict", "2025-06-01", "DL2XX", "2m", "FM"),
    row("e", "error", "20241231", "JA1AAA", "70cm", "ft8"),
]
COUNTRIES = {"a": "Fed. Rep. of Germany", "b": "Austria", "c": "England", "d": "FED. REP. OF GERMANY", "e": "Japan"}
TODAY = date(2026, 11, 20)


def ids(criteria, rows=ROWS):
    return [r[0] for r in filter_rows(rows, criteria, COUNTRIES, today=TODAY)]


class QsoFilterTests(unittest.TestCase):
    def test_no_filter_returns_everything(self):
        self.assertFalse(QsoFilter().active)
        self.assertEqual(ids(QsoFilter()), ["a", "b", "c", "d", "e"])

    def test_band_and_mode(self):
        self.assertEqual(ids(QsoFilter(band="20m")), ["a", "c"])
        self.assertEqual(ids(QsoFilter(mode="FT8")), ["a", "e"])  # case-insensitive
        self.assertEqual(ids(QsoFilter(band="20m", mode="FT8")), ["a"])

    def test_periods(self):
        self.assertEqual(ids(QsoFilter(period="today")), ["a"])
        self.assertEqual(ids(QsoFilter(period="7d")), ["a", "b"])  # 14.11.–20.11.
        self.assertEqual(ids(QsoFilter(period="30d")), ["a", "b"])
        self.assertEqual(ids(QsoFilter(period="365d")), ["a", "b", "c"])
        self.assertEqual(ids(QsoFilter(period="year:2025")), ["d"])
        self.assertEqual(ids(QsoFilter(period="year:2024")), ["e"])  # ADIF date without dashes
        self.assertIsNone(period_bounds("year:20x5", TODAY))
        self.assertIsNone(period_bounds("", TODAY))
        self.assertEqual(period_bounds("7d", TODAY), ("2026-11-14", "2026-11-20"))

    def test_country_is_case_insensitive(self):
        self.assertEqual(ids(QsoFilter(country="Fed. Rep. of Germany")), ["a", "d"])
        self.assertEqual(ids(QsoFilter(country="Japan")), ["e"])

    def test_qsl_status(self):
        self.assertEqual(ids(QsoFilter(qsl="confirmed")), ["a", "c"])
        self.assertEqual(ids(QsoFilter(qsl="unconfirmed")), ["b", "d", "e"])
        self.assertEqual(ids(QsoFilter(qsl="lotw")), ["a"])
        self.assertEqual(ids(QsoFilter(qsl="qrz")), ["c"])
        self.assertEqual(ids(QsoFilter(qsl="email_sent")), ["b"])
        self.assertEqual(ids(QsoFilter(qsl="email_open")), ["a", "c", "d", "e"])

    def test_sync_status(self):
        self.assertEqual(ids(QsoFilter(sync="local")), ["b"])
        self.assertEqual(ids(QsoFilter(sync="wavelog")), ["a"])
        self.assertEqual(ids(QsoFilter(sync="open")), ["c", "d", "e"])

    def test_filters_combine_with_callsign_search(self):
        criteria = QsoFilter(call="DL", band="20m")
        self.assertTrue(criteria.active)
        self.assertFalse(criteria.only_call)
        self.assertEqual(ids(criteria), ["a"])
        self.assertTrue(QsoFilter(call="DL").only_call)
        self.assertEqual(ids(QsoFilter(call="DL*", country="Fed. Rep. of Germany", sync="open")), ["d"])

    def test_broken_rows_do_not_crash(self):
        broken = [("x", "", ()), ("y", None, ("2026-11-20",))]
        self.assertEqual(ids(QsoFilter(band="20m"), broken), [])
        self.assertEqual(ids(QsoFilter(period="today"), broken), ["y"])
        self.assertEqual(ids(QsoFilter(qsl="unconfirmed"), broken), ["x", "y"])

    def test_choices(self):
        choices = filter_choices(ROWS, COUNTRIES)
        self.assertEqual(choices["bands"], ["40m", "20m", "2m", "70cm"])
        self.assertEqual(choices["modes"], ["CW", "FM", "FT8", "SSB"])
        self.assertEqual(choices["years"], ["2026", "2025", "2024"])
        self.assertEqual(choices["countries"], ["Austria", "England", "Fed. Rep. of Germany", "Japan"])

    def test_no_country_and_band_case(self):
        rows = ROWS + [row("f", "local", "2026-11-20", "XX9XX", "20M", "FT8")]
        countries = dict(COUNTRIES)
        self.assertEqual([r[0] for r in filter_rows(rows, QsoFilter(country="__none__"), countries, today=TODAY)], ["f"])
        self.assertEqual([r[0] for r in filter_rows(rows, QsoFilter(band="20m"), countries, today=TODAY)], ["a", "c", "f"])
        choices = filter_choices(rows, countries)
        self.assertTrue(choices["no_country"])
        self.assertEqual(choices["bands"].count("20m"), 1)
        self.assertFalse(filter_choices(ROWS, COUNTRIES)["no_country"])

    def test_day_field_drives_relative_periods(self):
        self.assertEqual([r[0] for r in filter_rows(ROWS, QsoFilter(period="today", day="2026-11-14"), COUNTRIES)], ["b"])
        self.assertNotEqual(QsoFilter(period="today", day="2026-11-14"), QsoFilter(period="today", day="2026-11-15"))

    def test_normalize_qso_date(self):
        self.assertEqual(normalize_qso_date("20261120"), "2026-11-20")
        self.assertEqual(normalize_qso_date("2026-11-20"), "2026-11-20")
        self.assertEqual(normalize_qso_date(""), "")
        self.assertEqual(normalize_qso_date("kaputt"), "")

    def test_large_logbook_filter_is_fast(self):
        import time

        rows = [
            row(str(i), "wavelog" if i % 2 else "local", f"2026-{(i % 12) + 1:02d}-15", f"DL{i:05d}", "20m" if i % 3 else "40m", "FT8")
            for i in range(30000)
        ]
        countries = {str(i): "Fed. Rep. of Germany" for i in range(30000)}
        started = time.perf_counter()
        result = filter_rows(rows, QsoFilter(band="20m", period="year:2026", sync="local", qsl="unconfirmed"), countries, today=TODAY)
        elapsed = time.perf_counter() - started
        self.assertEqual(len(result), sum(1 for i in range(30000) if i % 3 and not i % 2))
        self.assertLess(elapsed, 1.0)


if __name__ == "__main__":
    unittest.main()
