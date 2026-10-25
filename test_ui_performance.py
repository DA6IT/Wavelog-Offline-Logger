"""Regression tests for the v0.22.0 UI performance paths."""
from __future__ import annotations

import random
import re
import sqlite3
from collections import Counter
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest import TestCase, main, skipIf

from dx_cluster import LazyWorkedHistory, normalize_worked_mode
from feature_dxcluster import DxClusterFeatureMixin
from logger_core import CountryDB, MetadataDB, band_from_mhz
from qso_tree_view import apply_row_diff, insert_row, plan_row_diff

ROOT = Path(__file__).resolve().parent


def make_row(i: int, tag: str = "local", note: str = "") -> tuple[str, str, tuple]:
    return (f"id{i}", tag, (f"2026-10-{1 + i % 28:02d}", "12:00:00", f"DL{i}ABC", note))


def simulate(rows: list, ops: list) -> list:
    """Apply diff operations to a plain list model of the Treeview."""
    current = [row for row in rows if row[0] not in {op[1] for op in ops if op[0] == "delete"}]
    for op in ops:
        if op[0] == "insert":
            current.insert(op[1], op[2])
        elif op[0] == "update":
            current = [op[1] if row[0] == op[1][0] else row for row in current]
    return current


class RowDiffTests(TestCase):
    def test_typical_changes_produce_small_exact_plans(self):
        old = [make_row(i) for i in range(50)]
        new = [make_row(1000)] + old[:10] + old[11:]          # new QSO on top, one deleted
        replacements = {"id5": make_row(5, "wavelog"), "id7": make_row(7, note="edited")}  # status, edit
        new = [replacements.get(row[0], row) for row in new]
        ops = plan_row_diff(old, new)
        self.assertIsNotNone(ops)
        self.assertEqual(len(ops), 4)
        self.assertEqual(simulate(old, ops), new)

    def test_randomized_changes_apply_exactly(self):
        rng = random.Random(7)
        for _ in range(300):
            old = [make_row(i) for i in range(rng.randint(0, 40))]
            new = [row for row in old if rng.random() > 0.2]
            for _insert in range(rng.randint(0, 5)):
                new.insert(rng.randint(0, len(new)), make_row(rng.randint(100, 10_000)))
            new = list({row[0]: row for row in new}.values())
            new = [make_row(int(row[0][2:]), "modified") if rng.random() < 0.1 else row for row in new]
            ops = plan_row_diff(old, new)
            if ops is None:
                continue
            self.assertEqual(simulate(old, ops), new)

    def test_reorder_duplicates_and_large_changes_fall_back(self):
        old = [make_row(i) for i in range(10)]
        self.assertIsNone(plan_row_diff(old, list(reversed(old))))
        self.assertIsNone(plan_row_diff(old + [old[0]], old))
        self.assertIsNone(plan_row_diff(old, old + [make_row(99), make_row(99)]))
        self.assertIsNone(plan_row_diff(old, [make_row(i) for i in range(100, 200)], max_ops=50))
        self.assertEqual(plan_row_diff(old, old), [])


def _tk_root():
    try:
        import tkinter as tk
        root = tk.Tk()
        root.withdraw()
        return root
    except Exception:
        return None


_ROOT = _tk_root()


@skipIf(_ROOT is None, "no display for Tk")
class TreeviewApplyTests(TestCase):
    def test_apply_on_real_treeview_matches_target(self):
        from tkinter import ttk
        tree = ttk.Treeview(_ROOT, columns=("a", "b", "c", "d"), show="headings")
        old = [make_row(i) for i in range(30)]
        for row in old:
            insert_row(tree, "end", row)
        new = [make_row(500)] + [row for row in old if row[0] != "id3"]
        new[10] = make_row(int(new[10][0][2:]), "conflict", "{brace} [x] $y")
        ops = plan_row_diff(old, new)
        apply_row_diff(tree, ops)
        shown = [
            (iid, tuple(tree.item(iid, "tags")), tuple(str(v) for v in tree.item(iid, "values")))
            for iid in tree.get_children()
        ]
        expected = [(iid, (tag,), tuple(str(v) for v in values)) for iid, tag, values in new]
        self.assertEqual(shown, expected)
        tree.destroy()


def eager_worked_cache(country_db, qsos):
    """Pre-0.22 algorithm (behavioural oracle)."""
    calls, countries, counts, totals, history = set(), set(), Counter(), Counter(), {}
    for qso in qsos:
        call = str(qso.get("call") or "").strip().upper()
        if call:
            totals[call] += 1
            history.setdefault(call, []).append({
                "qso_date": str(qso.get("qso_date") or ""), "time_on": str(qso.get("time_on") or ""),
                "band": str(qso.get("band") or ""), "mode": str(qso.get("mode") or ""),
            })
        country = str(qso.get("country") or "").strip()
        if not country and call:
            info = country_db.lookup(call)
            country = info.country if info else ""
        frequency_hz = 0
        try:
            frequency_hz = int(round(float(str(qso.get("freq") or "0").replace(",", ".")) * 1_000_000))
        except (TypeError, ValueError):
            pass
        band = str(qso.get("band") or "").strip()
        if not band and frequency_hz:
            band = band_from_mhz(frequency_hz / 1_000_000) or ""
        mode = normalize_worked_mode(str(qso.get("mode") or ""), frequency_hz, band)
        if not band or not mode:
            continue
        if call:
            calls.add((call, band, mode))
            counts[(call, band, mode)] += 1
        if country:
            countries.add((country, band, mode))
    for rows in history.values():
        rows.sort(key=lambda item: (item["qso_date"], re.sub(r"[^0-9]", "", item["time_on"])), reverse=True)
    return calls, countries, counts, totals, history


class WorkedCacheTests(TestCase):
    def test_optimized_cache_equals_previous_algorithm(self):
        country_db = CountryDB(ROOT / "cty.dat", background=True)
        rng = random.Random(3)
        qsos = []
        for i in range(3000):
            qsos.append({
                "call": rng.choice(["DL1ABC", "dl1abc ", "G4XYZ", "JA1AA", "VK2BB", "", f"OH{i % 50}X"]),
                "band": rng.choice(["20m", "40m", "", " 80m"]),
                "mode": rng.choice(["SSB", "FT8", "cw", "PKTUSB", "", "DATA-L"]),
                "freq": rng.choice(["14.074", "7,074", "", "x", "3.573"]),
                "country": rng.choice(["", "Germany", " Japan "]),
                "qso_date": f"2026-0{1 + i % 9}-1{i % 10}", "time_on": rng.choice(["120000", "12:30:00", "0930", ""]),
            })
        fake = SimpleNamespace(country_db=country_db)
        data = DxClusterFeatureMixin._compute_dx_cluster_worked_cache(fake, qsos)
        calls, countries, counts, totals, history = eager_worked_cache(country_db, qsos)
        self.assertEqual(data["calls"], calls)
        self.assertEqual(data["countries"], countries)
        self.assertEqual(data["worked_counts"], counts)
        self.assertEqual(data["call_totals"], totals)
        for call, rows in history.items():
            self.assertEqual(data["worked_history"].get(call, []), rows)
        self.assertEqual(data["worked_history"].get("NOPE", []), [])
        self.assertEqual(len(data["worked_history"]), len(history))

    def test_lazy_history_default_and_memo(self):
        lazy = LazyWorkedHistory({"DL1ABC": [{"qso_date": "2026-01-01", "time_on": "1200"}]})
        self.assertIsNone(lazy.get("X"))
        first = lazy.get("DL1ABC")
        self.assertIs(first, lazy.get("DL1ABC"))
        self.assertIn("DL1ABC", lazy)


class CountryBackgroundLoadTests(TestCase):
    def test_background_load_gives_same_results(self):
        eager = CountryDB(ROOT / "cty.dat")
        lazy = CountryDB(ROOT / "cty.dat", background=True)
        for call in ("DL1ABC", "VP8/G4ABC", "JA1XYZ", "ZZ9ZZZ", "", "3D2AG/P"):
            a, b = eager.lookup(call), lazy.lookup(call)
            self.assertEqual(a and (a.country, a.cqz, a.matched_prefix), b and (b.country, b.cqz, b.matched_prefix))
        self.assertTrue(lazy.loaded)


class ListMetaTests(TestCase):
    def test_list_meta_matches_row_conversion(self):
        with TemporaryDirectory() as temp:
            db = MetadataDB(Path(temp) / "m.sqlite")
            for i in range(20):
                db.set_status(f"q{i}", "synced" if i % 2 else "local_only",
                              wavelog_id=(i if i % 2 else None), last_synced_hash="h", remote_hash="r")
            reference = [dict(r) for r in db.conn.execute("SELECT * FROM sync_meta ORDER BY created_at")]
            self.assertEqual(db.list_meta(), reference)
            self.assertIsInstance(db.conn.execute("SELECT 1").fetchone(), sqlite3.Row)
            db.close()


if __name__ == "__main__":
    main()
