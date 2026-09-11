from __future__ import annotations

import base64
import io
import re
import threading
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from datetime import datetime, timezone
from pathlib import Path
import tkinter as tk
from tkinter import messagebox, ttk
from app_common import display_now, utc_from_form
from callbook import (
    CALLBOOK_SOURCE_DISABLED, CALLBOOK_SOURCE_QRZ, CALLBOOK_SOURCE_WAVELOG, CallbookError, CallbookResult, QrzClient, lookup_candidate, normalize_wavelog_result,
)
from dx_cluster import normalize_worked_mode
from logger_core import (
    BANDS, CountryDB, MODES, VERSION, WavelogClient, band_from_mhz, qso_hash, secure_urlopen,
)
from notifications import notify_qso_logged
from qsl_background import QSL_BACKGROUND_NEW_QSO_MS
from xota import distance_m, initial_bearing_degrees, maidenhead_coordinates, normalize_references
from ui_theme import theme

try:
    from PIL import Image, ImageTk
except ImportError:
    Image = None
    ImageTk = None


class LogbookFeatureMixin:
    def _init_logbook_feature(self) -> None:
        self.callbook_generation = 0
        self.callbook_lookup_job = None
        self.callbook_result: CallbookResult | None = None
        self.callbook_photo = None
        self.callbook_image_bytes: bytes | None = None
        self.qrz_client: QrzClient | None = None
        self.qrz_client_credentials: tuple[str, str] | None = None
        self.callbook_autofill: dict[str, str] = {}
        self.callbook_last_call = ""
        self.country_db = CountryDB(Path(__file__).resolve().parent / "cty.dat")
        self.current_country = None

    def _build_log_page(self):
        p = self._new_page("log")
        self.log_page = p
        p.columnconfigure(0, weight=1)
        p.columnconfigure(1, weight=0, minsize=370)
        p.rowconfigure(0, weight=1)

        left = self._card(p, row=0, column=0, sticky="nsew", padx=(0, 8))
        left.columnconfigure(0, weight=1)
        left.columnconfigure(1, weight=1)
        left.columnconfigure(2, weight=1)
        left.columnconfigure(3, weight=1)

        call_header = ttk.Frame(left, style="Card.TFrame")
        call_header.grid(row=0, column=0, columnspan=4, sticky="ew", pady=(0, 8))
        call_header.columnconfigure(0, weight=1)
        ttk.Label(call_header, text="Gegenstation", style="CardTitle.TLabel").grid(row=0, column=0, sticky="w")
        self.wsjtx_live_badge = tk.Label(
            call_header, text="", bg=theme.CARD, fg=theme.ACCENT,
            font=("Segoe UI Semibold", 9), anchor="e", padx=8, pady=3,
        )
        self.wsjtx_live_badge.grid(row=0, column=1, sticky="e")
        self.qso_worked_badge = tk.Label(
            call_header, text="", bg=theme.CARD, fg=theme.MUTED, font=("Segoe UI Semibold", 9),
            anchor="e", padx=8, pady=3,
        )
        self.qso_worked_badge.grid(row=0, column=2, sticky="e")
        self.call_var = tk.StringVar()
        self.call_entry = ttk.Entry(left, textvariable=self.call_var, style="Call.TEntry")
        self.call_entry.grid(row=1, column=0, columnspan=4, sticky="ew", pady=(0, 14))
        self.call_entry.bind("<KeyRelease>", self._call_changed)
        self.call_entry.bind("<Return>", lambda e: self.save_qso())
        self.call_var.trace_add("write", lambda *_args: self._update_qrz_page_button())

        self.freq_var = tk.StringVar()
        self.band_var = tk.StringVar(value="20m")
        self.mode_var = tk.StringVar(value="SSB")
        self.rst_sent_var = tk.StringVar(value="59")
        self.rst_rcvd_var = tk.StringVar(value="59")
        self._field(left, "Frequenz (MHz)", self.freq_var, 2, 0)
        self.freq_entry = left.grid_slaves(row=3, column=0)[0]
        self.freq_entry.bind("<KeyRelease>", self._freq_changed)
        self._combo(left, "Band", self.band_var, BANDS, 2, 1)
        self._combo(left, "Mode", self.mode_var, MODES, 2, 2)
        self._field(left, "Leistung (W)", tk.StringVar(), 2, 3, key="tx_pwr")
        self._field(left, "RST gesendet", self.rst_sent_var, 4, 0)
        self._field(left, "RST empfangen", self.rst_rcvd_var, 4, 1)
        self._field(left, "Locator Gegenstation", tk.StringVar(), 4, 2, key="gridsquare")
        self._field(left, "Name", tk.StringVar(), 4, 3, key="name")
        self._field(left, "QTH Gegenstation", tk.StringVar(), 6, 0, span=2, key="qth")
        self._field(left, "POTA Ref Gegenstation", tk.StringVar(), 6, 2, key="pota_ref")
        self._field(left, "SOTA Ref Gegenstation", tk.StringVar(), 6, 3, key="sota_ref")
        self._field(left, "WWFF Ref Gegenstation", tk.StringVar(), 8, 0, key="wwff_ref")
        self._field(left, "Kommentar", tk.StringVar(), 8, 1, span=3, key="comment")

        ttk.Label(left, text="Notizen", style="Card.TLabel").grid(row=10, column=0, sticky="w", pady=(10, 4))
        self.notes_text = tk.Text(left, height=3, wrap="word", font=("Segoe UI", 10), relief="solid", borderwidth=1,
                                  highlightthickness=0, bg=theme.INPUT_BG, fg=theme.TEXT, insertbackground=theme.TEXT)
        self.notes_text.grid(row=11, column=0, columnspan=4, sticky="ew")

        btns = ttk.Frame(left, style="Card.TFrame")
        btns.grid(row=12, column=0, columnspan=4, sticky="ew", pady=(16, 0))
        ttk.Button(btns, text="QSO speichern", style="Primary.TButton", command=self.save_qso).pack(side="left")
        ttk.Button(btns, text="Felder leeren", style="Secondary.TButton", command=self.clear_qso_form).pack(side="left", padx=8)
        self.dx_spot_button = ttk.Button(
            btns, text="DX-Spot senden", style="Secondary.TButton", command=self.send_current_dx_spot,
        )
        self.dx_spot_button.pack(side="right")
        self.call_var.trace_add("write", lambda *_args: self._update_dx_spot_button())
        self.freq_var.trace_add("write", lambda *_args: self._update_dx_spot_button())
        self.tune_button = ttk.Button(
            btns, text="TUNE (ATU)", style="Secondary.TButton",
            command=self.start_tuner_from_qso, state="disabled",
        )
        self.tune_button.pack(side="right", padx=(0, 8))

        self.qso_history_frame = tk.Frame(
            left, bg=theme.SURFACE, highlightbackground=theme.BORDER, highlightthickness=1,
        )
        self.qso_history_frame.grid(row=13, column=0, columnspan=4, sticky="ew", pady=(14, 0))
        self.qso_history_frame.columnconfigure(0, weight=1)
        self.qso_history_title = tk.Label(
            self.qso_history_frame, text="", bg=theme.SURFACE, fg=theme.TEXT,
            font=("Segoe UI Semibold", 9), anchor="w", padx=10, pady=6,
        )
        self.qso_history_title.grid(row=0, column=0, sticky="ew")
        self.qso_history_details = tk.Label(
            self.qso_history_frame, text="", bg=theme.SURFACE, fg=theme.MUTED,
            font=("Segoe UI", 9), justify="left", anchor="nw",
            wraplength=760, padx=10, pady=5,
        )
        self.qso_history_details.grid(row=1, column=0, sticky="ew")
        self.qso_history_frame.grid_remove()

        right = self._card(p, row=0, column=1, sticky="nsew", padx=(8, 0))
        right.columnconfigure(0, weight=1)
        ttk.Label(right, text="Datum / Zeit", style="CardTitle.TLabel").grid(row=0, column=0, sticky="w")
        self.time_mode_var = tk.StringVar(value="UTC")
        self.live_time_var = tk.BooleanVar(value=True)
        row = ttk.Frame(right, style="Card.TFrame")
        row.grid(row=1, column=0, sticky="ew", pady=(6, 4))
        ttk.Radiobutton(row, text="UTC", variable=self.time_mode_var, value="UTC", command=self._time_mode_changed).pack(side="left")
        ttk.Radiobutton(row, text="Lokal", variable=self.time_mode_var, value="LOCAL", command=self._time_mode_changed).pack(side="left", padx=(12, 0))
        ttk.Checkbutton(row, text="Live", variable=self.live_time_var, command=self._live_changed).pack(side="right")
        self.qso_date_var = tk.StringVar()
        self.qso_time_var = tk.StringVar()
        datetime_row = ttk.Frame(right, style="Card.TFrame")
        datetime_row.grid(row=2, column=0, sticky="ew")
        datetime_row.columnconfigure(0, weight=1)
        datetime_row.columnconfigure(1, weight=1)
        self._field(datetime_row, "Datum", self.qso_date_var, 0, 0)
        self._field(datetime_row, "Uhrzeit", self.qso_time_var, 0, 1)

        ttk.Separator(right).grid(row=3, column=0, sticky="ew", pady=12)
        callbook_head = ttk.Frame(right, style="Card.TFrame")
        callbook_head.grid(row=4, column=0, sticky="ew")
        callbook_head.columnconfigure(0, weight=1)
        ttk.Label(callbook_head, text="Callbook-Informationen", style="CardTitle.TLabel").grid(row=0, column=0, sticky="w")
        self.callbook_source_label = tk.Label(callbook_head, text="OFFLINE", bg=theme.NEUTRAL_BADGE_BG, fg=theme.MUTED, font=("Segoe UI Semibold", 8), padx=8, pady=3)
        self.callbook_source_label.grid(row=0, column=1, sticky="e")

        self.callbook_image_frame = tk.Frame(right, bg=theme.PHOTO_BG, height=104, relief="flat")
        self.callbook_image_frame.grid(row=5, column=0, sticky="ew", pady=(8, 7))
        self.callbook_image_frame.grid_propagate(False)
        self.callbook_image_frame.columnconfigure(0, weight=1)
        self.callbook_image_frame.rowconfigure(0, weight=1)
        self.callbook_image_label = tk.Label(
            self.callbook_image_frame, text="Kein Foto geladen", bg=theme.PHOTO_BG, fg=theme.MUTED,
            font=("Segoe UI", 9), relief="flat",
        )
        self.callbook_image_label.grid(row=0, column=0, sticky="nsew")
        self.callbook_name_label = tk.Label(right, text="Rufzeichen eingeben …", bg=theme.CARD, fg=theme.TEXT, font=("Segoe UI Semibold", 13), anchor="w")
        self.callbook_name_label.grid(row=6, column=0, sticky="ew")
        self.callbook_details_label = tk.Label(right, text="", bg=theme.CARD, fg=theme.TEXT, font=("Segoe UI", 9), justify="left", anchor="nw", wraplength=350)
        self.callbook_details_label.grid(row=7, column=0, sticky="ew", pady=(3, 0))
        self.callbook_distance_label = tk.Label(
            right, text="", bg=theme.CARD, fg=theme.ACCENT, font=("Segoe UI Semibold", 9),
            justify="left", anchor="w", wraplength=350,
        )
        self.callbook_distance_label.grid(row=8, column=0, sticky="ew", pady=(3, 0))
        self.rotor_log_frame = tk.Frame(
            right, bg=theme.SURFACE, highlightbackground=theme.BORDER, highlightthickness=1,
        )
        self.rotor_log_frame.grid(row=9, column=0, sticky="ew", pady=(8, 0))
        self._build_rotor_log_controls(self.rotor_log_frame)
        self.callbook_status_label = tk.Label(
            right, text="Online-Abfrage optional · Offline-Logging bleibt immer verfügbar.",
            bg=theme.CARD, fg=theme.MUTED, font=("Segoe UI", 8), justify="left", anchor="w", wraplength=350,
        )
        self.callbook_status_label.grid(row=10, column=0, sticky="ew", pady=(5, 0))
        callbook_actions = ttk.Frame(right, style="Card.TFrame")
        callbook_actions.grid(row=11, column=0, sticky="w", pady=(7, 0))
        ttk.Button(
            callbook_actions,
            text="Callbook neu laden",
            style="Secondary.TButton",
            command=self._manual_callbook_lookup,
        ).pack(side="left")
        self.qrz_page_button = ttk.Button(
            callbook_actions,
            text="QRZ.com öffnen",
            style="Secondary.TButton",
            command=self._open_current_qrz_page,
            state="disabled",
        )
        self.qrz_page_button.pack(side="left", padx=(8, 0))

        ttk.Separator(right).grid(row=12, column=0, sticky="ew", pady=12)
        ttk.Label(right, text="DXCC · offline", style="CardTitle.TLabel").grid(row=13, column=0, sticky="w")
        self.country_summary = tk.Label(right, bg=theme.CARD, fg=theme.TEXT, font=("Segoe UI", 9), justify="left", anchor="nw", wraplength=350)
        self.country_summary.grid(row=14, column=0, sticky="ew", pady=(5, 0))
        self.country_source = tk.Label(right, text="CTY.DAT · keine Internetverbindung nötig", bg=theme.CARD, fg=theme.MUTED, font=("Segoe UI", 8), justify="left", anchor="w")
        self.country_source.grid(row=15, column=0, sticky="ew", pady=(3, 0))

        # Kept for existing profile and log-file update helpers; the compact
        # footer/header now present these details instead of a second side card.
        self.profile_summary = tk.Label(right, bg=theme.CARD)
        self.logfile_preview = tk.Label(right, bg=theme.CARD)
        self._update_country_summary()

        self.form_vars = {
            "tx_pwr": self._vars["tx_pwr"], "gridsquare": self._vars["gridsquare"], "name": self._vars["name"],
            "qth": self._vars["qth"], "pota_ref": self._vars["pota_ref"], "sota_ref": self._vars["sota_ref"],
            "wwff_ref": self._vars["wwff_ref"], "comment": self._vars["comment"],
        }
        self.freq_var.trace_add("write", lambda *_args: self._update_qso_worked_status())
        self.band_var.trace_add("write", lambda *_args: self._update_qso_worked_status())
        self.mode_var.trace_add("write", lambda *_args: self._update_qso_worked_status())
        self.form_vars["gridsquare"].trace_add("write", lambda *_args: self._update_callbook_distance())

    def _update_callbook_distance(self):
        if not hasattr(self, "callbook_distance_label") or self.db is None:
            return
        own_locator = self.db.get_setting("locator", "").strip().upper()
        remote_var = self.form_vars.get("gridsquare")
        remote_locator = remote_var.get().strip().upper() if remote_var is not None else ""
        try:
            own_lat, own_lon = maidenhead_coordinates(own_locator)
            remote_lat, remote_lon = maidenhead_coordinates(remote_locator)
        except ValueError:
            self.callbook_distance_label.configure(text="")
            self._set_rotor_target(None)
            return
        kilometres = distance_m(own_lat, own_lon, remote_lat, remote_lon) / 1000.0
        bearing = initial_bearing_degrees(own_lat, own_lon, remote_lat, remote_lon)
        directions_de = ("N", "NNO", "NO", "ONO", "O", "OSO", "SO", "SSO", "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW")
        directions_en = ("N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE", "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW")
        direction = (directions_en if self.language == "en" else directions_de)[int((bearing + 11.25) // 22.5) % 16]
        distance_text = f"{kilometres:.1f}" if kilometres < 10 else f"{kilometres:,.0f}"
        if self.language == "de":
            distance_text = distance_text.replace(",", "_").replace(".", ",").replace("_", ".")
            text = f"Entfernung: ca. {distance_text} km · Peilung {bearing:.0f}° ({direction})"
        else:
            text = f"Distance: approx. {distance_text} km · bearing {bearing:.0f}° ({direction})"
        self.callbook_distance_label.configure(text=text)
        self._set_rotor_target(bearing)

    def _field(self, parent, label, var, row, col, span=1, key=None):
        ttk.Label(parent, text=label, style="Card.TLabel").grid(row=row, column=col, columnspan=span, sticky="w", padx=(0, 8), pady=(7, 3))
        e = ttk.Entry(parent, textvariable=var)
        e.grid(row=row + 1, column=col, columnspan=span, sticky="ew", padx=(0, 8))
        if key:
            self._vars[key] = var
        return e

    def _combo(self, parent, label, var, values, row, col):
        ttk.Label(parent, text=label, style="Card.TLabel").grid(row=row, column=col, sticky="w", padx=(0, 8), pady=(7, 3))
        cb = ttk.Combobox(parent, textvariable=var, values=values, state="readonly")
        cb.grid(row=row + 1, column=col, sticky="ew", padx=(0, 8))
        return cb

    def _call_changed(self, _event=None):
        value = self.call_var.get().upper()
        if value != self.call_var.get():
            pos = self.call_entry.index(tk.INSERT)
            self.call_var.set(value)
            try:
                self.call_entry.icursor(pos)
            except Exception:
                pass
        if value != self.callbook_last_call:
            for key, old_value in self.callbook_autofill.items():
                variable = self.form_vars.get(key) if hasattr(self, "form_vars") else None
                if variable is not None and variable.get() == old_value:
                    variable.set("")
            self.callbook_autofill.clear()
            self.callbook_last_call = value
        self.current_country = self.country_db.lookup(value)
        self._update_country_summary()
        self._update_qso_worked_status()
        self._schedule_callbook_lookup(value)

    def _update_qso_worked_status(self):
        """Show worked-before state for the active profile, band and mode."""
        if not hasattr(self, "call_entry") or not hasattr(self, "qso_worked_badge"):
            return
        call = self.call_var.get().strip().upper()
        if not call:
            self.call_entry.configure(style="Call.TEntry")
            self.qso_worked_badge.configure(text="", bg=theme.CARD, fg=theme.MUTED)
            self._update_qso_worked_history("")
            return

        frequency_hz = 0
        try:
            frequency_hz = int(round(float(self.freq_var.get().strip().replace(",", ".")) * 1_000_000))
        except (TypeError, ValueError):
            pass
        band = self.band_var.get().strip()
        mode = normalize_worked_mode(self.mode_var.get(), frequency_hz, band)
        exact_count = self.qso_worked_counts.get((call, band, mode), 0) if band and mode else 0
        total_count = self.qso_worked_call_totals.get(call, 0)

        if exact_count:
            text = (
                f"✓ WORKED · {exact_count}× · {band} {mode}"
                if self.language == "en"
                else f"✓ BEREITS GEARBEITET · {exact_count}× · {band} {mode}"
            )
            self.call_entry.configure(style="Worked.Call.TEntry")
            self.qso_worked_badge.configure(text=text, bg=theme.OK_BADGE_BG, fg=theme.OK)
        elif total_count:
            detail = f"{band} {mode}".strip() or "dieser Auswahl"
            text = (
                f"Worked {total_count}× · not on {detail}"
                if self.language == "en"
                else f"Schon {total_count}× gearbeitet · nicht auf {detail}"
            )
            self.call_entry.configure(style="Call.TEntry")
            self.qso_worked_badge.configure(text=text, bg=theme.WARN_BADGE_BG, fg=theme.WARN)
        else:
            self.call_entry.configure(style="Call.TEntry")
            self.qso_worked_badge.configure(text="", bg=theme.CARD, fg=theme.MUTED)
        self._update_qso_worked_history(call)

    def _update_qso_worked_history(self, call: str):
        """Show the most recent local QSOs for the callsign without growing the form indefinitely."""
        if not hasattr(self, "qso_history_frame"):
            return
        history = self.qso_worked_history.get(call, []) if call else []
        if not history:
            self.qso_history_frame.grid_remove()
            return

        history_limit = 3 if self.winfo_height() < 700 else 5
        shown = history[:history_limit]
        title = (
            f"Previous QSOs with {call} ({len(history)})"
            if self.language == "en"
            else f"Bisherige QSOs mit {call} ({len(history)})"
        )
        lines = []
        for qso in shown:
            raw_date = str(qso.get("qso_date") or "")
            display_date = raw_date
            if self.language != "en" and re.fullmatch(r"\d{4}-\d{2}-\d{2}", raw_date):
                display_date = f"{raw_date[8:10]}.{raw_date[5:7]}.{raw_date[:4]}"
            raw_time = re.sub(r"[^0-9]", "", str(qso.get("time_on") or ""))[:6]
            if len(raw_time) >= 4:
                display_time = f"{raw_time[:2]}:{raw_time[2:4]}" + (f":{raw_time[4:6]}" if len(raw_time) >= 6 else "")
            else:
                display_time = raw_time or "—"
            lines.append(
                f"{display_date or '—'} · {display_time} UTC · "
                f"{qso.get('band') or '—'} · {qso.get('mode') or '—'}"
            )
        remaining = len(history) - len(shown)
        if remaining:
            lines.append(
                f"… and {remaining} more in the local logbook"
                if self.language == "en"
                else f"… und {remaining} weitere im lokalen Logbuch"
            )
        self.qso_history_title.configure(text=title)
        self.qso_history_details.configure(text="\n".join(lines))
        self.qso_history_frame.grid()

    def _configured_callbook_source(self) -> str:
        source = self.db.get_setting("callbook_source", CALLBOOK_SOURCE_WAVELOG).strip().lower()
        if source not in {CALLBOOK_SOURCE_WAVELOG, CALLBOOK_SOURCE_QRZ, CALLBOOK_SOURCE_DISABLED}:
            source = CALLBOOK_SOURCE_WAVELOG
        return source

    def _schedule_callbook_lookup(self, callsign: str, *, force: bool = False):
        if self.callbook_lookup_job is not None:
            try:
                self.after_cancel(self.callbook_lookup_job)
            except Exception:
                pass
            self.callbook_lookup_job = None
        self.callbook_generation += 1
        generation = self.callbook_generation
        self.callbook_result = None
        self.callbook_photo = None
        self.callbook_image_bytes = None
        if hasattr(self, "callbook_image_label"):
            self.callbook_image_label.configure(image="", text="Kein Foto geladen")
        if not lookup_candidate(callsign):
            if hasattr(self, "callbook_name_label"):
                self.callbook_name_label.configure(text="Rufzeichen eingeben …")
                self.callbook_details_label.configure(text="")
                self.callbook_source_label.configure(text="OFFLINE", bg=theme.NEUTRAL_BADGE_BG, fg=theme.MUTED)
                self.callbook_status_label.configure(text="Online-Abfrage optional · Offline-Logging bleibt immer verfügbar.", fg=theme.MUTED)
            return
        if not force and self.db.get_setting("callbook_auto_lookup", "1") != "1":
            self.callbook_name_label.configure(text=callsign)
            self.callbook_details_label.configure(text="Automatische Abfrage ist deaktiviert.")
            return
        if self._configured_callbook_source() == CALLBOOK_SOURCE_DISABLED:
            self.callbook_name_label.configure(text=callsign)
            self.callbook_details_label.configure(text="Callbook-Abfrage ist deaktiviert.")
            return
        self.callbook_status_label.configure(text="Callbook wird abgefragt …", fg=theme.MUTED)
        delay = 0 if force else 700
        self.callbook_lookup_job = self.after(delay, lambda: self._start_callbook_lookup(callsign, generation, force))

    def _manual_callbook_lookup(self):
        self._schedule_callbook_lookup(self.call_var.get().strip().upper(), force=True)

    def _update_qrz_page_button(self) -> None:
        if not hasattr(self, "qrz_page_button"):
            return
        callsign = self.call_var.get().strip().upper()
        self.qrz_page_button.configure(
            state="normal" if lookup_candidate(callsign) else "disabled",
        )

    def _open_current_qrz_page(self) -> None:
        callsign = self.call_var.get().strip().upper()
        if not lookup_candidate(callsign):
            messagebox.showinfo(
                "QRZ.com",
                (
                    "Please enter a complete callsign first."
                    if self.language == "en"
                    else "Bitte zuerst ein vollständiges Rufzeichen eingeben."
                ),
                parent=self,
            )
            return

        url = "https://www.qrz.com/db/" + urllib.parse.quote(callsign, safe="")
        try:
            opened = webbrowser.open_new_tab(url)
        except Exception as exc:
            messagebox.showerror(
                "QRZ.com",
                (
                    f"QRZ.com could not be opened:\n{exc}"
                    if self.language == "en"
                    else f"QRZ.com konnte nicht geöffnet werden:\n{exc}"
                ),
                parent=self,
            )
            return

        if not opened:
            messagebox.showwarning(
                "QRZ.com",
                (
                    "The default browser could not open QRZ.com."
                    if self.language == "en"
                    else "Der Standardbrowser konnte QRZ.com nicht öffnen."
                ),
                parent=self,
            )
            return

        self.status_var.set(
            f"QRZ.com opened: {callsign}"
            if self.language == "en"
            else f"QRZ.com geöffnet: {callsign}"
        )

    def _start_callbook_lookup(self, callsign: str, generation: int, force: bool = False):
        self.callbook_lookup_job = None
        source = self._configured_callbook_source()
        band = self.band_var.get()
        mode = self.mode_var.get()

        def worker():
            try:
                result = self._lookup_callbook_result(
                    callsign, source, band=band, mode=mode, use_cache=not force,
                )
                if not self.closing:
                    self.after(0, lambda current=result: self._apply_callbook_result(callsign, generation, current))
            except Exception as exc:
                if not self.closing:
                    error_message = str(exc)
                    self.after(0, lambda message=error_message: self._callbook_lookup_failed(callsign, generation, message))

        threading.Thread(target=worker, name="callbook-lookup", daemon=True).start()

    def _lookup_callbook_result(
        self, callsign: str, source: str, *, band: str = "", mode: str = "", use_cache: bool = True,
        metadata_db: MetadataDB | None = None,
    ) -> CallbookResult:
        """Run one configured lookup; safe to call from a background thread."""
        db = metadata_db or self.db
        result = None
        if use_cache:
            cached = db.get_callbook_cache(callsign, source)
            if cached:
                result = CallbookResult.from_json(cached)
                result.cached = True
        if result is None:
            if source == CALLBOOK_SOURCE_QRZ:
                username = db.get_setting("qrz_username", "").strip()
                password = db.get_secret("qrz_password")
                credentials = (username, password)
                if self.qrz_client is None or self.qrz_client_credentials != credentials:
                    self.qrz_client = QrzClient(username, password, timeout=8)
                    self.qrz_client_credentials = credentials
                result = self.qrz_client.lookup(callsign)
            elif source == CALLBOOK_SOURCE_WAVELOG:
                client = WavelogClient(
                    db.get_setting("wavelog_url", ""), db.get_token(), timeout=8,
                )
                payload = client.lookup_callsign(callsign, band=band, mode=mode, include_callbook=True)
                result = normalize_wavelog_result(payload, callsign)
            else:
                raise CallbookError("Callbook-Abfrage ist deaktiviert")
            if not any((result.name, result.qth, result.grid, result.country, result.image_url, result.email)):
                raise CallbookError("Keine Callbook-Daten gefunden")
            db.set_callbook_cache(callsign, source, result.to_json())
        return result

    def _apply_callbook_result(self, callsign: str, generation: int, result: CallbookResult):
        if self.closing or generation != self.callbook_generation or self.call_var.get().strip().upper() != callsign:
            return
        self.callbook_result = result
        for key, value in (("name", result.name), ("gridsquare", result.grid), ("qth", result.qth)):
            variable = self.form_vars.get(key)
            if value and variable is not None and (not variable.get().strip() or variable.get() == self.callbook_autofill.get(key, "")):
                variable.set(value)
                self.callbook_autofill[key] = value
        source_text = result.source or "CALLBOOK"
        self.callbook_source_label.configure(text=source_text.upper(), bg=theme.OK_BADGE_BG, fg=theme.OK)
        title = result.callsign or callsign
        if result.name:
            title += " · " + result.name
        self.callbook_name_label.configure(text=title)
        place = ", ".join(part for part in (result.qth, result.state, result.country) if part)
        details = []
        if place:
            details.append(place)
        if result.grid:
            details.append("Locator: " + result.grid)
        zones = " / ".join(part for part in (result.cq_zone, result.itu_zone) if part)
        if zones:
            details.append("CQ / ITU: " + zones)
        self.callbook_details_label.configure(text="\n".join(details) or "Keine weiteren Angaben")
        suffix = " · aus lokalem Cache" if result.cached else ""
        self.callbook_status_label.configure(text="Daten automatisch übernommen" + suffix, fg=theme.OK)
        if result.image_url:
            threading.Thread(
                target=self._load_callbook_image,
                args=(callsign, generation, result.image_url),
                name="callbook-image",
                daemon=True,
            ).start()

    def _callbook_lookup_failed(self, callsign: str, generation: int, message: str):
        if self.closing or generation != self.callbook_generation or self.call_var.get().strip().upper() != callsign:
            return
        self.callbook_source_label.configure(text="OFFLINE", bg=theme.NEUTRAL_BADGE_BG, fg=theme.MUTED)
        self.callbook_name_label.configure(text=callsign)
        self.callbook_details_label.configure(text="Keine Online-Daten verfügbar.")
        detail = (message or "Callbook ist nicht erreichbar").strip()[:240]
        self.callbook_status_label.configure(
            text=f"{detail} · Offline-Logging läuft ohne Unterbrechung weiter.", fg=theme.MUTED,
        )

    def _load_callbook_image(self, callsign: str, generation: int, image_url: str):
        try:
            parsed = urllib.parse.urlparse(image_url)
            if parsed.scheme not in {"http", "https"}:
                return
            if parsed.scheme == "http":
                image_url = urllib.parse.urlunparse(parsed._replace(scheme="https"))
            request = urllib.request.Request(
                image_url,
                headers={"User-Agent": f"DA6IT.de-Wavelog-Offline-Logger/{VERSION}", "Accept": "image/*"},
            )
            with secure_urlopen(request, timeout=8) as response:
                content_type = str(response.headers.get("Content-Type") or "").lower()
                if content_type and not content_type.startswith("image/"):
                    return
                data = response.read(5 * 1024 * 1024 + 1)
            if not data or len(data) > 5 * 1024 * 1024:
                return
            if not self.closing:
                self.after(0, lambda payload=data: self._show_callbook_image(callsign, generation, payload))
        except Exception:
            return

    def _show_callbook_image(self, callsign: str, generation: int, data: bytes):
        if self.closing or generation != self.callbook_generation or self.call_var.get().strip().upper() != callsign:
            return
        self.callbook_image_bytes = data
        self._render_callbook_image(data)

    def _render_callbook_image(self, data: bytes):
        """Render a callbook image at the size of the current responsive zoom."""
        try:
            if Image is not None and ImageTk is not None:
                image = Image.open(io.BytesIO(data))
                if image.width * image.height > 24_000_000:
                    return
                image.thumbnail(
                    (180, 94),
                    Image.Resampling.LANCZOS,
                )
                photo = ImageTk.PhotoImage(image)
            else:
                photo = tk.PhotoImage(data=base64.b64encode(data).decode("ascii"))
            self.callbook_photo = photo
            self.callbook_image_label.configure(image=photo, text="")
        except Exception:
            self.callbook_image_label.configure(image="", text="Fotoformat in dieser Laufzeit nicht verfügbar")

    def _update_country_summary(self):
        if not hasattr(self, "country_summary"):
            return
        info = self.current_country
        if not info:
            txt = "Land / DXCC:  —\nKontinent:     —\nCQ / ITU:      — / —"
        else:
            txt = (f"Land / DXCC:  {info.country}\n"
                   f"Kontinent:     {info.cont}\n"
                   f"CQ / ITU:      {info.cqz} / {info.ituz}")
        self.country_summary.configure(text=txt)

    def _country_fields_for_call(self, call: str) -> dict[str, str]:
        info = self.country_db.lookup(call)
        if not info:
            return {"country": "", "cont": "", "cqz": "", "ituz": ""}
        return {"country": info.country, "cont": info.cont, "cqz": info.cqz, "ituz": info.ituz}

    def _freq_changed(self, _event=None):
        raw = self.freq_var.get().strip().replace(",", ".")
        try:
            mhz = float(raw)
            b = band_from_mhz(mhz)
            if b:
                self.band_var.set(b)
        except Exception:
            pass

    def _time_mode_changed(self):
        self.db.set_setting("time_mode", self.time_mode_var.get())
        if self.live_time_var.get():
            self._set_current_qso_time()

    def _live_changed(self):
        state = "readonly" if self.live_time_var.get() else "normal"
        # Entries are found by their variables; normal/read-only not crucial, keep editable only when live off.
        if self.live_time_var.get():
            self._set_current_qso_time()

    def _set_current_qso_time(self):
        n = display_now(self.time_mode_var.get())
        self.qso_date_var.set(n.strftime("%Y-%m-%d"))
        self.qso_time_var.set(n.strftime("%H:%M:%S"))

    def _tick_clock(self):
        if self.closing:
            return
        n = display_now(self.time_mode_var.get() if hasattr(self, "time_mode_var") else "UTC")
        self.clock_label.configure(text=n.strftime("%H:%M:%S"))
        self.clock_zone_label.configure(text="LOCAL" if getattr(self, "time_mode_var", tk.StringVar(value="UTC")).get() == "LOCAL" else "UTC")
        if hasattr(self, "live_time_var") and self.live_time_var.get():
            self.qso_date_var.set(n.strftime("%Y-%m-%d"))
            self.qso_time_var.set(n.strftime("%H:%M:%S"))
        if hasattr(self, "fast_log_utc_label"):
            fast_now = datetime.now(timezone.utc)
            self.fast_log_utc_label.configure(
                text=fast_now.strftime("UTC · %Y-%m-%d · %H:%M:%S"),
            )
        self._update_logfile_preview()
        self.after(250, self._tick_clock)

    def _profile_values(self) -> dict[str, str]:
        values = {
            "operator_call": self.db.get_setting("operator_call", "").upper(),
            "station_call": self.db.get_setting("station_call", "").upper(),
            "my_gridsquare": self.db.get_setting("locator", "").upper(),
            "my_qth": self.db.get_setting("qth", ""),
            "my_pota_ref": self.db.get_setting("my_pota_ref", "").upper(),
            "my_sota_ref": self.db.get_setting("my_sota_ref", "").upper(),
            "my_wwff_ref": self.db.get_setting("my_wwff_ref", "").upper(),
        }
        activation = self.xota_repository.active() if hasattr(self, "xota_repository") else None
        if activation:
            refs = normalize_references(activation.references)
            values.update({
                "station_call": activation.callsign,
                "my_gridsquare": activation.gridsquare,
                "my_qth": activation.city,
                "my_state": activation.state,
                "my_dxcc": activation.dxcc,
                "my_cq_zone": activation.cq_zone,
                "my_itu_zone": activation.itu_zone,
                "my_pota_ref": ",".join(refs["POTA"]),
                "my_sota_ref": ",".join(refs["SOTA"]),
                "my_wwff_ref": ",".join(refs["WWFF"]),
                "my_iota": ",".join(refs["IOTA"]),
                "my_sig": "WCA" if refs["WCA"] else "",
                "my_sig_info": ",".join(refs["WCA"]),
            })
        return values

    def _update_profile_summary(self):
        p = self._profile_values()
        power = self.db.get_setting("default_power", "")
        lines = [
            f"Operator:  {p['operator_call'] or '—'}",
            f"Station:   {p['station_call'] or '—'}",
            f"Locator:   {p['my_gridsquare'] or '—'}",
            f"QTH:       {p['my_qth'] or '—'}",
            f"Power:     {power + ' W' if power else '—'}",
        ]
        acts = []
        if p["my_pota_ref"]: acts.append("POTA " + p["my_pota_ref"])
        if p["my_sota_ref"]: acts.append("SOTA " + p["my_sota_ref"])
        if p["my_wwff_ref"]: acts.append("WWFF " + p["my_wwff_ref"])
        if acts:
            lines.append("Aktivität: " + " · ".join(acts))
        self.profile_summary.configure(text="\n".join(lines))

    def _update_logfile_preview(self):
        if not hasattr(self, "logfile_preview"):
            return
        self.logfile_preview.configure(text=str(self.store.canonical_path))

    def _bind_active_xota_qso(self, qso: dict) -> None:
        if not hasattr(self, "xota_repository"):
            return
        activation = self.xota_repository.active()
        if activation and qso.get("local_id"):
            self.xota_repository.bind_qso(activation.uuid, qso["local_id"])

    def _collect_qso(self) -> dict:
        call = self.call_var.get().strip().upper()
        if not call:
            raise ValueError("Bitte ein Rufzeichen eingeben")
        qdate, qtime = utc_from_form(self.qso_date_var.get(), self.qso_time_var.get(), self.time_mode_var.get())
        freq = self.freq_var.get().strip().replace(",", ".")
        if freq:
            float(freq)  # validate
        profile = self._profile_values()
        station_call = profile["station_call"] or profile["operator_call"]
        if not station_call:
            raise ValueError("Bitte in den Einstellungen mindestens das eigene/Stations-Rufzeichen eintragen")
        txp = self.form_vars["tx_pwr"].get().strip().replace(",", ".")
        if txp:
            float(txp)
        return {
            "call": call,
            **self._country_fields_for_call(call),
            "band": self.band_var.get(),
            "mode": self.mode_var.get(),
            "freq": freq,
            "qso_date": qdate,
            "time_on": qtime,
            "rst_sent": self.rst_sent_var.get().strip(),
            "rst_rcvd": self.rst_rcvd_var.get().strip(),
            "gridsquare": self.form_vars["gridsquare"].get().strip().upper(),
            "name": self.form_vars["name"].get().strip(),
            "qth": self.form_vars["qth"].get().strip(),
            "pota_ref": self.form_vars["pota_ref"].get().strip().upper(),
            "sota_ref": self.form_vars["sota_ref"].get().strip().upper(),
            "wwff_ref": self.form_vars["wwff_ref"].get().strip().upper(),
            "comment": self.form_vars["comment"].get().strip(),
            "notes": self.notes_text.get("1.0", "end").strip(),
            "tx_pwr": txp,
            **profile,
        }

    def _notify_qso_saved(self, qso: dict) -> None:
        try:
            notify_qso_logged(
                qso,
                enabled=self.ui_preferences.qso_notifications,
                window_id=self.winfo_id(),
                language=self.language,
            )
        except Exception:
            # A desktop notification is optional and must never affect the
            # already completed local ADI write.
            pass

    def save_qso(self):
        try:
            q = self._collect_qso()
            q = self.store.add(q)
            self.db.ensure_local(q["local_id"], qso_hash(q))
            self._remember_qsl_recipient_hint(q)
            self._queue_qsl_recipient_check(q)
            self._schedule_qsl_background_sync(
                QSL_BACKGROUND_NEW_QSO_MS,
                reason="new-qso",
            )
            self._bind_active_xota_qso(q)
            self._notify_qso_saved(q)
            self.status_var.set(f"Gespeichert: {q['call']} · {q['band']} · {q['mode']} · {Path(q['_file']).name}")
            self.refresh_qsos()
            self._local_sync_change()
            self.clear_qso_form()
            # Remember only after clearing the form.  CAT may repopulate the
            # rig frequency immediately, but the completed QSO must stay the
            # default candidate until another callsign is entered.
            self._remember_last_spottable_qso(q)
            self.wsjtx_live_form_call = ""
            self.call_entry.focus_set()
        except Exception as e:
            messagebox.showerror("QSO konnte nicht gespeichert werden", str(e), parent=self)

    def clear_qso_form(self, keep_freq=False):
        self.call_var.set("")
        self.callbook_last_call = ""
        self.callbook_autofill.clear()
        self._schedule_callbook_lookup("")
        self.current_country = None
        self._update_country_summary()
        if not keep_freq:
            self.freq_var.set("")
        self.form_vars["gridsquare"].set("")
        self.form_vars["name"].set("")
        self.form_vars["qth"].set("")
        self.form_vars["pota_ref"].set("")
        self.form_vars["sota_ref"].set("")
        self.form_vars["wwff_ref"].set("")
        self.form_vars["comment"].set("")
        self.notes_text.delete("1.0", "end")
        self.rst_sent_var.set("59" if self.mode_var.get() in ("SSB", "USB", "LSB", "FM", "AM") else "")
        self.rst_rcvd_var.set("59" if self.mode_var.get() in ("SSB", "USB", "LSB", "FM", "AM") else "")
        self.form_vars["tx_pwr"].set(self.db.get_setting("default_power", ""))
        if self.live_time_var.get():
            self._set_current_qso_time()
        self._update_qso_worked_status()
        self._update_dx_spot_button()

    def _remember_last_spottable_qso(self, qso: dict | None):
        if not qso:
            return
        call = str(qso.get("call") or "").strip().upper()
        frequency = str(qso.get("freq") or qso.get("frequency") or "").strip().replace(",", ".")
        try:
            if not call or float(frequency) <= 0:
                return
        except ValueError:
            return
        self.last_spottable_qso = {
            "call": call,
            "freq": frequency,
            "mode": str(qso.get("mode") or "").strip().upper(),
            "comment": str(qso.get("comment") or "").strip(),
            "qso_date": str(qso.get("qso_date") or ""),
            "time_on": str(qso.get("time_on") or ""),
            "local_id": str(qso.get("local_id") or ""),
        }
        self._update_dx_spot_button()

    def _load_last_spottable_qso(self):
        try:
            qsos = self.store.scan()
            candidates = [q for q in qsos if q.get("call") and (q.get("freq") or q.get("frequency"))]
            latest = max(
                candidates,
                key=lambda q: (
                    str(q.get("qso_date") or ""), str(q.get("time_on") or ""),
                    str(q.get("local_id") or ""),
                ),
                default=None,
            )
            self.last_spottable_qso = None
            self._remember_last_spottable_qso(latest)
        except Exception:
            self.last_spottable_qso = None
            self._update_dx_spot_button()

    def _update_dx_spot_button(self):
        if not hasattr(self, "dx_spot_button"):
            return
        current_call = bool(self.call_var.get().strip())
        if current_call:
            text = "DX-Spot senden"
            state = "normal"
        elif self.last_spottable_qso:
            text = f"Letztes QSO spotten · {self.last_spottable_qso['call']}"
            state = "normal"
        else:
            text = "DX-Spot senden"
            state = "disabled"
        self.dx_spot_button.configure(text=self._tr(text), state=state)
