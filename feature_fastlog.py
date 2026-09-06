from __future__ import annotations

from datetime import datetime, timezone
import tkinter as tk
from tkinter import messagebox, ttk
from dx_cluster import normalize_worked_mode
from logger_core import (
    BANDS, MODES, band_from_mhz, build_fast_log_qso, qso_hash,
)
from ui_theme import theme


class FastLogFeatureMixin:
    def _init_fastlog_feature(self) -> None:
        self.fast_log_session_started = datetime.now(timezone.utc)
        self.fast_log_session_ids: list[str] = []
        self.fast_log_session_qsos: dict[str, dict] = {}
        self.fast_log_worked_keys: set[tuple[str, str, str]] = set()
        self._fast_log_cache_generation = -1

    def _build_fast_log_page(self):
        p = self._new_page("fast_log")
        p.columnconfigure(0, weight=1)
        p.rowconfigure(1, weight=1)

        setup = self._card(p, row=0, column=0, sticky="ew", pady=(0, 10))
        for column in range(7):
            setup.columnconfigure(column, weight=1)
        ttk.Label(setup, text="Feste QSO-Daten", style="CardTitle.TLabel").grid(
            row=0, column=0, columnspan=5, sticky="w",
        )
        self.fast_log_utc_label = tk.Label(
            setup, text="", bg=theme.CARD, fg=theme.TEXT, font=("Segoe UI Semibold", 11), anchor="e",
        )
        self.fast_log_utc_label.grid(row=0, column=5, columnspan=2, sticky="e")
        ttk.Label(
            setup,
            text=(
                "Band, Mode, Frequenz und Rapporte einmal festlegen. Danach genügt: "
                "Rufzeichen eingeben und Enter. Jedes QSO wird sofort lokal in ADI gespeichert; "
                "Wavelog wird erst über den manuellen Sync angesprochen."
            ),
            style="Muted.Card.TLabel", wraplength=1050,
        ).grid(row=1, column=0, columnspan=7, sticky="w", pady=(3, 10))

        self.fast_log_band_var = tk.StringVar(value="20m")
        self.fast_log_mode_var = tk.StringVar(value="USB")
        self.fast_log_freq_var = tk.StringVar()
        self.fast_log_rst_sent_var = tk.StringVar(value="59")
        self.fast_log_rst_rcvd_var = tk.StringVar(value="59")
        self.fast_log_power_var = tk.StringVar()
        fields = (
            ("Band", self.fast_log_band_var, BANDS, True),
            ("Mode", self.fast_log_mode_var, MODES, True),
            ("Frequenz (MHz)", self.fast_log_freq_var, (), False),
            ("RST gesendet", self.fast_log_rst_sent_var, (), False),
            ("RST empfangen", self.fast_log_rst_rcvd_var, (), False),
            ("Leistung (W)", self.fast_log_power_var, (), False),
        )
        for column, (label, variable, values, combo) in enumerate(fields):
            ttk.Label(setup, text=label, style="Card.TLabel").grid(
                row=2, column=column, sticky="w", padx=(0, 8), pady=(2, 3),
            )
            if combo:
                widget = ttk.Combobox(setup, textvariable=variable, values=values, state="readonly")
            else:
                widget = ttk.Entry(setup, textvariable=variable)
            widget.grid(row=3, column=column, sticky="ew", padx=(0, 8))
        self.fast_log_freq_var.trace_add("write", lambda *_args: self._fast_log_freq_changed())
        self.fast_log_mode_var.trace_add("write", lambda *_args: self._fast_log_mode_changed())
        ttk.Button(
            setup, text="Werte aus QSO/CAT", style="Secondary.TButton",
            command=self._fast_log_take_current_values,
        ).grid(row=3, column=6, sticky="e")

        body = self._card(p, row=1, column=0, sticky="nsew")
        body.columnconfigure(0, weight=3)
        body.columnconfigure(1, weight=2)
        body.rowconfigure(2, weight=1)
        ttk.Label(body, text="Pileup-Eingabe", style="CardTitle.TLabel").grid(
            row=0, column=0, sticky="w",
        )
        self.fast_log_station_label = tk.Label(
            body, text="", bg=theme.CARD, fg=theme.MUTED, font=("Segoe UI", 9), anchor="e",
        )
        self.fast_log_station_label.grid(row=0, column=1, sticky="e")

        entry_box = ttk.Frame(body, style="Card.TFrame")
        entry_box.grid(row=1, column=0, sticky="new", padx=(0, 14), pady=(10, 0))
        entry_box.columnconfigure(0, weight=1)
        self.fast_log_call_var = tk.StringVar()
        self.fast_log_call_entry = ttk.Entry(
            entry_box, textvariable=self.fast_log_call_var, style="Call.TEntry",
        )
        self.fast_log_call_entry.grid(row=0, column=0, sticky="ew")
        self.fast_log_call_entry.bind("<KeyRelease>", self._fast_log_call_changed)
        self.fast_log_call_entry.bind("<Return>", self.save_fast_log_qso)
        ttk.Label(
            entry_box, text="Nur Rufzeichen + Enter", style="Muted.Card.TLabel",
        ).grid(row=1, column=0, sticky="w", pady=(4, 0))
        self.fast_log_duplicate_label = tk.Label(
            entry_box, text="", bg=theme.CARD, fg=theme.WARN, font=("Segoe UI Semibold", 10), anchor="w",
        )
        self.fast_log_duplicate_label.grid(row=2, column=0, sticky="ew", pady=(16, 0))
        self.fast_log_stats_label = tk.Label(
            entry_box, text="", bg=theme.CARD, fg=theme.TEXT, font=("Segoe UI Semibold", 12),
            justify="left", anchor="w",
        )
        self.fast_log_stats_label.grid(row=3, column=0, sticky="ew", pady=(18, 0))
        buttons = ttk.Frame(entry_box, style="Card.TFrame")
        buttons.grid(row=4, column=0, sticky="ew", pady=(18, 0))
        ttk.Button(
            buttons, text="QSO lokal speichern", style="Primary.TButton",
            command=self.save_fast_log_qso,
        ).pack(side="left")
        ttk.Button(
            buttons, text="Letztes QSO zurücknehmen", style="Secondary.TButton",
            command=self.undo_last_fast_log_qso,
        ).pack(side="left", padx=8)

        recent_box = ttk.Frame(body, style="Card.TFrame")
        recent_box.grid(row=1, column=1, rowspan=2, sticky="nsew", pady=(10, 0))
        recent_box.columnconfigure(0, weight=1)
        recent_box.rowconfigure(1, weight=1)
        ttk.Label(recent_box, text="QSOs dieser Fast-Log-Sitzung", style="CardTitle.TLabel").grid(
            row=0, column=0, sticky="w", pady=(0, 6),
        )
        self.fast_log_recent = tk.Listbox(
            recent_box, font=("Consolas", 10), relief="solid", borderwidth=1,
            activestyle="none",
        )
        self.fast_log_recent.grid(row=1, column=0, sticky="nsew")

    def _fast_log_take_current_values(self):
        if self.freq_var.get().strip():
            self.fast_log_freq_var.set(self.freq_var.get().strip())
        if self.band_var.get() in BANDS:
            self.fast_log_band_var.set(self.band_var.get())
        if self.mode_var.get() in MODES:
            self.fast_log_mode_var.set(self.mode_var.get())
        self.fast_log_power_var.set(
            self.form_vars["tx_pwr"].get().strip() or self.db.get_setting("default_power", ""),
        )
        self.status_var.set("Fast Log: aktuelle QSO-/CAT-Werte übernommen")
        self.fast_log_call_entry.focus_set()

    def _fast_log_freq_changed(self):
        try:
            band = band_from_mhz(float(self.fast_log_freq_var.get().strip().replace(",", ".")))
            if band:
                self.fast_log_band_var.set(band)
        except (TypeError, ValueError):
            pass

    def _fast_log_mode_changed(self):
        if not hasattr(self, "fast_log_rst_sent_var"):
            return
        default = "59" if self.fast_log_mode_var.get() in ("SSB", "USB", "LSB", "FM", "AM") else "599"
        self.fast_log_rst_sent_var.set(default)
        self.fast_log_rst_rcvd_var.set(default)
        if hasattr(self, "fast_log_call_var"):
            self._fast_log_call_changed()

    def _fast_log_call_changed(self, _event=None):
        if not hasattr(self, "fast_log_call_var"):
            return
        value = self.fast_log_call_var.get().upper()
        if value != self.fast_log_call_var.get():
            self.fast_log_call_var.set(value)
        call = value.strip()
        if not call:
            self.fast_log_duplicate_label.configure(text="")
            return
        band = self.fast_log_band_var.get()
        mode = normalize_worked_mode(self.fast_log_mode_var.get(), band=band)
        duplicate = (call, band, mode) in self.fast_log_worked_keys
        self.fast_log_duplicate_label.configure(
            text=(f"Hinweis: {call} wurde auf {band} / {mode} bereits gearbeitet · Enter speichert trotzdem"
                  if duplicate else "Noch nicht auf diesem Band und Mode gearbeitet"),
            fg=(theme.WARN if duplicate else theme.OK),
        )

    def refresh_fast_log_page(self):
        if not hasattr(self, "fast_log_recent"):
            return

        profile = self._profile_values()
        station = profile.get("station_call") or profile.get("operator_call") or "—"
        self.fast_log_station_label.configure(
            text=f"Station: {station} · Zeit automatisch in UTC · LOCAL ONLY",
        )
        if not self.fast_log_power_var.get().strip():
            self.fast_log_power_var.set(self.db.get_setting("default_power", ""))

        # Never parse the complete ADIF file just because this page was opened.
        # The shared QSO cache is prepared asynchronously by QsoSyncFeatureMixin.
        if not getattr(self, "_qso_view_loaded", False):
            self.fast_log_stats_label.configure(
                text="QSO-Index wird im Hintergrund geladen …",
            )
            self.refresh_qsos(force=False, immediate=True)
            self.fast_log_call_entry.focus_set()
            return

        if getattr(self, "_qso_view_dirty", False):
            # Keep the already available cache on screen while a fresh snapshot
            # is prepared. Navigation remains instant.
            self.refresh_qsos(force=False, immediate=True)

        cache_generation = int(getattr(self, "_qso_cache_generation", 0))
        if self._fast_log_cache_generation != cache_generation:
            self.fast_log_worked_keys = set(
                getattr(self, "_qso_cached_fastlog_worked_keys", set())
            )
            self._fast_log_cache_generation = cache_generation

        # Session-local QSOs are merged in so a freshly saved QSO appears
        # immediately, even before the asynchronous shared cache refresh ends.
        by_id = dict(getattr(self, "_qso_cached_by_id", {}))
        by_id.update(self.fast_log_session_qsos)

        self.fast_log_session_ids = [
            local_id for local_id in self.fast_log_session_ids if local_id in by_id
        ]
        self.fast_log_recent.delete(0, "end")
        for local_id in reversed(self.fast_log_session_ids[-30:]):
            qso = by_id[local_id]
            self.fast_log_recent.insert(
                "end",
                f"{str(qso.get('time_on') or '')[:4]:4}  "
                f"{str(qso.get('call') or ''):12}  "
                f"{str(qso.get('band') or ''):6}  {str(qso.get('mode') or '')}",
            )

        elapsed = max(
            60.0,
            (datetime.now(timezone.utc) - self.fast_log_session_started).total_seconds(),
        )
        count = len(self.fast_log_session_ids)
        rate = round(count * 3600.0 / elapsed)
        self.fast_log_stats_label.configure(
            text=f"{count} QSO(s) in dieser Sitzung\nØ {rate} QSO/h",
        )
        self._fast_log_call_changed()


    def save_fast_log_qso(self, _event=None):
        try:
            profile = self._profile_values()
            call = self.fast_log_call_var.get().strip().upper()
            qso = build_fast_log_qso(
                call,
                self.fast_log_band_var.get(),
                self.fast_log_mode_var.get(),
                self.fast_log_freq_var.get(),
                self.fast_log_rst_sent_var.get(),
                self.fast_log_rst_rcvd_var.get(),
                self.fast_log_power_var.get(),
                profile,
                self._country_fields_for_call(call),
            )
            saved = self.store.add(qso)
            self.db.ensure_local(saved["local_id"], qso_hash(saved))
            self._bind_active_xota_qso(saved)
            self._notify_qso_saved(saved)
            self.fast_log_session_ids.append(saved["local_id"])
            self.fast_log_session_qsos[saved["local_id"]] = dict(saved)
            saved_band = str(saved.get("band") or "").strip()
            saved_mode = normalize_worked_mode(
                str(saved.get("mode") or ""), band=saved_band,
            )
            if saved.get("call") and saved_band and saved_mode:
                self.fast_log_worked_keys.add(
                    (str(saved["call"]).strip().upper(), saved_band, saved_mode)
                )
            self.fast_log_call_var.set("")
            self.refresh_qsos()
            self.refresh_fast_log_page()
            self.status_var.set(
                f"Fast Log: {saved['call']} · {saved['band']} · {saved['mode']} lokal gespeichert",
            )
            self._local_sync_change()
            self.fast_log_call_entry.focus_set()
        except Exception as exc:
            messagebox.showerror("Fast-Log-QSO konnte nicht gespeichert werden", str(exc), parent=self)
            self.fast_log_call_entry.focus_set()
        return "break"

    def undo_last_fast_log_qso(self):
        if not self.fast_log_session_ids:
            messagebox.showinfo("Fast Log", "In dieser Sitzung wurde noch kein QSO gespeichert.", parent=self)
            return
        local_id = self.fast_log_session_ids[-1]
        qso = self.fast_log_session_qsos.get(local_id)
        if qso is None:
            qso = self._cached_qso(local_id)
        if not qso:
            self.fast_log_session_ids.pop()
            self.refresh_fast_log_page()
            return
        meta = self.db.get_meta(local_id) or {}
        if meta.get("status") != "local_only" or meta.get("wavelog_id") is not None:
            messagebox.showwarning(
                "Fast Log",
                "Dieses QSO ist nicht mehr ausschließlich lokal und kann hier nicht zurückgenommen werden.",
                parent=self,
            )
            return
        if not messagebox.askyesno(
            "Letztes Fast-Log-QSO zurücknehmen",
            f"{qso.get('call', '—')} · {qso.get('band', '—')} · {qso.get('mode', '—')} wirklich lokal löschen?",
            parent=self,
        ):
            return
        if self.store.delete(local_id):
            self.db.delete_meta(local_id)
            self.fast_log_session_ids.pop()
            self.fast_log_session_qsos.pop(local_id, None)
            self.refresh_qsos()
            self.refresh_fast_log_page()
            self.status_var.set(f"Fast Log: {qso.get('call', 'QSO')} lokal zurückgenommen")
        self.fast_log_call_entry.focus_set()
