"""Callsign search in the logbook view (v0.24.0)."""
from __future__ import annotations

from unittest import TestCase, main

from qso_tree_view import filter_rows_by_call, normalize_call_query


def row(iid: str, call: str) -> tuple[str, str, tuple]:
    return (iid, "local", ("2026-11-08", "12:00", call, "", "", "20m", "SSB", "14.250", "59/59", "LOCAL ONLY"))


ROWS = [row("1", "DL1AB"), row("2", "DL1XYZ/P"), row("3", "OE3ABC"), row("4", "dl2ab"), row("5", "DA6IT"), row("6", "")]


class CallSearchTests(TestCase):
    def ids(self, query):
        return [r[0] for r in filter_rows_by_call(ROWS, query)]

    def test_empty_query_returns_everything_in_order(self):
        self.assertEqual(self.ids(""), ["1", "2", "3", "4", "5", "6"])
        self.assertEqual(self.ids("   "), ["1", "2", "3", "4", "5", "6"])
        self.assertEqual(self.ids(None), ["1", "2", "3", "4", "5", "6"])

    def test_substring_is_case_insensitive(self):
        self.assertEqual(self.ids("dl1"), ["1", "2"])
        self.assertEqual(self.ids("AB"), ["1", "3", "4"])
        self.assertEqual(self.ids("/p"), ["2"])

    def test_spaces_are_ignored(self):
        self.assertEqual(normalize_call_query(" dl 1ab "), "DL1AB")
        self.assertEqual(self.ids(" dl1ab "), ["1"])

    def test_wildcards(self):
        self.assertEqual(self.ids("DL?AB"), ["1", "4"])
        self.assertEqual(self.ids("DL*AB"), ["1", "4"])
        self.assertEqual(self.ids("OE*C"), ["3"])
        self.assertEqual(self.ids("*"), ["1", "2", "3", "4", "5", "6"])

    def test_regex_characters_are_literal(self):
        self.assertEqual(self.ids("."), [])
        self.assertEqual(self.ids("DL1XYZ/P"), ["2"])
        self.assertEqual(self.ids("[A"), [])

    def test_no_match(self):
        self.assertEqual(self.ids("K1ABC"), [])

    def test_short_or_broken_rows_do_not_fail(self):
        broken = [("x", "local", ()), ("y", "local", None), row("z", "DL1AB")]
        self.assertEqual([r[0] for r in filter_rows_by_call(broken, "DL1")], ["z"])

    def test_large_logbook_is_fast(self):
        import time

        rows = [row(str(i), f"DL{i % 10}A{i:05d}") for i in range(50_000)]
        started = time.perf_counter()
        hits = filter_rows_by_call(rows, "DL3A")
        wild = filter_rows_by_call(rows, "DL?A0001*")
        self.assertEqual(len(hits), 5_000)
        self.assertEqual(len(wild), 10)  # A00010 … A00019
        self.assertLess(time.perf_counter() - started, 1.0)


if __name__ == "__main__":
    main()
