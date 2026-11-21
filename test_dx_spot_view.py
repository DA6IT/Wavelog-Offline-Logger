"""Tests for the "Empfangene DX-Spots" table on the DX Cluster page (v0.24.0).

The table is a ttk.Treeview with real columns that is updated incrementally
(qso_tree_view.plan_row_diff), so selection and scroll position survive the
continuous stream of new spots.
"""
from __future__ import annotations

import tkinter as tk
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest import TestCase, main, mock, skipIf

import feature_dxcluster
from dx_cluster import DxSpot
from feature_dxcluster import (
    DX_SPOT_COLUMNS, DX_SPOT_WORKED_LABELS, DxClusterFeatureMixin, build_dx_spot_row, dx_spot_anchor_index,
    dx_spot_column_widths, dx_spot_default_descending, dx_spot_row_tag, dx_spot_scroll_anchor, dx_spot_sort_value,
    format_dx_spot_frequency, format_dx_spot_time,
)

NOW = datetime.now(timezone.utc)


def make_spot(call: str, khz: float = 14074.0, minutes_ago: float = 10.0, *, band: str = "20m", mode: str = "FT8",
              spotter: str = "DL1ABC", comment: str = "", locator: str = "") -> DxSpot:
    when = NOW - timedelta(minutes=minutes_ago)
    return DxSpot(
        spotter=spotter, call=call, frequency_hz=int(round(khz * 1000)), band=band, mode=mode,
        comment=comment, time_utc=when.strftime("%H%M"), spotted_at_utc=when, locator=locator,
    )


class FormattingTests(TestCase):
    def test_time_and_frequency_have_fixed_shape(self):
        self.assertEqual(format_dx_spot_time("1254"), "12:54")
        self.assertEqual(format_dx_spot_time("0007Z"), "00:07")
        self.assertEqual(format_dx_spot_time(""), "—")
        self.assertEqual(format_dx_spot_time("12:54"), "12:54")
        # Same number of decimals -> right-aligned values line up.
        self.assertEqual(format_dx_spot_frequency(14_074_000), "14.0740")
        self.assertEqual(format_dx_spot_frequency(7_003_500), "7.0035")
        self.assertEqual(format_dx_spot_frequency(10_368_100_000), "10368.1000")
        self.assertEqual(format_dx_spot_frequency(14_074_250), "14.07425")
        self.assertEqual(format_dx_spot_frequency(0), "—")

    def test_row_tag_combines_new_and_worked_state(self):
        self.assertEqual(dx_spot_row_tag(False, False, False), "dx_plain")
        self.assertEqual(dx_spot_row_tag(True, False, False), "dx_new")
        self.assertEqual(dx_spot_row_tag(False, True, True), "dx_call")
        self.assertEqual(dx_spot_row_tag(True, True, True), "dx_new_call")
        self.assertEqual(dx_spot_row_tag(False, False, True), "dx_country")
        self.assertEqual(dx_spot_row_tag(True, False, True), "dx_new_country")

    def test_row_values_follow_column_order(self):
        spot = make_spot("VP8LP", 14205.0, mode="USB", comment="QSL via M0OXO", locator="GD18")
        iid, tag, values = build_dx_spot_row(
            "dx-1", spot, "Falkland Islands", "Fed. Rep. of Germany", "QSL via M0OXO · GD18",
            is_new=False, worked_call=False, worked_country=True,
        )
        self.assertEqual((iid, tag), ("dx-1", "dx_country"))
        self.assertEqual(len(values), len(DX_SPOT_COLUMNS))
        by_key = dict(zip((column[0] for column in DX_SPOT_COLUMNS), values))
        self.assertEqual(by_key["call"], "VP8LP")
        self.assertEqual(by_key["dx_country"], "Falkland Islands")
        self.assertEqual(by_key["worked"], DX_SPOT_WORKED_LABELS[1])
        self.assertEqual(by_key["frequency"], "14.2050")
        self.assertEqual(by_key["mode"], "USB")
        self.assertEqual(by_key["comment"], "QSL via M0OXO · GD18")
        _iid, _tag, plain = build_dx_spot_row(
            "dx-2", make_spot("K1ABC", band="", mode=""), "", "", "",
            is_new=True, worked_call=False, worked_country=False,
        )
        plain_by_key = dict(zip((column[0] for column in DX_SPOT_COLUMNS), plain))
        self.assertEqual((plain_by_key["band"], plain_by_key["mode"], plain_by_key["dx_country"]), ("—", "—", "—"))
        self.assertEqual((plain_by_key["worked"], plain_by_key["comment"]), ("", ""))

    def test_sort_values_and_default_direction(self):
        spot = make_spot("JA1XYZ")
        self.assertEqual(dx_spot_sort_value(spot, "worked", worked_call=True, worked_country=True), 2)
        self.assertEqual(dx_spot_sort_value(spot, "worked", worked_country=True), 1)
        self.assertEqual(dx_spot_sort_value(spot, "worked"), 0)
        self.assertEqual(dx_spot_sort_value(spot, "call"), "ja1xyz")
        self.assertEqual(dx_spot_sort_value(spot, "frequency"), 14_074_000)
        self.assertTrue(dx_spot_default_descending("time"))
        self.assertTrue(dx_spot_default_descending("frequency"))
        self.assertFalse(dx_spot_default_descending("call"))
        self.assertFalse(dx_spot_default_descending("worked"))

    def test_column_widths_fit_heading_with_arrow_and_sample(self):
        widths = {key: (width, minimum) for key, width, minimum in dx_spot_column_widths(
            lambda text: 10 * len(text), lambda text: 7 * len(text), 1.0,
        )}
        self.assertEqual(set(widths), {column[0] for column in DX_SPOT_COLUMNS})
        # "DX-Land ▼" (9 chars * 10) < "Fed. Rep. of Germany" (20 chars * 7)
        self.assertEqual(widths["dx_country"][0], 20 * 7 + 18)
        # "UTC ▼" (5 * 10) > "00:00" (5 * 7)
        self.assertEqual(widths["time"][0], 5 * 10 + 18)
        # The stretching comment column never shrinks below its minimum.
        self.assertGreaterEqual(widths["comment"][1], 160)
        self.assertEqual(widths["comment"][0], widths["comment"][1])
        # Translated headings are measured, not the German ones.
        english = dict((key, width) for key, width, _min in dx_spot_column_widths(
            lambda text: 10 * len(text), lambda text: 1, 1.0,
            lambda text: {"DX-Land": "DX country of the station"}.get(text, text),
        ) if key == "dx_country")
        self.assertEqual(english["dx_country"], len("DX country of the station ▼") * 10 + 18)

    def test_scroll_anchor_helpers(self):
        rows = [(f"dx-{i}", "dx_plain", ()) for i in range(40)]
        self.assertIsNone(dx_spot_scroll_anchor(rows, 0.0))  # at the top: follow new spots
        self.assertIsNone(dx_spot_scroll_anchor([], 0.5))
        self.assertEqual(dx_spot_scroll_anchor(rows, 10 / 40), "dx-10")
        self.assertEqual(dx_spot_scroll_anchor(rows, 1.0), "dx-39")
        self.assertEqual(dx_spot_anchor_index(["a", "b", "c"], "c"), 2)
        self.assertIsNone(dx_spot_anchor_index(["a"], "gone"))
        self.assertIsNone(dx_spot_anchor_index(["a"], None))


def _display_available() -> bool:
    try:
        root = tk.Tk()
        root.destroy()
        return True
    except Exception:
        return False


_HAS_DISPLAY = _display_available()

COUNTRIES = {"JA": ("Japan", "AS"), "VK": ("Australia", "OC"), "DL": ("Fed. Rep. of Germany", "EU"),
             "K": ("United States", "NA"), "G": ("England", "EU"), "PY": ("Brazil", "SA")}


class _Settings:
    def __init__(self):
        self.values = {}

    def get_setting(self, key, default=""):
        return self.values.get(key, default)

    def set_setting(self, key, value):
        self.values[key] = value


class _CountryDB:
    def lookup(self, call):
        for prefix in sorted(COUNTRIES, key=len, reverse=True):
            if call.startswith(prefix):
                country, cont = COUNTRIES[prefix]
                return SimpleNamespace(country=country, cont=cont)
        return None


if _HAS_DISPLAY:
    class Harness(DxClusterFeatureMixin, tk.Tk):
        """The DX Cluster page with the minimum of the app shell around it."""

        def __init__(self):
            tk.Tk.__init__(self)
            self.geometry("1100x700+0+0")
            self.closing = False
            self.language = "de"
            self._ui_scale = 1.0
            self.db = _Settings()
            self.country_db = _CountryDB()
            self.status_var = tk.StringVar(master=self)
            self.tuned: list[str] = []
            self.pages = {}
            self._init_dxcluster_feature()
            container = tk.Frame(self)
            container.pack(fill="both", expand=True)
            container.columnconfigure(0, weight=1)
            container.rowconfigure(0, weight=1)
            self.page_container = container
            self._build_dx_cluster_page()

        # -- app shell stubs --------------------------------------------------
        def _new_page(self, name):
            frame = tk.Frame(self.page_container)
            frame.grid(row=0, column=0, sticky="nsew")
            self.pages[name] = frame
            return frame

        def _card(self, parent, **grid):
            frame = tk.Frame(parent)
            frame.grid(**grid)
            return frame

        def _tr(self, value):
            return "" if value is None else str(value)

        def _canonical_choice(self, value, canonical_values):
            return value if value in canonical_values else value

        def _update_qso_worked_status(self):
            pass

        def _tune_selected_dx_spot(self):
            spot = self._selected_dx_cluster_spot()
            self.tuned.append(spot.call if spot else "")

        # -- helpers ------------------------------------------------------------
        def add(self, spot: DxSpot) -> None:
            self._accept_dx_cluster_spot(self.dx_cluster_generation, spot)

        def shown(self) -> list[str]:
            return [self.dx_cluster_tree.set(iid, "call") for iid in self.dx_cluster_tree.get_children()]

        def iid_of(self, call: str) -> str:
            return next(iid for iid, spot in self.dx_cluster_spots if spot.call == call)


@skipIf(not _HAS_DISPLAY, "no display for Tk")
class SpotTableTests(TestCase):
    def setUp(self):
        self.app = Harness()
        self.app.update()

    def tearDown(self):
        self.app.closing = True
        for job in (self.app.dx_cluster_filter_job, self.app.dx_cluster_refresh_job, self.app.dx_cluster_layout_job):
            if job is not None:
                self.app.after_cancel(job)
        self.app.destroy()

    def test_rows_columns_and_colour_tags(self):
        app = self.app
        app.dx_cluster_worked_calls = {("VK2ABC", "40m", "CW")}
        app.dx_cluster_worked_countries = {("Japan", "20m", "FT8")}
        app.add(make_spot("JA1XYZ", minutes_ago=5))
        app.add(make_spot("VK2ABC", 7003.5, minutes_ago=0.5, band="40m", mode="CW", comment="TNX", locator="QF56"))
        app._refresh_dx_cluster_spots()
        tree = app.dx_cluster_tree
        self.assertEqual(tuple(tree["columns"]), tuple(column[0] for column in DX_SPOT_COLUMNS))
        self.assertEqual(app.shown(), ["VK2ABC", "JA1XYZ"])  # newest first
        vk, ja = tree.get_children()
        self.assertEqual(tree.item(vk, "tags"), ("dx_new_call",))
        self.assertEqual(tree.item(ja, "tags"), ("dx_country",))
        self.assertEqual(tree.set(vk, "worked"), DX_SPOT_WORKED_LABELS[0])
        self.assertEqual(tree.set(vk, "frequency"), "7.0035")
        self.assertEqual(tree.set(vk, "comment"), "TNX · QF56")
        self.assertEqual(tree.set(vk, "dx_country"), "Australia")
        self.assertEqual(tree.set(ja, "spotter_country"), "Fed. Rep. of Germany")
        self.assertEqual(app.dx_cluster_visible_ids, [vk, ja])
        self.assertIn("▼", tree.heading("time", "text"))

    def test_selection_survives_incremental_refresh_and_qrz_follows_it(self):
        app = self.app
        for index, call in enumerate(("DL1AAA", "DL2BBB", "DL3CCC")):
            app.add(make_spot(call, minutes_ago=10 - index))
        app._refresh_dx_cluster_spots()
        target = app.iid_of("DL2BBB")
        app.dx_cluster_tree.selection_set(target)
        app.update()
        self.assertEqual(app.dx_cluster_selected_id, target)
        self.assertEqual(str(app.dx_cluster_qrz_button.cget("state")), "normal")

        captured = []
        real_apply = feature_dxcluster.apply_row_diff
        with mock.patch.object(feature_dxcluster, "apply_row_diff", side_effect=lambda tree, ops: (captured.append(list(ops)), real_apply(tree, ops))):
            app.add(make_spot("JA1NEW", minutes_ago=0.1))
            app._refresh_dx_cluster_spots()
        app.update()
        self.assertEqual(captured and [op[0] for op in captured[0]], ["insert"])  # one insert, nothing rebuilt
        self.assertEqual(app.shown(), ["JA1NEW", "DL3CCC", "DL2BBB", "DL1AAA"])
        self.assertEqual(app.dx_cluster_tree.selection(), (target,))
        self.assertEqual(app._selected_dx_cluster_spot().call, "DL2BBB")

        # A filter that hides the selected spot clears the selection.
        app.dx_cluster_band_filter_var.set("40m")
        app._refresh_dx_cluster_spots()
        app.update()
        self.assertEqual(app.shown(), [])
        self.assertIsNone(app.dx_cluster_selected_id)
        self.assertEqual(str(app.dx_cluster_qrz_button.cget("state")), "disabled")

    def test_scrolled_view_keeps_its_top_row_while_spots_arrive(self):
        app = self.app
        for index in range(80):
            app.add(make_spot(f"DL{index}ABC", minutes_ago=20 - index * 0.2))
        app._refresh_dx_cluster_spots()
        tree = app.dx_cluster_tree
        app.update()
        tree.yview_moveto(30 / 80)
        app.update()
        top_before = tree.identify_row(tree.bbox(tree.get_children()[30])[1] + 2) if tree.bbox(tree.get_children()[30]) else None
        self.assertEqual(top_before, tree.get_children()[30])
        for index in range(3):
            app.add(make_spot(f"JA{index}NEW", minutes_ago=0.05))
        app._refresh_dx_cluster_spots()
        app.update()
        self.assertEqual(tree.get_children()[33], top_before)
        self.assertTrue(tree.bbox(top_before), "anchored row must stay visible")
        self.assertAlmostEqual(tree.yview()[0], 33 / 83, places=3)

        # At the very top the list follows the newest spots.
        tree.yview_moveto(0)
        app.update()
        app.add(make_spot("VK9TOP", minutes_ago=0.01))
        app._refresh_dx_cluster_spots()
        app.update()
        self.assertEqual(tree.yview()[0], 0.0)
        self.assertEqual(app.shown()[0], "VK9TOP")

    def test_header_sort_toggles_and_keeps_selection(self):
        app = self.app
        app.dx_cluster_worked_calls = {("DL2BBB", "20m", "FT8")}
        for index, (call, khz) in enumerate((("K1AAA", 14010.0), ("DL2BBB", 14074.0), ("JA3CCC", 14020.0))):
            app.add(make_spot(call, khz, minutes_ago=10 - index))
        app._refresh_dx_cluster_spots()
        app.dx_cluster_tree.selection_set(app.iid_of("K1AAA"))
        app.update()
        app._dx_cluster_sort_by("call")
        self.assertEqual(app.shown(), ["DL2BBB", "JA3CCC", "K1AAA"])
        self.assertTrue(app.dx_cluster_tree.heading("call", "text").endswith("▲"))
        self.assertNotIn("▼", app.dx_cluster_tree.heading("time", "text"))
        app._dx_cluster_sort_by("call")
        self.assertEqual(app.shown(), ["K1AAA", "JA3CCC", "DL2BBB"])
        self.assertTrue(app.dx_cluster_tree.heading("call", "text").endswith("▼"))
        app._dx_cluster_sort_by("frequency")
        self.assertEqual(app.shown(), ["DL2BBB", "JA3CCC", "K1AAA"])
        app._dx_cluster_sort_by("worked")  # not worked first, newest first within a group
        self.assertEqual(app.shown(), ["JA3CCC", "K1AAA", "DL2BBB"])
        app.update()
        self.assertEqual(app.dx_cluster_tree.selection(), (app.iid_of("K1AAA"),))
        # Clicking a heading runs the same sort (Tk heading -command).
        app.dx_cluster_tree.tk.call(app.dx_cluster_tree.heading("call", "command"))
        self.assertEqual(app.shown(), ["DL2BBB", "JA3CCC", "K1AAA"])
        self.assertEqual(app.dx_cluster_tree.selection(), (app.iid_of("K1AAA"),))

    def test_double_click_and_return_tune_but_not_on_heading(self):
        app = self.app
        app.add(make_spot("JA1XYZ", minutes_ago=3))
        app.add(make_spot("VK2ABC", minutes_ago=2))
        app._refresh_dx_cluster_spots()
        app.update()
        tree = app.dx_cluster_tree
        target = app.iid_of("JA1XYZ")
        x, y, _w, h = tree.bbox(target, "call")
        self.assertEqual(app._dx_cluster_table_double_click(SimpleNamespace(x=x + 3, y=y + h // 2)), "break")
        self.assertEqual(app.tuned, ["JA1XYZ"])
        self.assertEqual(tree.selection(), (target,))
        self.assertIsNone(app._dx_cluster_table_double_click(SimpleNamespace(x=x + 3, y=3)))  # heading
        self.assertEqual(app.tuned, ["JA1XYZ"])
        tree.selection_set(app.iid_of("VK2ABC"))
        app.update()
        app._dx_cluster_table_return()
        self.assertEqual(app.tuned, ["JA1XYZ", "VK2ABC"])

    def test_new_highlight_expires_with_the_periodic_refresh(self):
        app = self.app
        spot = make_spot("JA1XYZ", minutes_ago=1)
        app.add(spot)
        app._refresh_dx_cluster_spots()
        iid = app.iid_of("JA1XYZ")
        self.assertEqual(app.dx_cluster_tree.item(iid, "tags"), ("dx_new",))
        later = NOW + timedelta(minutes=2)
        with mock.patch.object(feature_dxcluster, "datetime", wraps=datetime) as fake_datetime:
            fake_datetime.now.return_value = later
            app._refresh_dx_cluster_spots()
        self.assertEqual(app.dx_cluster_tree.item(iid, "tags"), ("dx_plain",))

    def test_clear_list_empties_table(self):
        app = self.app
        app.add(make_spot("JA1XYZ"))
        app._refresh_dx_cluster_spots()
        app._clear_dx_cluster_spots()
        self.assertEqual(app.dx_cluster_tree.get_children(), ())
        self.assertEqual(app.dx_cluster_count_label.cget("text"), "0 / 0 Spots")

    def test_column_layout_follows_ui_zoom(self):
        app = self.app
        wide = app.dx_cluster_tree.column("dx_country", "width")
        app._ui_scale = 0.7
        app._dx_cluster_apply_layout()
        self.assertEqual(app.dx_cluster_column_scale, 0.7)
        self.assertLessEqual(app.dx_cluster_tree.column("comment", "minwidth"), 160)
        # Font size is unchanged in this harness, so measured widths stay.
        self.assertEqual(app.dx_cluster_tree.column("dx_country", "width"), wide - 18 + max(10, round(18 * 0.7)))


if __name__ == "__main__":
    main()
