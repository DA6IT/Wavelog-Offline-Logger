from __future__ import annotations

import threading
import urllib.error
import urllib.parse
import urllib.request
import tkinter as tk
from tkinter import messagebox, simpledialog, ttk
from xota import (
    GPSService, WavelogStationService, XOTA_PROGRAMS, maidenhead_locator, merge_candidate_references,
)


class XotaFeatureMixin:
    def _build_xota_page(self):
        p = self._new_page("xota")
        p.columnconfigure(0, weight=3); p.columnconfigure(1, weight=2)
        p.rowconfigure(1, weight=1)

        status = self._card(p, row=0, column=0, columnspan=2, sticky="ew", pady=(0, 10))
        status.columnconfigure(0, weight=1)
        self.xota_status_label = ttk.Label(status, text="Keine Aktivierung aktiv", style="CardTitle.TLabel")
        self.xota_status_label.grid(row=0, column=0, sticky="w")
        self.xota_status_detail = ttk.Label(status, text="", style="Muted.Card.TLabel")
        self.xota_status_detail.grid(row=1, column=0, sticky="w", pady=(3, 0))
        self.xota_wavelog_button = ttk.Button(
            status, text="Mit Wavelog verbinden & synchronisieren", style="Secondary.TButton",
            command=self._xota_assign_station,
        )
        self.xota_wavelog_button.grid(row=0, column=1, rowspan=2, padx=6)
        self.xota_finish_button = ttk.Button(
            status, text="Aktivierung beenden", style="Secondary.TButton", command=self._xota_finish,
        )
        self.xota_finish_button.grid(row=0, column=2, rowspan=2)

        form = self._card(p, row=1, column=0, sticky="nsew", padx=(0, 8))
        for c in range(4): form.columnconfigure(c, weight=1)
        ttk.Label(form, text="Neue xOTA-Aktivierung", style="CardTitle.TLabel").grid(row=0, column=0, columnspan=4, sticky="w")
        ttk.Label(form, text="GPS, Internet und Referenzdienste sind optional. Alle Werte bleiben editierbar.",
                  style="Muted.Card.TLabel").grid(row=1, column=0, columnspan=4, sticky="w", pady=(2, 8))
        self.xota_vars = {name: tk.StringVar() for name in (
            "callsign","latitude","longitude","accuracy","locator","city","state","country",
            "dxcc","cq","itu","power","note","POTA","SOTA","WWFF","IOTA","COTA","WCA",
        )}
        fields = (
            ("Callsign", "callsign"), ("Breitengrad", "latitude"), ("Längengrad", "longitude"), ("Locator", "locator"),
            ("Ort / QTH", "city"), ("Bundesland / State", "state"), ("Land", "country"), ("Leistung (W)", "power"),
            ("DXCC", "dxcc"), ("CQ-Zone", "cq"), ("ITU-Zone", "itu"), ("GPS-Genauigkeit (m)", "accuracy"),
        )
        for index, (label, key) in enumerate(fields):
            row = 2 + (index // 4) * 2; col = index % 4
            ttk.Label(form, text=label, style="Card.TLabel").grid(row=row, column=col, sticky="w", padx=(0, 8))
            ttk.Entry(form, textvariable=self.xota_vars[key]).grid(row=row+1, column=col, sticky="ew", padx=(0, 8), pady=(2, 7))
        ref_row = 8
        ttk.Label(form, text="Bestätigte Referenzen (mehrere mit Komma)", style="CardTitle.TLabel").grid(row=ref_row, column=0, columnspan=4, sticky="w", pady=(6, 4))
        for index, key in enumerate(XOTA_PROGRAMS):
            row = ref_row + 1 + (index // 3) * 2; col = index % 3
            ttk.Label(form, text=key, style="Card.TLabel").grid(row=row, column=col, sticky="w", padx=(0, 8))
            ttk.Entry(form, textvariable=self.xota_vars[key]).grid(row=row+1, column=col, sticky="ew", padx=(0, 8), pady=(2, 7))
        note_row = ref_row + 5
        ttk.Label(form, text="Notiz", style="Card.TLabel").grid(row=note_row, column=0, sticky="w")
        ttk.Entry(form, textvariable=self.xota_vars["note"]).grid(row=note_row+1, column=0, columnspan=4, sticky="ew", pady=(2, 8))
        controls = ttk.Frame(form, style="Card.TFrame"); controls.grid(row=note_row+2, column=0, columnspan=4, sticky="ew")
        for column in range(4):
            controls.columnconfigure(column, weight=1, uniform="xota-form-actions")
        self.xota_gps_button = ttk.Button(controls, text="Aktuellen Standort verwenden", style="Secondary.TButton", command=self._xota_use_gps)
        self.xota_geocode_button = ttk.Button(controls, text="Standortdaten online ergänzen", style="Secondary.TButton", command=self._xota_reverse_geocode)
        self.xota_find_button = ttk.Button(controls, text="Mögliche Referenzen suchen", style="Secondary.TButton", command=self._xota_find_references)
        self.xota_start_button = ttk.Button(controls, text="Aktivierung starten", style="Primary.TButton", command=self._xota_start)
        for column, button in enumerate((self.xota_gps_button, self.xota_geocode_button, self.xota_find_button, self.xota_start_button)):
            button.grid(row=0, column=column, sticky="ew", padx=(0 if column == 0 else 3, 0 if column == 3 else 3))

        right = self._card(p, row=1, column=1, sticky="nsew")
        right.columnconfigure(0, weight=1); right.rowconfigure(1, weight=1); right.rowconfigure(4, weight=1)
        self.xota_candidate_title = ttk.Label(right, text="Mögliche Referenzen · Mehrfachauswahl mit Strg/Shift", style="CardTitle.TLabel")
        self.xota_candidate_title.grid(row=0, column=0, sticky="w")
        self.xota_candidate_tree = ttk.Treeview(
            right, columns=("program","ref","name","distance","status"),
            show="headings", height=8, selectmode="extended",
        )
        for key, title, width in (("program","Programm",75),("ref","Referenz",95),("name","Name",180),("distance","Distanz",75),("status","Hinweis",155)):
            self.xota_candidate_tree.heading(key, text=title); self.xota_candidate_tree.column(key, width=width, minwidth=35, stretch=False)
        self.xota_candidate_tree.grid(row=1, column=0, sticky="nsew", pady=(6, 5))
        self.xota_candidate_tree.bind("<Configure>", self._xota_resize_candidate_columns, add="+")
        self.xota_candidates = []
        buttons = ttk.Frame(right, style="Card.TFrame"); buttons.grid(row=2, column=0, sticky="ew")
        for column in range(3):
            buttons.columnconfigure(column, weight=1, uniform="xota-reference-actions")
        self.xota_accept_button = ttk.Button(buttons, text="Ausgewählte Treffer übernehmen", style="Secondary.TButton", command=self._xota_accept_candidate)
        self.xota_map_button = ttk.Button(buttons, text="POTA-Grenze prüfen", style="Secondary.TButton", command=self._xota_open_pota_map)
        self.xota_update_button = ttk.Button(buttons, text="Referenzdaten aktualisieren", style="Secondary.TButton", command=self._xota_update_references)
        for column, button in enumerate((self.xota_accept_button, self.xota_map_button, self.xota_update_button)):
            button.grid(row=0, column=column, sticky="ew", padx=(0 if column == 0 else 3, 0 if column == 2 else 3))
        self.xota_provider_label = ttk.Label(right, text="", style="Muted.Card.TLabel", wraplength=520)
        self.xota_provider_label.grid(row=3, column=0, sticky="ew", pady=(8, 5))
        ttk.Label(right, text="Letzte Aktivierungen", style="CardTitle.TLabel").grid(row=4, column=0, sticky="nw", pady=(8, 0))
        self.xota_history = ttk.Treeview(right, columns=("start","call","refs","qsos","state"), show="headings", height=7)
        for key, title, width in (("start","Start",120),("call","Call",85),("refs","Referenzen",190),("qsos","QSOs",45),("state","Status",65)):
            self.xota_history.heading(key, text=title); self.xota_history.column(key, width=width, minwidth=32, stretch=False)
        self.xota_history.grid(row=5, column=0, sticky="nsew", pady=(5, 5))
        self.xota_history.bind("<Configure>", self._xota_resize_history_columns, add="+")
        self.xota_repeat_button = ttk.Button(right, text="Ausgewählte Aktivierung wiederholen", style="Secondary.TButton", command=self._xota_repeat)
        self.xota_repeat_button.grid(row=6, column=0, sticky="e")
        for key in ("latitude", "longitude"):
            self.xota_vars[key].trace_add("write", lambda *_args: self._xota_coordinates_changed())
        self.refresh_xota_page()

    def _xota_resize_candidate_columns(self, event=None):
        width = max(320, int(getattr(event, "width", self.xota_candidate_tree.winfo_width())) - 4)
        ratios = {"program": 0.13, "ref": 0.17, "name": 0.31, "distance": 0.16, "status": 0.23}
        for key, ratio in ratios.items():
            self.xota_candidate_tree.column(key, width=max(42, int(width * ratio)), stretch=False)

    def _xota_resize_history_columns(self, event=None):
        width = max(320, int(getattr(event, "width", self.xota_history.winfo_width())) - 4)
        ratios = {"start": 0.24, "call": 0.17, "refs": 0.37, "qsos": 0.10, "state": 0.12}
        for key, ratio in ratios.items():
            self.xota_history.column(key, width=max(32, int(width * ratio)), stretch=False)

    def _apply_xota_responsive_layout(self):
        if not hasattr(self, "xota_gps_button"):
            return
        compact = self.winfo_width() < 1220
        full = {
            self.xota_wavelog_button: "Mit Wavelog verbinden & synchronisieren",
            self.xota_finish_button: "Aktivierung beenden",
            self.xota_gps_button: "Aktuellen Standort verwenden",
            self.xota_geocode_button: "Standortdaten online ergänzen",
            self.xota_find_button: "Mögliche Referenzen suchen",
            self.xota_start_button: "Aktivierung starten",
            self.xota_accept_button: "Ausgewählte Treffer übernehmen",
            self.xota_map_button: "POTA-Grenze prüfen",
            self.xota_update_button: "Referenzdaten aktualisieren",
            self.xota_repeat_button: "Ausgewählte Aktivierung wiederholen",
        }
        short = {
            self.xota_wavelog_button: "Wavelog verbinden",
            self.xota_finish_button: "Beenden",
            self.xota_gps_button: "GPS übernehmen",
            self.xota_geocode_button: "Standort ergänzen",
            self.xota_find_button: "Referenzen suchen",
            self.xota_start_button: "Starten",
            self.xota_accept_button: "Treffer übernehmen",
            self.xota_map_button: "POTA-Map",
            self.xota_update_button: "Daten aktualisieren",
            self.xota_repeat_button: "Aktivierung wiederholen",
        }
        labels = short if compact else full
        for button, label in labels.items():
            button.configure(text=self._tr(label))
        title = "Mögliche Referenzen · Strg/Shift" if compact else "Mögliche Referenzen · Mehrfachauswahl mit Strg/Shift"
        self.xota_candidate_title.configure(text=self._tr(title))

    def _xota_coordinates(self):
        return float(self.xota_vars["latitude"].get().replace(",", ".")), float(self.xota_vars["longitude"].get().replace(",", "."))

    def _xota_coordinates_changed(self):
        try:
            lat, lon = self._xota_coordinates()
            self.xota_vars["locator"].set(maidenhead_locator(lat, lon, 6))
        except (ValueError, tk.TclError):
            pass

    def _xota_use_gps(self):
        self.status_var.set("Betriebssystem-Standort wird abgefragt …")
        def worker():
            try: result, error = GPSService.current_position(), ""
            except Exception as exc: result, error = None, str(exc)
            self.after(0, lambda: self._xota_gps_finished(result, error))
        threading.Thread(target=worker, name="xota-gps", daemon=True).start()

    def _xota_gps_finished(self, fix, error):
        if error:
            messagebox.showwarning("xOTA GPS", error + "\n\nKoordinaten können weiterhin manuell eingetragen werden.", parent=self); return
        self.xota_vars["latitude"].set(f"{fix.latitude:.6f}"); self.xota_vars["longitude"].set(f"{fix.longitude:.6f}")
        self.xota_vars["accuracy"].set("" if fix.accuracy is None else f"{fix.accuracy:.0f}")
        self.status_var.set(f"GPS übernommen · {maidenhead_locator(fix.latitude, fix.longitude)} · offline berechnet")

    def _xota_reverse_geocode(self):
        try: lat, lon = self._xota_coordinates()
        except ValueError: messagebox.showerror("xOTA", "Bitte gültige Koordinaten eintragen.", parent=self); return
        self.status_var.set("Standortdaten werden online ergänzt …")
        def worker():
            try: result, error = self.xota_geocoder.reverse(lat, lon), ""
            except Exception as exc: result, error = {}, str(exc)
            self.after(0, lambda: self._xota_geocode_finished(result, error))
        threading.Thread(target=worker, name="xota-geocode", daemon=True).start()

    def _xota_geocode_finished(self, result, error):
        if error: messagebox.showwarning("xOTA Standortdaten", "Online-Abfrage fehlgeschlagen: " + error + "\nDie Aktivierung kann trotzdem gestartet werden.", parent=self); return
        for key in ("city","state","country"):
            if result.get(key): self.xota_vars[key].set(result[key])
        self.status_var.set("Standortdaten ergänzt · © OpenStreetMap contributors")

    def _xota_find_references(self):
        try: lat, lon = self._xota_coordinates()
        except ValueError: messagebox.showerror("xOTA", "Bitte gültige Koordinaten eintragen.", parent=self); return
        self.status_var.set("Lokale und verfügbare Online-Referenzen werden gesucht …")
        def worker():
            try: result, error = self.xota_references.find_nearby(lat, lon, refresh_pota=True), ""
            except Exception as exc: result, error = [], str(exc)
            self.after(0, lambda: self._xota_references_finished(result, error))
        threading.Thread(target=worker, name="xota-reference-search", daemon=True).start()

    def _xota_references_finished(self, result, error):
        self.xota_candidates = list(result); self.xota_candidate_tree.delete(*self.xota_candidate_tree.get_children())
        for index, item in enumerate(self.xota_candidates):
            status = item.warning or ("möglicher Treffer" if item.eligible else "außerhalb Radius")
            self.xota_candidate_tree.insert("", "end", iid=str(index), values=(item.program,item.reference,item.name,f"{item.distance_m:.0f} m",status))
        self.xota_provider_label.configure(text=(error or f"{len(result)} mögliche Treffer im Umkreis. POTA nutzt den lokalen Gesamtkatalog; Parkgrenzen bitte mit ‚POTA-Grenze prüfen‘ kontrollieren."))
        self.status_var.set(f"xOTA: {len(result)} mögliche Referenz(en) gefunden")

    def _xota_open_pota_map(self):
        reference = ""
        selected = self.xota_candidate_tree.selection()
        if selected:
            candidate = self.xota_candidates[int(selected[0])]
            if candidate.program == "POTA" or candidate.references.get("POTA"):
                reference = (candidate.references.get("POTA") or [candidate.reference])[0]
        url = "https://pota-map.info/"
        if reference:
            url += "?p=" + urllib.parse.quote(reference, safe="-")
        self._open_external_url(url, "POTA-Map")

    def _xota_accept_candidate(self):
        selected = self.xota_candidate_tree.selection()
        if not selected:
            return
        candidates = [self.xota_candidates[int(item_id)] for item_id in sorted(selected, key=int)]
        warnings = [candidate for candidate in candidates if candidate.warning]
        if warnings:
            references = ", ".join(candidate.reference for candidate in warnings)
            message = (
                f"Die Grenzen der ausgewählten Referenzen ({references}) wurden nicht automatisch "
                "nachgewiesen. Katalogkoordinaten sind nur Näherungspunkte.\n\n"
                "Alle ausgewählten Referenzen trotzdem bewusst übernehmen?"
            )
            if not messagebox.askyesno("Referenzen übernehmen", message, parent=self):
                return
        current = {program: self.xota_vars[program].get() for program in XOTA_PROGRAMS}
        merged = merge_candidate_references(candidates, current)
        for program, references in merged.items():
            self.xota_vars[program].set(", ".join(references))
        self.status_var.set(f"xOTA: {len(candidates)} ausgewählte Referenz(en) übernommen")

    def _xota_update_references(self):
        try: lat, lon = self._xota_coordinates()
        except ValueError: lat = lon = None
        self.status_var.set("xOTA-Referenzdaten werden aktualisiert …")
        def worker():
            result = self.xota_references.update_all(lat, lon)
            self.after(0, lambda: self._xota_update_finished(result))
        threading.Thread(target=worker, name="xota-reference-update", daemon=True).start()

    def _xota_update_finished(self, result):
        text = " · ".join(f"{name}: {value}" for name, value in result.items())
        self.xota_provider_label.configure(text=text); self.status_var.set("xOTA-Referenzdaten aktualisiert")

    def _xota_activation_from_form(self):
        callsign = self.xota_vars["callsign"].get().strip().upper()
        if not callsign: raise ValueError("Bitte das Aktivierungsrufzeichen eingeben")
        lat_text, lon_text = self.xota_vars["latitude"].get().strip(), self.xota_vars["longitude"].get().strip()
        lat = float(lat_text.replace(",", ".")) if lat_text else None; lon = float(lon_text.replace(",", ".")) if lon_text else None
        if (lat is None) != (lon is None): raise ValueError("Breiten- und Längengrad bitte gemeinsam angeben")
        locator = self.xota_vars["locator"].get().strip().upper()
        if not locator and lat is not None: locator = maidenhead_locator(lat, lon)
        refs = {program: self.xota_vars[program].get() for program in XOTA_PROGRAMS}
        return self.xota_repository.create(
            self.active_profile_id, callsign, latitude=lat, longitude=lon,
            gps_accuracy=float(self.xota_vars["accuracy"].get().replace(",", ".")) if self.xota_vars["accuracy"].get().strip() else None,
            gridsquare=locator, city=self.xota_vars["city"].get().strip(), state=self.xota_vars["state"].get().strip(),
            country=self.xota_vars["country"].get().strip(), dxcc=self.xota_vars["dxcc"].get().strip(),
            cq_zone=self.xota_vars["cq"].get().strip(), itu_zone=self.xota_vars["itu"].get().strip(),
            references=refs, power=self.xota_vars["power"].get().strip(), note=self.xota_vars["note"].get().strip(),
        )

    def _xota_start(self):
        try:
            activation = self._xota_activation_from_form(); self.xota_repository.start(activation.uuid)
            self.form_vars["tx_pwr"].set(activation.power or self.form_vars["tx_pwr"].get())
            self.refresh_xota_page(); self._update_profile_summary(); self.status_var.set(f"xOTA aktiv: {activation.callsign} · QSOs bleiben zuerst lokal")
        except Exception as exc: messagebox.showerror("xOTA-Aktivierung", str(exc), parent=self)

    def _xota_finish(self):
        activation = self.xota_repository.active()
        if not activation: messagebox.showinfo("xOTA", "Es läuft keine Aktivierung.", parent=self); return
        if messagebox.askyesno("xOTA beenden", f"Aktivierung {activation.callsign} mit {self.xota_repository.qso_count(activation.uuid)} QSO(s) beenden?", parent=self):
            self.xota_repository.finish(activation.uuid); self.refresh_xota_page(); self._update_profile_summary()

    def _xota_repeat(self):
        selected = self.xota_history.selection()
        if not selected: return
        activation = self.xota_repository.get(selected[0])
        if not activation: return
        values = {"callsign":activation.callsign,"latitude":"" if activation.latitude is None else str(activation.latitude),"longitude":"" if activation.longitude is None else str(activation.longitude),
                  "accuracy":"" if activation.gps_accuracy is None else str(activation.gps_accuracy),"locator":activation.gridsquare,"city":activation.city,"state":activation.state,
                  "country":activation.country,"dxcc":activation.dxcc,"cq":activation.cq_zone,"itu":activation.itu_zone,"power":activation.power,"note":activation.note}
        for key, value in values.items(): self.xota_vars[key].set(value)
        for program, refs in activation.references.items(): self.xota_vars[program].set(", ".join(refs))

    def refresh_xota_page(self):
        if not hasattr(self, "xota_history"): return
        active = self.xota_repository.active()
        if active:
            refs = [f"{p} {'/'.join(v)}" for p, v in active.references.items() if v]
            station = f"Wavelog Station {active.wavelog_station_id}" if active.wavelog_station_id else "noch keiner Wavelog Station zugeordnet"
            self.xota_status_label.configure(text=f"● AKTIV · {active.callsign} · {active.gridsquare or 'ohne Locator'}")
            self.xota_status_detail.configure(text=f"{self.xota_repository.qso_count(active.uuid)} QSO(s) · {' · '.join(refs) or 'manuelle Aktivierung ohne Referenz'} · {station}")
        else:
            self.xota_status_label.configure(text="Keine xOTA-Aktivierung aktiv"); self.xota_status_detail.configure(text="Offline-Logging ist jederzeit möglich.")
        self.xota_history.delete(*self.xota_history.get_children())
        for item in self.xota_repository.list(50):
            refs = " · ".join(f"{p} {'/'.join(v)}" for p, v in item.references.items() if v)
            self.xota_history.insert("", "end", iid=item.uuid, values=(item.started_at[:16].replace("T"," "),item.callsign,refs,self.xota_repository.qso_count(item.uuid),item.status))

    def _xota_assign_station(self):
        activation = self.xota_repository.active()
        if not activation:
            selected = self.xota_history.selection(); activation = self.xota_repository.get(selected[0]) if selected else None
        if not activation: messagebox.showinfo("xOTA", "Bitte eine aktive oder gespeicherte Aktivierung auswählen.", parent=self); return
        try:
            client = self._client_from_settings(); stations = client.stations(); service = WavelogStationService(client)
            current = next((s for s in stations if int(s.get("id") or 0) == int(activation.wavelog_station_id or 0)), None)
            match = current or service.confident_match(activation, stations)
            if match:
                if not messagebox.askyesno("Wavelog Station Location", f"Vorhandene Location verwenden?\n\n{match.get('name','')} · ID {match.get('id')}", parent=self): return
            else:
                candidates = service.candidates(activation, stations)[:8]
                if candidates:
                    lines = [f"{i+1}: ID {row[2].get('id')} · {row[2].get('name','')} · Treffer {row[0]}" for i, row in enumerate(candidates)]
                    choice = simpledialog.askinteger("Wavelog Location auswählen", "0 = neue Location erstellen\n\n" + "\n".join(lines), minvalue=0, maxvalue=len(lines), parent=self)
                    if choice is None: return
                    match = candidates[choice-1][2] if choice else None
                if not match:
                    if not all((activation.dxcc, activation.cq_zone, activation.itu_zone)):
                        raise ValueError("Zum Erstellen benötigt Wavelog DXCC, CQ- und ITU-Zone. Bitte die Werte ergänzen.")
                    name = simpledialog.askstring("Wavelog Location erstellen", "Name der neuen Station Location:", initialvalue=" · ".join([activation.callsign] + [refs[0] for refs in activation.references.values() if refs])[:80], parent=self)
                    if not name: return
                    if not messagebox.askyesno("Station Location erstellen", f"Neue Wavelog Station Location wirklich erstellen?\n\n{name}", parent=self): return
                    match = service.create(activation, name)
            station_id = int(match.get("id")); self.xota_repository.set_wavelog_station(activation.uuid, station_id, str(match.get("uuid") or ""))
            self.refresh_xota_page(); self.status_var.set(f"xOTA ist Wavelog Station {station_id} zugeordnet"); self.sync_now()
        except Exception as exc: messagebox.showerror("xOTA / Wavelog", str(exc), parent=self)
