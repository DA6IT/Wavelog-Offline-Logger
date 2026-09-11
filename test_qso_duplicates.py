from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from logger_core import LogStore, qso_to_adif_record
from qso_duplicates import QsoMatcher, find_duplicate_qso


def qso(
    call: str,
    time_on: str,
    *,
    band: str = "20m",
    mode: str = "FT8",
    freq: str = "14.074",
) -> dict:
    return {
        "call": call,
        "qso_date": "2026-09-10",
        "time_on": time_on,
        "band": band,
        "mode": mode,
        "freq": freq,
        "station_call": "DA6IT",
        "operator_call": "DA6IT",
    }


class QsoDuplicateTests(unittest.TestCase):
    def test_repeated_73_with_shifted_time_is_duplicate(self):
        first = qso("DL1ABC", "120000", freq="14.075230")
        repeated = qso("DL1ABC", "120045", freq="14.075245")
        self.assertIsNotNone(find_duplicate_qso([first], repeated))

    def test_contact_outside_time_window_is_not_duplicate(self):
        first = qso("DL1ABC", "120000")
        later = qso("DL1ABC", "120131")
        self.assertIsNone(QsoMatcher([first]).find(later))

    def test_other_band_is_not_duplicate(self):
        first = qso("DL1ABC", "120000", band="20m", freq="14.074")
        other_band = qso("DL1ABC", "120030", band="40m", freq="7.074")
        self.assertIsNone(QsoMatcher([first]).find(other_band))

    def test_frequency_more_than_ten_khz_apart_is_not_duplicate(self):
        first = qso("DL1ABC", "120000", freq="14.074")
        other_frequency = qso("DL1ABC", "120030", freq="14.090")
        self.assertIsNone(QsoMatcher([first]).find(other_frequency))

    def test_ssb_repeat_with_shifted_time_is_not_collapsed(self):
        first = qso("DL1ABC", "120000", mode="SSB", freq="14.250")
        repeated = qso("DL1ABC", "120045", mode="SSB", freq="14.250")
        self.assertIsNone(QsoMatcher([first]).find(repeated))

    def test_adif_import_deduplicates_repeated_wsjtx_records_inside_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            store = LogStore(root / "logs", "test")
            source = root / "wsjtx_log.adi"
            source.write_text(
                qso_to_adif_record(
                    qso("DL1ABC", "120000", freq="14.075230")
                )
                + qso_to_adif_record(
                    qso("DL1ABC", "120045", freq="14.075245")
                ),
                encoding="utf-8",
            )

            report = store.import_adif(source)

            self.assertEqual(report["imported"], 1)
            self.assertEqual(report["skipped"], 1)
            self.assertEqual(len(store.scan()), 1)


if __name__ == "__main__":
    unittest.main()
