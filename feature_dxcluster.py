from __future__ import annotations

import atexit
import re
import threading
import urllib.parse
import webbrowser
from collections import Counter
from datetime import datetime, timezone
import tkinter as tk
from tkinter import font as tkfont
from tkinter import messagebox, simpledialog, ttk
from typing import Callable, Sequence
from dx_cluster import (
    DEFAULT_CLUSTER_HOST, DEFAULT_CLUSTER_PORT, DxClusterClient, DxClusterConfig, DxClusterError, DxSpot, DxSpotterConfig, LazyWorkedHistory, SPOTTER_REGION_OPTIONS, normalize_worked_mode, select_dx_spot_candidate, spot_comment_with_mode, spot_sort_value, spotter_region_for_continent, worked_flags,
)
from logger_core import BANDS, MODES, band_from_mhz
from qso_tree_view import apply_row_diff, insert_row, plan_row_diff
from ui_theme import theme


# Spot table ("Empfangene DX-Spots"): key, German heading, sample cell text
# that must fit, cell anchor, stretch.  Column widths are measured from the
# heading and the sample in the current (zoomed) fonts, so they fit in every
# language and UI scale.  Only the comment column stretches; every other
# column keeps its width and position while spots arrive.
DX_SPOT_COLUMNS = (
    ("time", "UTC", "00:00", "center", False),
    ("call", "DX-Rufzeichen", "EA8/DL1ABC", "w", False),
    ("dx_country", "DX-Land", "Fed. Rep. of Germany", "w", False),
    ("worked", "Gearbeitet", "✓ Land", "center", False),
    ("frequency", "MHz", "28.4950", "e", False),
    ("band", "Band", "160m", "center", False),
    ("mode", "Mode", "PSK31", "center", False),
    ("spotter", "Spotter", "DL8ABC-#", "w", False),
    ("spotter_country", "Spotter-Land", "Fed. Rep. of Germany", "w", False),
    ("comment", "Kommentar", "", "w", True),
)
DX_SPOT_COMMENT_MIN_WIDTH = 160
DX_SPOT_CELL_PADDING = 18
DX_SPOT_NEW_SECONDS = 120
# Text of the "Gearbeitet" column: callsign / only the DXCC entity worked on
# the spot's band and mode (German; translated via ui_preferences).
DX_SPOT_WORKED_LABELS = ("✓ Call", "✓ Land")


def format_dx_spot_time(time_utc: str) -> str:
    """Cluster time "1254" -> "12:54"; anything else unchanged or "—"."""
    text = str(time_utc or "").strip().upper().removesuffix("Z")
    if len(text) == 4 and text.isdigit():
        return f"{text[:2]}:{text[2:]}"
    return text or "—"


def format_dx_spot_frequency(frequency_hz: int) -> str:
    """MHz with a fixed number of decimals so right-aligned values line up.

    Cluster spots have 100 Hz resolution, i.e. four MHz decimals; finer
    values keep their precision.
    """
    try:
        hz = int(frequency_hz)
    except (TypeError, ValueError):
        return "—"
    if hz <= 0:
        return "—"
    if hz % 100 == 0:
        return f"{hz / 1_000_000:.4f}"
    return f"{hz / 1_000_000:.6f}".rstrip("0")


def dx_spot_row_tag(is_new: bool, worked_call: bool, worked_country: bool) -> str:
    """One Treeview tag per row (combined state, so no tag precedence issues)."""
    state = "call" if worked_call else ("country" if worked_country else "")
    if is_new:
        return "dx_new_" + state if state else "dx_new"
    return "dx_" + state if state else "dx_plain"


def build_dx_spot_row(
    item_id: str,
    spot: DxSpot,
    dx_country: str,
    spotter_country: str,
    comment: str,
    *,
    is_new: bool,
    worked_call: bool,
    worked_country: bool,
    worked_labels: tuple[str, str] = DX_SPOT_WORKED_LABELS,
) -> tuple[str, str, tuple]:
    """``(iid, tag, values)`` in the order of :data:`DX_SPOT_COLUMNS`."""
    worked = worked_labels[0] if worked_call else (worked_labels[1] if worked_country else "")
    values = (
        format_dx_spot_time(spot.time_utc),
        spot.call or "—",
        dx_country or "—",
        worked,
        format_dx_spot_frequency(spot.frequency_hz),
        spot.band or "—",
        spot.mode or "—",
        spot.spotter or "—",
        spotter_country or "—",
        comment or "",
    )
    return item_id, dx_spot_row_tag(is_new, worked_call, worked_country), values


def dx_spot_sort_value(
    spot: DxSpot,
    key: str,
    dx_country: str = "",
    spotter_country: str = "",
    comment: str = "",
    worked_call: bool = False,
    worked_country: bool = False,
):
    if key == "worked":
        # Ties keep the newest-first order of the spot list (stable sort).
        return 2 if worked_call else (1 if worked_country else 0)
    return spot_sort_value(spot, key, dx_country, spotter_country, comment)


def dx_spot_default_descending(key: str) -> bool:
    """Newest spot / highest frequency first; text columns A→Z; not worked first."""
    return key in {"time", "frequency"}


def dx_spot_column_widths(
    measure_heading: Callable[[str], int],
    measure_cell: Callable[[str], int],
    scale: float = 1.0,
    translate: Callable[[str], str] = lambda text: text,
) -> list[tuple[str, int, int]]:
    """``(key, width, minwidth)`` per column, measured in the current fonts.

    A column is as wide as its heading including the sort arrow or its
    sample text, whichever is wider, plus padding.  The comment column takes
    the remaining space but never less than its minimum.
    """
    padding = max(10, int(round(DX_SPOT_CELL_PADDING * scale)))
    result = []
    for key, label, sample, _anchor, stretch in DX_SPOT_COLUMNS:
        heading = measure_heading(translate(label) + " ▼")
        cell = measure_cell(translate(sample)) if sample else 0
        width = max(heading, cell) + padding
        if stretch:
            width = max(width, int(round(DX_SPOT_COMMENT_MIN_WIDTH * scale)))
            result.append((key, width, width))
        else:
            result.append((key, width, max(20, min(width, int(round(36 * scale))))))
    return result


def dx_spot_scroll_anchor(rows: Sequence[tuple], first_fraction: float) -> str | None:
    """Id of the row at the top of a scrolled view; ``None`` at the very top.

    At the top the view stays at the top so new spots remain visible.
    """
    if not rows or first_fraction <= 0:
        return None
    index = min(len(rows) - 1, max(0, int(round(first_fraction * len(rows)))))
    return rows[index][0]


def dx_spot_anchor_index(visible_ids: Sequence[str], anchor: str | None) -> int | None:
    if anchor is None:
        return None
    try:
        return list(visible_ids).index(anchor)
    except ValueError:
        return None


class DxClusterFeatureMixin:
    def _init_dxcluster_feature(self) -> None:
        self.dx_cluster = DxClusterClient()
        atexit.register(self.dx_cluster.stop)
        self.dx_cluster_generation = 0
        self.dx_spotter = DxClusterClient()
        atexit.register(self.dx_spotter.stop)
        self.dx_spotter_generation = 0
        self.dx_spotter_active_config: DxSpotterConfig | None = None
        self.dx_cluster_spots: list[tuple[str, DxSpot]] = []
        self.dx_cluster_spot_by_id: dict[str, DxSpot] = {}
        self.dx_cluster_sequence = 0
        self.dx_cluster_country_cache: dict[str, str] = {}
        self.dx_cluster_continent_cache: dict[str, str] = {}
        self.dx_cluster_worked_calls: set[tuple[str, str, str]] = set()
        self.dx_cluster_worked_countries: set[tuple[str, str, str]] = set()
        self.qso_worked_counts: Counter[tuple[str, str, str]] = Counter()
        self.qso_worked_call_totals: Counter[str] = Counter()
        self.qso_worked_history: LazyWorkedHistory = LazyWorkedHistory()
        self.dx_cluster_filter_job = None
        self.dx_cluster_refresh_job = None
        self.dx_cluster_session_received = 0
        self.dx_cluster_last_spot_utc: datetime | None = None
        self.dx_cluster_seen_keys: set[tuple] = set()
        self.dx_cluster_sort_key = "time"
        self.dx_cluster_sort_descending = True
        self.dx_cluster_reveal_selection = False

    def _build_dx_cluster_page(self):
        p = self._new_page("dx_cluster")
        p.columnconfigure(0, weight=1)
        p.rowconfigure(2, weight=1)

        setup = self._card(p, row=0, column=0, sticky="ew", pady=(0, 10))
        setup.columnconfigure(0, weight=3)
        setup.columnconfigure(1, weight=1)
        setup.columnconfigure(2, weight=2)
        setup.columnconfigure(3, weight=3)
        ttk.Label(setup, text="Telnet-Verbindung", style="CardTitle.TLabel").grid(row=0, column=0, columnspan=4, sticky="w")
        ttk.Label(
            setup,
            text="Online-Funktion: Der Empfang funktioniert nur bei bestehender Internetverbindung. Host und Port gehören zum aktiven Profil; das Login-Rufzeichen kommt immer aus dessen Stationsdaten. Die Empfangsverbindung wird nach jedem Programmstart bewusst manuell hergestellt.",
            style="Muted.Card.TLabel", wraplength=950,
        ).grid(row=1, column=0, columnspan=4, sticky="w", pady=(3, 10))

        self.dx_cluster_host_var = tk.StringVar(value=DEFAULT_CLUSTER_HOST)
        self.dx_cluster_port_var = tk.StringVar(value=str(DEFAULT_CLUSTER_PORT))
        self.dx_cluster_call_var = tk.StringVar()
        fields = (
            ("DX-Cluster-Host", self.dx_cluster_host_var),
            ("Telnet-Port", self.dx_cluster_port_var),
            ("Login-Rufzeichen", self.dx_cluster_call_var),
        )
        for column, (label, variable) in enumerate(fields):
            ttk.Label(setup, text=label, style="Card.TLabel").grid(row=2, column=column, sticky="w", padx=(0, 10), pady=(2, 3))
            state = "readonly" if variable is self.dx_cluster_call_var else "normal"
            ttk.Entry(setup, textvariable=variable, state=state).grid(
                row=3, column=column, sticky="ew", padx=(0, 10),
            )

        buttons = ttk.Frame(setup, style="Card.TFrame")
        buttons.grid(row=3, column=3, sticky="e")
        ttk.Button(buttons, text="Einstellungen speichern", style="Secondary.TButton", command=self.save_dx_cluster_settings).pack(side="left")
        self.dx_cluster_start_button = ttk.Button(buttons, text="Verbinden", style="Primary.TButton", command=self.start_dx_cluster)
        self.dx_cluster_start_button.pack(side="left", padx=8)
        self.dx_cluster_stop_button = ttk.Button(buttons, text="Trennen", style="Secondary.TButton", command=self.stop_dx_cluster)
        self.dx_cluster_stop_button.pack(side="left")

        self.dx_cluster_status_label = tk.Label(
            setup, text="DX Cluster ist getrennt.", bg=theme.CARD, fg=theme.MUTED, font=("Segoe UI", 9),
            justify="left", anchor="w", wraplength=1050,
        )
        self.dx_cluster_status_label.grid(row=4, column=0, columnspan=4, sticky="ew", pady=(10, 0))

        filters = self._card(p, row=1, column=0, sticky="ew", pady=(0, 10))
        ttk.Label(filters, text="Spot-Filter", style="CardTitle.TLabel").pack(side="left", padx=(0, 18))
        tk.Label(filters, text="Band", bg=theme.CARD, fg=theme.MUTED, font=("Segoe UI", 9)).pack(side="left", padx=(0, 5))
        self.dx_cluster_band_filter_var = tk.StringVar(value=self._tr("Alle"))
        band_filter = ttk.Combobox(filters, textvariable=self.dx_cluster_band_filter_var, values=[self._tr("Alle"), *BANDS], state="readonly", width=10)
        band_filter.pack(side="left")
        band_filter.bind("<<ComboboxSelected>>", lambda _event: self._refresh_dx_cluster_spots())
        tk.Label(filters, text="Mode", bg=theme.CARD, fg=theme.MUTED, font=("Segoe UI", 9)).pack(side="left", padx=(18, 5))
        self.dx_cluster_mode_filter_var = tk.StringVar(value=self._tr("Alle"))
        mode_filter = ttk.Combobox(filters, textvariable=self.dx_cluster_mode_filter_var, values=[self._tr("Alle"), *[mode for mode in MODES if mode != "SSB"]], state="readonly", width=14)
        mode_filter.pack(side="left")
        mode_filter.bind("<<ComboboxSelected>>", lambda _event: self._refresh_dx_cluster_spots())
        tk.Label(filters, text="Spotter-Region", bg=theme.CARD, fg=theme.MUTED, font=("Segoe UI", 9)).pack(side="left", padx=(18, 5))
        self.dx_cluster_spotter_region_filter_var = tk.StringVar(value=self._tr("Alle"))
        region_filter = ttk.Combobox(
            filters, textvariable=self.dx_cluster_spotter_region_filter_var,
            values=tuple(self._tr(value) for value in SPOTTER_REGION_OPTIONS), state="readonly", width=16,
        )
        region_filter.pack(side="left")
        region_filter.bind("<<ComboboxSelected>>", self._dx_cluster_spotter_region_changed)
        tk.Label(filters, text="Zeitraum", bg=theme.CARD, fg=theme.MUTED, font=("Segoe UI", 9)).pack(side="left", padx=(18, 5))
        self.dx_cluster_time_filter_var = tk.StringVar(value=self._tr("30 Minuten"))
        time_filter = ttk.Combobox(
            filters, textvariable=self.dx_cluster_time_filter_var,
            values=tuple(self._tr(value) for value in ("15 Minuten", "30 Minuten", "60 Minuten", "2 Stunden", "Alle")),
            state="readonly", width=12,
        )
        time_filter.pack(side="left")
        time_filter.bind("<<ComboboxSelected>>", self._dx_cluster_time_filter_changed)
        ttk.Button(filters, text="Liste leeren", style="Secondary.TButton", command=self._clear_dx_cluster_spots).pack(side="right")

        table = self._card(p, row=2, column=0, sticky="nsew")
        table.columnconfigure(0, weight=1)
        table.rowconfigure(1, weight=1)
        ttk.Label(table, text="Empfangene DX-Spots", style="CardTitle.TLabel").grid(row=0, column=0, sticky="w", pady=(0, 8))
        tk.Label(
            table,
            text="Doppelklick/Enter: TRX abstimmen · neu (< 2 min): hellblau · auf Band und Mode gearbeitet: grün",
            bg=theme.CARD, fg=theme.MUTED, font=("Segoe UI", 9), anchor="e", justify="right", wraplength=760,
        ).grid(row=0, column=1, sticky="e", padx=(12, 0), pady=(0, 8))

        tree_box = ttk.Frame(table, style="Card.TFrame")
        tree_box.grid(row=1, column=0, columnspan=2, sticky="nsew")
        tree_box.columnconfigure(0, weight=1)
        tree_box.rowconfigure(0, weight=1)
        self.dx_cluster_visible_ids: list[str] = []
        self.dx_cluster_selected_id: str | None = None
        # Rows the Treeview currently shows, as (iid, tag, values); None
        # forces a full rebuild on the next refresh.
        self.dx_cluster_shown_rows: list[tuple[str, str, tuple]] | None = None
        self.dx_cluster_column_scale: float | None = None
        self.dx_cluster_layout_job = None
        style = ttk.Style(self)
        # Own style: the selected row must stay distinguishable from the
        # light-blue "new" rows (the shared Treeview style uses ACTIVE_BG for
        # both).  Everything else (font, colours) is inherited from Treeview.
        style.map(
            "DxSpots.Treeview",
            background=[("selected", theme.ACCENT)],
            foreground=[("selected", theme.INPUT_BG)],
        )
        self.dx_cluster_bold_font = tkfont.Font(root=self, family="Segoe UI", size=9, weight="bold")
        self.dx_cluster_tree = ttk.Treeview(
            tree_box, columns=tuple(column[0] for column in DX_SPOT_COLUMNS), show="headings",
            selectmode="browse", style="DxSpots.Treeview",
        )
        for key, label, _sample, anchor, stretch in DX_SPOT_COLUMNS:
            self.dx_cluster_tree.heading(
                key, text=self._tr(label), anchor=anchor,
                command=lambda key=key: self._dx_cluster_sort_by(key),
            )
            self.dx_cluster_tree.column(key, anchor=anchor, stretch=stretch)
        self._dx_cluster_update_headings()
        self.dx_cluster_tree.tag_configure("dx_new", background=theme.ACTIVE_BG)
        for prefix, background in (("dx_", None), ("dx_new_", theme.ACTIVE_BG)):
            extra = {"background": background} if background else {}
            self.dx_cluster_tree.tag_configure(prefix + "call", foreground=theme.OK, font=self.dx_cluster_bold_font, **extra)
            self.dx_cluster_tree.tag_configure(prefix + "country", foreground=theme.OK, **extra)
        self.dx_cluster_tree.grid(row=0, column=0, sticky="nsew")
        scroll = ttk.Scrollbar(tree_box, orient="vertical", command=self.dx_cluster_tree.yview)
        scroll.grid(row=0, column=1, sticky="ns")
        hscroll = ttk.Scrollbar(tree_box, orient="horizontal", command=self.dx_cluster_tree.xview)
        hscroll.grid(row=1, column=0, sticky="ew")
        self.dx_cluster_tree.configure(yscrollcommand=scroll.set, xscrollcommand=hscroll.set)
        self.dx_cluster_tree.bind("<<TreeviewSelect>>", self._dx_cluster_selection_changed)
        self.dx_cluster_tree.bind("<Double-1>", self._dx_cluster_table_double_click)
        self.dx_cluster_tree.bind("<Return>", self._dx_cluster_table_return)
        self.dx_cluster_tree.bind("<Configure>", self._dx_cluster_schedule_layout, add="+")
        self._dx_cluster_apply_layout()

        actions = ttk.Frame(table, style="Card.TFrame")
        actions.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(10, 0))
        actions.columnconfigure(2, weight=1)
        ttk.Button(actions, text="QSO übernehmen", style="Primary.TButton", command=self._use_selected_dx_spot).grid(row=0, column=0, sticky="w")
        self.dx_cluster_qrz_button = ttk.Button(
            actions,
            text="QRZ.com öffnen",
            style="Secondary.TButton",
            command=self._open_selected_dx_spot_qrz,
            state="disabled",
        )
        self.dx_cluster_qrz_button.grid(row=0, column=1, sticky="w", padx=(8, 0))
        self.dx_cluster_count_label = tk.Label(
            actions, text="", bg=theme.CARD, fg=theme.MUTED, font=("Segoe UI", 9), anchor="e",
        )
        self.dx_cluster_count_label.grid(row=0, column=2, sticky="e", padx=(12, 0))
        self.dx_cluster_filter_job = self.after(10_000, self._dx_cluster_filter_tick)

    def _active_station_callsign(self) -> str:
        profile = self._profile_values()
        return (profile.get("station_call") or profile.get("operator_call") or "").strip().upper()

    def _load_dx_cluster_settings_to_ui(self):
        login_call = self._active_station_callsign()
        config = DxClusterConfig.from_getter(self.db.get_setting, login_call)
        self.dx_cluster_host_var.set(config.host)
        self.dx_cluster_port_var.set(str(config.port))
        self.dx_cluster_call_var.set(login_call)
        saved_window = self.db.get_setting("dx_cluster_time_window", "30 Minuten")
        if saved_window not in {"15 Minuten", "30 Minuten", "60 Minuten", "2 Stunden", "Alle"}:
            saved_window = "30 Minuten"
        self.dx_cluster_time_filter_var.set(self._tr(saved_window))
        saved_region = self.db.get_setting("dx_cluster_spotter_region", "Alle")
        if saved_region not in SPOTTER_REGION_OPTIONS:
            saved_region = "Alle"
        self.dx_cluster_spotter_region_filter_var.set(self._tr(saved_region))
        self._clear_dx_cluster_spots()
        self.dx_cluster_status_label.configure(
            text="DX Cluster ist getrennt · zum Empfangen bitte manuell verbinden.", fg=theme.MUTED,
        )
        self.dx_cluster_start_button.configure(state="normal")
        self.dx_cluster_stop_button.configure(state="disabled")

    def _dx_cluster_config_from_ui(self) -> DxClusterConfig:
        try:
            port = int(self.dx_cluster_port_var.get().strip())
        except ValueError as exc:
            raise DxClusterError("Der DX-Cluster-Port muss eine ganze Zahl sein.") from exc
        config = DxClusterConfig(
            host=self.dx_cluster_host_var.get().strip(),
            port=port,
            callsign=self._active_station_callsign(),
        )
        config.validate()
        return config

    def _store_dx_cluster_config(self, config: DxClusterConfig):
        for key, value in config.settings().items():
            self.db.set_setting(key, value)

    def _load_dx_spotter_settings_to_ui(self):
        callsign = self._active_station_callsign()
        config = DxSpotterConfig.from_getter(self.db.get_setting, callsign)
        self.dx_spotter_host_var.set(config.host)
        self.dx_spotter_port_var.set(str(config.port))
        self.dx_spotter_call_var.set(callsign)
        self.dx_spotter_status_label.configure(
            text="Spotter-Verbindung wird erst beim Senden aufgebaut.", fg=theme.MUTED,
        )

    def _dx_spotter_config_from_ui(self) -> DxSpotterConfig:
        try:
            port = int(self.dx_spotter_port_var.get().strip())
        except ValueError as exc:
            raise DxClusterError("Der DX-Spotter-Port muss eine ganze Zahl sein.") from exc
        config = DxSpotterConfig(
            host=self.dx_spotter_host_var.get().strip(),
            port=port,
            callsign=self._active_station_callsign(),
        )
        config.validate()
        return config

    def _store_dx_spotter_config(self, config: DxSpotterConfig):
        for key, value in config.settings().items():
            self.db.set_setting(key, value)

    def _stop_dx_spotter_runtime(self, *, update_ui: bool = True):
        self.dx_spotter_generation += 1
        self.dx_spotter.stop()
        self.dx_spotter_active_config = None
        if update_ui and hasattr(self, "dx_spotter_status_label"):
            self.dx_spotter_status_label.configure(
                text="Spotter-Verbindung ist getrennt.", fg=theme.MUTED,
            )

    def save_dx_cluster_settings(self):
        try:
            config = self._dx_cluster_config_from_ui()
            self._store_dx_cluster_config(config)
            if self.dx_cluster.running:
                message = "DX-Cluster-Einstellungen gespeichert · Änderungen gelten nach Trennen und erneutem Verbinden."
            else:
                message = "DX-Cluster-Einstellungen gespeichert · Verbindung bleibt getrennt."
            self.dx_cluster_status_label.configure(text=message, fg=theme.OK)
            self.status_var.set("DX-Cluster-Einstellungen gespeichert")
        except Exception as exc:
            messagebox.showerror("DX Cluster", str(exc), parent=self)

    def start_dx_cluster(self):
        try:
            config = self._dx_cluster_config_from_ui()
            self._store_dx_cluster_config(config)
            self.dx_cluster_session_received = 0
            self.dx_cluster_last_spot_utc = None
            self.dx_cluster_generation += 1
            generation = self.dx_cluster_generation
            self.dx_cluster.start(
                config,
                lambda spot: self._queue_dx_cluster_spot(generation, spot),
                lambda message: self._queue_dx_cluster_status(generation, message),
                lambda message: self._queue_dx_cluster_error(generation, message),
            )
        except Exception as exc:
            self.dx_cluster_status_label.configure(text="Verbindung fehlgeschlagen: " + str(exc), fg=theme.ERR)
            messagebox.showerror("DX Cluster", str(exc), parent=self)
            return
        self.dx_cluster_start_button.configure(state="disabled")
        self.dx_cluster_stop_button.configure(state="normal")
        self.dx_cluster_status_label.configure(text=f"Verbinde mit {config.host}:{config.port} …", fg=theme.MUTED)
        self.status_var.set("DX Cluster verbindet …")

    def stop_dx_cluster(self):
        self._stop_dx_cluster_runtime()
        self.status_var.set("DX Cluster getrennt")

    def _stop_dx_cluster_runtime(self, *, update_ui: bool = True):
        self.dx_cluster_generation += 1
        self.dx_cluster.stop()
        if update_ui and hasattr(self, "dx_cluster_status_label"):
            self.dx_cluster_status_label.configure(text="DX Cluster ist getrennt.", fg=theme.MUTED)
            self.dx_cluster_start_button.configure(state="normal")
            self.dx_cluster_stop_button.configure(state="disabled")

    def _queue_dx_cluster_spot(self, generation: int, spot: DxSpot):
        if not self.closing:
            self.after(0, lambda: self._accept_dx_cluster_spot(generation, spot))

    def _queue_dx_cluster_status(self, generation: int, message: str):
        if not self.closing:
            self.after(0, lambda: self._show_dx_cluster_status(generation, message))

    def _queue_dx_cluster_error(self, generation: int, message: str):
        if not self.closing:
            self.after(0, lambda: self._show_dx_cluster_error(generation, message))

    def _show_dx_cluster_status(self, generation: int, message: str):
        if generation != self.dx_cluster_generation or self.closing:
            return
        active = "aktiv" in message.lower()
        if active:
            self._update_dx_cluster_live_status()
        else:
            self.dx_cluster_status_label.configure(text=message, fg=theme.MUTED)
        self.status_var.set(message)

    def _update_dx_cluster_live_status(self):
        if not hasattr(self, "dx_cluster_status_label") or not self.dx_cluster.connected:
            return
        last = (
            self.dx_cluster_last_spot_utc.strftime("%H:%M:%S UTC")
            if self.dx_cluster_last_spot_utc else "noch keiner"
        )
        visible = len(getattr(self, "dx_cluster_visible_ids", []))
        host = self.dx_cluster_host_var.get().strip()
        port = self.dx_cluster_port_var.get().strip()
        self.dx_cluster_status_label.configure(
            text=(
                f"✓ Live-Telnet {host}:{port} · {self.dx_cluster_session_received} Spot(s) empfangen · "
                f"{visible} sichtbar · letzter Spot: {last}"
            ),
            fg=theme.OK,
        )

    def _show_dx_cluster_error(self, generation: int, message: str):
        if generation != self.dx_cluster_generation or self.closing:
            return
        self.dx_cluster_status_label.configure(text="DX-Cluster-Verbindung beendet: " + message, fg=theme.ERR)
        self.dx_cluster_start_button.configure(state="normal")
        self.dx_cluster_stop_button.configure(state="disabled")
        self.status_var.set("DX-Cluster-Verbindung beendet")

    def _accept_dx_cluster_spot(self, generation: int, spot: DxSpot):
        if generation != self.dx_cluster_generation or self.closing:
            return
        identity = (
            spot.spotter, spot.call, spot.frequency_hz, spot.time_utc, spot.comment,
        )
        if identity in self.dx_cluster_seen_keys:
            return
        self.dx_cluster_seen_keys.add(identity)
        self.dx_cluster_sequence += 1
        self.dx_cluster_session_received += 1
        self.dx_cluster_last_spot_utc = datetime.now(timezone.utc)
        item_id = f"dx-{self.dx_cluster_sequence}"
        self.dx_cluster_spots.insert(0, (item_id, spot))
        if len(self.dx_cluster_spots) > 500:
            removed = self.dx_cluster_spots[500:]
            self.dx_cluster_spots = self.dx_cluster_spots[:500]
            for _old_id, old_spot in removed:
                self.dx_cluster_seen_keys.discard((
                    old_spot.spotter, old_spot.call, old_spot.frequency_hz,
                    old_spot.time_utc, old_spot.comment,
                ))
        # Busy clusters deliver many spots per second; coalesce the full
        # table rebuild instead of re-rendering for every single spot.
        self._schedule_dx_cluster_refresh()
        self.status_var.set(f"Neuer Live-DX-Spot: {spot.call} · {spot.frequency_mhz} MHz")

    def _schedule_dx_cluster_refresh(self, delay_ms: int = 300):
        if self.closing or self.dx_cluster_refresh_job is not None:
            return
        self.dx_cluster_refresh_job = self.after(delay_ms, self._run_scheduled_dx_cluster_refresh)

    def _run_scheduled_dx_cluster_refresh(self):
        self.dx_cluster_refresh_job = None
        if self.closing:
            return
        self._refresh_dx_cluster_spots()

    def _clear_dx_cluster_spots(self):
        self.dx_cluster_spots.clear()
        self.dx_cluster_spot_by_id.clear()
        self.dx_cluster_visible_ids = []
        self.dx_cluster_selected_id = None
        self.dx_cluster_seen_keys.clear()
        if hasattr(self, "dx_cluster_qrz_button"):
            self.dx_cluster_qrz_button.configure(state="disabled")
        self._refresh_dx_cluster_spots()

    def _dx_cluster_time_filter_changed(self, _event=None):
        value = self._canonical_choice(
            self.dx_cluster_time_filter_var.get(), ("15 Minuten", "30 Minuten", "60 Minuten", "2 Stunden", "Alle"),
        )
        self.db.set_setting("dx_cluster_time_window", value)
        self._refresh_dx_cluster_spots()

    def _dx_cluster_spotter_region_changed(self, _event=None):
        value = self._canonical_choice(self.dx_cluster_spotter_region_filter_var.get(), SPOTTER_REGION_OPTIONS)
        if value not in SPOTTER_REGION_OPTIONS:
            value = "Alle"
            self.dx_cluster_spotter_region_filter_var.set(self._tr(value))
        self.db.set_setting("dx_cluster_spotter_region", value)
        self._refresh_dx_cluster_spots()

    @staticmethod
    def _dx_cluster_spot_age_seconds(spot: DxSpot, now: datetime | None = None) -> float:
        current = now or datetime.now(timezone.utc)
        return max(0.0, (current - spot.spotted_at_utc).total_seconds())

    def _dx_cluster_filter_tick(self):
        self.dx_cluster_filter_job = None
        if self.closing:
            return
        self._refresh_dx_cluster_spots()
        self.dx_cluster_filter_job = self.after(10_000, self._dx_cluster_filter_tick)

    def _update_dx_cluster_worked_cache(self, qsos: list[dict]):
        self._apply_dx_cluster_worked_cache(self._compute_dx_cluster_worked_cache(qsos))

    def _compute_dx_cluster_worked_cache(self, qsos: list[dict]) -> dict:
        """Pure computation; safe to run in the logbook refresh worker thread."""
        calls: set[tuple[str, str, str]] = set()
        countries: set[tuple[str, str, str]] = set()
        worked_counts: Counter[tuple[str, str, str]] = Counter()
        call_totals: Counter[str] = Counter()
        history_refs: dict[str, list[tuple[str, str, str, str]]] = {}
        # Per-run memos: large logs repeat the same calls and mode/band pairs.
        country_memo: dict[str, str] = {}
        mode_memo: dict[tuple[str, str], str] = {}
        lookup = self.country_db.lookup
        for qso in qsos:
            call = str(qso.get("call") or "").strip().upper()
            if call:
                call_totals[call] += 1
                history_refs.setdefault(call, []).append((
                    str(qso.get("qso_date") or ""), str(qso.get("time_on") or ""),
                    str(qso.get("band") or ""), str(qso.get("mode") or ""),
                ))
            # CTY.DAT name first: spots are looked up there too, and imported
            # QSOs may carry another spelling ("FEDERAL REPUBLIC OF GERMANY").
            country = ""
            if call:
                country = country_memo.get(call)
                if country is None:
                    info = lookup(call)
                    country = country_memo[call] = info.country if info else ""
            if not country:
                country = str(qso.get("country") or "").strip()
            raw_mode = str(qso.get("mode") or "")
            band = str(qso.get("band") or "").strip()
            if band:
                # The frequency only matters without a band (band derivation
                # and SSB sideband), so it is not parsed here.
                mode_key = (raw_mode, band)
                mode = mode_memo.get(mode_key)
                if mode is None:
                    mode = mode_memo[mode_key] = normalize_worked_mode(raw_mode, 0, band)
            else:
                frequency_hz = 0
                try:
                    frequency_hz = int(round(float(str(qso.get("freq") or "0").replace(",", ".")) * 1_000_000))
                except (TypeError, ValueError):
                    pass
                if frequency_hz:
                    band = band_from_mhz(frequency_hz / 1_000_000) or ""
                mode = normalize_worked_mode(raw_mode, frequency_hz, band)
            if not band or not mode:
                continue
            if call:
                calls.add((call, band, mode))
                worked_counts[(call, band, mode)] += 1
            if country:
                countries.add((country, band, mode))
        worked_history = LazyWorkedHistory(history_refs)
        return {
            "calls": calls, "countries": countries, "worked_counts": worked_counts,
            "call_totals": call_totals, "worked_history": worked_history,
        }

    def _apply_dx_cluster_worked_cache(self, data: dict):
        self.dx_cluster_worked_calls = data["calls"]
        self.dx_cluster_worked_countries = data["countries"]
        self.qso_worked_counts = data["worked_counts"]
        self.qso_worked_call_totals = data["call_totals"]
        self.qso_worked_history = data["worked_history"]
        self._update_qso_worked_status()
        if hasattr(self, "dx_cluster_tree"):
            self._refresh_dx_cluster_spots()

    def _dx_cluster_country(self, callsign: str) -> str:
        key = (callsign or "").strip().upper()
        if key in self.dx_cluster_country_cache:
            return self.dx_cluster_country_cache[key]
        lookup_call = re.sub(r"-(?:\d+|#)$", "", key)
        info = self.country_db.lookup(lookup_call)
        country = info.country if info else "—"
        self.dx_cluster_country_cache[key] = country
        self.dx_cluster_continent_cache[key] = (info.cont or "").upper() if info else ""
        return country

    def _dx_cluster_continent(self, callsign: str) -> str:
        key = (callsign or "").strip().upper()
        if key not in self.dx_cluster_continent_cache:
            self._dx_cluster_country(callsign)
        return self.dx_cluster_continent_cache.get(key, "")

    def _dx_cluster_spot_rows(self) -> tuple[list[tuple[str, str, tuple]], dict[str, DxSpot]]:
        """Filter, sort and format the received spots for the Treeview."""
        band_filter = self._canonical_choice(self.dx_cluster_band_filter_var.get(), ("Alle", *BANDS))
        mode_filter = self._canonical_choice(self.dx_cluster_mode_filter_var.get(), ("Alle", *MODES))
        spotter_region_filter = self._canonical_choice(self.dx_cluster_spotter_region_filter_var.get(), SPOTTER_REGION_OPTIONS)
        window_label = self._canonical_choice(
            self.dx_cluster_time_filter_var.get(), ("15 Minuten", "30 Minuten", "60 Minuten", "2 Stunden", "Alle"),
        )
        window_minutes = {
            "15 Minuten": 15, "30 Minuten": 30, "60 Minuten": 60, "2 Stunden": 120,
        }.get(window_label)
        now = datetime.now(timezone.utc)
        entries = []
        for item_id, spot in self.dx_cluster_spots:
            age_seconds = self._dx_cluster_spot_age_seconds(spot, now)
            if window_minutes is not None and age_seconds > window_minutes * 60:
                continue
            if band_filter != "Alle" and spot.band != band_filter:
                continue
            if mode_filter != "Alle" and spot.mode != mode_filter:
                continue
            comment = spot.comment
            if spot.locator:
                comment = (comment + " · " if comment else "") + spot.locator
            dx_country = self._dx_cluster_country(spot.call)
            spotter_country = self._dx_cluster_country(spot.spotter)
            spotter_region = spotter_region_for_continent(self._dx_cluster_continent(spot.spotter))
            if spotter_region_filter != "Alle" and spotter_region != spotter_region_filter:
                continue
            worked_call, worked_country = worked_flags(
                spot.call, dx_country, spot.band, spot.mode,
                self.dx_cluster_worked_calls, self.dx_cluster_worked_countries,
            )
            entries.append((
                item_id, spot, dx_country, spotter_country, comment,
                age_seconds <= DX_SPOT_NEW_SECONDS, worked_call, worked_country,
            ))
        sort_key = self.dx_cluster_sort_key
        entries.sort(
            key=lambda entry: dx_spot_sort_value(
                entry[1], sort_key, entry[2], entry[3], entry[4], entry[6], entry[7],
            ),
            reverse=self.dx_cluster_sort_descending,
        )
        worked_labels = (self._tr(DX_SPOT_WORKED_LABELS[0]), self._tr(DX_SPOT_WORKED_LABELS[1]))
        rows = [
            build_dx_spot_row(
                item_id, spot, dx_country, spotter_country, comment,
                is_new=is_new, worked_call=worked_call, worked_country=worked_country,
                worked_labels=worked_labels,
            )
            for item_id, spot, dx_country, spotter_country, comment, is_new, worked_call, worked_country in entries
        ]
        return rows, {entry[0]: entry[1] for entry in entries}

    def _refresh_dx_cluster_spots(self):
        if not hasattr(self, "dx_cluster_tree"):
            return
        if self.dx_cluster_layout_job is None:
            self._dx_cluster_apply_layout()  # no-op unless the UI zoom changed
        rows, spots = self._dx_cluster_spot_rows()
        tree = self.dx_cluster_tree
        previous = self.dx_cluster_shown_rows
        anchor = dx_spot_scroll_anchor(previous or [], tree.yview()[0])
        # Incremental update: new spots are inserted, expired ones removed and
        # only rows whose text or colour changed are touched.  Ids stay
        # stable, so the selection and the scroll position survive refreshes.
        ops = plan_row_diff(previous, rows) if previous is not None else None
        if ops:
            try:
                apply_row_diff(tree, ops)
            except tk.TclError:
                ops = None  # table and bookkeeping disagree: rebuild below
        if ops is None:
            children = tree.get_children()
            if children:
                tree.delete(*children)
            for row in rows:
                try:
                    insert_row(tree, "end", row)
                except tk.TclError:
                    continue
        self.dx_cluster_shown_rows = rows
        self.dx_cluster_spot_by_id = spots
        self.dx_cluster_visible_ids = [row[0] for row in rows]

        selected_id = self.dx_cluster_selected_id
        if selected_id in spots:
            if tuple(tree.selection()) != (selected_id,):
                tree.selection_set(selected_id)
            if tree.focus() != selected_id:
                # Keyboard navigation continues from the selected row.
                tree.focus(selected_id)
        else:
            self.dx_cluster_selected_id = None
        if self.dx_cluster_reveal_selection:
            # After a sort change show the selected spot (or the top).
            self.dx_cluster_reveal_selection = False
            if self.dx_cluster_selected_id:
                tree.see(self.dx_cluster_selected_id)
            else:
                tree.yview_moveto(0)
        elif anchor is not None and rows:
            new_index = dx_spot_anchor_index(self.dx_cluster_visible_ids, anchor)
            if new_index is not None:
                # Keep the row that was at the top of the view at the top:
                # Treeview scrolls by row index, so rows inserted above would
                # push it down.  "yview moveto" lays the tree out first (Tk
                # >= 8.6.13), i.e. the fraction refers to the new row count.
                tree.yview_moveto(new_index / len(rows))
        if hasattr(self, "dx_cluster_qrz_button"):
            self.dx_cluster_qrz_button.configure(
                state="normal" if self.dx_cluster_selected_id else "disabled",
            )
        if hasattr(self, "dx_cluster_count_label"):
            self.dx_cluster_count_label.configure(text=f"{len(rows)} / {len(self.dx_cluster_spots)} Spots")
        self._update_dx_cluster_live_status()

    def _dx_cluster_update_headings(self):
        for key, label, _sample, _anchor, _stretch in DX_SPOT_COLUMNS:
            text = self._tr(label)
            if key == self.dx_cluster_sort_key:
                text += " ▼" if self.dx_cluster_sort_descending else " ▲"
            self.dx_cluster_tree.heading(key, text=text)

    def _dx_cluster_sort_by(self, key: str):
        if self.dx_cluster_sort_key == key:
            self.dx_cluster_sort_descending = not self.dx_cluster_sort_descending
        else:
            self.dx_cluster_sort_key = key
            self.dx_cluster_sort_descending = dx_spot_default_descending(key)
        self.dx_cluster_reveal_selection = True
        self._dx_cluster_update_headings()
        self._refresh_dx_cluster_spots()

    def _dx_cluster_schedule_layout(self, _event=None):
        if self.dx_cluster_layout_job is None and not self.closing:
            self.dx_cluster_layout_job = self.after(150, self._dx_cluster_apply_layout)

    def _dx_cluster_apply_layout(self):
        """Scale column widths, row height and the bold font with the UI zoom."""
        if self.dx_cluster_layout_job is not None:
            try:
                self.after_cancel(self.dx_cluster_layout_job)
            except tk.TclError:
                pass
        self.dx_cluster_layout_job = None
        if self.closing or not hasattr(self, "dx_cluster_tree"):
            return
        try:
            scale = float(getattr(self, "_ui_scale", 1.0) or 1.0)
        except (TypeError, ValueError):
            scale = 1.0
        if self.dx_cluster_column_scale is not None and abs(scale - self.dx_cluster_column_scale) < 0.001:
            return
        self.dx_cluster_column_scale = scale
        tree = self.dx_cluster_tree
        try:
            style = ttk.Style(self)
            cell_font = style.lookup("Treeview", "font") or "TkDefaultFont"
            heading_font = style.lookup("Treeview.Heading", "font") or cell_font

            def measure(font, text: str) -> int:
                return int(self.tk.call("font", "measure", font, text))

            widths = dx_spot_column_widths(
                lambda text: measure(heading_font, text), lambda text: measure(cell_font, text),
                scale, self._tr,
            )
            for key, width, minwidth in widths:
                tree.column(key, width=width, minwidth=minwidth)
            linespace = int(self.tk.call("font", "metrics", cell_font, "-linespace"))
            style.configure("DxSpots.Treeview", rowheight=max(linespace + 4, int(round(22 * scale))))
            family = self.tk.call("font", "actual", cell_font, "-family")
            size = int(self.tk.call("font", "actual", cell_font, "-size"))
            self.dx_cluster_bold_font.configure(family=family, size=size, weight="bold")
        except (tk.TclError, TypeError, ValueError):
            pass

    def _dx_cluster_selection_changed(self, _event=None):
        selection = self.dx_cluster_tree.selection()
        self.dx_cluster_selected_id = selection[0] if selection else None
        if hasattr(self, "dx_cluster_qrz_button"):
            self.dx_cluster_qrz_button.configure(
                state="normal" if self.dx_cluster_selected_id else "disabled",
            )

    def _dx_cluster_table_double_click(self, event):
        tree = self.dx_cluster_tree
        if tree.identify_region(event.x, event.y) != "cell":
            return None  # headings (sorting) and column separators keep their default handling
        item_id = tree.identify_row(event.y)
        if not item_id or item_id not in self.dx_cluster_spot_by_id:
            return "break"
        tree.selection_set(item_id)
        self.dx_cluster_selected_id = item_id
        self._tune_selected_dx_spot()
        return "break"

    def _dx_cluster_table_return(self, _event=None):
        if self._selected_dx_cluster_spot() is not None:
            self._tune_selected_dx_spot()
        return "break"

    def _selected_dx_cluster_spot(self) -> DxSpot | None:
        return self.dx_cluster_spot_by_id.get(self.dx_cluster_selected_id or "")

    def _open_selected_dx_spot_qrz(self):
        spot = self._selected_dx_cluster_spot()
        if spot is None:
            messagebox.showinfo("DX Cluster", "Bitte zuerst einen DX-Spot auswählen.", parent=self)
            return
        self._open_qrz_callsign(spot.call)

    def _open_qrz_callsign(self, callsign: str):
        callsign = (callsign or "").strip().upper()
        if not callsign:
            return
        url = "https://www.qrz.com/db/" + urllib.parse.quote(callsign, safe="")
        try:
            opened = webbrowser.open_new_tab(url)
        except Exception as exc:
            messagebox.showerror(
                "QRZ.com öffnen",
                f"QRZ.com konnte nicht geöffnet werden:\n{exc}",
                parent=self,
            )
            return
        if not opened:
            messagebox.showwarning(
                "QRZ.com öffnen",
                "Der Standardbrowser konnte QRZ.com nicht öffnen.",
                parent=self,
            )
            return
        self.status_var.set(f"QRZ.com geöffnet: {callsign}")

    def _use_selected_dx_spot(self):
        spot = self._selected_dx_cluster_spot()
        if spot is None:
            messagebox.showinfo("DX Cluster", "Bitte zuerst einen DX-Spot auswählen.", parent=self)
            return
        self._use_dx_spot(spot)

    def _use_dx_spot(self, spot: DxSpot):
        """Fill the QSO form from a spot (DX Cluster and DXpeditions page)."""
        self.call_var.set(spot.call)
        self._call_changed()
        self.freq_var.set(spot.frequency_mhz)
        if spot.band:
            self.band_var.set(spot.band)
        if spot.mode in MODES:
            self.mode_var.set(spot.mode)
        self._show_page("log")
        self.call_entry.focus_set()
        self.status_var.set(f"DX-Spot als QSO übernommen: {spot.call} · noch nicht gespeichert")

    def _tune_selected_dx_spot(self):
        spot = self._selected_dx_cluster_spot()
        if spot is None:
            messagebox.showinfo("DX Cluster", "Bitte zuerst einen DX-Spot auswählen.", parent=self)
            return
        self._tune_dx_spot(spot)

    def _tune_dx_spot(self, spot: DxSpot):
        """Tune the radio via CAT to a spot (DX Cluster and DXpeditions page)."""
        if not self.cat_manager.running:
            messagebox.showwarning(
                "CAT ist ausgeschaltet",
                "Zum Abstimmen des TRX bitte zuerst CAT im CAT Setup starten.",
                parent=self,
            )
            return
        generation = self.cat_generation
        self.status_var.set(f"CAT stimmt auf {spot.call} · {spot.frequency_mhz} MHz ab …")

        def worker():
            try:
                self.cat_manager.set_frequency_and_mode(spot.frequency_hz, spot.mode)
                if not self.closing:
                    self.after(0, lambda: self._dx_cluster_tuned(generation, spot))
            except Exception as exc:
                message = str(exc)
                if not self.closing:
                    self.after(0, lambda message=message: messagebox.showerror("CAT abstimmen", message, parent=self))

        threading.Thread(target=worker, name="dx-cluster-cat-tune", daemon=True).start()

    def _dx_cluster_tuned(self, generation: int, spot: DxSpot):
        if generation != self.cat_generation or self.closing:
            return
        mode = f" · {spot.mode}" if spot.mode else ""
        self.status_var.set(f"CAT abgestimmt: {spot.call} · {spot.frequency_mhz} MHz{mode}")

    def send_current_dx_spot(self):
        current_call = self.call_var.get().strip().upper()
        current_frequency = self.freq_var.get().strip().replace(",", ".")
        candidate, _using_last_saved = select_dx_spot_candidate({
            "call": current_call,
            "freq": current_frequency,
            "mode": self.mode_var.get().strip().upper(),
            "comment": self.form_vars["comment"].get().strip(),
        }, self.last_spottable_qso)
        try:
            call = str(candidate.get("call") or "").strip().upper()
            if not call:
                raise ValueError
            frequency_hz = int(round(float(str(candidate.get("freq") or "").replace(",", ".")) * 1_000_000))
            if frequency_hz <= 0:
                raise ValueError
        except ValueError:
            messagebox.showerror(
                "DX-Spot senden",
                "Bitte Rufzeichen und eine gültige Frequenz im QSO-Formular eintragen.",
                parent=self,
            )
            return
        try:
            config = DxSpotterConfig.from_getter(
                self.db.get_setting, self._active_station_callsign(),
            )
            config.validate()
        except Exception as exc:
            messagebox.showerror(
                "DX-Spotter-Verbindung",
                str(exc) + "\n\nBitte die Spotter-Verbindung in den Einstellungen prüfen.",
                parent=self,
            )
            return
        comment = simpledialog.askstring(
            "DX-Spot senden",
            "Optionaler Kommentar für den öffentlichen DX-Spot:",
            initialvalue=str(candidate.get("comment") or "").strip(),
            parent=self,
        )
        if comment is None:
            return
        mode = str(candidate.get("mode") or "").strip().upper()
        transmitted_comment = spot_comment_with_mode(comment, mode)
        frequency_mhz = f"{frequency_hz / 1_000_000:.6f}".rstrip("0").rstrip(".")
        if not messagebox.askyesno(
            "DX-Spot öffentlich senden",
            f"Folgenden Spot wirklich öffentlich über {config.host}:{config.port} senden?\n\n"
            f"Rufzeichen: {call}\nFrequenz: {frequency_mhz} MHz\nMode: {mode or '—'}\n"
            f"Login: {config.callsign}\nÜbertragener Kommentar: {transmitted_comment or '—'}",
            parent=self,
        ):
            return
        self.dx_spotter_generation += 1
        generation = self.dx_spotter_generation
        self.dx_spotter_status_label.configure(
            text=f"Verbinde zum Spotten mit {config.host}:{config.port} …", fg=theme.MUTED,
        )
        self.status_var.set("DX-Spotter verbindet …")

        def worker():
            try:
                if self.dx_spotter_active_config != config or not self.dx_spotter.connected:
                    self.dx_spotter.start(config, lambda _spot: None)
                    self.dx_spotter_active_config = config
                    self.dx_spotter.wait_until_connected()
                self.dx_spotter.send_spot(call, frequency_hz, comment, mode)
                if not self.closing:
                    self.after(
                        0, lambda: self._dx_spot_sent(
                            generation, call, frequency_mhz, config,
                        ),
                    )
            except Exception as exc:
                message = str(exc)
                self.dx_spotter.stop()
                self.dx_spotter_active_config = None
                if not self.closing:
                    self.after(
                        0, lambda message=message: self._dx_spot_failed(generation, message),
                    )

        threading.Thread(target=worker, name="dx-spotter-send", daemon=True).start()

    def _dx_spot_sent(
        self, generation: int, call: str, frequency_mhz: str, config: DxSpotterConfig,
    ):
        if generation != self.dx_spotter_generation or self.closing:
            return
        self.status_var.set(f"DX-Spot gesendet: {call} · {frequency_mhz} MHz")
        self.dx_spotter_status_label.configure(
            text=(
                f"✓ DX-Spot gesendet: {call} · {frequency_mhz} MHz · "
                f"{config.host}:{config.port} als {config.callsign}"
            ),
            fg=theme.OK,
        )

    def _dx_spot_failed(self, generation: int, message: str):
        if generation != self.dx_spotter_generation or self.closing:
            return
        self.dx_spotter_status_label.configure(
            text="DX-Spot konnte nicht gesendet werden: " + message, fg=theme.ERR,
        )
        self.status_var.set("DX-Spot konnte nicht gesendet werden")
        messagebox.showerror("DX-Spot senden", message, parent=self)
