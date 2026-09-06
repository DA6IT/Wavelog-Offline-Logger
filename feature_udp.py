from __future__ import annotations

import atexit
import threading
from datetime import datetime
import tkinter as tk
from tkinter import messagebox, ttk
from app_common import write_startup_log
from callbook import CALLBOOK_SOURCE_DISABLED, enrich_qso_from_callbook, lookup_candidate
from cat_control import format_frequency_mhz
from external_logging import ExternalLogError, UdpLogConfig, UdpLogReceiver, find_duplicate_qso
from logger_core import VERSION, band_from_mhz, qso_hash
from ui_theme import theme


class UdpFeatureMixin:
    def _init_udp_feature(self) -> None:
        self.udp_log_receiver = UdpLogReceiver(app_version=VERSION)
        atexit.register(self.udp_log_receiver.stop)
        self.udp_log_generation = 0
        self.udp_log_received = 0
        self.wsjtx_live_form_call = ""

    def _build_udp_log_page(self):
        p = self._new_page("udp_log")
        p.columnconfigure(0, weight=1)
        p.columnconfigure(1, weight=1)
        p.rowconfigure(0, weight=1)

        left = self._card(p, row=0, column=0, sticky="nsew", padx=(0, 8))
        left.columnconfigure(0, weight=1)
        ttk.Label(left, text="UDP-Empfänger", style="CardTitle.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(
            left,
            text=(
                "Empfängt den laufenden QSO-Status und geloggte QSOs aus WSJT-X oder anderen Programmen. "
                "Die Einstellungen gehören zum aktiven Logger-Profil."
            ),
            style="Muted.Card.TLabel",
            wraplength=470,
        ).grid(row=1, column=0, sticky="w", pady=(3, 14))

        ttk.Label(left, text="Bind-Adresse", style="Card.TLabel").grid(row=2, column=0, sticky="w", pady=(2, 3))
        self.udp_log_host_var = tk.StringVar(value="127.0.0.1")
        ttk.Combobox(
            left,
            textvariable=self.udp_log_host_var,
            # 0.0.0.0 is an explicit user opt-in; the default remains loopback-only.
            values=("127.0.0.1", "0.0.0.0"),  # nosec B104
            state="readonly",
        ).grid(row=3, column=0, sticky="ew")
        ttk.Label(
            left,
            text="127.0.0.1 nimmt nur Programme auf diesem PC an. 0.0.0.0 erlaubt auch Pakete aus dem lokalen Netzwerk.",
            style="Muted.Card.TLabel",
            wraplength=470,
        ).grid(row=4, column=0, sticky="w", pady=(4, 12))

        ttk.Label(left, text="UDP-Port", style="Card.TLabel").grid(row=5, column=0, sticky="w", pady=(2, 3))
        self.udp_log_port_var = tk.StringVar(value="2237")
        ttk.Entry(left, textvariable=self.udp_log_port_var).grid(row=6, column=0, sticky="ew")
        ttk.Label(
            left,
            text="Der Port ist frei wählbar. Er muss in Sender und Logger identisch und auf diesem PC noch frei sein.",
            style="Muted.Card.TLabel",
            wraplength=470,
        ).grid(row=7, column=0, sticky="w", pady=(4, 16))

        self.udp_log_autostart_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            left,
            text="UDP Logging beim App-Start und Profilwechsel automatisch starten",
            variable=self.udp_log_autostart_var,
        ).grid(row=8, column=0, sticky="w", pady=(0, 14))

        ttk.Separator(left).grid(row=9, column=0, sticky="ew", pady=(0, 14))
        ttk.Label(left, text="UDP-Status", style="CardTitle.TLabel").grid(row=10, column=0, sticky="w")
        self.udp_log_status_label = tk.Label(
            left,
            text="UDP-Logging ist ausgeschaltet.",
            bg=theme.CARD,
            fg=theme.MUTED,
            font=("Segoe UI", 10),
            justify="left",
            anchor="nw",
            wraplength=470,
        )
        self.udp_log_status_label.grid(row=11, column=0, sticky="ew", pady=(6, 10))
        self.udp_log_live_label = tk.Label(
            left,
            text="WSJT-X Live: kein aktives QSO.",
            bg=theme.SURFACE, fg=theme.MUTED, font=("Segoe UI Semibold", 9),
            justify="left", anchor="nw", wraplength=470, padx=9, pady=7,
        )
        self.udp_log_live_label.grid(row=12, column=0, sticky="ew", pady=(0, 10))
        self.udp_log_last_label = tk.Label(
            left,
            text="Noch kein QSO empfangen.",
            bg=theme.CARD,
            fg=theme.MUTED,
            font=("Segoe UI", 9),
            justify="left",
            anchor="nw",
            wraplength=470,
        )
        self.udp_log_last_label.grid(row=13, column=0, sticky="ew", pady=(0, 12))

        buttons = ttk.Frame(left, style="Card.TFrame")
        buttons.grid(row=14, column=0, sticky="ew")
        ttk.Button(buttons, text="Einstellungen speichern", style="Secondary.TButton", command=self.save_udp_log_settings).pack(side="left")
        self.udp_log_start_button = ttk.Button(buttons, text="UDP starten", style="Primary.TButton", command=self.start_udp_log)
        self.udp_log_start_button.pack(side="left", padx=8)
        self.udp_log_stop_button = ttk.Button(buttons, text="UDP stoppen", style="Secondary.TButton", command=self.stop_udp_log)
        self.udp_log_stop_button.pack(side="left")

        right = self._card(p, row=0, column=1, sticky="nsew", padx=(8, 0))
        right.columnconfigure(0, weight=1)
        ttk.Label(right, text="Einrichtung in WSJT-X", style="CardTitle.TLabel").grid(row=0, column=0, sticky="w")
        wsjtx_help = (
            "Empfohlen: In WSJT-X unter File > Settings > Reporting beim UDP Server "
            "127.0.0.1 und denselben freien Port eintragen (typisch 2237). Der Logger "
            "erkennt das native WSJT-X-Protokoll automatisch.\n\n"
            "Falls der primäre WSJT-X-Port bereits von JTAlert, GridTracker oder einem "
            "anderen Programm belegt ist, kann alternativ der 'logged contact ADIF broadcast' "
            "auf einen zweiten freien Port (zum Beispiel 2333) zeigen. Auch dieses ADIF-Format "
            "wird automatisch erkannt."
        )
        tk.Label(
            right, text=wsjtx_help, bg=theme.CARD, fg=theme.TEXT, font=("Segoe UI", 10),
            justify="left", anchor="nw", wraplength=480,
        ).grid(row=1, column=0, sticky="ew", pady=(8, 18))

        ttk.Separator(right).grid(row=2, column=0, sticky="ew", pady=(0, 16))
        ttk.Label(right, text="Andere Logprogramme", style="CardTitle.TLabel").grid(row=3, column=0, sticky="w")
        tk.Label(
            right,
            text=(
                "Programme, die einen vollständigen ADIF-Datensatz mit <EOR> per UDP senden, "
                "können denselben Empfänger verwenden. Andere Protokolle wie N1MM-XML brauchen "
                "einen eigenen Adapter."
            ),
            bg=theme.CARD, fg=theme.TEXT, font=("Segoe UI", 10), justify="left", anchor="nw", wraplength=480,
        ).grid(row=4, column=0, sticky="ew", pady=(8, 18))

        ttk.Separator(right).grid(row=5, column=0, sticky="ew", pady=(0, 16))
        ttk.Label(right, text="Speicherung", style="CardTitle.TLabel").grid(row=6, column=0, sticky="w")
        tk.Label(
            right,
            text=(
                "Jedes empfangene QSO landet direkt in der ADI-Datei des aktiven Profils und "
                "erscheint als LOCAL ONLY im Logbuch. Es wird später über den normalen Wavelog-Sync "
                "übertragen. Fehlende Callbook-Felder werden über die konfigurierte Wavelog- oder "
                "QRZ.com-Quelle ergänzt; vorhandene Senderdaten bleiben erhalten. Ohne Internet "
                "wird unverändert lokal weitergeloggt. Mehrfach gesendete identische QSOs werden ignoriert.\n\n"
                "Optional kann der UDP-Empfänger beim App-Start automatisch gestartet werden."
            ),
            bg=theme.CARD, fg=theme.TEXT, font=("Segoe UI", 10), justify="left", anchor="nw", wraplength=480,
        ).grid(row=7, column=0, sticky="ew", pady=(8, 0))

    def _load_udp_log_settings_to_ui(self):
        try:
            config = UdpLogConfig.from_getter(self.db.get_setting)
        except ExternalLogError:
            config = UdpLogConfig()
        self.udp_log_host_var.set(config.bind_host)
        self.udp_log_port_var.set(str(config.port))
        self.udp_log_autostart_var.set(self.db.get_setting("udp_log_autostart", "0") == "1")
        self.udp_log_received = 0
        self.wsjtx_live_form_call = ""
        self.wsjtx_live_badge.configure(text="", bg=theme.CARD, fg=theme.ACCENT)
        self.udp_log_status_label.configure(
            text="UDP-Logging ist ausgeschaltet · zum Empfangen bitte UDP starten.", fg=theme.MUTED,
        )
        self.udp_log_live_label.configure(text="WSJT-X Live: kein aktives QSO.", fg=theme.MUTED)
        self.udp_log_last_label.configure(text="Noch kein QSO empfangen.", fg=theme.MUTED)
        self.udp_log_start_button.configure(state="normal")
        self.udp_log_stop_button.configure(state="disabled")

    def _udp_log_config_from_ui(self) -> UdpLogConfig:
        try:
            port = int(self.udp_log_port_var.get().strip())
        except ValueError as exc:
            raise ExternalLogError("Der UDP-Port muss eine ganze Zahl sein.") from exc
        config = UdpLogConfig(self.udp_log_host_var.get().strip(), port)
        config.validate()
        return config

    def save_udp_log_settings(self):
        try:
            config = self._udp_log_config_from_ui()
            for key, value in config.settings().items():
                self.db.set_setting(key, value)
            self.db.set_setting("udp_log_autostart", "1" if self.udp_log_autostart_var.get() else "0")
            if self.udp_log_receiver.running:
                message = "UDP-Einstellungen gespeichert · Änderungen gelten nach UDP stoppen und erneut starten."
            else:
                message = "UDP-Einstellungen gespeichert · UDP bleibt ausgeschaltet."
            self.udp_log_status_label.configure(text=message, fg=theme.OK)
            self.status_var.set("UDP-Einstellungen gespeichert")
        except Exception as exc:
            messagebox.showerror("UDP Logging", str(exc), parent=self)

    def start_udp_log(self, *, show_error: bool = True):
        try:
            config = self._udp_log_config_from_ui()
            for key, value in config.settings().items():
                self.db.set_setting(key, value)
            self.db.set_setting("udp_log_autostart", "1" if self.udp_log_autostart_var.get() else "0")
            self.udp_log_generation += 1
            generation = self.udp_log_generation
            self.udp_log_receiver.start(
                config,
                lambda event: self._queue_udp_log_event(generation, event),
                lambda message: self._queue_udp_log_error(generation, message),
                lambda event: self._queue_udp_status_event(generation, event),
            )
        except Exception as exc:
            self.udp_log_status_label.configure(text="UDP konnte nicht gestartet werden: " + str(exc), fg=theme.ERR)
            self.status_var.set("UDP Logging konnte nicht gestartet werden")
            write_startup_log("UDP Logging konnte nicht gestartet werden: " + repr(exc))
            if show_error:
                messagebox.showerror("UDP Logging", str(exc), parent=self)
            return
        self.udp_log_start_button.configure(state="disabled")
        self.udp_log_stop_button.configure(state="normal")
        self.udp_log_status_label.configure(
            text=f"✓ UDP aktiv auf {config.bind_host}:{config.port} · warte auf QSOs …", fg=theme.OK,
        )
        self.status_var.set(f"UDP Logging aktiv · Port {config.port}")

    def _autostart_udp_log(self):
        if self.closing or self.udp_log_receiver.running:
            return
        if self.db.get_setting("udp_log_autostart", "0") != "1":
            return
        self.start_udp_log(show_error=False)

    def stop_udp_log(self):
        self._stop_udp_log_runtime()
        self.status_var.set("UDP Logging gestoppt")

    def _stop_udp_log_runtime(self, *, update_ui: bool = True):
        self.udp_log_generation += 1
        self.udp_log_receiver.stop()
        if update_ui and hasattr(self, "udp_log_status_label"):
            self.udp_log_status_label.configure(text="UDP-Logging ist ausgeschaltet.", fg=theme.MUTED)
            self.udp_log_live_label.configure(text="WSJT-X Live: kein aktives QSO.", fg=theme.MUTED)
            self.wsjtx_live_badge.configure(text="", bg=theme.CARD, fg=theme.ACCENT)
            self.udp_log_start_button.configure(state="normal")
            self.udp_log_stop_button.configure(state="disabled")

    def _queue_udp_log_event(self, generation: int, event: UdpLogEvent):
        if not self.closing:
            self.after(0, lambda: self._accept_udp_log_event(generation, event))

    def _queue_udp_log_error(self, generation: int, message: str):
        if not self.closing:
            self.after(0, lambda: self._show_udp_log_error(generation, message))

    def _queue_udp_status_event(self, generation: int, event: UdpStatusEvent):
        if not self.closing:
            self.after(0, lambda: self._accept_udp_status_event(generation, event))

    def _show_udp_log_error(self, generation: int, message: str):
        if generation != self.udp_log_generation or self.closing:
            return
        self.udp_log_status_label.configure(text="UDP-Datagramm konnte nicht gelesen werden: " + message, fg=theme.WARN)
        self.status_var.set("UDP-Empfangsfehler")

    def _accept_udp_status_event(self, generation: int, event: UdpStatusEvent):
        """Mirror the selected WSJT-X partner into the normal form without logging it."""
        if generation != self.udp_log_generation or self.closing or not self.udp_log_receiver.running:
            return
        status = event.status
        call = status.dx_call.strip().upper()
        if not lookup_candidate(call):
            previous = self.wsjtx_live_form_call
            self.wsjtx_live_form_call = ""
            self.wsjtx_live_badge.configure(text="", bg=theme.CARD, fg=theme.ACCENT)
            self.udp_log_live_label.configure(text="WSJT-X Live: kein aktives QSO.", fg=theme.MUTED)
            if previous and self.call_var.get().strip().upper() == previous:
                self.clear_qso_form()
            return

        qso_frequency_hz = status.qso_frequency_hz
        frequency = format_frequency_mhz(qso_frequency_hz)
        mode = status.tx_mode or status.mode
        band = band_from_mhz(qso_frequency_hz / 1_000_000) or ""
        state = "TX" if status.transmitting else ("Dekodierung" if status.decoding else "RX")
        self.wsjtx_live_badge.configure(text="● WSJT-X LIVE", bg=theme.ACTIVE_BG, fg=theme.ACCENT)
        self.udp_log_live_label.configure(
            text=(
                f"WSJT-X Live: {call} · {status.dx_grid or 'Locator —'} · "
                f"{band or 'Band —'} · {mode or 'Mode —'} · {state}"
            ),
            fg=theme.ACCENT,
        )

        current_call = self.call_var.get().strip().upper()
        if current_call and current_call not in {call, self.wsjtx_live_form_call}:
            self.udp_log_live_label.configure(
                text=self.udp_log_live_label.cget("text") + " · manuelle Formulareingabe bleibt unverändert",
                fg=theme.WARN,
            )
            return
        if self.wsjtx_live_form_call and self.wsjtx_live_form_call != call and current_call == self.wsjtx_live_form_call:
            self.clear_qso_form()

        changed_call = self.wsjtx_live_form_call != call or current_call != call
        self.wsjtx_live_form_call = call
        self.call_var.set(call)
        if frequency:
            self.freq_var.set(frequency)
        if band:
            self.band_var.set(band)
        if mode:
            self.mode_var.set(mode)
        if status.dx_grid:
            self.form_vars["gridsquare"].set(status.dx_grid)
        if status.report:
            self.rst_sent_var.set(status.report)
        if changed_call:
            self._call_changed()
        else:
            self._update_qso_worked_status()

    def _prepare_external_qso(self, incoming: dict) -> dict:
        qso = dict(incoming)
        call = str(qso.get("call") or "").strip().upper()
        if not call:
            raise ValueError("Empfangenes QSO enthält kein Rufzeichen.")
        qso["call"] = call

        qso_date = str(qso.get("qso_date") or "").strip()
        if len(qso_date) == 8 and qso_date.isdigit():
            qso_date = f"{qso_date[:4]}-{qso_date[4:6]}-{qso_date[6:8]}"
        datetime.strptime(qso_date, "%Y-%m-%d")
        qso["qso_date"] = qso_date

        time_on = "".join(ch for ch in str(qso.get("time_on") or "") if ch.isdigit())
        if len(time_on) == 4:
            time_on += "00"
        if len(time_on) != 6:
            raise ValueError("Empfangenes QSO enthält keine gültige TIME_ON.")
        datetime.strptime(time_on, "%H%M%S")
        qso["time_on"] = time_on

        freq = str(qso.get("freq") or "").strip().replace(",", ".")
        if freq:
            mhz = float(freq)
            if mhz <= 0:
                raise ValueError("Empfangenes QSO enthält keine gültige Frequenz.")
            qso["freq"] = freq
            if not qso.get("band"):
                qso["band"] = band_from_mhz(mhz) or ""
        qso["band"] = str(qso.get("band") or "").strip()
        qso["mode"] = str(qso.get("mode") or "").strip().upper()
        if not qso["mode"]:
            raise ValueError("Empfangenes QSO enthält keinen Modus.")

        profile = self._profile_values()
        defaults = {
            **profile,
            "station_call": profile.get("station_call") or profile.get("operator_call") or "",
            "tx_pwr": self.db.get_setting("default_power", ""),
        }
        for key, value in defaults.items():
            if not str(qso.get(key) or "").strip():
                qso[key] = value
        if not qso.get("station_call"):
            raise ValueError("Weder das empfangene QSO noch das aktive Profil enthält ein Stationsrufzeichen.")

        country = self._country_fields_for_call(call)
        for key, value in country.items():
            if not str(qso.get(key) or "").strip():
                qso[key] = value
        for key in (
            "rst_sent", "rst_rcvd", "gridsquare", "name", "qth", "comment", "notes",
            "pota_ref", "sota_ref", "wwff_ref", "contest_id", "stx", "srx",
            "stx_string", "srx_string", "prop_mode", "qso_date_off", "time_off",
        ):
            qso[key] = str(qso.get(key) or "").strip()
        return qso

    def _accept_udp_log_event(self, generation: int, event: UdpLogEvent):
        if generation != self.udp_log_generation or self.closing or not self.udp_log_receiver.running:
            return
        try:
            qso = self._prepare_external_qso(event.qso)
            duplicate = find_duplicate_qso(self.store.scan(), qso)
            if duplicate is not None:
                if self.call_var.get().strip().upper() == qso["call"]:
                    self.clear_qso_form()
                    self.wsjtx_live_form_call = ""
                    self.wsjtx_live_badge.configure(text="", bg=theme.CARD, fg=theme.ACCENT)
                self.udp_log_last_label.configure(
                    text=f"Duplikat ignoriert: {qso['call']} · {qso['qso_date']} {qso['time_on']} · {event.source}",
                    fg=theme.WARN,
                )
                self.status_var.set(f"UDP-Duplikat ignoriert: {qso['call']}")
                return
            saved = self.store.add(qso)
            self.db.ensure_local(saved["local_id"], qso_hash(saved))
            self._bind_active_xota_qso(saved)
            self._notify_qso_saved(saved)
            self._remember_last_spottable_qso(saved)
            self.udp_log_received += 1
            if self.call_var.get().strip().upper() == saved["call"]:
                self.clear_qso_form()
                self.wsjtx_live_form_call = ""
                self.wsjtx_live_badge.configure(text="", bg=theme.CARD, fg=theme.ACCENT)
            self.refresh_qsos()
            self.udp_log_last_label.configure(
                text=(
                    f"Zuletzt gespeichert: {saved['call']} · {saved.get('band') or '—'} · "
                    f"{saved['mode']} · {event.source}\n"
                    f"Callbook-Ergänzung wird geprüft · in dieser Sitzung: {self.udp_log_received}"
                ),
                fg=theme.OK,
            )
            self.status_var.set(f"UDP-QSO gespeichert: {saved['call']} · LOCAL ONLY")
            self._start_external_qso_enrichment(
                self.active_profile_id, event, saved,
            )
        except Exception as exc:
            self._show_udp_log_error(generation, str(exc))

    def _start_external_qso_enrichment(self, profile_id: str, event: UdpLogEvent, saved: dict):
        source = self._configured_callbook_source()
        auto_lookup = self.db.get_setting("callbook_auto_lookup", "1") == "1"
        needs_lookup = any(
            not str(saved.get(key) or "").strip() for key in ("name", "gridsquare", "qth")
        )
        if source == CALLBOOK_SOURCE_DISABLED or not auto_lookup or not needs_lookup or not lookup_candidate(saved["call"]):
            self._finish_external_qso_enrichment(profile_id, event, saved["local_id"], None, "")
            return

        callsign = saved["call"]
        band = str(saved.get("band") or "")
        mode = str(saved.get("mode") or "")
        local_id = saved["local_id"]
        metadata_db = self.db
        pending_key = (profile_id, local_id)
        self.external_enrichment_pending.add(pending_key)
        if self.auto_sync_job is not None:
            try:
                self.after_cancel(self.auto_sync_job)
            except Exception:
                pass
            self.auto_sync_job = None

        def worker():
            try:
                result = self._lookup_callbook_result(
                    callsign, source, band=band, mode=mode, use_cache=True,
                    metadata_db=metadata_db,
                )
                if not self.closing:
                    self.after(
                        0, lambda current=result: self._finish_external_qso_enrichment(
                            profile_id, event, local_id, current, "",
                        ),
                    )
            except Exception as exc:
                message = str(exc)
                if not self.closing:
                    self.after(
                        0, lambda current_error=message: self._finish_external_qso_enrichment(
                            profile_id, event, local_id, None, current_error,
                        ),
                    )

        threading.Thread(target=worker, name="external-qso-callbook", daemon=True).start()

    def _finish_external_qso_enrichment(
        self, profile_id: str, event: UdpLogEvent, local_id: str,
        result: CallbookResult | None, error: str,
    ):
        self.external_enrichment_pending.discard((profile_id, local_id))
        if self.closing or profile_id != self.active_profile_id:
            return
        current = self.store.find(local_id)
        if current is None:
            return
        filled: tuple[str, ...] = ()
        if result is not None:
            enriched, filled = enrich_qso_from_callbook(current, result)
            if filled:
                current = self.store.update(local_id, enriched)
                self.db.ensure_local(local_id, qso_hash(current))
        if self.last_spottable_qso and self.last_spottable_qso.get("local_id") == local_id:
            self._remember_last_spottable_qso(current)
        source_text = (result.source if result is not None else "").strip()
        if filled:
            enrichment = f"ergänzt über {source_text or 'Callbook'}: {', '.join(filled)}"
        elif error:
            enrichment = "ohne Callbook-Ergänzung"
            write_startup_log(f"Externes QSO {current.get('call', '')}: Callbook nicht verfügbar: {error}")
        else:
            enrichment = "Callbook-Daten bereits vollständig oder Abfrage deaktiviert"
        self.udp_log_last_label.configure(
            text=(
                f"Zuletzt gespeichert: {current['call']} · {current.get('band') or '—'} · "
                f"{current['mode']} · {event.source}\n{enrichment} · "
                f"in dieser Sitzung: {self.udp_log_received}"
            ),
            fg=theme.OK,
        )
        self.status_var.set(f"UDP-QSO gespeichert: {current['call']} · {enrichment}")
        self.refresh_qsos()
        self._local_sync_change()
