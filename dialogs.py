from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any

import tkinter as tk
from tkinter import messagebox, simpledialog, ttk

from logger_core import BANDS, MODES, valid_contest_adif_name
from ui_theme import theme


def configure_responsive_dialog(
    dialog: tk.Toplevel,
    preferred: tuple[int, int],
    minimum: tuple[int, int],
) -> None:
    """Fit a dialog to the usable screen and keep its content resizable."""
    screen_width = max(360, dialog.winfo_screenwidth() - 80)
    screen_height = max(300, dialog.winfo_screenheight() - 100)
    width = min(preferred[0], screen_width)
    height = min(preferred[1], screen_height)
    min_width = min(minimum[0], width)
    min_height = min(minimum[1], height)
    dialog.geometry(f"{width}x{height}")
    dialog.minsize(min_width, min_height)
    dialog.resizable(True, True)


class SyncProgressDialog(tk.Toplevel):
    """Modal progress/status window for automatic start and shutdown syncs."""

    def __init__(self, parent: Any, reason: str, status_text: str):
        super().__init__(parent)
        self.parent = parent
        self.reason = reason
        self.title(parent._tr("Wavelog-Synchronisierung"))
        configure_responsive_dialog(self, (640, 330), (460, 260))
        self.transient(parent)
        self.configure(bg=theme.CARD)
        self.protocol("WM_DELETE_WINDOW", lambda: None)

        body = tk.Frame(self, bg=theme.CARD, padx=28, pady=24)
        body.pack(fill="both", expand=True)
        self.heading = tk.Label(
            body, text=parent._tr("Wavelog wird synchronisiert"), bg=theme.CARD, fg=theme.TEXT,
            font=("Segoe UI Semibold", 17), anchor="w",
        )
        self.heading.pack(fill="x")
        self.explanation = tk.Label(
            body, text="", bg=theme.CARD, fg=theme.MUTED, font=("Segoe UI", 10),
            justify="left", anchor="w", wraplength=570,
        )
        self.explanation.pack(fill="x", pady=(8, 16))
        self.progress = ttk.Progressbar(body, mode="indeterminate", length=570)
        self.progress.pack(fill="x")
        self.progress.start(12)
        self.status_label = tk.Label(
            body, text=parent._tr(status_text), bg=theme.CARD, fg=theme.TEXT, font=("Segoe UI", 10),
            justify="left", anchor="nw", wraplength=570,
        )
        self.status_label.pack(fill="both", expand=True, pady=(16, 12))
        self.ok_button = ttk.Button(
            body, text="OK", style="Primary.TButton", state="disabled",
            command=parent._sync_progress_acknowledged,
        )
        self.ok_button.pack(anchor="e")
        self.set_running(reason, status_text)
        self.update_idletasks()
        x = parent.winfo_rootx() + max(0, (parent.winfo_width() - self.winfo_width()) // 2)
        y = parent.winfo_rooty() + max(0, (parent.winfo_height() - self.winfo_height()) // 2)
        self.geometry(f"+{x}+{y}")
        self.grab_set()
        self.lift()

    def set_running(self, reason: str, status_text: str):
        self.reason = reason
        explanation = (
            "Vor der Bedienung wird das aktive Profil vollständig mit Wavelog abgeglichen."
            if reason == "startup"
            else "Vor dem Beenden wird das aktive Profil vollständig mit Wavelog abgeglichen."
        )
        self.heading.configure(text=self.parent._tr("Wavelog wird synchronisiert"), fg=theme.TEXT)
        self.explanation.configure(text=self.parent._tr(explanation))
        self.status_label.configure(text=self.parent._tr(status_text), fg=theme.TEXT)
        self.ok_button.configure(state="disabled")
        self.progress.configure(mode="indeterminate")
        self.progress.start(12)

    def complete(self, success: bool, details: str):
        self.progress.stop()
        self.progress.configure(mode="determinate", maximum=1, value=1)
        heading = "Synchronisierung abgeschlossen" if success else "Synchronisierung fehlgeschlagen"
        suffix = (
            "Die App wird nach OK geschlossen."
            if self.reason == "shutdown"
            else "Nach OK kann die App verwendet werden."
        )
        self.heading.configure(text=self.parent._tr(heading), fg=(theme.OK if success else theme.ERR))
        self.explanation.configure(text=self.parent._tr(suffix))
        self.status_label.configure(text=self.parent._tr(details), fg=(theme.TEXT if success else theme.ERR))
        self.ok_button.configure(state="normal")
        self.ok_button.focus_set()


class ContestPresetDialog(tk.Toplevel):
    def __init__(self, app: Any, preset: dict | None, callback):
        super().__init__(app)
        self.app=app; self.callback=callback; self.old_name=(preset or {}).get("name")
        self.title("Contest-Preset")
        configure_responsive_dialog(self, (720, 540), (500, 420)); self.transient(app); self.grab_set(); self.configure(bg=theme.BG)
        box=tk.Frame(self,bg=theme.CARD,highlightbackground=theme.BORDER,highlightthickness=1); box.pack(fill="both",expand=True,padx=18,pady=18)
        inner=ttk.Frame(box,style="Card.TFrame",padding=18); inner.pack(fill="both",expand=True); inner.columnconfigure(0,weight=1)
        p=preset or {}
        self.name=tk.StringVar(value=str(p.get("name") or "")); self.cid=tk.StringVar(value=str(p.get("contest_id") or ""))
        self.serial=tk.BooleanVar(value=bool(p.get("use_serial",True))); self.grid=tk.BooleanVar(value=bool(p.get("use_grid",False))); self.text=tk.BooleanVar(value=bool(p.get("use_text",False)))
        self.sent=tk.StringVar(value=str(p.get("sent_exchange") or "")); self.start=tk.StringVar(value=str(p.get("start_serial") or "1"))
        self.freq=tk.StringVar(value=str(p.get("freq") or "")); self.band=tk.StringVar(value=str(p.get("band") or "2m")); self.mode=tk.StringVar(value=str(p.get("mode") or "SSB")); self.rst=tk.StringVar(value=str(p.get("rst_default") or "59"))
        now=datetime.now(timezone.utc).replace(microsecond=0)
        self.time_start=tk.StringVar(value=str(p.get("time_start") or now.strftime("%Y-%m-%d %H:%M:%S")))
        self.time_end=tk.StringVar(value=str(p.get("time_end") or (now+timedelta(hours=24)).strftime("%Y-%m-%d %H:%M:%S")))
        self.comment=tk.StringVar(value=str(p.get("comment") or ""))
        try:
            catalog=json.loads(app.db.get_setting("contest_catalog", "[]") or "[]")
        except Exception:
            catalog=[]
        self.catalog_names=[]
        for row in catalog if isinstance(catalog,list) else []:
            code=str(row.get("adif_name") or row.get("contest") or row.get("name") or "").strip().upper()
            if code and code not in self.catalog_names:
                self.catalog_names.append(code)
        ttk.Label(inner,text="Contest-Preset",style="CardTitle.TLabel").grid(row=0,column=0,sticky="w",pady=(0,8))
        form=ttk.Frame(inner,style="Card.TFrame"); form.grid(row=1,column=0,sticky="nsew"); inner.rowconfigure(1,weight=1)
        for column in range(3): form.columnconfigure(column,weight=1,uniform="contest-form")

        def stacked(parent,label,var,row,column,span=1,combo_values=None):
            cell=ttk.Frame(parent,style="Card.TFrame"); cell.grid(row=row,column=column,columnspan=span,sticky="nsew",padx=(0 if column==0 else 5,5 if column+span<3 else 0),pady=3)
            cell.columnconfigure(0,weight=1)
            ttk.Label(cell,text=label,style="Card.TLabel").grid(row=0,column=0,sticky="w",pady=(0,2))
            widget=(ttk.Combobox(cell,textvariable=var,values=combo_values,state="normal") if combo_values is not None else ttk.Entry(cell,textvariable=var))
            widget.grid(row=1,column=0,sticky="ew")
            return widget

        stacked(form,"Name",self.name,0,0,3)
        self.cid_combo=stacked(form,"Contest (ADIF-Name)",self.cid,1,0,3,self.catalog_names)
        stacked(form,"Start UTC",self.time_start,2,0); stacked(form,"Ende UTC",self.time_end,2,1); stacked(form,"Kommentar",self.comment,2,2)
        stacked(form,"Start-Seriennummer",self.start,3,0); stacked(form,"Standardfrequenz (MHz)",self.freq,3,1); stacked(form,"Standard-RST",self.rst,3,2)
        stacked(form,"Gesendeter Text-Exchange",self.sent,4,0)
        band_cell=ttk.Frame(form,style="Card.TFrame"); band_cell.grid(row=4,column=1,columnspan=2,sticky="nsew",padx=(5,0),pady=3); band_cell.columnconfigure(0,weight=1); band_cell.columnconfigure(1,weight=1)
        ttk.Label(band_cell,text="Standardband",style="Card.TLabel").grid(row=0,column=0,sticky="w",pady=(0,2)); ttk.Label(band_cell,text="Mode",style="Card.TLabel").grid(row=0,column=1,sticky="w",padx=(5,0),pady=(0,2))
        ttk.Combobox(band_cell,textvariable=self.band,values=BANDS,state="readonly").grid(row=1,column=0,sticky="ew",padx=(0,5)); ttk.Combobox(band_cell,textvariable=self.mode,values=MODES,state="readonly").grid(row=1,column=1,sticky="ew",padx=(5,0))
        ttk.Separator(form).grid(row=5,column=0,columnspan=3,sticky="ew",pady=6)
        exchange=ttk.Frame(form,style="Card.TFrame"); exchange.grid(row=6,column=0,columnspan=3,sticky="ew"); ttk.Label(exchange,text="Exchange-Felder",style="CardTitle.TLabel").pack(side="left",padx=(0,14)); ttk.Checkbutton(exchange,text="Seriennummer",variable=self.serial).pack(side="left",padx=5); ttk.Checkbutton(exchange,text="Grid Square",variable=self.grid).pack(side="left",padx=5); ttk.Checkbutton(exchange,text="Exchange (Text)",variable=self.text).pack(side="left",padx=5)
        api_status=app.db.get_setting("contest_sync_status", "")
        if "Unknown resource: catalog" in api_status or "Unknown resource: contest" in api_status:
            api_status="Diese Wavelog-Version bietet noch keine Contest-Session-API. Contest-QSOs werden mit CONTEST_ID weiterhin normal synchronisiert."
        help_text=(api_status if api_status and api_status != "ok" else "Wavelog vergibt die numerische Session-ID automatisch. Verwende den ADIF-Namen aus dem Wavelog-Katalog, keine Zahl aus der Weboberfläche.")
        self.help_label=tk.Label(form,text=help_text,bg=theme.CARD,fg=(theme.WARN if api_status and api_status != "ok" else theme.MUTED),font=("Segoe UI",9),justify="left",anchor="w",wraplength=620)
        self.help_label.grid(row=7,column=0,columnspan=3,sticky="ew",pady=(8,0))
        self.bind("<Configure>",lambda e:self.help_label.configure(wraplength=max(300,e.width-90)) if e.widget is self else None,add="+")
        b=ttk.Frame(inner,style="Card.TFrame"); b.grid(row=2,column=0,sticky="e",pady=(10,0))
        ttk.Button(b,text="Abbrechen",command=self.destroy).pack(side="right"); ttk.Button(b,text="Speichern",style="Primary.TButton",command=self.save).pack(side="right",padx=8)

    def save(self):
        try:
            name=self.name.get().strip(); cid=self.cid.get().strip().upper()
            if not name: raise ValueError("Bitte einen Namen eingeben")
            if not cid: raise ValueError("Bitte den ADIF-Namen des Contests eingeben")
            if not valid_contest_adif_name(cid):
                raise ValueError("Der Contest benötigt einen ADIF-Namen wie DARC-WAG oder DARC-FT4 – keine numerische Wavelog-ID.")
            start=int(self.start.get().strip() or "1")
            if start<1: raise ValueError("Start-Seriennummer muss mindestens 1 sein")
            freq=self.freq.get().strip().replace(",", ".")
            if freq: float(freq)
            try:
                start_dt=datetime.fromisoformat(self.time_start.get().strip().replace("T"," "))
                end_dt=datetime.fromisoformat(self.time_end.get().strip().replace("T"," "))
            except ValueError:
                raise ValueError("Start und Ende bitte als YYYY-MM-DD HH:MM[:SS] in UTC eingeben")
            if end_dt <= start_dt: raise ValueError("Das Contest-Ende muss nach dem Start liegen")
            preset={"name":name,"contest_id":cid,"use_serial":bool(self.serial.get()),"use_grid":bool(self.grid.get()),"use_text":bool(self.text.get()),"sent_exchange":self.sent.get().strip(),"start_serial":start,
                    "freq":freq,"band":self.band.get(),"mode":self.mode.get(),"rst_default":self.rst.get().strip(),
                    "time_start":start_dt.strftime("%Y-%m-%d %H:%M:%S"),"time_end":end_dt.strftime("%Y-%m-%d %H:%M:%S"),
                    "comment":self.comment.get().strip(),"station_id":int(self.app.db.get_setting("station_profile_id","0") or 0)}
            self.callback(self.old_name,preset); self.destroy()
        except Exception as e:
            messagebox.showerror("Contest-Preset",str(e),parent=self)


class ProfileDeleteDialog(tk.Toplevel):
    """Local-only profile deletion confirmation. Never touches Wavelog."""
    def __init__(self, parent, profile_name: str):
        super().__init__(parent)
        self.result = None
        self.title("Profil lokal löschen")
        configure_responsive_dialog(self, (560, 300), (440, 270))
        self.configure(bg=theme.BG)
        self.transient(parent)
        self.grab_set()
        self.protocol("WM_DELETE_WINDOW", self._cancel)

        outer = ttk.Frame(self, padding=22)
        outer.pack(fill="both", expand=True)
        ttk.Label(outer, text="Profil lokal löschen", style="Title.TLabel").pack(anchor="w")
        tk.Label(outer, text=f"Profil: {profile_name}", bg=theme.BG, fg=theme.TEXT, font=("Segoe UI Semibold", 11)).pack(anchor="w", pady=(12, 5))
        tk.Label(outer, text="Gelöscht werden die lokalen Einstellungen und Sync-Metadaten dieses Logger-Profils.", bg=theme.BG, fg=theme.TEXT, font=("Segoe UI", 10), wraplength=500, justify="left").pack(anchor="w")

        warning = tk.Frame(outer, bg=theme.WARN_BADGE_BG, highlightbackground=theme.WARN, highlightthickness=1)
        warning.pack(fill="x", pady=14)
        tk.Label(warning, text="Wavelog wird NICHT verändert. Es werden weder QSOs noch Stationsprofile in Wavelog gelöscht.", bg=theme.WARN_BADGE_BG, fg=theme.WARN, font=("Segoe UI Semibold", 9), wraplength=475, justify="left", padx=12, pady=10).pack(anchor="w")

        self.delete_adi_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(outer, text="Lokale ADI-Dateien dieses Profils ebenfalls löschen", variable=self.delete_adi_var).pack(anchor="w", pady=(0, 12))

        buttons = ttk.Frame(outer)
        buttons.pack(fill="x", side="bottom")
        ttk.Button(buttons, text="Abbrechen", style="Secondary.TButton", command=self._cancel).pack(side="right")
        ttk.Button(buttons, text="Profil lokal löschen", style="Primary.TButton", command=self._confirm).pack(side="right", padx=(0, 8))

    def _confirm(self):
        self.result = bool(self.delete_adi_var.get())
        self.destroy()

    def _cancel(self):
        self.result = None
        self.destroy()

    @classmethod
    def ask(cls, parent, profile_name: str):
        dlg = cls(parent, profile_name)
        parent.wait_window(dlg)
        return dlg.result


class ProfileManagerDialog(tk.Toplevel):
    def __init__(self, parent: Any):
        super().__init__(parent)
        self.parent = parent
        self.title("Profile verwalten")
        configure_responsive_dialog(self, (650, 430), (500, 350))
        self.configure(bg=theme.BG)
        self.transient(parent)
        self.grab_set()
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)

        head = ttk.Frame(self, padding=(18, 16, 18, 8))
        head.grid(row=0, column=0, sticky="ew")
        ttk.Label(head, text="Logger-Profile", style="Title.TLabel").pack(anchor="w")
        tk.Label(head, text="Jedes Profil hat eigene Einstellungen, Wavelog-Zugangsdaten, ADI-Dateien und Sync-Metadaten.", bg=theme.BG, fg=theme.MUTED, font=("Segoe UI", 9)).pack(anchor="w", pady=(3,0))

        card = tk.Frame(self, bg=theme.CARD, highlightbackground=theme.BORDER, highlightthickness=1)
        card.grid(row=1, column=0, sticky="nsew", padx=18, pady=8)
        card.rowconfigure(0, weight=1); card.columnconfigure(0, weight=1)
        self.listbox = tk.Listbox(card, font=("Segoe UI", 11), relief="flat", borderwidth=0, activestyle="none")
        self.listbox.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)
        self.listbox.bind("<Double-1>", lambda e: self.activate_selected())

        buttons = ttk.Frame(self, padding=(18, 8, 18, 18))
        buttons.grid(row=2, column=0, sticky="ew")
        ttk.Button(buttons, text="Neu", style="Primary.TButton", command=lambda: self._new(False)).pack(side="left")
        ttk.Button(buttons, text="Duplizieren", style="Secondary.TButton", command=lambda: self._new(True)).pack(side="left", padx=(7,0))
        ttk.Button(buttons, text="Umbenennen", style="Secondary.TButton", command=self.rename_selected).pack(side="left", padx=(7,0))
        ttk.Button(buttons, text="Löschen", style="Secondary.TButton", command=self.delete_selected).pack(side="left", padx=(7,0))
        ttk.Button(buttons, text="Aktivieren", style="Secondary.TButton", command=self.activate_selected).pack(side="right")
        self.refresh()

    def refresh(self):
        self.rows = self.parent.profile_manager.list_profiles()
        self.listbox.delete(0, "end")
        selected_index = 0
        for i, p in enumerate(self.rows):
            marker = "● " if p["id"] == self.parent.active_profile_id else "   "
            self.listbox.insert("end", marker + p["name"])
            if p["id"] == self.parent.active_profile_id:
                selected_index = i
        if self.rows:
            self.listbox.selection_set(selected_index)

    def selected(self):
        sel = self.listbox.curselection()
        if not sel:
            return None
        return self.rows[int(sel[0])]

    def activate_selected(self):
        p = self.selected()
        if not p:
            return
        self.parent.switch_profile(p["id"])
        self.refresh()

    def _new(self, duplicate: bool):
        p = self.selected() if duplicate else None
        source_id = p["id"] if p else None
        base = p["name"] if p else ""
        name = simpledialog.askstring("Profil anlegen", "Profilname:", initialvalue=(base + " Kopie") if duplicate else "", parent=self)
        if not name:
            return
        try:
            self.parent.profile_manager.create(name, duplicate_from=source_id)
            self.parent._refresh_profile_selector()
            self.refresh()
        except Exception as e:
            messagebox.showerror("Profil anlegen", str(e), parent=self)

    def rename_selected(self):
        p = self.selected()
        if not p:
            return
        name = simpledialog.askstring("Profil umbenennen", "Neuer Profilname:", initialvalue=p["name"], parent=self)
        if not name or name == p["name"]:
            return
        try:
            self.parent.profile_manager.rename(p["id"], name)
            self.parent._refresh_profile_selector()
            self.refresh()
        except Exception as e:
            messagebox.showerror("Profil umbenennen", str(e), parent=self)

    def delete_selected(self):
        p = self.selected()
        if not p:
            return
        if p["id"] == self.parent.active_profile_id:
            messagebox.showinfo("Profil löschen", "Das aktive Profil kann nicht gelöscht werden. Bitte zuerst ein anderes Profil aktivieren.", parent=self)
            return
        choice = ProfileDeleteDialog.ask(self, p["name"])
        if choice is None:
            return
        try:
            result = self.parent.profile_manager.delete(p["id"], delete_adi=choice)
            self.parent._refresh_profile_selector()
            self.refresh()
            deleted = int(result.get("adi_deleted") or 0)
            log_dir = result.get("log_dir")
            text = "Lokales Profil gelöscht. Wavelog wurde nicht verändert."
            if choice:
                text += f"\n\n{deleted} lokale ADI-Datei(en) wurden gelöscht."
            else:
                text += "\n\nDie lokalen ADI-Dateien wurden behalten."
                if log_dir:
                    text += f"\nLog-Ordner: {log_dir}"
            messagebox.showinfo("Profil gelöscht", text, parent=self)
        except Exception as e:
            messagebox.showerror("Profil löschen", str(e), parent=self)


class EditDialog(tk.Toplevel):
    def __init__(self, parent: Any, q: dict, callback):
        super().__init__(parent)
        self.parent = parent
        self.q = q
        self.callback = callback
        self.title(f"QSO bearbeiten · {q.get('call','')}")
        configure_responsive_dialog(self, (760, 520), (520, 420))
        self.transient(parent)
        self.grab_set()
        self.configure(bg=theme.BG)
        frame = ttk.Frame(self, padding=18)
        frame.pack(fill="both", expand=True)
        frame.columnconfigure(1, weight=1)
        frame.columnconfigure(3, weight=1)
        self.vars = {}
        fields = [
            ("call","Rufzeichen"),("qso_date","Datum UTC"),("time_on","Zeit UTC HHMMSS"),("freq","Frequenz MHz"),
            ("band","Band"),("mode","Mode"),("rst_sent","RST gesendet"),("rst_rcvd","RST empfangen"),
            ("gridsquare","Locator"),("name","Name"),("qth","QTH"),("pota_ref","POTA Ref"),("sota_ref","SOTA Ref"),
            ("wwff_ref","WWFF Ref"),("tx_pwr","Leistung W"),("comment","Kommentar"),
        ]
        for i, (key, label) in enumerate(fields):
            row, group = divmod(i, 2)
            label_column = group * 2
            entry_column = label_column + 1
            ttk.Label(frame, text=label).grid(row=row, column=label_column, sticky="w", padx=(0,8), pady=4)
            v = tk.StringVar(value=str(q.get(key) or ""))
            self.vars[key] = v
            ttk.Entry(frame, textvariable=v).grid(row=row, column=entry_column, sticky="ew", padx=(0 if group else 0,0), pady=4)
        notes_row = (len(fields) + 1) // 2
        ttk.Label(frame, text="Notizen").grid(row=notes_row, column=0, sticky="nw", pady=4)
        self.notes = tk.Text(frame, height=4, wrap="word", font=("Segoe UI", 9), bg=theme.INPUT_BG, fg=theme.TEXT, insertbackground=theme.TEXT)
        self.notes.grid(row=notes_row, column=1, columnspan=3, sticky="nsew", pady=4)
        frame.rowconfigure(notes_row, weight=1)
        self.notes.insert("1.0", str(q.get("notes") or ""))
        btn = ttk.Frame(frame)
        btn.grid(row=notes_row+1, column=0, columnspan=4, sticky="e", pady=(14,0))
        ttk.Button(btn, text="Abbrechen", command=self.destroy).pack(side="right")
        ttk.Button(btn, text="Speichern", style="Primary.TButton", command=self.save).pack(side="right", padx=8)

    def save(self):
        try:
            d = {k:v.get().strip() for k,v in self.vars.items()}
            d["call"] = d["call"].upper()
            d["gridsquare"] = d["gridsquare"].upper()
            d["pota_ref"] = d["pota_ref"].upper()
            d["sota_ref"] = d["sota_ref"].upper()
            d["wwff_ref"] = d["wwff_ref"].upper()
            d["time_on"] = d["time_on"].replace(":", "")
            if len(d["time_on"]) == 4: d["time_on"] += "00"
            datetime.strptime(d["qso_date"] + d["time_on"], "%Y-%m-%d%H%M%S")
            if d["freq"]: float(d["freq"].replace(",",".")); d["freq"] = d["freq"].replace(",",".")
            if d["tx_pwr"]: float(d["tx_pwr"].replace(",",".")); d["tx_pwr"] = d["tx_pwr"].replace(",",".")
            d["notes"] = self.notes.get("1.0", "end").strip()
            self.callback(self.q["local_id"], d)
            self.destroy()
        except Exception as e:
            messagebox.showerror("Ungültige Eingabe", str(e), parent=self)
