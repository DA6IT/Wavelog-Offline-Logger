from __future__ import annotations

import atexit
import re
import threading
import urllib.parse
import webbrowser
from collections import Counter
from datetime import datetime, timezone
import tkinter as tk
from tkinter import messagebox, simpledialog, ttk
from dx_cluster import (
    DEFAULT_CLUSTER_HOST, DEFAULT_CLUSTER_PORT, DxClusterClient, DxClusterConfig, DxClusterError, DxSpotterConfig, SPOTTER_REGION_OPTIONS, normalize_worked_mode, select_dx_spot_candidate, spot_comment_with_mode, spot_sort_value, spotter_region_for_continent, worked_flags,
)
from logger_core import BANDS, MODES, band_from_mhz
from ui_theme import theme


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
        self.qso_worked_history: dict[str, list[dict[str, str]]] = {}
        self.dx_cluster_filter_job = None
        self.dx_cluster_session_received = 0
        self.dx_cluster_last_spot_utc: datetime | None = None
        self.dx_cluster_seen_keys: set[tuple] = set()
        self.dx_cluster_sort_key = "time"
        self.dx_cluster_sort_descending = True

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
            table, text="Doppelklick stimmt den TRX auf Frequenz und Mode ab. QSO übernehmen füllt anschließend das Formular.",
            bg=theme.CARD, fg=theme.MUTED, font=("Segoe UI", 9), anchor="e",
        ).grid(row=0, column=1, sticky="e", pady=(0, 8))

        tree_box = ttk.Frame(table, style="Card.TFrame")
        tree_box.grid(row=1, column=0, columnspan=2, sticky="nsew")
        tree_box.columnconfigure(0, weight=1)
        tree_box.rowconfigure(0, weight=1)
        self.dx_cluster_visible_ids: list[str] = []
        self.dx_cluster_selected_id: str | None = None
        self.dx_cluster_table_columns = (
            ("time", self._tr("UTC"), 7), ("call", self._tr("DX-Rufzeichen"), 15),
            ("dx_country", self._tr("DX-Land"), 20), ("frequency", self._tr("MHz"), 11),
            ("band", self._tr("Band"), 8), ("mode", self._tr("Mode"), 10),
            ("spotter", self._tr("Spotter"), 15), ("spotter_country", self._tr("Spotter-Land"), 20),
            ("comment", self._tr("Kommentar"), 60),
        )
        self.dx_cluster_tree = tk.Text(
            tree_box, wrap="none", state="disabled", bg=theme.INPUT_BG, fg=theme.TEXT, insertbackground=theme.TEXT,
            font=("Consolas", 9), relief="solid", borderwidth=1,
            highlightthickness=0, cursor="arrow", padx=4, pady=2,
        )
        self.dx_cluster_tree.tag_configure("header", background=theme.NEUTRAL_BADGE_BG, foreground=theme.TEXT, font=("Consolas", 9, "bold"))
        self.dx_cluster_tree.tag_configure("new", background=theme.ACTIVE_BG)
        self.dx_cluster_tree.tag_configure("worked", foreground=theme.OK, font=("Consolas", 9, "bold"))
        self.dx_cluster_tree.tag_configure("selected", background=theme.NAV_ACTIVE_HOVER)
        self.dx_cluster_tree.grid(row=0, column=0, sticky="nsew")
        scroll = ttk.Scrollbar(tree_box, orient="vertical", command=self.dx_cluster_tree.yview)
        scroll.grid(row=0, column=1, sticky="ns")
        hscroll = ttk.Scrollbar(tree_box, orient="horizontal", command=self.dx_cluster_tree.xview)
        hscroll.grid(row=1, column=0, sticky="ew")
        self.dx_cluster_tree.configure(yscrollcommand=scroll.set, xscrollcommand=hscroll.set)
        self.dx_cluster_tree.bind("<Button-1>", self._dx_cluster_table_click)
        self.dx_cluster_tree.bind("<Double-1>", self._dx_cluster_table_double_click)

        actions = ttk.Frame(table, style="Card.TFrame")
        actions.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(10, 0))
        ttk.Button(actions, text="QSO übernehmen", style="Primary.TButton", command=self._use_selected_dx_spot).pack(side="left")
        self.dx_cluster_qrz_button = ttk.Button(
            actions,
            text="QRZ.com öffnen",
            style="Secondary.TButton",
            command=self._open_selected_dx_spot_qrz,
            state="disabled",
        )
        self.dx_cluster_qrz_button.pack(side="left", padx=(8, 0))
        tk.Label(
            actions, text="Überschriften sortieren · neu: hellblau · gleicher Mode gearbeitet: grün · Doppelklick stimmt TRX ab.",
            bg=theme.CARD, fg=theme.MUTED, font=("Segoe UI", 9),
        ).pack(side="right")
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
        self._refresh_dx_cluster_spots()
        self.status_var.set(f"Neuer Live-DX-Spot: {spot.call} · {spot.frequency_mhz} MHz")

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
        calls: set[tuple[str, str, str]] = set()
        countries: set[tuple[str, str, str]] = set()
        worked_counts: Counter[tuple[str, str, str]] = Counter()
        call_totals: Counter[str] = Counter()
        worked_history: dict[str, list[dict[str, str]]] = {}
        for qso in qsos:
            call = str(qso.get("call") or "").strip().upper()
            if call:
                call_totals[call] += 1
                worked_history.setdefault(call, []).append({
                    "qso_date": str(qso.get("qso_date") or ""),
                    "time_on": str(qso.get("time_on") or ""),
                    "band": str(qso.get("band") or ""),
                    "mode": str(qso.get("mode") or ""),
                })
            country = str(qso.get("country") or "").strip()
            if not country and call:
                info = self.country_db.lookup(call)
                country = info.country if info else ""
            frequency_hz = 0
            try:
                frequency_hz = int(round(float(str(qso.get("freq") or "0").replace(",", ".")) * 1_000_000))
            except (TypeError, ValueError):
                pass
            band = str(qso.get("band") or "").strip()
            if not band and frequency_hz:
                band = band_from_mhz(frequency_hz / 1_000_000) or ""
            mode = normalize_worked_mode(
                str(qso.get("mode") or ""), frequency_hz, band,
            )
            if not band or not mode:
                continue
            if call:
                calls.add((call, band, mode))
                worked_counts[(call, band, mode)] += 1
            if country:
                countries.add((country, band, mode))
        self.dx_cluster_worked_calls = calls
        self.dx_cluster_worked_countries = countries
        self.qso_worked_counts = worked_counts
        self.qso_worked_call_totals = call_totals
        for history in worked_history.values():
            history.sort(key=lambda item: (item["qso_date"], re.sub(r"[^0-9]", "", item["time_on"])), reverse=True)
        self.qso_worked_history = worked_history
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

    @staticmethod
    def _dx_cluster_table_cell(value: str, width: int) -> str:
        text = str(value or "—")
        if len(text) > width - 1:
            text = text[: width - 2] + "…"
        return text.ljust(width)

    def _dx_cluster_sort_value(self, row: tuple):
        _item_id, spot, dx_country, spotter_country, comment, _age = row
        return spot_sort_value(
            spot, self.dx_cluster_sort_key, dx_country, spotter_country, comment,
        )

    def _refresh_dx_cluster_spots(self):
        if not hasattr(self, "dx_cluster_tree"):
            return
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
        rows = []
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
            rows.append((item_id, spot, dx_country, spotter_country, comment, age_seconds))
        rows.sort(key=self._dx_cluster_sort_value, reverse=self.dx_cluster_sort_descending)

        old_y = self.dx_cluster_tree.yview()
        old_x = self.dx_cluster_tree.xview()
        selected_id = self.dx_cluster_selected_id
        self.dx_cluster_tree.configure(state="normal")
        self.dx_cluster_tree.delete("1.0", "end")
        self.dx_cluster_spot_by_id.clear()
        self.dx_cluster_visible_ids = []
        header_parts = []
        for key, label, width in self.dx_cluster_table_columns:
            if key == self.dx_cluster_sort_key:
                label += " ▼" if self.dx_cluster_sort_descending else " ▲"
            header_parts.append(self._dx_cluster_table_cell(label, width))
        self.dx_cluster_tree.insert("end", "".join(header_parts) + "\n", ("header",))

        for item_id, spot, dx_country, spotter_country, comment, age_seconds in rows:
            worked_call, worked_country = worked_flags(
                spot.call, dx_country, spot.band, spot.mode,
                self.dx_cluster_worked_calls, self.dx_cluster_worked_countries,
            )
            line_number = len(self.dx_cluster_visible_ids) + 2
            self.dx_cluster_tree.insert("end", self._dx_cluster_table_cell((spot.time_utc + "Z") if spot.time_utc else "—", 7))
            self.dx_cluster_tree.insert(
                "end", self._dx_cluster_table_cell(spot.call, 15), ("worked",) if worked_call else (),
            )
            self.dx_cluster_tree.insert(
                "end", self._dx_cluster_table_cell(dx_country, 20), ("worked",) if worked_country else (),
            )
            for value, width in (
                (spot.frequency_mhz, 11), (spot.band or "—", 8), (spot.mode or "—", 10),
                (spot.spotter, 15), (spotter_country, 20), (comment, 60),
            ):
                self.dx_cluster_tree.insert("end", self._dx_cluster_table_cell(value, width))
            self.dx_cluster_tree.insert("end", "\n")
            line_start = f"{line_number}.0"
            line_end = f"{line_number}.end"
            if age_seconds <= 120:
                self.dx_cluster_tree.tag_add("new", line_start, line_end)
            if item_id == selected_id:
                self.dx_cluster_tree.tag_add("selected", line_start, line_end)
            self.dx_cluster_visible_ids.append(item_id)
            self.dx_cluster_spot_by_id[item_id] = spot

        if selected_id not in self.dx_cluster_spot_by_id:
            self.dx_cluster_selected_id = None
        if hasattr(self, "dx_cluster_qrz_button"):
            self.dx_cluster_qrz_button.configure(
                state="normal" if self.dx_cluster_selected_id else "disabled",
            )
        self.dx_cluster_tree.configure(state="disabled")
        if old_y:
            self.dx_cluster_tree.yview_moveto(old_y[0])
        if old_x:
            self.dx_cluster_tree.xview_moveto(old_x[0])
        self._update_dx_cluster_live_status()

    def _dx_cluster_sort_from_character(self, character: int):
        start = 0
        for key, _label, width in self.dx_cluster_table_columns:
            if start <= character < start + width:
                if self.dx_cluster_sort_key == key:
                    self.dx_cluster_sort_descending = not self.dx_cluster_sort_descending
                else:
                    self.dx_cluster_sort_key = key
                    self.dx_cluster_sort_descending = key in {"time", "frequency"}
                self._refresh_dx_cluster_spots()
                return
            start += width

    def _dx_cluster_table_click(self, event):
        line_text, character_text = self.dx_cluster_tree.index(f"@{event.x},{event.y}").split(".")
        line = int(line_text)
        if line == 1:
            self._dx_cluster_sort_from_character(int(character_text))
            return "break"
        visible_index = line - 2
        if not 0 <= visible_index < len(self.dx_cluster_visible_ids):
            return "break"
        self.dx_cluster_selected_id = self.dx_cluster_visible_ids[visible_index]
        self.dx_cluster_tree.tag_remove("selected", "1.0", "end")
        self.dx_cluster_tree.tag_add("selected", f"{line}.0", f"{line}.end")
        if hasattr(self, "dx_cluster_qrz_button"):
            self.dx_cluster_qrz_button.configure(state="normal")
        return "break"

    def _dx_cluster_table_double_click(self, event):
        line = int(self.dx_cluster_tree.index(f"@{event.x},{event.y}").split(".")[0])
        if line == 1:
            return "break"
        self._dx_cluster_table_click(event)
        self._tune_selected_dx_spot()
        return "break"

    def _selected_dx_cluster_spot(self) -> DxSpot | None:
        return self.dx_cluster_spot_by_id.get(self.dx_cluster_selected_id or "")

    def _open_selected_dx_spot_qrz(self):
        spot = self._selected_dx_cluster_spot()
        if spot is None:
            messagebox.showinfo("DX Cluster", "Bitte zuerst einen DX-Spot auswählen.", parent=self)
            return
        callsign = (spot.call or "").strip().upper()
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
