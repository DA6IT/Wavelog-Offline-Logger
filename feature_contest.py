from __future__ import annotations

import json
from datetime import datetime, timezone
import tkinter as tk
from tkinter import messagebox, ttk
from dialogs import ContestPresetDialog
from logger_core import (
    BANDS, MODES, band_from_mhz, qso_hash, valid_contest_adif_name,
)
from ui_theme import theme


class ContestFeatureMixin:
    def _contest_presets(self) -> list[dict]:
        try:
            raw = json.loads(self.db.get_setting("contest_presets", "[]") or "[]")
            return [x for x in raw if isinstance(x, dict) and str(x.get("name") or "").strip()]
        except Exception:
            return []

    def _save_contest_presets(self, presets: list[dict]):
        self.db.set_setting("contest_presets", json.dumps(presets, ensure_ascii=False))

    def _contest_session(self) -> dict:
        try:
            value = json.loads(self.db.get_setting("contest_session", "{}") or "{}")
            return value if isinstance(value, dict) else {}
        except Exception:
            return {}

    def _set_contest_session(self, session: dict):
        self.db.set_setting("contest_session", json.dumps(session, ensure_ascii=False))

    def _selected_contest_preset(self) -> dict | None:
        name = self.contest_preset_var.get().strip() if hasattr(self, "contest_preset_var") else ""
        for p in self._contest_presets():
            if p.get("name") == name:
                return p
        return None

    def _contest_operator_values(self) -> list[str]:
        values = {self.db.get_setting("operator_call", "").strip().upper()}
        for q in self.store.scan():
            op = str(q.get("operator_call") or "").strip().upper()
            if op:
                values.add(op)
        values.discard("")
        return sorted(values)

    def _build_contest_page(self):
        p = self._new_page("contest")
        p.columnconfigure(0, weight=3)
        p.columnconfigure(1, weight=2)
        p.rowconfigure(1, weight=1)

        top = self._card(p, row=0, column=0, columnspan=2, sticky="ew", pady=(0, 10))
        ttk.Label(top, text="Contest", style="CardTitle.TLabel").pack(side="left")
        self.contest_preset_var = tk.StringVar()
        self.contest_preset_combo = ttk.Combobox(top, textvariable=self.contest_preset_var, state="readonly", width=30)
        self.contest_preset_combo.pack(side="left", padx=(12, 6))
        self.contest_preset_combo.bind("<<ComboboxSelected>>", lambda e: self._contest_preset_changed())
        ttk.Button(top, text="Neu", style="Secondary.TButton", command=self.new_contest_preset).pack(side="left", padx=3)
        ttk.Button(top, text="Bearbeiten", style="Secondary.TButton", command=self.edit_contest_preset).pack(side="left", padx=3)
        ttk.Button(top, text="Löschen", style="Secondary.TButton", command=self.delete_contest_preset).pack(side="left", padx=3)
        self.contest_session_status = tk.Label(top, text="Keine Session", bg=theme.CARD, fg=theme.MUTED, font=("Segoe UI Semibold", 9))
        self.contest_session_status.pack(side="right")

        left = self._card(p, row=1, column=0, sticky="nsew", padx=(0, 8))
        for c in range(4): left.columnconfigure(c, weight=1)
        ttk.Label(left, text="Contest-QSO", style="CardTitle.TLabel").grid(row=0, column=0, columnspan=4, sticky="w")
        self.contest_call_var = tk.StringVar()
        self.contest_call_entry = ttk.Entry(left, textvariable=self.contest_call_var, style="Call.TEntry")
        self.contest_call_entry.grid(row=1, column=0, columnspan=4, sticky="ew", pady=(7, 10))
        self.contest_call_entry.bind("<KeyRelease>", self._contest_call_changed)
        self.contest_call_entry.bind("<Return>", lambda e: self.save_contest_qso())

        self.contest_freq_var = tk.StringVar()
        self.contest_band_var = tk.StringVar(value="2m")
        self.contest_mode_var = tk.StringVar(value="SSB")
        self.contest_rst_sent_var = tk.StringVar(value="59")
        self.contest_rst_rcvd_var = tk.StringVar(value="59")
        self.contest_serial_sent_var = tk.StringVar(value="001")
        self.contest_serial_rcvd_var = tk.StringVar()
        self.contest_grid_var = tk.StringVar()
        self.contest_exchange_rx_var = tk.StringVar()
        self.contest_operator_var = tk.StringVar()
        self.contest_power_var = tk.StringVar()

        self._field(left, "Frequenz (MHz)", self.contest_freq_var, 2, 0)
        ce = left.grid_slaves(row=3, column=0)[0]; ce.bind("<KeyRelease>", self._contest_freq_changed)
        self._combo(left, "Band", self.contest_band_var, BANDS, 2, 1)
        self._combo(left, "Mode", self.contest_mode_var, MODES, 2, 2)
        self._field(left, "Leistung (W)", self.contest_power_var, 2, 3)
        self._field(left, "RST gesendet", self.contest_rst_sent_var, 4, 0)
        self._field(left, "RST empfangen", self.contest_rst_rcvd_var, 4, 1)
        self._field(left, "Seriennr. gesendet", self.contest_serial_sent_var, 4, 2)
        self._field(left, "Seriennr. empfangen", self.contest_serial_rcvd_var, 4, 3)
        self._field(left, "Grid Square", self.contest_grid_var, 6, 0, span=2)
        self._field(left, "Exchange RX (Text)", self.contest_exchange_rx_var, 6, 2, span=2)

        self.contest_exchange_hint = tk.Label(left, text="", bg=theme.CARD, fg=theme.MUTED, font=("Segoe UI", 9), anchor="w")
        self.contest_exchange_hint.grid(row=8, column=0, columnspan=4, sticky="ew", pady=(10, 0))
        btns = ttk.Frame(left, style="Card.TFrame")
        btns.grid(row=9, column=0, columnspan=4, sticky="ew", pady=(16, 0))
        ttk.Button(btns, text="Contest-QSO loggen", style="Primary.TButton", command=self.save_contest_qso).pack(side="left")
        ttk.Button(btns, text="Felder leeren", style="Secondary.TButton", command=self.clear_contest_form).pack(side="left", padx=8)

        right = self._card(p, row=1, column=1, sticky="nsew", padx=(8, 0))
        right.columnconfigure(0, weight=1)
        ttk.Label(right, text="Contest-Session", style="CardTitle.TLabel").grid(row=0, column=0, sticky="w")
        self.contest_station_label = tk.Label(right, text="Station: —", bg=theme.CARD, fg=theme.TEXT, font=("Segoe UI", 10), anchor="w")
        self.contest_station_label.grid(row=1, column=0, sticky="ew", pady=(8, 2))
        ttk.Label(right, text="Operator", style="Card.TLabel").grid(row=2, column=0, sticky="w", pady=(8, 3))
        self.contest_operator_combo = ttk.Combobox(right, textvariable=self.contest_operator_var, state="normal")
        self.contest_operator_combo.grid(row=3, column=0, sticky="ew")
        self.contest_operator_combo.bind("<<ComboboxSelected>>", lambda e: self._contest_operator_changed())
        self.contest_operator_combo.bind("<FocusOut>", lambda e: self._contest_operator_changed())
        self.contest_session_detail = tk.Label(right, text="", bg=theme.CARD, fg=theme.MUTED, font=("Segoe UI", 9), justify="left", anchor="nw", wraplength=360)
        self.contest_session_detail.grid(row=4, column=0, sticky="ew", pady=(12, 8))
        sbtn = ttk.Frame(right, style="Card.TFrame")
        sbtn.grid(row=5, column=0, sticky="ew")
        self.contest_start_btn = ttk.Button(sbtn, text="Session starten", style="Primary.TButton", command=self.start_contest_session)
        self.contest_start_btn.pack(side="left")
        self.contest_stop_btn = ttk.Button(sbtn, text="Session beenden", style="Secondary.TButton", command=self.stop_contest_session)
        self.contest_stop_btn.pack(side="left", padx=8)

        ttk.Button(right, text="Mit Wavelog abgleichen", style="Secondary.TButton", command=self.sync_now).grid(row=6, column=0, sticky="ew", pady=(10, 0))
        ttk.Separator(right).grid(row=7, column=0, sticky="ew", pady=16)
        ttk.Label(right, text="Letzte Contest-QSOs", style="CardTitle.TLabel").grid(row=8, column=0, sticky="w")
        self.contest_recent = tk.Listbox(right, height=10, font=("Consolas", 9), relief="solid", borderwidth=1)
        self.contest_recent.grid(row=9, column=0, sticky="nsew", pady=(7, 0))
        right.rowconfigure(9, weight=1)

    def _contest_preset_changed(self):
        self.db.set_setting("contest_active_preset", self.contest_preset_var.get())
        self.refresh_contest_page()

    def new_contest_preset(self):
        ContestPresetDialog(self, None, self._save_contest_preset)

    def edit_contest_preset(self):
        preset = self._selected_contest_preset()
        if not preset:
            messagebox.showinfo("Contest", "Bitte zuerst ein Contest-Preset auswählen.", parent=self); return
        ContestPresetDialog(self, preset, self._save_contest_preset)

    def _save_contest_preset(self, old_name: str | None, preset: dict):
        presets = self._contest_presets()
        name = preset["name"].strip()
        for p in presets:
            if p.get("name", "").casefold() == name.casefold() and p.get("name") != old_name:
                raise ValueError("Ein Contest-Preset mit diesem Namen existiert bereits")
        if old_name:
            previous = next((p for p in presets if p.get("name") == old_name), {})
            for key in ("wavelog_session_id", "wavelog_updated_at", "local_qso_ids"):
                if previous.get(key) not in (None, ""):
                    preset[key] = previous[key]
            preset["sync_dirty"] = True
            presets = [preset if p.get("name") == old_name else p for p in presets]
        else:
            preset["sync_dirty"] = True
            preset["sync_enabled"] = True
            presets.append(preset)
        self._save_contest_presets(presets)
        self.contest_preset_var.set(name)
        self.db.set_setting("contest_active_preset", name)
        self.refresh_contest_page()

    def delete_contest_preset(self):
        preset = self._selected_contest_preset()
        if not preset: return
        session = self._contest_session()
        if session.get("running") and session.get("preset_name") == preset.get("name"):
            messagebox.showwarning("Contest", "Dieses Preset wird von der laufenden Session benutzt. Bitte Session zuerst beenden.", parent=self); return
        if not messagebox.askyesno("Contest-Preset löschen", f"Preset '{preset['name']}' wirklich lokal löschen?\n\nQSOs werden nicht gelöscht.", parent=self): return
        presets = [p for p in self._contest_presets() if p.get("name") != preset.get("name")]
        self._save_contest_presets(presets)
        self.contest_preset_var.set(presets[0]["name"] if presets else "")
        self.db.set_setting("contest_active_preset", self.contest_preset_var.get())
        self.refresh_contest_page()

    def start_contest_session(self):
        preset = self._selected_contest_preset()
        if not preset:
            messagebox.showerror("Contest", "Bitte zuerst ein Contest-Preset anlegen/auswählen.", parent=self); return
        if self._contest_session().get("running"):
            messagebox.showinfo("Contest", "Es läuft bereits eine Contest-Session.", parent=self); return
        if not valid_contest_adif_name(preset.get("contest_id")):
            messagebox.showerror("Contest", "Bitte das Preset bearbeiten und einen ADIF-Namen wie DARC-WAG oder DARC-FT4 eintragen. Eine numerische Wavelog-ID ist hier nicht gültig.", parent=self); return
        profile = self._profile_values()
        station = profile.get("station_call") or profile.get("operator_call")
        operator = self.contest_operator_var.get().strip().upper() or profile.get("operator_call")
        if not station or not operator:
            messagebox.showerror("Contest", "Station und Operator müssen gesetzt sein.", parent=self); return
        try:
            start_serial = max(1, int(preset.get("start_serial") or 1))
        except Exception:
            start_serial = 1
        # Continue after the highest serial already linked to this exact
        # Wavelog/local contest session. This removes manual "free number"
        # guessing after switching profiles, PCs or returning online.
        for local_id in preset.get("local_qso_ids") or []:
            qso = self.store.find(str(local_id))
            if preset.get("serial_per_band") and str((qso or {}).get("band") or "") != self.contest_band_var.get():
                continue
            if str(preset.get("serial_scope") or "station") == "operator" and str((qso or {}).get("operator_call") or "").upper() != operator:
                continue
            try:
                used_serial = int(str((qso or {}).get("stx") or "").strip())
            except (TypeError, ValueError):
                continue
            start_serial = max(start_serial, used_serial + 1)
        session = {"running": True, "preset_name": preset["name"], "started_at": datetime.now(timezone.utc).isoformat(),
                   "next_serial": start_serial, "qso_count": 0, "operator": operator}
        self._set_contest_session(session)
        self.db.set_setting("contest_active_preset", preset["name"])
        self.refresh_contest_page()
        self.contest_call_entry.focus_set()

    def stop_contest_session(self):
        session = self._contest_session()
        if not session.get("running"):
            messagebox.showinfo("Contest", "Es läuft keine Contest-Session.", parent=self); return
        count = int(session.get("qso_count") or 0)
        started = str(session.get("started_at") or "")
        session["running"] = False; session["ended_at"] = datetime.now(timezone.utc).isoformat()
        self._set_contest_session(session)
        presets = self._contest_presets()
        for preset in presets:
            if preset.get("name") == session.get("preset_name"):
                preset["time_end"] = session["ended_at"][:19].replace("T", " ")
                preset["sync_dirty"] = True
        self._save_contest_presets(presets)
        self.refresh_contest_page()
        messagebox.showinfo("Contest beendet", f"Contest: {session.get('preset_name','—')}\nQSOs dieser Session: {count}\nStart: {started[:19].replace('T',' ')} UTC", parent=self)

    def _contest_operator_changed(self):
        op = self.contest_operator_var.get().strip().upper()
        self.contest_operator_var.set(op)
        session = self._contest_session()
        if session.get("running") and op:
            session["operator"] = op
            self._set_contest_session(session)
            self.refresh_contest_page()

    def _contest_call_changed(self, _event=None):
        v = self.contest_call_var.get().upper()
        if v != self.contest_call_var.get(): self.contest_call_var.set(v)

    def _contest_freq_changed(self, _event=None):
        try:
            b = band_from_mhz(float(self.contest_freq_var.get().strip().replace(",", ".")))
            if b: self.contest_band_var.set(b)
        except Exception: pass

    def clear_contest_form(self):
        self.contest_call_var.set(""); self.contest_serial_rcvd_var.set(""); self.contest_grid_var.set(""); self.contest_exchange_rx_var.set("")
        self.contest_rst_sent_var.set("59" if self.contest_mode_var.get() in ("SSB","USB","LSB","FM","AM") else "")
        self.contest_rst_rcvd_var.set("59" if self.contest_mode_var.get() in ("SSB","USB","LSB","FM","AM") else "")
        self.contest_call_entry.focus_set()

    def refresh_contest_page(self):
        if not hasattr(self, "contest_preset_combo"): return
        presets = self._contest_presets()
        names = [p["name"] for p in presets]
        self.contest_preset_combo.configure(values=names)
        preferred = self.db.get_setting("contest_active_preset", "")
        if self.contest_preset_var.get() not in names:
            self.contest_preset_var.set(preferred if preferred in names else (names[0] if names else ""))
        preset = self._selected_contest_preset()
        session = self._contest_session()
        profile = self._profile_values()
        station = profile.get("station_call") or profile.get("operator_call") or "—"
        self.contest_station_label.configure(text=f"Station: {station}")
        ops = self._contest_operator_values()
        self.contest_operator_combo.configure(values=ops)
        if session.get("running"):
            self.contest_operator_var.set(str(session.get("operator") or profile.get("operator_call") or "").upper())
        elif self.contest_operator_var.get().strip().upper() not in ops:
            self.contest_operator_var.set(profile.get("operator_call") or (ops[0] if ops else ""))
        self.contest_power_var.set(self.contest_power_var.get() or self.db.get_setting("default_power", ""))

        if preset:
            if not session.get("running"):
                self.contest_freq_var.set(str(preset.get("freq") or ""))
                self.contest_band_var.set(str(preset.get("band") or "2m"))
                self.contest_mode_var.set(str(preset.get("mode") or "SSB"))
                rst=str(preset.get("rst_default") or ("59" if self.contest_mode_var.get() in ("SSB","USB","LSB","FM","AM") else ""))
                self.contest_rst_sent_var.set(rst); self.contest_rst_rcvd_var.set(rst)
            enabled=[]
            if preset.get("use_serial"): enabled.append("Seriennummer")
            if preset.get("use_grid"): enabled.append("Grid")
            if preset.get("use_text"): enabled.append("Text")
            tx = str(preset.get("sent_exchange") or "").strip()
            self.contest_exchange_hint.configure(text=f"{preset.get('contest_id','')} · Exchange: {', '.join(enabled) if enabled else 'keine Zusatzfelder'}" + (f" · TX-Text: {tx}" if tx else ""))
        else:
            self.contest_exchange_hint.configure(text="Noch kein Contest-Preset angelegt")

        running = bool(session.get("running"))
        self.contest_session_status.configure(text=("● Session läuft" if running else "Keine Session"), fg=(theme.OK if running else theme.MUTED))
        self.contest_start_btn.configure(state=("disabled" if running else "normal"))
        self.contest_stop_btn.configure(state=("normal" if running else "disabled"))
        if running:
            serial = int(session.get("next_serial") or 1)
            self.contest_serial_sent_var.set(f"{serial:03d}")
            remote_text = f"Wavelog-Session: {preset.get('wavelog_session_id')}" if preset and preset.get("wavelog_session_id") else "Wavelog-Session: noch lokal"
            sync_status = self.db.get_setting("contest_sync_status", "")
            if sync_status and sync_status != "ok":
                remote_text += "\nContest-API: " + sync_status
            self.contest_session_detail.configure(text=f"{session.get('preset_name')}\nOperator: {session.get('operator','—')}\nNächste Seriennummer: {serial:03d}\nQSOs: {int(session.get('qso_count') or 0)}\n{remote_text}")
        else:
            try: serial=max(1,int((preset or {}).get("start_serial") or 1))
            except Exception: serial=1
            self.contest_serial_sent_var.set(f"{serial:03d}")
            sync_status = self.db.get_setting("contest_sync_status", "")
            remote_text = f"Wavelog-Session: {preset.get('wavelog_session_id')}" if preset and preset.get("wavelog_session_id") else "Noch nicht mit Wavelog verknüpft"
            if sync_status and sync_status != "ok":
                remote_text += "\nContest-API: " + sync_status
            serial_rule = "Seriennummer je Band" if (preset or {}).get("serial_per_band") else ("Seriennummer je Operator" if str((preset or {}).get("serial_scope") or "station") == "operator" else "Seriennummer stationsweit")
            self.contest_session_detail.configure(text=f"Preset auswählen und Session starten.\n{serial_rule}; bereits zugeordnete QSOs bestimmen die nächste freie Nummer.\n" + remote_text)

        self.contest_recent.delete(0, "end")
        contest_id = str((preset or {}).get("contest_id") or "").upper()
        exact_ids = {str(value) for value in ((preset or {}).get("local_qso_ids") or [])}
        if exact_ids:
            recent = [q for q in self.store.scan() if str(q.get("local_id") or "") in exact_ids]
        else:
            recent = [q for q in self.store.scan() if contest_id and str(q.get("contest_id") or "").upper() == contest_id]
        for q in sorted(recent, key=lambda x:(x.get("qso_date",""),x.get("time_on","")), reverse=True)[:12]:
            self.contest_recent.insert("end", f"{q.get('time_on','')[:4]:4}  {q.get('call',''):10}  {q.get('operator_call',''):8}  {q.get('stx','')}/{q.get('srx','')}")

    def save_contest_qso(self):
        session = self._contest_session(); preset = self._selected_contest_preset()
        if not session.get("running"):
            messagebox.showerror("Contest Logging", "Bitte zuerst die Contest-Session starten.", parent=self); return
        if not preset or preset.get("name") != session.get("preset_name"):
            messagebox.showerror("Contest Logging", "Das aktive Preset passt nicht zur laufenden Session.", parent=self); return
        try:
            call = self.contest_call_var.get().strip().upper()
            if not call: raise ValueError("Bitte ein Rufzeichen eingeben")
            freq = self.contest_freq_var.get().strip().replace(",", ".")
            if freq: float(freq)
            txp=self.contest_power_var.get().strip().replace(",", ".")
            if txp: float(txp)
            serial = int(session.get("next_serial") or 1)
            srx = self.contest_serial_rcvd_var.get().strip()
            grid = self.contest_grid_var.get().strip().upper()
            rxtext = self.contest_exchange_rx_var.get().strip()
            if preset.get("use_serial") and (not srx or not srx.isdigit()): raise ValueError("Bitte die empfangene Seriennummer eingeben")
            if preset.get("use_grid") and not grid: raise ValueError("Bitte das empfangene Grid Square eingeben")
            if preset.get("use_text") and not rxtext: raise ValueError("Bitte den empfangenen Text-Exchange eingeben")
            profile=self._profile_values(); station=profile.get("station_call") or profile.get("operator_call")
            now=datetime.now(timezone.utc)
            q={"call":call, **self._country_fields_for_call(call), "band":self.contest_band_var.get(), "mode":self.contest_mode_var.get(),
               "freq":freq, "qso_date":now.strftime("%Y-%m-%d"), "time_on":now.strftime("%H%M%S"),
               "rst_sent":self.contest_rst_sent_var.get().strip(), "rst_rcvd":self.contest_rst_rcvd_var.get().strip(),
               "gridsquare":grid if preset.get("use_grid") else "", "name":"", "qth":"", "pota_ref":"", "sota_ref":"", "wwff_ref":"",
               "comment":"", "notes":"", "tx_pwr":txp, **profile,
               "operator_call":str(session.get("operator") or profile.get("operator_call") or "").upper(), "station_call":station,
               "contest_id":str(preset.get("contest_id") or "").upper(),
               "stx":str(serial) if preset.get("use_serial") else "", "srx":str(int(srx)) if preset.get("use_serial") else "",
               "stx_string":str(preset.get("sent_exchange") or "") if preset.get("use_text") else "",
               "srx_string":rxtext if preset.get("use_text") else ""}
            if not q["contest_id"]: raise ValueError("Im Contest-Preset fehlt die ADIF Contest-ID")
            if not valid_contest_adif_name(q["contest_id"]): raise ValueError("Der Contest benötigt einen ADIF-Namen wie DARC-WAG oder DARC-FT4 – keine numerische Wavelog-ID")
            q=self.store.add(q); self.db.ensure_local(q["local_id"],qso_hash(q)); self._bind_active_xota_qso(q)
            presets = self._contest_presets()
            for item in presets:
                if item.get("name") == preset.get("name"):
                    local_ids = list(item.get("local_qso_ids") or [])
                    if q["local_id"] not in local_ids:
                        local_ids.append(q["local_id"])
                    item["local_qso_ids"] = local_ids
            self._save_contest_presets(presets)
            self._notify_qso_saved(q)
            if preset.get("use_serial"): session["next_serial"]=serial+1
            session["qso_count"]=int(session.get("qso_count") or 0)+1
            self._set_contest_session(session)
            self.status_var.set(f"Contest-QSO #{serial:03d}: {call} gespeichert")
            self.refresh_qsos(); self.refresh_contest_page(); self.clear_contest_form()
            self._local_sync_change()
        except Exception as e:
            messagebox.showerror("Contest-QSO konnte nicht gespeichert werden", str(e), parent=self)
