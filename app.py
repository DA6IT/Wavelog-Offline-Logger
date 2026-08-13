from __future__ import annotations

import atexit
import os
import re
import sys
import json
import threading
import time
import traceback
import webbrowser
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk

from logger_core import (
    APP_NAME, VERSION, BANDS, MODES, LogStore, MetadataDB, WavelogClient,
    WavelogError, SyncEngine, app_data_dir, default_log_dir, band_from_mhz,
    qso_hash, CountryDB, ProfileManager,
)
from cat_control import (
    CAT_BAUD_RATES, CAT_DATA_BITS, CAT_HANDSHAKES, CAT_LINE_STATES,
    CAT_PARITIES, CAT_STOP_BITS, CatConfig, CatError, HamlibManager,
    RigModel, format_frequency_mhz, hamlib_version, list_rig_models,
    list_serial_ports, map_hamlib_mode,
)
from update_check import ReleaseInfo, find_newer_release


BG = "#f3f5f7"
CARD = "#ffffff"
TEXT = "#17202a"
MUTED = "#667085"
ACCENT = "#1769aa"
ACCENT_DARK = "#0f4f82"
BORDER = "#d9e0e7"
OK = "#287d3c"
WARN = "#9a6700"
ERR = "#b42318"
SIDEBAR = "#14212b"
SIDEBAR_TEXT = "#f7f9fb"


def write_startup_log(text: str):
    try:
        p = app_data_dir() / "startup.log"
        with p.open("a", encoding="utf-8") as f:
            f.write(f"[{datetime.now().isoformat(timespec='seconds')}] {text}\n")
    except Exception:
        pass


def utc_from_form(date_s: str, time_s: str, time_mode: str) -> tuple[str, str]:
    date_s = date_s.strip()
    time_s = time_s.strip().replace(":", "")
    if len(time_s) == 4:
        time_s += "00"
    if len(time_s) != 6:
        raise ValueError("Uhrzeit muss HHMM, HHMMSS oder HH:MM:SS sein")
    dt = datetime.strptime(date_s + time_s, "%Y-%m-%d%H%M%S")
    if time_mode == "LOCAL":
        # Use the operating system's local timezone/DST rules.
        ts = time.mktime(dt.timetuple())
        u = datetime.fromtimestamp(ts, timezone.utc)
    else:
        u = dt.replace(tzinfo=timezone.utc)
    return u.strftime("%Y-%m-%d"), u.strftime("%H%M%S")


def display_now(time_mode: str) -> datetime:
    return datetime.now().astimezone() if time_mode == "LOCAL" else datetime.now(timezone.utc)


class LoggerApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(f"{APP_NAME} {VERSION}")
        self.geometry("1420x820")
        self.minsize(1180, 700)
        self.configure(bg=BG)
        self.protocol("WM_DELETE_WINDOW", self.on_close)
        self.closing = False
        self.shutdown_started = False
        self.sync_busy = False
        self.station_rows: list[dict] = []
        self.station_by_label: dict[str, dict] = {}
        self.cat_manager = HamlibManager()
        atexit.register(self.cat_manager.stop)
        self.cat_models: list[RigModel] = []
        self.cat_model_by_label: dict[str, RigModel] = {}
        self.cat_generation = 0
        self.cat_poll_job = None
        self.cat_poll_busy = False

        self.data_dir = app_data_dir()
        self.country_db = CountryDB(Path(__file__).resolve().parent / "cty.dat")
        self.current_country = None
        self.profile_manager = ProfileManager(self.data_dir)
        self.active_profile_id = self.profile_manager.active_id
        self.db = None
        self.store = None
        self._open_profile_storage(self.active_profile_id)

        self._setup_style()
        self._build_shell()
        self._build_log_page()
        self._build_contest_page()
        self._build_qsos_page()
        self._build_stats_page()
        self._build_cat_page()
        self._build_settings_page()
        self._load_settings_to_ui()
        self._show_page("log")
        self._tick_clock()
        self.refresh_qsos()
        self.after(250, lambda: self.call_entry.focus_set())
        self.after(1500, self._start_update_check)
        write_startup_log(f"{APP_NAME} {VERSION} gestartet")

    def _start_update_check(self):
        """Look for a newer release without ever blocking or disturbing startup."""
        def worker():
            release = find_newer_release(VERSION)
            if release is not None and not self.closing:
                self.after(0, lambda: self._show_update_available(release))

        threading.Thread(target=worker, name="release-check", daemon=True).start()

    def _show_update_available(self, release: ReleaseInfo):
        if self.closing:
            return
        kind = "Release Candidate" if release.prerelease else "Version"
        open_page = messagebox.askyesno(
            "Update verfügbar",
            f"Eine neue {kind} ist verfügbar: v{release.version}\n\n"
            "Möchtest du die GitHub-Downloadseite jetzt öffnen?",
            parent=self,
        )
        if open_page:
            try:
                webbrowser.open(release.url)
            except Exception:
                pass

    # ---------- UI shell ----------
    def _setup_style(self):
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except Exception:
            pass
        style.configure("TFrame", background=BG)
        style.configure("Card.TFrame", background=CARD, relief="flat")
        style.configure("TLabel", background=BG, foreground=TEXT, font=("Segoe UI", 10))
        style.configure("Card.TLabel", background=CARD, foreground=TEXT, font=("Segoe UI", 10))
        style.configure("Muted.Card.TLabel", background=CARD, foreground=MUTED, font=("Segoe UI", 9))
        style.configure("Title.TLabel", background=BG, foreground=TEXT, font=("Segoe UI Semibold", 20))
        style.configure("CardTitle.TLabel", background=CARD, foreground=TEXT, font=("Segoe UI Semibold", 12))
        style.configure("Call.TEntry", font=("Segoe UI Semibold", 18), padding=8)
        style.configure("TEntry", padding=6)
        style.configure("TCombobox", padding=5)
        style.configure("Primary.TButton", background=ACCENT, foreground="white", padding=(14, 8), borderwidth=0, font=("Segoe UI Semibold", 10))
        style.map("Primary.TButton", background=[("active", ACCENT_DARK), ("disabled", "#9bb8cf")])
        style.configure("Secondary.TButton", padding=(12, 7), font=("Segoe UI", 10))
        style.configure("Nav.TButton", background=SIDEBAR, foreground=SIDEBAR_TEXT, padding=(16, 11), anchor="w", borderwidth=0, font=("Segoe UI", 10))
        style.map("Nav.TButton", background=[("active", "#203441")])
        style.configure("Treeview", rowheight=28, font=("Segoe UI", 9), background="white", fieldbackground="white")
        style.configure("Treeview.Heading", font=("Segoe UI Semibold", 9), padding=5)
        style.configure("Stats.Horizontal.TProgressbar", troughcolor="#e9eef3", background=ACCENT, borderwidth=0, thickness=10)
        style.configure("TLabelframe", background=CARD, bordercolor=BORDER, relief="solid")
        style.configure("TLabelframe.Label", background=CARD, foreground=TEXT, font=("Segoe UI Semibold", 10))
        style.configure("TRadiobutton", background=CARD, foreground=TEXT)
        style.configure("TCheckbutton", background=CARD, foreground=TEXT)

    def _build_shell(self):
        self.columnconfigure(1, weight=1)
        self.rowconfigure(0, weight=1)

        side = tk.Frame(self, bg=SIDEBAR, width=210)
        side.grid(row=0, column=0, sticky="nsew")
        side.grid_propagate(False)
        tk.Label(side, text="DA6IT.de", bg=SIDEBAR, fg="white", font=("Segoe UI Semibold", 17)).pack(anchor="w", padx=20, pady=(24, 2))
        tk.Label(side, text="Wavelog Offline Logger", bg=SIDEBAR, fg="#aebdca", font=("Segoe UI", 9)).pack(anchor="w", padx=20, pady=(0, 24))
        ttk.Button(side, text="  QSO loggen", style="Nav.TButton", command=lambda: self._show_page("log")).pack(fill="x")
        ttk.Button(side, text="  Contest Logging", style="Nav.TButton", command=lambda: self._show_page("contest")).pack(fill="x")
        ttk.Button(side, text="  Logbuch & Sync", style="Nav.TButton", command=lambda: self._show_page("qsos")).pack(fill="x")
        ttk.Button(side, text="  Statistiken", style="Nav.TButton", command=lambda: self._show_page("stats")).pack(fill="x")
        ttk.Button(side, text="  CAT Setup", style="Nav.TButton", command=lambda: self._show_page("cat")).pack(fill="x")
        ttk.Button(side, text="  Einstellungen", style="Nav.TButton", command=lambda: self._show_page("settings")).pack(fill="x")
        tk.Label(side, text=f"v{VERSION}", bg=SIDEBAR, fg="#8297a6", font=("Segoe UI", 8)).pack(side="bottom", anchor="w", padx=20, pady=18)

        self.main = ttk.Frame(self, padding=(24, 18))
        self.main.grid(row=0, column=1, sticky="nsew")
        self.main.columnconfigure(0, weight=1)
        self.main.rowconfigure(1, weight=1)

        header = ttk.Frame(self.main)
        header.grid(row=0, column=0, sticky="ew", pady=(0, 14))
        header.columnconfigure(0, weight=1)
        self.page_title = ttk.Label(header, text="QSO loggen", style="Title.TLabel")
        self.page_title.grid(row=0, column=0, sticky="w")

        profile_card = tk.Frame(header, bg=CARD, highlightbackground=BORDER, highlightthickness=1)
        profile_card.grid(row=0, column=1, sticky="e", padx=(10, 10))
        tk.Label(profile_card, text="PROFIL", bg=CARD, fg=MUTED, font=("Segoe UI Semibold", 8)).pack(side="left", padx=(10, 6))
        self.active_profile_var = tk.StringVar()
        self.profile_combo = ttk.Combobox(profile_card, textvariable=self.active_profile_var, state="readonly", width=22)
        self.profile_combo.pack(side="left", pady=5)
        self.profile_combo.bind("<<ComboboxSelected>>", self._profile_combo_changed)
        ttk.Button(profile_card, text="Verwalten", style="Secondary.TButton", command=self.manage_profiles).pack(side="left", padx=(6, 6), pady=4)
        self._refresh_profile_selector()

        clock_card = tk.Frame(header, bg=CARD, highlightbackground=BORDER, highlightthickness=1)
        clock_card.grid(row=0, column=2, sticky="e")
        self.clock_label = tk.Label(clock_card, text="--:--:--", bg=CARD, fg=TEXT, font=("Segoe UI Semibold", 18), padx=16, pady=5)
        self.clock_label.pack(side="left")
        self.clock_zone_label = tk.Label(clock_card, text="UTC", bg=CARD, fg=MUTED, font=("Segoe UI Semibold", 9), padx=(0), pady=5)
        self.clock_zone_label.pack(side="left", padx=(0, 12))

        self.page_container = ttk.Frame(self.main)
        self.page_container.grid(row=1, column=0, sticky="nsew")
        self.page_container.columnconfigure(0, weight=1)
        self.page_container.rowconfigure(0, weight=1)
        self.pages: dict[str, ttk.Frame] = {}

        self.status_var = tk.StringVar(value="Bereit · Offline-Logging aktiv")
        status = tk.Label(self.main, textvariable=self.status_var, bg=BG, fg=MUTED, font=("Segoe UI", 9), anchor="w")
        status.grid(row=2, column=0, sticky="ew", pady=(10, 0))

    # ---------- application profiles ----------
    def _open_profile_storage(self, profile_id: str):
        profile = self.profile_manager.get(profile_id)
        if not profile:
            raise RuntimeError("Profil nicht gefunden")
        self.active_profile_id = profile_id
        self.profile_manager.set_active(profile_id)
        self.db = MetadataDB(self.profile_manager.metadata_path(profile_id))
        fallback = self.profile_manager.default_log_dir(profile_id)
        raw_log_dir = self.db.get_setting("log_dir", "").strip()
        if not raw_log_dir:
            raw_log_dir = str(fallback)
            self.db.set_setting("log_dir", raw_log_dir)
        self.store = LogStore(Path(raw_log_dir))
        self.db.reconcile_index(self.store.scan())

    def _current_profile(self) -> dict:
        return self.profile_manager.get(self.active_profile_id) or {"id": self.active_profile_id, "name": "Profil"}

    def _profile_default_log_dir(self) -> Path:
        return self.profile_manager.default_log_dir(self.active_profile_id)

    def _refresh_profile_selector(self):
        if not hasattr(self, "profile_combo"):
            return
        profiles = self.profile_manager.list_profiles()
        self._profile_name_to_id = {p["name"]: p["id"] for p in profiles}
        names = list(self._profile_name_to_id.keys())
        self.profile_combo.configure(values=names)
        current = self.profile_manager.get(self.active_profile_id)
        if current:
            self.active_profile_var.set(current["name"])

    def _profile_combo_changed(self, _event=None):
        pid = getattr(self, "_profile_name_to_id", {}).get(self.active_profile_var.get())
        if pid and pid != self.active_profile_id:
            self.switch_profile(pid)

    def switch_profile(self, profile_id: str):
        if profile_id == self.active_profile_id:
            return
        if self.sync_busy:
            messagebox.showwarning("Profil wechseln", "Während einer Synchronisierung kann das Profil nicht gewechselt werden.", parent=self)
            self._refresh_profile_selector()
            return
        if hasattr(self, "call_var") and self.call_var.get().strip():
            if not messagebox.askyesno("Profil wechseln", "Im QSO-Formular stehen noch Eingaben. Beim Profilwechsel wird das Formular geleert.\n\nTrotzdem wechseln?", parent=self):
                self._refresh_profile_selector()
                return
        try:
            old = self._current_profile().get("name", "")
            self._stop_cat_runtime(update_ui=False)
            if self.db:
                self.db.close()
            self._open_profile_storage(profile_id)
            self.station_rows = []
            self.station_by_label.clear()
            if hasattr(self, "station_combo"):
                self.station_combo.configure(values=[])
            self._load_settings_to_ui()
            self.clear_qso_form()
            if hasattr(self, "contest_power_var"):
                self.contest_power_var.set(self.db.get_setting("default_power", ""))
            self.refresh_contest_page()
            self.refresh_qsos()
            self.refresh_stats()
            self._refresh_profile_selector()
            self.status_var.set(f"Profil gewechselt: {old} → {self._current_profile()['name']}")
        except Exception as e:
            messagebox.showerror("Profil wechseln", str(e), parent=self)
            self._refresh_profile_selector()

    def manage_profiles(self):
        ProfileManagerDialog(self)

    def create_profile(self, duplicate=False):
        base = self._current_profile()["name"] if duplicate else ""
        prompt = "Name für das duplizierte Profil:" if duplicate else "Name des neuen Profils:"
        initial = (base + " Kopie") if duplicate else ""
        name = simpledialog.askstring("Profil anlegen", prompt, initialvalue=initial, parent=self)
        if not name:
            return
        try:
            row = self.profile_manager.create(name, duplicate_from=self.active_profile_id if duplicate else None)
            self._refresh_profile_selector()
            self.switch_profile(row["id"])
        except Exception as e:
            messagebox.showerror("Profil anlegen", str(e), parent=self)

    def rename_profile(self, profile_id: str | None = None):
        profile_id = profile_id or self.active_profile_id
        p = self.profile_manager.get(profile_id)
        if not p:
            return
        name = simpledialog.askstring("Profil umbenennen", "Neuer Profilname:", initialvalue=p["name"], parent=self)
        if not name or name == p["name"]:
            return
        try:
            self.profile_manager.rename(profile_id, name)
            self._refresh_profile_selector()
            self.status_var.set(f"Profil umbenannt: {name}")
        except Exception as e:
            messagebox.showerror("Profil umbenennen", str(e), parent=self)

    def delete_profile(self, profile_id: str):
        p = self.profile_manager.get(profile_id)
        if not p:
            return
        if profile_id == self.active_profile_id:
            messagebox.showinfo("Profil löschen", "Bitte zuerst auf ein anderes Profil wechseln und dieses Profil dann löschen.", parent=self)
            return
        choice = ProfileDeleteDialog.ask(self, p["name"])
        if choice is None:
            return
        try:
            result = self.profile_manager.delete(profile_id, delete_adi=choice)
            self._refresh_profile_selector()
            deleted = int(result.get("adi_deleted") or 0)
            log_dir = result.get("log_dir")
            msg = "Lokales Profil gelöscht. Wavelog wurde nicht verändert."
            if choice:
                msg += f"\n\n{deleted} lokale ADI-Datei(en) wurden gelöscht."
            else:
                msg += "\n\nDie lokalen ADI-Dateien wurden behalten."
                if log_dir:
                    msg += f"\nLog-Ordner: {log_dir}"
            messagebox.showinfo("Profil gelöscht", msg, parent=self)
        except Exception as e:
            messagebox.showerror("Profil löschen", str(e), parent=self)

    def _new_page(self, name: str) -> ttk.Frame:
        f = ttk.Frame(self.page_container)
        f.grid(row=0, column=0, sticky="nsew")
        self.pages[name] = f
        return f

    def _show_page(self, name: str):
        titles = {"log": "QSO loggen", "contest": "Contest Logging", "qsos": "Logbuch & Sync", "stats": "Statistiken", "cat": "CAT Setup", "settings": "Einstellungen"}
        self.page_title.configure(text=titles[name])
        self.pages[name].tkraise()
        if name == "contest":
            self.refresh_contest_page()
        elif name == "qsos":
            self.refresh_qsos()
        elif name == "stats":
            self.refresh_stats()
        elif name == "cat":
            self._refresh_cat_ports()

    def _card(self, parent, **grid):
        outer = tk.Frame(parent, bg=CARD, highlightbackground=BORDER, highlightthickness=1)
        outer.grid(**grid)
        inner = ttk.Frame(outer, style="Card.TFrame", padding=16)
        inner.pack(fill="both", expand=True)
        return inner

    # ---------- log page ----------
    def _build_log_page(self):
        p = self._new_page("log")
        p.columnconfigure(0, weight=3)
        p.columnconfigure(1, weight=2)
        p.rowconfigure(0, weight=1)

        left = self._card(p, row=0, column=0, sticky="nsew", padx=(0, 8))
        left.columnconfigure(0, weight=1)
        left.columnconfigure(1, weight=1)
        left.columnconfigure(2, weight=1)
        left.columnconfigure(3, weight=1)

        ttk.Label(left, text="Gegenstation", style="CardTitle.TLabel").grid(row=0, column=0, columnspan=4, sticky="w", pady=(0, 8))
        self.call_var = tk.StringVar()
        self.call_entry = ttk.Entry(left, textvariable=self.call_var, style="Call.TEntry")
        self.call_entry.grid(row=1, column=0, columnspan=4, sticky="ew", pady=(0, 14))
        self.call_entry.bind("<KeyRelease>", self._call_changed)
        self.call_entry.bind("<Return>", lambda e: self.save_qso(new_after=True))

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
        self.notes_text = tk.Text(left, height=3, wrap="word", font=("Segoe UI", 10), relief="solid", borderwidth=1, highlightthickness=0)
        self.notes_text.grid(row=11, column=0, columnspan=4, sticky="ew")

        btns = ttk.Frame(left, style="Card.TFrame")
        btns.grid(row=12, column=0, columnspan=4, sticky="ew", pady=(16, 0))
        ttk.Button(btns, text="QSO speichern", style="Primary.TButton", command=lambda: self.save_qso(False)).pack(side="left")
        ttk.Button(btns, text="Speichern + Neu", style="Secondary.TButton", command=lambda: self.save_qso(True)).pack(side="left", padx=8)
        ttk.Button(btns, text="Felder leeren", style="Secondary.TButton", command=self.clear_qso_form).pack(side="left")

        right = self._card(p, row=0, column=1, sticky="nsew", padx=(8, 0))
        right.columnconfigure(0, weight=1)
        ttk.Label(right, text="Zeit", style="CardTitle.TLabel").grid(row=0, column=0, sticky="w")
        self.time_mode_var = tk.StringVar(value="UTC")
        self.live_time_var = tk.BooleanVar(value=True)
        row = ttk.Frame(right, style="Card.TFrame")
        row.grid(row=1, column=0, sticky="ew", pady=(8, 10))
        ttk.Radiobutton(row, text="UTC", variable=self.time_mode_var, value="UTC", command=self._time_mode_changed).pack(side="left")
        ttk.Radiobutton(row, text="Lokal", variable=self.time_mode_var, value="LOCAL", command=self._time_mode_changed).pack(side="left", padx=(12, 0))
        ttk.Checkbutton(row, text="Live", variable=self.live_time_var, command=self._live_changed).pack(side="right")
        self.qso_date_var = tk.StringVar()
        self.qso_time_var = tk.StringVar()
        self._field(right, "Datum", self.qso_date_var, 2, 0)
        self._field(right, "Uhrzeit", self.qso_time_var, 4, 0)

        ttk.Separator(right).grid(row=6, column=0, sticky="ew", pady=14)
        ttk.Label(right, text="Gegenstation · offline", style="CardTitle.TLabel").grid(row=7, column=0, sticky="w")
        self.country_summary = tk.Label(right, bg=CARD, fg=TEXT, font=("Segoe UI", 10), justify="left", anchor="nw", wraplength=330)
        self.country_summary.grid(row=8, column=0, sticky="ew", pady=(7, 0))
        self.country_source = tk.Label(right, text="CTY.DAT · keine Internetverbindung nötig", bg=CARD, fg=MUTED, font=("Segoe UI", 8), justify="left", anchor="w")
        self.country_source.grid(row=9, column=0, sticky="ew", pady=(4, 0))

        ttk.Separator(right).grid(row=10, column=0, sticky="ew", pady=14)
        ttk.Label(right, text="Aktives Stationsprofil", style="CardTitle.TLabel").grid(row=11, column=0, sticky="w")
        self.profile_summary = tk.Label(right, bg=CARD, fg=TEXT, font=("Segoe UI", 10), justify="left", anchor="nw", wraplength=330)
        self.profile_summary.grid(row=12, column=0, sticky="ew", pady=(8, 0))
        ttk.Button(right, text="Profil bearbeiten", style="Secondary.TButton", command=lambda: self._show_page("settings")).grid(row=13, column=0, sticky="w", pady=(12, 0))

        ttk.Separator(right).grid(row=14, column=0, sticky="ew", pady=14)
        ttk.Label(right, text="Logdatei", style="CardTitle.TLabel").grid(row=15, column=0, sticky="w")
        self.logfile_preview = tk.Label(right, bg=CARD, fg=MUTED, font=("Segoe UI", 9), justify="left", anchor="nw", wraplength=330)
        self.logfile_preview.grid(row=16, column=0, sticky="ew", pady=(6, 0))
        self._update_country_summary()

        self.form_vars = {
            "tx_pwr": self._vars["tx_pwr"], "gridsquare": self._vars["gridsquare"], "name": self._vars["name"],
            "qth": self._vars["qth"], "pota_ref": self._vars["pota_ref"], "sota_ref": self._vars["sota_ref"],
            "wwff_ref": self._vars["wwff_ref"], "comment": self._vars["comment"],
        }

    _vars: dict[str, tk.StringVar] = {}

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
        self.current_country = self.country_db.lookup(value)
        self._update_country_summary()

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
        self._update_logfile_preview()
        self.after(250, self._tick_clock)

    def _profile_values(self) -> dict[str, str]:
        return {
            "operator_call": self.db.get_setting("operator_call", "").upper(),
            "station_call": self.db.get_setting("station_call", "").upper(),
            "my_gridsquare": self.db.get_setting("locator", "").upper(),
            "my_qth": self.db.get_setting("qth", ""),
            "my_pota_ref": self.db.get_setting("my_pota_ref", "").upper(),
            "my_sota_ref": self.db.get_setting("my_sota_ref", "").upper(),
            "my_wwff_ref": self.db.get_setting("my_wwff_ref", "").upper(),
        }

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
        p = self._profile_values()
        date_s = self.qso_date_var.get() if hasattr(self, "qso_date_var") else datetime.now(timezone.utc).strftime("%Y-%m-%d")
        call = p["station_call"] or p["operator_call"] or "NOCALL"
        safe = call.replace("/", "_")
        self.logfile_preview.configure(text=f"{self.store.log_dir}\n{safe}.{date_s}.adi")

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

    def save_qso(self, new_after=False):
        try:
            q = self._collect_qso()
            q = self.store.add(q)
            self.db.ensure_local(q["local_id"], qso_hash(q))
            self.status_var.set(f"Gespeichert: {q['call']} · {q['band']} · {q['mode']} · {Path(q['_file']).name}")
            self.refresh_qsos()
            if new_after:
                self.clear_qso_form(keep_freq=True)
                self.call_entry.focus_set()
        except Exception as e:
            messagebox.showerror("QSO konnte nicht gespeichert werden", str(e), parent=self)

    def clear_qso_form(self, keep_freq=False):
        self.call_var.set("")
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

    # ---------- contest logging ----------
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
        self.contest_session_status = tk.Label(top, text="Keine Session", bg=CARD, fg=MUTED, font=("Segoe UI Semibold", 9))
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

        self.contest_exchange_hint = tk.Label(left, text="", bg=CARD, fg=MUTED, font=("Segoe UI", 9), anchor="w")
        self.contest_exchange_hint.grid(row=8, column=0, columnspan=4, sticky="ew", pady=(10, 0))
        btns = ttk.Frame(left, style="Card.TFrame")
        btns.grid(row=9, column=0, columnspan=4, sticky="ew", pady=(16, 0))
        ttk.Button(btns, text="Contest-QSO loggen", style="Primary.TButton", command=self.save_contest_qso).pack(side="left")
        ttk.Button(btns, text="Felder leeren", style="Secondary.TButton", command=self.clear_contest_form).pack(side="left", padx=8)

        right = self._card(p, row=1, column=1, sticky="nsew", padx=(8, 0))
        right.columnconfigure(0, weight=1)
        ttk.Label(right, text="Contest-Session", style="CardTitle.TLabel").grid(row=0, column=0, sticky="w")
        self.contest_station_label = tk.Label(right, text="Station: —", bg=CARD, fg=TEXT, font=("Segoe UI", 10), anchor="w")
        self.contest_station_label.grid(row=1, column=0, sticky="ew", pady=(8, 2))
        ttk.Label(right, text="Operator", style="Card.TLabel").grid(row=2, column=0, sticky="w", pady=(8, 3))
        self.contest_operator_combo = ttk.Combobox(right, textvariable=self.contest_operator_var, state="normal")
        self.contest_operator_combo.grid(row=3, column=0, sticky="ew")
        self.contest_operator_combo.bind("<<ComboboxSelected>>", lambda e: self._contest_operator_changed())
        self.contest_operator_combo.bind("<FocusOut>", lambda e: self._contest_operator_changed())
        self.contest_session_detail = tk.Label(right, text="", bg=CARD, fg=MUTED, font=("Segoe UI", 9), justify="left", anchor="nw", wraplength=360)
        self.contest_session_detail.grid(row=4, column=0, sticky="ew", pady=(12, 8))
        sbtn = ttk.Frame(right, style="Card.TFrame")
        sbtn.grid(row=5, column=0, sticky="ew")
        self.contest_start_btn = ttk.Button(sbtn, text="Session starten", style="Primary.TButton", command=self.start_contest_session)
        self.contest_start_btn.pack(side="left")
        self.contest_stop_btn = ttk.Button(sbtn, text="Session beenden", style="Secondary.TButton", command=self.stop_contest_session)
        self.contest_stop_btn.pack(side="left", padx=8)

        ttk.Separator(right).grid(row=6, column=0, sticky="ew", pady=16)
        ttk.Label(right, text="Letzte Contest-QSOs", style="CardTitle.TLabel").grid(row=7, column=0, sticky="w")
        self.contest_recent = tk.Listbox(right, height=10, font=("Consolas", 9), relief="solid", borderwidth=1)
        self.contest_recent.grid(row=8, column=0, sticky="nsew", pady=(7, 0))
        right.rowconfigure(8, weight=1)

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
            presets = [preset if p.get("name") == old_name else p for p in presets]
        else:
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
        profile = self._profile_values()
        station = profile.get("station_call") or profile.get("operator_call")
        operator = self.contest_operator_var.get().strip().upper() or profile.get("operator_call")
        if not station or not operator:
            messagebox.showerror("Contest", "Station und Operator müssen gesetzt sein.", parent=self); return
        try:
            start_serial = max(1, int(preset.get("start_serial") or 1))
        except Exception:
            start_serial = 1
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
        self.contest_session_status.configure(text=("● Session läuft" if running else "Keine Session"), fg=(OK if running else MUTED))
        self.contest_start_btn.configure(state=("disabled" if running else "normal"))
        self.contest_stop_btn.configure(state=("normal" if running else "disabled"))
        if running:
            serial = int(session.get("next_serial") or 1)
            self.contest_serial_sent_var.set(f"{serial:03d}")
            self.contest_session_detail.configure(text=f"{session.get('preset_name')}\nOperator: {session.get('operator','—')}\nNächste Seriennummer: {serial:03d}\nQSOs: {int(session.get('qso_count') or 0)}")
        else:
            try: serial=max(1,int((preset or {}).get("start_serial") or 1))
            except Exception: serial=1
            self.contest_serial_sent_var.set(f"{serial:03d}")
            self.contest_session_detail.configure(text="Preset auswählen und Session starten.\nDie Seriennummer läuft stationsweit weiter, auch wenn der Operator wechselt.")

        self.contest_recent.delete(0, "end")
        contest_id = str((preset or {}).get("contest_id") or "").upper()
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
            q=self.store.add(q); self.db.ensure_local(q["local_id"],qso_hash(q))
            if preset.get("use_serial"): session["next_serial"]=serial+1
            session["qso_count"]=int(session.get("qso_count") or 0)+1
            self._set_contest_session(session)
            self.status_var.set(f"Contest-QSO #{serial:03d}: {call} gespeichert")
            self.refresh_qsos(); self.refresh_contest_page(); self.clear_contest_form()
        except Exception as e:
            messagebox.showerror("Contest-QSO konnte nicht gespeichert werden", str(e), parent=self)

    # ---------- QSO list / sync ----------
    def _build_qsos_page(self):
        p = self._new_page("qsos")
        p.columnconfigure(0, weight=1)
        p.rowconfigure(1, weight=1)
        top = self._card(p, row=0, column=0, sticky="ew", pady=(0, 10))
        ttk.Button(top, text="Synchronisieren", style="Primary.TButton", command=self.sync_now).pack(side="left")
        ttk.Button(top, text="ADI-Ordner öffnen", style="Secondary.TButton", command=self.open_log_dir).pack(side="left", padx=8)
        self.sync_label = tk.Label(top, text="", bg=CARD, fg=MUTED, font=("Segoe UI", 9))
        self.sync_label.pack(side="right")

        card = self._card(p, row=1, column=0, sticky="nsew")
        card.columnconfigure(0, weight=1)
        card.rowconfigure(0, weight=1)
        cols = ("date", "time", "call", "operator", "contest", "band", "mode", "freq", "rst", "status", "qrz", "lotw", "eqsl", "dcl")
        self.tree = ttk.Treeview(card, columns=cols, show="headings", selectmode="browse")
        headings = {"date":"Datum UTC", "time":"Zeit", "call":"Call", "operator":"Operator", "contest":"Contest", "band":"Band", "mode":"Mode", "freq":"MHz", "rst":"RST", "status":"Sync",
                    "qrz":"QRZ", "lotw":"LoTW", "eqsl":"eQSL", "dcl":"DCL"}
        widths = {"date":88,"time":62,"call":88,"operator":82,"contest":100,"band":52,"mode":60,"freq":80,"rst":62,"status":88,
                  "qrz":52,"lotw":52,"eqsl":52,"dcl":52}
        for c in cols:
            self.tree.heading(c, text=headings[c])
            self.tree.column(c, width=widths[c], minwidth=45, stretch=(c in ("call", "contest")))
        self.tree.grid(row=0, column=0, sticky="nsew")
        sb = ttk.Scrollbar(card, orient="vertical", command=self.tree.yview)
        sb.grid(row=0, column=1, sticky="ns")
        self.tree.configure(yscrollcommand=sb.set)
        self.tree.tag_configure("local", foreground=MUTED)
        self.tree.tag_configure("wavelog", foreground=OK)
        self.tree.tag_configure("modified", foreground=WARN)
        self.tree.tag_configure("conflict", foreground=ERR)
        self.tree.tag_configure("error", foreground=ERR)
        self.tree.bind("<Double-1>", lambda e: self.edit_selected_qso())

        actions = ttk.Frame(card, style="Card.TFrame")
        actions.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(10, 0))
        ttk.Button(actions, text="QSO bearbeiten", style="Secondary.TButton", command=self.edit_selected_qso).pack(side="left")
        ttk.Button(actions, text="QSO löschen", style="Secondary.TButton", command=self.delete_selected_qso).pack(side="left", padx=8)
        ttk.Button(actions, text="Wavelog-Version übernehmen", style="Secondary.TButton", command=lambda: self.resolve_conflict(False)).pack(side="right")
        ttk.Button(actions, text="Lokale Version erzwingen", style="Secondary.TButton", command=lambda: self.resolve_conflict(True)).pack(side="right", padx=8)

        legend = tk.Label(card, text="QSL-Status: ✓ bestätigt · ↑ gesendet/hochgeladen · … wartet · — kein Status · ? nicht verfügbar",
                          bg=CARD, fg=MUTED, font=("Segoe UI", 8), anchor="w")
        legend.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(8, 0))

    @staticmethod
    def _display_qsl_status(value: str | None) -> str:
        return {"confirmed":"✓", "sent":"↑", "pending":"…", "none":"—", "unknown":"?"}.get((value or "unknown").lower(), "?")

    @staticmethod
    def _display_sync_status(meta: dict | None) -> tuple[str, str]:
        if not meta or meta.get("wavelog_id") is None:
            status = (meta or {}).get("status", "local_only")
            if status == "error":
                return "SYNC-FEHLER", "error"
            return "LOCAL ONLY", "local"
        status = meta.get("status", "synced")
        if status == "synced":
            return "WAVELOG ✓", "wavelog"
        if status == "modified":
            return "GEÄNDERT", "modified"
        if status == "pending_delete":
            return "LÖSCHEN …", "modified"
        if status == "conflict":
            return "KONFLIKT", "conflict"
        if status == "error":
            return "SYNC-FEHLER", "error"
        return status.upper(), "modified"

    def refresh_qsos(self):
        if not hasattr(self, "tree"):
            return
        qsos = self.store.scan()
        self.db.reconcile_index(qsos)
        self.tree.delete(*self.tree.get_children())
        for q in qsos:
            meta = self.db.get_meta(q["local_id"])
            s, tag = self._display_sync_status(meta)
            tm = q.get("time_on", "")
            if len(tm) >= 6:
                tm = f"{tm[:2]}:{tm[2:4]}:{tm[4:6]}"
            qsl = self.db.get_qsl_status(meta.get("wavelog_id") if meta else None)
            self.tree.insert("", "end", iid=q["local_id"], tags=(tag,), values=(
                q.get("qso_date", ""), tm, q.get("call", ""), q.get("operator_call", "") or "—", q.get("contest_id", "") or "—", q.get("band", ""), q.get("mode", ""), q.get("freq", ""),
                f"{q.get('rst_sent','')}/{q.get('rst_rcvd','')}", s,
                self._display_qsl_status(qsl.get("qrz")), self._display_qsl_status(qsl.get("lotw")),
                self._display_qsl_status(qsl.get("eqsl")), self._display_qsl_status(qsl.get("dcl")),
            ))
        metas = self.db.list_meta()
        local_only = sum(1 for m in metas if m.get("wavelog_id") is None and m.get("status") not in ("pending_delete",))
        wavelog = sum(1 for m in metas if m.get("wavelog_id") is not None and m.get("status") == "synced")
        issues = sum(1 for m in metas if m.get("status") in ("modified", "conflict", "error", "pending_delete"))
        last = self.db.get_setting("last_sync_at", "")
        suffix = f" · letzter Sync {last}" if last else " · noch nicht synchronisiert"
        issue_text = f" · {issues} offen" if issues else ""
        self.sync_label.configure(text=f"{len(qsos)} QSOs · {wavelog} WAVELOG · {local_only} LOCAL ONLY{issue_text}{suffix}")

    def selected_id(self) -> str | None:
        s = self.tree.selection() if hasattr(self, "tree") else []
        return s[0] if s else None

    def edit_selected_qso(self):
        lid = self.selected_id()
        if not lid:
            return
        q = self.store.find(lid)
        if not q:
            return
        EditDialog(self, q, self._save_edited_qso)

    def _save_edited_qso(self, local_id: str, q: dict):
        try:
            old = self.store.find(local_id)
            if not old:
                raise ValueError("QSO nicht mehr vorhanden")
            profile = {k: old.get(k, "") for k in ("operator_call","station_call","my_gridsquare","my_qth","my_pota_ref","my_sota_ref","my_wwff_ref",
                                                       "contest_id","stx","srx","stx_string","srx_string")}
            q.update(profile)
            q.update(self._country_fields_for_call(q.get("call", "")))
            updated = self.store.update(local_id, q)
            self.db.ensure_local(local_id, qso_hash(updated))
            self.refresh_qsos()
            self.status_var.set(f"QSO {updated['call']} geändert")
        except Exception as e:
            messagebox.showerror("Bearbeiten fehlgeschlagen", str(e), parent=self)

    def delete_selected_qso(self):
        lid = self.selected_id()
        if not lid:
            return
        q = self.store.find(lid)
        if not q:
            return
        if not messagebox.askyesno("QSO löschen", f"{q['call']} vom {q['qso_date']} wirklich löschen?\n\nIst es bereits synchronisiert, wird die Löschung beim nächsten Sync auch an Wavelog übertragen.", parent=self):
            return
        self.db.mark_pending_delete(lid)
        self.store.delete(lid)
        self.refresh_qsos()
        self.status_var.set("QSO lokal gelöscht")

    def _client_from_settings(self) -> WavelogClient:
        return WavelogClient(self.db.get_setting("wavelog_url", ""), self.db.get_token())

    def sync_now(self):
        if self.sync_busy:
            return
        try:
            station_id = int(self.db.get_setting("station_profile_id", "0"))
            if station_id <= 0:
                raise ValueError("Bitte in den Einstellungen zuerst ein Wavelog-Stationsprofil auswählen")
            client = self._client_from_settings()
        except Exception as e:
            messagebox.showerror("Sync", str(e), parent=self)
            return
        self.sync_busy = True
        self.status_var.set("Synchronisierung läuft …")
        self.sync_label.configure(text="Synchronisierung läuft …")

        def worker():
            try:
                stations = client.stations()
                smap = {int(s.get("id")): s for s in stations if s.get("id") is not None}
                engine = SyncEngine(self.store, self.db, client)
                summary = engine.sync(station_id, smap)
                msg = (f"Upload {summary.pushed} · zu Wavelog geändert {summary.patched} · "
                       f"neu aus Wavelog {summary.pulled} · aus Wavelog aktualisiert {summary.remote_updated} · "
                       f"remote gelöscht {summary.remote_deleted} · verknüpft {summary.linked} · "
                       f"lokal→Wavelog gelöscht {summary.deleted} · QSL-Status {summary.qsl_updated} · "
                       f"Konflikte {summary.conflicts} · Fehler {summary.errors} · QSL-Statusfehler {summary.qsl_errors}")
                if not self.closing:
                    self.after(0, lambda: self._sync_finished(msg))
            except Exception as e:
                if not self.closing:
                    self.after(0, lambda: self._sync_failed(str(e)))

        threading.Thread(target=worker, name="wavelog-sync", daemon=True).start()

    def _sync_finished(self, msg):
        self.sync_busy = False
        self.db.set_setting("last_sync_at", datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S"))
        self.status_var.set("Sync fertig · " + msg)
        self.refresh_qsos()

    def _sync_failed(self, msg):
        self.sync_busy = False
        self.status_var.set("Sync fehlgeschlagen")
        messagebox.showerror("Wavelog Sync", msg, parent=self)
        self.refresh_qsos()

    def resolve_conflict(self, force_local: bool):
        lid = self.selected_id()
        if not lid:
            return
        m = self.db.get_meta(lid)
        if not m or m.get("status") != "conflict" or not m.get("wavelog_id"):
            messagebox.showinfo("Konflikt", "Das ausgewählte QSO hat keinen Sync-Konflikt.", parent=self)
            return
        q = self.store.find(lid)
        if not q:
            return
        try:
            client = self._client_from_settings()
            wid = int(m["wavelog_id"])
            remote_deleted = m.get("last_error") == "remote_deleted"
            if remote_deleted:
                if force_local:
                    # Re-create the locally changed QSO in Wavelog and link the new id.
                    sid = int(self.db.get_setting("station_profile_id", "0"))
                    from logger_core import local_to_wavelog, remote_hash
                    remote = client.create_qso(local_to_wavelog(q, sid, include_operator=True))
                    new_wid = int(remote.get("id"))
                    self.db.set_status(lid, "synced", wavelog_id=new_wid,
                                       last_synced_hash=qso_hash(q), remote_hash=remote_hash(remote))
                else:
                    # Wavelog deletion wins.
                    self.store.delete(lid)
                    self.db.delete_meta(lid)
            elif force_local:
                sid = int(self.db.get_setting("station_profile_id", "0"))
                from logger_core import local_to_wavelog, remote_hash
                remote = client.patch_qso(wid, local_to_wavelog(q, sid))
                self.db.set_status(lid, "synced", last_synced_hash=qso_hash(q), remote_hash=remote_hash(remote))
            else:
                from logger_core import remote_to_local, remote_hash
                remote = client.get_qso(wid)
                stations = client.stations()
                smap = {int(s["id"]): s for s in stations if s.get("id") is not None}
                rq = remote_to_local(remote, smap.get(int(remote.get("station_id") or 0), {}))
                rq["local_id"] = lid
                self.store.update(lid, rq)
                self.db.set_status(lid, "synced", last_synced_hash=qso_hash(rq), remote_hash=remote_hash(remote))
            self.refresh_qsos()
        except Exception as e:
            messagebox.showerror("Konflikt konnte nicht aufgelöst werden", str(e), parent=self)

    def open_log_dir(self):
        p = str(self.store.log_dir)
        try:
            if sys.platform == "win32":
                os.startfile(p)
            elif sys.platform == "darwin":
                os.system(f'open "{p}"')
            else:
                os.system(f'xdg-open "{p}" >/dev/null 2>&1 &')
        except Exception as e:
            messagebox.showerror("Ordner öffnen", str(e), parent=self)

    # ---------- statistics ----------
    def _build_stats_page(self):
        p = self._new_page("stats")
        for c in range(4):
            p.columnconfigure(c, weight=1, uniform="stats")

        controls = self._card(p, row=0, column=0, columnspan=4, sticky="ew", pady=(0, 10))
        ttk.Label(controls, text="Auswertung", style="CardTitle.TLabel").pack(side="left")
        tk.Label(controls, text="Zeitraum", bg=CARD, fg=MUTED, font=("Segoe UI", 9)).pack(side="left", padx=(24, 7))
        self.stats_period_var = tk.StringVar(value="Gesamt")
        period = ttk.Combobox(controls, textvariable=self.stats_period_var, state="readonly", width=18,
                              values=("Gesamt", "Dieses Jahr", "Dieser Monat", "Diese Woche", "Heute (UTC)"))
        period.pack(side="left")
        period.bind("<<ComboboxSelected>>", lambda e: self.refresh_stats())
        tk.Label(controls, text="Operator:", bg=CARD, fg=MUTED, font=("Segoe UI", 9)).pack(side="left", padx=(18, 6))
        self.stats_operator_var = tk.StringVar(value="Alle Operatoren")
        self.stats_operator_combo = ttk.Combobox(controls, textvariable=self.stats_operator_var, state="readonly", width=18,
                                                  values=("Alle Operatoren",))
        self.stats_operator_combo.pack(side="left")
        self.stats_operator_combo.bind("<<ComboboxSelected>>", lambda e: self.refresh_stats())
        self.stats_hint = tk.Label(controls, text="", bg=CARD, fg=MUTED, font=("Segoe UI", 9))
        self.stats_hint.pack(side="right")

        self.stats_metric_vars = []
        for idx, title in enumerate(("QSOs", "DXCC-Entities", "Bänder", "Modes")):
            card = self._card(p, row=1, column=idx, sticky="nsew", padx=(0 if idx == 0 else 5, 0 if idx == 3 else 5), pady=(0, 10))
            var = tk.StringVar(value="0")
            self.stats_metric_vars.append(var)
            tk.Label(card, text=title.upper(), bg=CARD, fg=MUTED, font=("Segoe UI Semibold", 8)).pack(anchor="w")
            tk.Label(card, textvariable=var, bg=CARD, fg=TEXT, font=("Segoe UI Semibold", 25)).pack(anchor="w", pady=(4, 0))

        bands = self._card(p, row=2, column=0, columnspan=2, sticky="nsew", padx=(0, 5), pady=(0, 10))
        modes = self._card(p, row=2, column=2, columnspan=2, sticky="nsew", padx=(5, 0), pady=(0, 10))
        ttk.Label(bands, text="QSOs nach Band", style="CardTitle.TLabel").pack(anchor="w", pady=(0, 8))
        ttk.Label(modes, text="QSOs nach Mode", style="CardTitle.TLabel").pack(anchor="w", pady=(0, 8))
        self.stats_bands_frame = ttk.Frame(bands, style="Card.TFrame")
        self.stats_bands_frame.pack(fill="both", expand=True)
        self.stats_modes_frame = ttk.Frame(modes, style="Card.TFrame")
        self.stats_modes_frame.pack(fill="both", expand=True)

        countries = self._card(p, row=3, column=0, sticky="nsew", padx=(0, 4))
        calls = self._card(p, row=3, column=1, sticky="nsew", padx=4)
        operators = self._card(p, row=3, column=2, sticky="nsew", padx=4)
        sync = self._card(p, row=3, column=3, sticky="nsew", padx=(4, 0))
        ttk.Label(countries, text="Top Länder / DXCC", style="CardTitle.TLabel").pack(anchor="w", pady=(0, 8))
        ttk.Label(calls, text="Top Calls", style="CardTitle.TLabel").pack(anchor="w", pady=(0, 8))
        ttk.Label(operators, text="QSOs nach Operator", style="CardTitle.TLabel").pack(anchor="w", pady=(0, 8))
        ttk.Label(sync, text="Sync & QSL", style="CardTitle.TLabel").pack(anchor="w", pady=(0, 8))
        self.stats_countries_frame = ttk.Frame(countries, style="Card.TFrame")
        self.stats_countries_frame.pack(fill="both", expand=True)
        self.stats_calls_frame = ttk.Frame(calls, style="Card.TFrame")
        self.stats_calls_frame.pack(fill="both", expand=True)
        self.stats_operators_frame = ttk.Frame(operators, style="Card.TFrame")
        self.stats_operators_frame.pack(fill="both", expand=True)
        self.stats_sync_frame = ttk.Frame(sync, style="Card.TFrame")
        self.stats_sync_frame.pack(fill="both", expand=True)

    def _stats_period_only_qsos(self, qsos: list[dict]) -> list[dict]:
        current = self.stats_operator_var.get() if hasattr(self, "stats_operator_var") else "Alle Operatoren"
        try:
            if hasattr(self, "stats_operator_var"):
                self.stats_operator_var.set("Alle Operatoren")
            return self._stats_filtered_qsos(qsos)
        finally:
            if hasattr(self, "stats_operator_var"):
                self.stats_operator_var.set(current)

    def _stats_filtered_qsos(self, qsos: list[dict]) -> list[dict]:
        period = self.stats_period_var.get() if hasattr(self, "stats_period_var") else "Gesamt"
        now = datetime.now(timezone.utc)
        filtered = list(qsos)
        if period == "Heute (UTC)":
            key = now.strftime("%Y-%m-%d")
            filtered = [q for q in filtered if q.get("qso_date") == key]
        elif period == "Dieser Monat":
            key = now.strftime("%Y-%m")
            filtered = [q for q in filtered if str(q.get("qso_date", "")).startswith(key)]
        elif period == "Diese Woche":
            current_week = now.date().isocalendar()[:2]
            out = []
            for q in filtered:
                try:
                    d = datetime.strptime(str(q.get("qso_date", "")), "%Y-%m-%d").date()
                    if d.isocalendar()[:2] == current_week:
                        out.append(q)
                except Exception:
                    pass
            filtered = out
        elif period == "Dieses Jahr":
            key = now.strftime("%Y")
            filtered = [q for q in filtered if str(q.get("qso_date", "")).startswith(key)]

        operator = self.stats_operator_var.get() if hasattr(self, "stats_operator_var") else "Alle Operatoren"
        if operator and operator != "Alle Operatoren":
            filtered = [q for q in filtered if str(q.get("operator_call") or "").upper() == operator.upper()]
        return filtered

    def _render_stat_bars(self, parent, counts: Counter, total: int, max_rows: int = 7):
        for w in parent.winfo_children():
            w.destroy()
        rows = [(str(k), int(v)) for k, v in counts.most_common(max_rows) if str(k).strip()]
        if not rows:
            tk.Label(parent, text="Noch keine Daten", bg=CARD, fg=MUTED, font=("Segoe UI", 9)).pack(anchor="w", pady=8)
            return
        maximum = max(v for _, v in rows) or 1
        parent.columnconfigure(1, weight=1)
        for r, (name, count) in enumerate(rows):
            label = name if len(name) <= 24 else name[:22] + "…"
            tk.Label(parent, text=label, bg=CARD, fg=TEXT, font=("Segoe UI", 9), anchor="w", width=15).grid(row=r, column=0, sticky="w", pady=2)
            bar = ttk.Progressbar(parent, style="Stats.Horizontal.TProgressbar", orient="horizontal", mode="determinate", maximum=maximum, value=count)
            bar.grid(row=r, column=1, sticky="ew", padx=(7, 8), pady=4)
            pct = (count / total * 100.0) if total else 0.0
            tk.Label(parent, text=f"{count}  ·  {pct:.0f}%", bg=CARD, fg=MUTED, font=("Segoe UI", 8), width=11, anchor="e").grid(row=r, column=2, sticky="e")

    def _render_stat_rank(self, parent, counts: Counter, max_rows: int = 8):
        for w in parent.winfo_children():
            w.destroy()
        rows = [(str(k), int(v)) for k, v in counts.most_common(max_rows) if str(k).strip()]
        if not rows:
            tk.Label(parent, text="Noch keine Daten", bg=CARD, fg=MUTED, font=("Segoe UI", 9)).pack(anchor="w", pady=8)
            return
        for i, (name, count) in enumerate(rows, 1):
            row = tk.Frame(parent, bg=CARD)
            row.pack(fill="x", pady=2)
            tk.Label(row, text=f"{i}.", bg=CARD, fg=MUTED, font=("Segoe UI", 8), width=3, anchor="w").pack(side="left")
            tk.Label(row, text=name if len(name) <= 23 else name[:21] + "…", bg=CARD, fg=TEXT, font=("Segoe UI", 9), anchor="w").pack(side="left", fill="x", expand=True)
            tk.Label(row, text=str(count), bg=CARD, fg=TEXT, font=("Segoe UI Semibold", 9), anchor="e").pack(side="right")

    def _render_sync_stats(self, qsos: list[dict]):
        parent = self.stats_sync_frame
        for w in parent.winfo_children():
            w.destroy()
        linked = local = issues = 0
        qsl = {name: Counter() for name in ("qrz", "lotw", "eqsl", "dcl")}
        pota = sota = wwff = 0
        for q in qsos:
            meta = self.db.get_meta(q.get("local_id", ""))
            if meta and meta.get("wavelog_id") is not None:
                linked += 1
                st = self.db.get_qsl_status(meta.get("wavelog_id"))
                for svc in qsl:
                    qsl[svc][str(st.get(svc, "unknown"))] += 1
            else:
                local += 1
            if meta and meta.get("status") in ("modified", "conflict", "error", "pending_delete"):
                issues += 1
            pota += 1 if q.get("pota_ref") or q.get("my_pota_ref") else 0
            sota += 1 if q.get("sota_ref") or q.get("my_sota_ref") else 0
            wwff += 1 if q.get("wwff_ref") or q.get("my_wwff_ref") else 0

        def add_row(label, value, color=TEXT):
            r = tk.Frame(parent, bg=CARD)
            r.pack(fill="x", pady=2)
            tk.Label(r, text=label, bg=CARD, fg=MUTED, font=("Segoe UI", 9), anchor="w").pack(side="left")
            tk.Label(r, text=value, bg=CARD, fg=color, font=("Segoe UI Semibold", 9), anchor="e").pack(side="right")

        add_row("WAVELOG", str(linked), OK)
        add_row("LOCAL ONLY", str(local), MUTED)
        if issues:
            add_row("Offene Sync-Themen", str(issues), WARN)
        ttk.Separator(parent, orient="horizontal").pack(fill="x", pady=6)
        for svc, label in (("qrz", "QRZ"), ("lotw", "LoTW"), ("eqsl", "eQSL"), ("dcl", "DCL")):
            c = qsl[svc]
            parts = []
            if c.get("confirmed"): parts.append(f"{c['confirmed']} ✓")
            if c.get("sent"): parts.append(f"{c['sent']} ↑")
            if c.get("pending"): parts.append(f"{c['pending']} …")
            if c.get("unknown"): parts.append(f"{c['unknown']} ?")
            if c.get("none"): parts.append(f"{c['none']} —")
            add_row(label, " · ".join(parts) if parts else "—")
        ttk.Separator(parent, orient="horizontal").pack(fill="x", pady=6)
        add_row("Aktivitäten", f"POTA {pota}  ·  SOTA {sota}  ·  WWFF {wwff}")

    def refresh_stats(self):
        if not hasattr(self, "stats_metric_vars"):
            return
        all_qsos = self.store.scan()
        # Operator choices come directly from the ADIF OPERATOR field. This
        # works for personal logs as well as shared/club callsigns.
        operators_all = sorted({str(q.get("operator_call") or "").upper() for q in all_qsos if str(q.get("operator_call") or "").strip()})
        if hasattr(self, "stats_operator_combo"):
            values = ["Alle Operatoren"] + operators_all
            self.stats_operator_combo.configure(values=values)
            if self.stats_operator_var.get() not in values:
                self.stats_operator_var.set("Alle Operatoren")
        period_qsos = self._stats_period_only_qsos(all_qsos)
        operator_counts = Counter((q.get("operator_call") or "Unbekannt").upper() for q in period_qsos)
        qsos = self._stats_filtered_qsos(all_qsos)
        # Fill missing country information in-memory for older ADI records using the offline CTY database.
        enriched = []
        for q in qsos:
            q = dict(q)
            if not q.get("country") and q.get("call"):
                info = self.country_db.lookup(q.get("call", ""))
                if info:
                    q["country"], q["cont"], q["cqz"], q["ituz"] = info.country, info.cont, info.cqz, info.ituz
            enriched.append(q)
        qsos = enriched

        countries = Counter(q.get("country", "") for q in qsos if q.get("country"))
        bands = Counter(q.get("band", "") for q in qsos if q.get("band"))
        modes = Counter(q.get("mode", "") for q in qsos if q.get("mode"))
        calls = Counter(q.get("call", "") for q in qsos if q.get("call"))
        self.stats_metric_vars[0].set(str(len(qsos)))
        self.stats_metric_vars[1].set(str(len(countries)))
        self.stats_metric_vars[2].set(str(len(bands)))
        self.stats_metric_vars[3].set(str(len(modes)))
        self.stats_hint.configure(text=f"{self.stats_period_var.get()} · {self.stats_operator_var.get()} · lokale ADI-Daten")
        self._render_stat_bars(self.stats_bands_frame, bands, len(qsos), 8)
        self._render_stat_bars(self.stats_modes_frame, modes, len(qsos), 8)
        self._render_stat_rank(self.stats_countries_frame, countries, 8)
        self._render_stat_rank(self.stats_calls_frame, calls, 8)
        self._render_stat_rank(self.stats_operators_frame, operator_counts, 8)
        self._render_sync_stats(qsos)

    # ---------- CAT / Hamlib ----------
    def _build_cat_page(self):
        p = self._new_page("cat")
        p.columnconfigure(0, weight=1)
        p.columnconfigure(1, weight=1)
        p.rowconfigure(0, weight=1)

        left = self._card(p, row=0, column=0, sticky="nsew", padx=(0, 8))
        left.columnconfigure(0, weight=1)
        ttk.Label(left, text="Funkgerät & Schnittstelle", style="CardTitle.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(
            left,
            text="CAT-Einstellungen gehören zum aktiven Logger-Profil. Hamlib wird von der Anwendung selbst verwaltet.",
            style="Muted.Card.TLabel",
            wraplength=470,
        ).grid(row=1, column=0, sticky="w", pady=(3, 10))

        ttk.Label(
            left,
            text="CAT wird nach jedem Programmstart bewusst manuell gestartet.",
            style="Muted.Card.TLabel",
        ).grid(row=2, column=0, sticky="w", pady=(2, 10))

        self.cat_model_search_var = tk.StringVar()
        self.cat_model_var = tk.StringVar()
        self.cat_saved_model_id = 0
        ttk.Label(left, text="Funkgerät suchen", style="Card.TLabel").grid(row=3, column=0, sticky="w", pady=(5, 3))
        model_search = ttk.Entry(left, textvariable=self.cat_model_search_var)
        model_search.grid(row=4, column=0, sticky="ew")
        model_search.bind("<KeyRelease>", lambda _event: self._filter_cat_models())
        ttk.Label(left, text="Hamlib-Funkgerät", style="Card.TLabel").grid(row=5, column=0, sticky="w", pady=(8, 3))
        self.cat_model_combo = ttk.Combobox(left, textvariable=self.cat_model_var, state="readonly")
        self.cat_model_combo.grid(row=6, column=0, sticky="ew")
        self.cat_model_combo.bind("<<ComboboxSelected>>", self._cat_model_selected)

        ttk.Label(left, text="CAT-/COM-Schnittstelle", style="Card.TLabel").grid(row=7, column=0, sticky="w", pady=(10, 3))
        port_row = ttk.Frame(left, style="Card.TFrame")
        port_row.grid(row=8, column=0, sticky="ew")
        port_row.columnconfigure(0, weight=1)
        self.cat_device_var = tk.StringVar()
        self.cat_device_combo = ttk.Combobox(port_row, textvariable=self.cat_device_var, state="normal")
        self.cat_device_combo.grid(row=0, column=0, sticky="ew")
        ttk.Button(port_row, text="Neu laden", style="Secondary.TButton", command=self._refresh_cat_ports).grid(row=0, column=1, padx=(6, 0))

        ttk.Label(left, text="Baudrate", style="Card.TLabel").grid(row=9, column=0, sticky="w", pady=(10, 3))
        self.cat_baud_var = tk.StringVar(value="9600")
        ttk.Combobox(
            left,
            textvariable=self.cat_baud_var,
            values=[str(x) for x in CAT_BAUD_RATES],
            state="readonly",
        ).grid(row=10, column=0, sticky="ew")

        serial = ttk.LabelFrame(left, text="Serielle Parameter", padding=10)
        serial.grid(row=11, column=0, sticky="ew", pady=(14, 0))
        for column in range(2):
            serial.columnconfigure(column, weight=1)
        self.cat_data_bits_var = tk.StringVar(value="8")
        self.cat_stop_bits_var = tk.StringVar(value="1")
        self.cat_parity_var = tk.StringVar(value="None")
        self.cat_handshake_var = tk.StringVar(value="None")
        pairs = (
            ("Datenbits", self.cat_data_bits_var, [str(x) for x in CAT_DATA_BITS]),
            ("Stoppbits", self.cat_stop_bits_var, [str(x) for x in CAT_STOP_BITS]),
            ("Parität", self.cat_parity_var, list(CAT_PARITIES)),
            ("Flusssteuerung", self.cat_handshake_var, list(CAT_HANDSHAKES)),
        )
        for index, (label, variable, values) in enumerate(pairs):
            row, column = divmod(index, 2)
            ttk.Label(serial, text=label, style="Card.TLabel").grid(row=row * 2, column=column, sticky="w", padx=(0, 8), pady=(0 if row == 0 else 8, 3))
            ttk.Combobox(serial, textvariable=variable, values=values, state="readonly", width=16).grid(row=row * 2 + 1, column=column, sticky="ew", padx=(0, 8))

        right = self._card(p, row=0, column=1, sticky="nsew", padx=(8, 0))
        right.columnconfigure(0, weight=1)
        ttk.Label(right, text="Interne Hamlib-Steuerung", style="CardTitle.TLabel").grid(row=0, column=0, sticky="w")
        self.cat_hamlib_info = tk.Label(
            right,
            text="Hamlib wird geprüft …",
            bg=CARD,
            fg=MUTED,
            font=("Segoe UI", 9),
            justify="left",
            anchor="w",
            wraplength=470,
        )
        self.cat_hamlib_info.grid(row=1, column=0, sticky="ew", pady=(4, 12))

        advanced = ttk.LabelFrame(right, text="Erweitert", padding=10)
        advanced.grid(row=2, column=0, sticky="ew")
        advanced.columnconfigure(1, weight=1)
        self.cat_port_var = tk.StringVar(value="4532")
        self.cat_poll_var = tk.StringVar(value="1000")
        self.cat_dtr_var = tk.StringVar(value="Unset")
        self.cat_rts_var = tk.StringVar(value="Unset")
        advanced_fields = (
            ("Lokaler rigctld-Port", self.cat_port_var, None),
            ("Abfrageintervall (ms)", self.cat_poll_var, ("250", "500", "750", "1000", "1500", "2000")),
            ("DTR", self.cat_dtr_var, CAT_LINE_STATES),
            ("RTS", self.cat_rts_var, CAT_LINE_STATES),
        )
        for row, (label, variable, values) in enumerate(advanced_fields):
            ttk.Label(advanced, text=label, style="Card.TLabel").grid(row=row, column=0, sticky="w", padx=(0, 12), pady=5)
            if values:
                widget = ttk.Combobox(advanced, textvariable=variable, values=list(values), state="readonly")
            else:
                widget = ttk.Entry(advanced, textvariable=variable)
            widget.grid(row=row, column=1, sticky="ew", pady=5)

        ttk.Separator(right).grid(row=3, column=0, sticky="ew", pady=16)
        ttk.Label(right, text="CAT-Status", style="CardTitle.TLabel").grid(row=4, column=0, sticky="w")
        self.cat_status_label = tk.Label(
            right,
            text="CAT ist deaktiviert.",
            bg=CARD,
            fg=MUTED,
            font=("Segoe UI", 10),
            justify="left",
            anchor="nw",
            wraplength=470,
        )
        self.cat_status_label.grid(row=5, column=0, sticky="ew", pady=(6, 12))

        buttons = ttk.Frame(right, style="Card.TFrame")
        buttons.grid(row=6, column=0, sticky="ew")
        ttk.Button(buttons, text="Einstellungen speichern", style="Secondary.TButton", command=self.save_cat_settings).pack(side="left")
        self.cat_start_button = ttk.Button(buttons, text="CAT starten", style="Primary.TButton", command=self.start_cat)
        self.cat_start_button.pack(side="left", padx=8)
        ttk.Button(buttons, text="CAT stoppen", style="Secondary.TButton", command=self.stop_cat).pack(side="left")
        ttk.Button(buttons, text="Verbindung testen", style="Secondary.TButton", command=self.test_cat_connection).pack(side="left", padx=(8, 0))

        hint = tk.Label(
            right,
            text=(
                "Frequenz und der vom Funkgerät gemeldete Modus werden automatisch in normales und Contest-Logging übernommen. "
                "Digitale Betriebsarten wie FT8 kann CAT allein nicht sicher erkennen; ein bereits gewählter Digitalmodus bleibt deshalb erhalten."
            ),
            bg=CARD,
            fg=MUTED,
            font=("Segoe UI", 9),
            justify="left",
            wraplength=470,
        )
        hint.grid(row=7, column=0, sticky="w", pady=(16, 0))
        self.after(50, self._load_cat_runtime_info)

    def _load_cat_runtime_info(self):
        def worker():
            try:
                models = list_rig_models()
                version = hamlib_version()
                if not self.closing:
                    self.after(0, lambda: self._cat_runtime_loaded(models, version))
            except Exception as exc:
                if not self.closing:
                    self.after(0, lambda: self._cat_runtime_failed(str(exc)))

        threading.Thread(target=worker, name="cat-runtime-info", daemon=True).start()

    def _cat_runtime_loaded(self, models: list[RigModel], version: str):
        self.cat_models = models
        self.cat_hamlib_info.configure(
            text=f"✓ {version}\n{len(models)} Funkgerätemodelle · vollständig lokal gebündelt · keine separate Installation",
            fg=OK,
        )
        self._filter_cat_models()
        self._select_cat_model_id(self.cat_saved_model_id)

    def _cat_runtime_failed(self, message: str):
        self.cat_hamlib_info.configure(text="✕ " + message, fg=ERR)
        self.cat_status_label.configure(text="Hamlib ist nicht verfügbar.", fg=ERR)

    def _filter_cat_models(self):
        query = self.cat_model_search_var.get().strip().casefold()
        selected_id = self._selected_cat_model_id() or self.cat_saved_model_id
        models = self.cat_models
        if query:
            models = [
                model for model in models
                if query in model.manufacturer.casefold()
                or query in model.model.casefold()
                or query == str(model.model_id)
            ]
        self.cat_model_by_label = {model.label: model for model in models}
        labels = list(self.cat_model_by_label)
        self.cat_model_combo.configure(values=labels)
        if selected_id:
            self._select_cat_model_id(selected_id, labels_only=True)

    def _select_cat_model_id(self, model_id: int, labels_only: bool = False):
        if not model_id:
            return
        pool = self.cat_model_by_label if labels_only else {model.label: model for model in self.cat_models}
        for label, model in pool.items():
            if model.model_id == model_id:
                self.cat_model_var.set(label)
                self.cat_saved_model_id = model_id
                return

    def _selected_cat_model_id(self) -> int:
        selected = self.cat_model_by_label.get(self.cat_model_var.get())
        if selected:
            return selected.model_id
        match = re.search(r"\[ID\s+(\d+)\]", self.cat_model_var.get())
        return int(match.group(1)) if match else 0

    def _cat_model_selected(self, _event=None):
        selected_id = self._selected_cat_model_id()
        if selected_id:
            self.cat_saved_model_id = selected_id

    def _refresh_cat_ports(self):
        if not hasattr(self, "cat_device_combo"):
            return
        ports = list_serial_ports()
        current = self.cat_device_var.get().strip()
        if current and current not in ports:
            ports.append(current)
        self.cat_device_combo.configure(values=ports)
        if not current and len(ports) == 1:
            self.cat_device_var.set(ports[0])

    def _load_cat_settings_to_ui(self):
        config = CatConfig.from_getter(self.db.get_setting)
        self.cat_saved_model_id = config.model_id
        self.cat_device_var.set(config.device)
        self.cat_baud_var.set(str(config.baud))
        self.cat_data_bits_var.set(str(config.data_bits))
        self.cat_stop_bits_var.set(str(config.stop_bits))
        self.cat_parity_var.set(config.parity)
        self.cat_handshake_var.set(config.handshake)
        self.cat_dtr_var.set(config.dtr_state)
        self.cat_rts_var.set(config.rts_state)
        self.cat_port_var.set(str(config.port))
        self.cat_poll_var.set(str(config.poll_interval_ms))
        self.cat_model_search_var.set("")
        self._filter_cat_models()
        self._select_cat_model_id(config.model_id)
        self._refresh_cat_ports()
        self.cat_status_label.configure(
            text="CAT ist ausgeschaltet · zum Verbinden bitte CAT starten.",
            fg=MUTED,
        )

    def _cat_config_from_ui(self, *, enabled: bool = False) -> CatConfig:
        model_id = self._selected_cat_model_id() or self.cat_saved_model_id
        return CatConfig(
            enabled=enabled,
            model_id=model_id,
            device=self.cat_device_var.get().strip(),
            baud=int(self.cat_baud_var.get().strip()),
            data_bits=int(self.cat_data_bits_var.get().strip()),
            stop_bits=int(self.cat_stop_bits_var.get().strip()),
            parity=self.cat_parity_var.get(),
            handshake=self.cat_handshake_var.get(),
            dtr_state=self.cat_dtr_var.get(),
            rts_state=self.cat_rts_var.get(),
            port=int(self.cat_port_var.get().strip()),
            poll_interval_ms=int(self.cat_poll_var.get().strip()),
        )

    def _store_cat_config(self, config: CatConfig):
        for key, value in config.settings().items():
            self.db.set_setting(key, value)

    def save_cat_settings(self):
        try:
            # Runtime state is deliberately not persisted. Every application
            # start begins with CAT off until the user starts it explicitly.
            config = self._cat_config_from_ui(enabled=False)
            config.validate()
            self._store_cat_config(config)
            if self.cat_manager.running:
                message = "CAT-Einstellungen gespeichert · Änderungen gelten nach CAT stoppen und erneut starten."
            else:
                message = "CAT-Einstellungen gespeichert · CAT bleibt ausgeschaltet."
            self.cat_status_label.configure(text=message, fg=OK)
            self.status_var.set("CAT-Einstellungen gespeichert")
        except Exception as exc:
            messagebox.showerror("CAT Setup", str(exc), parent=self)

    def start_cat(self):
        try:
            config = self._cat_config_from_ui(enabled=True)
            config.validate()
        except Exception as exc:
            messagebox.showerror("CAT starten", str(exc), parent=self)
            return
        self._start_cat_runtime(config, notify=True)

    def _start_cat_runtime(self, config: CatConfig, *, notify: bool):
        self.cat_generation += 1
        generation = self.cat_generation
        self._cancel_cat_poll()
        self.cat_start_button.configure(state="disabled")
        self.cat_status_label.configure(text="CAT wird gestartet …", fg=MUTED)
        self.status_var.set("CAT wird gestartet …")

        def worker():
            try:
                self.cat_manager.start(config)
                if not self.closing:
                    self.after(0, lambda: self._cat_started(generation, config, notify))
            except Exception as exc:
                if not self.closing:
                    self.after(0, lambda: self._cat_start_failed(generation, str(exc), notify))

        threading.Thread(target=worker, name="cat-start", daemon=True).start()

    def _cat_started(self, generation: int, config: CatConfig, notify: bool):
        if generation != self.cat_generation or self.closing:
            return
        self.cat_start_button.configure(state="normal")
        self.cat_status_label.configure(text="✓ CAT verbunden · warte auf Funkgerätedaten …", fg=OK)
        self.status_var.set("CAT verbunden")
        self._schedule_cat_poll(0, config.poll_interval_ms)
        if notify:
            messagebox.showinfo("CAT Setup", "CAT wurde erfolgreich gestartet.", parent=self)

    def _cat_start_failed(self, generation: int, message: str, notify: bool):
        if generation != self.cat_generation or self.closing:
            return
        self.cat_start_button.configure(state="normal")
        self.cat_status_label.configure(text="✕ " + message, fg=ERR)
        self.status_var.set("CAT-Verbindung fehlgeschlagen")
        if notify:
            messagebox.showerror("CAT-Verbindung", message, parent=self)

    def _schedule_cat_poll(self, delay_ms: int, interval_ms: int):
        self._cancel_cat_poll()
        if not self.closing:
            self.cat_poll_job = self.after(delay_ms, lambda: self._cat_poll(interval_ms))

    def _cancel_cat_poll(self):
        if self.cat_poll_job is not None:
            try:
                self.after_cancel(self.cat_poll_job)
            except Exception:
                pass
            self.cat_poll_job = None

    def _cat_poll(self, interval_ms: int):
        self.cat_poll_job = None
        if self.closing or not self.cat_manager.running:
            return
        if self.cat_poll_busy:
            self._schedule_cat_poll(interval_ms, interval_ms)
            return
        self.cat_poll_busy = True
        generation = self.cat_generation
        current_mode = self.mode_var.get()

        def worker():
            try:
                reading = self.cat_manager.read(current_mode)
                if not self.closing:
                    self.after(0, lambda: self._cat_poll_ok(generation, reading, interval_ms))
            except Exception as exc:
                if not self.closing:
                    self.after(0, lambda: self._cat_poll_failed(generation, str(exc), interval_ms))

        threading.Thread(target=worker, name="cat-poll", daemon=True).start()

    def _cat_poll_ok(self, generation: int, reading, interval_ms: int):
        self.cat_poll_busy = False
        if generation != self.cat_generation or self.closing:
            return
        frequency = format_frequency_mhz(reading.frequency_hz)
        if frequency:
            self.freq_var.set(frequency)
            self.contest_freq_var.set(frequency)
            band = band_from_mhz(reading.frequency_hz / 1_000_000)
            if band:
                self.band_var.set(band)
                self.contest_band_var.set(band)
        normal_mode = map_hamlib_mode(reading.raw_mode, self.mode_var.get())
        contest_mode = map_hamlib_mode(reading.raw_mode, self.contest_mode_var.get())
        if normal_mode in MODES:
            self.mode_var.set(normal_mode)
        if contest_mode in MODES:
            self.contest_mode_var.set(contest_mode)
        display_mode = normal_mode if normal_mode == contest_mode else f"{normal_mode} / Contest {contest_mode}"
        self.cat_status_label.configure(
            text=f"✓ CAT verbunden\nFrequenz: {frequency or '—'} MHz\nHamlib-Modus: {reading.raw_mode} · Logger-Modus: {display_mode or 'unverändert'}",
            fg=OK,
        )
        self._schedule_cat_poll(interval_ms, interval_ms)

    def _cat_poll_failed(self, generation: int, message: str, interval_ms: int):
        self.cat_poll_busy = False
        if generation != self.cat_generation or self.closing:
            return
        self.cat_status_label.configure(text="CAT-Lesefehler: " + message, fg=WARN)
        self._schedule_cat_poll(max(interval_ms, 1500), interval_ms)

    def test_cat_connection(self):
        try:
            config = self._cat_config_from_ui(enabled=True)
            config.validate()
        except Exception as exc:
            messagebox.showerror("CAT-Verbindung", str(exc), parent=self)
            return
        self.cat_generation += 1
        generation = self.cat_generation
        self._cancel_cat_poll()
        self.cat_status_label.configure(text="CAT-Test läuft …", fg=MUTED)

        def worker():
            try:
                self.cat_manager.start(config)
                reading = self.cat_manager.read(self.mode_var.get())
                self.cat_manager.stop()
                if not self.closing:
                    self.after(0, lambda: self._cat_test_ok(generation, reading))
            except Exception as exc:
                self.cat_manager.stop()
                if not self.closing:
                    self.after(0, lambda: self._cat_start_failed(generation, str(exc), True))

        threading.Thread(target=worker, name="cat-test", daemon=True).start()

    def _cat_test_ok(self, generation: int, reading):
        if generation != self.cat_generation or self.closing:
            return
        frequency = format_frequency_mhz(reading.frequency_hz)
        self.cat_status_label.configure(
            text=f"✓ CAT-Test erfolgreich\nFrequenz: {frequency} MHz\nModus: {reading.raw_mode}",
            fg=OK,
        )
        messagebox.showinfo(
            "CAT-Verbindung",
            f"Verbindung erfolgreich.\n\nFrequenz: {frequency} MHz\nHamlib-Modus: {reading.raw_mode}\n\nCAT bleibt nach dem Test ausgeschaltet.",
            parent=self,
        )
        self.cat_status_label.configure(
            text=f"✓ CAT-Test erfolgreich · CAT ist ausgeschaltet\nFrequenz: {frequency} MHz\nModus: {reading.raw_mode}",
            fg=OK,
        )

    def stop_cat(self):
        self._stop_cat_runtime()
        self.cat_status_label.configure(text="CAT ist ausgeschaltet.", fg=MUTED)
        self.status_var.set("CAT gestoppt")

    def _stop_cat_runtime(self, *, update_ui: bool = True):
        self.cat_generation += 1
        self._cancel_cat_poll()
        self.cat_poll_busy = False
        self.cat_manager.stop()
        if update_ui and hasattr(self, "cat_status_label"):
            self.cat_status_label.configure(text="CAT ist gestoppt.", fg=MUTED)

    # ---------- settings ----------
    def _build_settings_page(self):
        p = self._new_page("settings")
        p.columnconfigure(0, weight=1)
        p.columnconfigure(1, weight=1)
        p.rowconfigure(0, weight=1)

        left = self._card(p, row=0, column=0, sticky="nsew", padx=(0, 8))
        left.columnconfigure(1, weight=1)
        ttk.Label(left, text="Offline-Stationsprofil", style="CardTitle.TLabel").grid(row=0, column=0, columnspan=2, sticky="w")
        ttk.Label(left, text="Diese Daten werden in deine ADI-Dateien geschrieben und funktionieren auch komplett ohne Internet.", style="Muted.Card.TLabel", wraplength=450).grid(row=1, column=0, columnspan=2, sticky="w", pady=(3, 12))
        self.set_operator = tk.StringVar()
        self.set_station = tk.StringVar()
        self.set_locator = tk.StringVar()
        self.set_qth = tk.StringVar()
        self.set_power = tk.StringVar()
        self.set_pota = tk.StringVar()
        self.set_sota = tk.StringVar()
        self.set_wwff = tk.StringVar()
        self._settings_row(left, "Operator-Rufzeichen", self.set_operator, 2)
        self._settings_row(left, "Stationsrufzeichen", self.set_station, 3)
        self._settings_row(left, "Eigener Locator", self.set_locator, 4)
        self._settings_row(left, "QTH / Ort", self.set_qth, 5)
        self._settings_row(left, "Standardleistung (W)", self.set_power, 6)
        ttk.Separator(left).grid(row=7, column=0, columnspan=2, sticky="ew", pady=14)
        ttk.Label(left, text="Aktuelle Aktivierung (optional)", style="CardTitle.TLabel").grid(row=8, column=0, columnspan=2, sticky="w", pady=(0,4))
        self._settings_row(left, "POTA-Referenz", self.set_pota, 9)
        self._settings_row(left, "SOTA-Referenz", self.set_sota, 10)
        self._settings_row(left, "WWFF-Referenz", self.set_wwff, 11)
        hint = tk.Label(left, text="Die Aktivierungsreferenzen werden automatisch als MY_* Felder in jedes neue QSO geschrieben.", bg=CARD, fg=MUTED, font=("Segoe UI", 9), justify="left", wraplength=430)
        hint.grid(row=12, column=0, columnspan=2, sticky="w", pady=(12,0))

        right = self._card(p, row=0, column=1, sticky="nsew", padx=(8, 0))
        right.columnconfigure(0, weight=1)
        ttk.Label(right, text="Wavelog Sync", style="CardTitle.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(right, text="API v2 (wl2_… Token). Der Logger bleibt auch ohne Verbindung vollständig nutzbar.", style="Muted.Card.TLabel", wraplength=450).grid(row=1, column=0, sticky="w", pady=(3, 10))
        self.set_url = tk.StringVar()
        self.set_token = tk.StringVar()
        self.set_station_profile = tk.StringVar()
        ttk.Label(right, text="Wavelog URL", style="Card.TLabel").grid(row=2, column=0, sticky="w", pady=(5,3))
        ttk.Entry(right, textvariable=self.set_url).grid(row=3, column=0, sticky="ew")
        ttk.Label(right, text="API-v2 Token", style="Card.TLabel").grid(row=4, column=0, sticky="w", pady=(8, 3))
        ttk.Entry(right, textvariable=self.set_token, show="●").grid(row=5, column=0, sticky="ew")
        ttk.Button(right, text="Verbindung testen & Profile laden", style="Secondary.TButton", command=self.test_wavelog).grid(row=6, column=0, sticky="w", pady=(10, 8))
        self.connection_label = tk.Label(right, text="", bg=CARD, fg=MUTED, font=("Segoe UI", 9), justify="left", anchor="w", wraplength=450)
        self.connection_label.grid(row=7, column=0, sticky="ew")
        ttk.Label(right, text="Wavelog-Stationsprofil", style="Card.TLabel").grid(row=8, column=0, sticky="w", pady=(12, 3))
        self.station_combo = ttk.Combobox(right, textvariable=self.set_station_profile, state="readonly")
        self.station_combo.grid(row=9, column=0, sticky="ew")
        self.station_combo.bind("<<ComboboxSelected>>", lambda e: self._station_selection_changed())
        ttk.Button(right, text="Werte aus Wavelog-Profil übernehmen", style="Secondary.TButton", command=self.copy_station_values).grid(row=10, column=0, sticky="w", pady=(8, 12))

        ttk.Separator(right).grid(row=11, column=0, sticky="ew", pady=8)
        ttk.Label(right, text="Logdateien", style="CardTitle.TLabel").grid(row=12, column=0, sticky="w")
        self.set_log_dir = tk.StringVar()
        logrow = ttk.Frame(right, style="Card.TFrame")
        logrow.grid(row=13, column=0, sticky="ew", pady=(6, 0))
        logrow.columnconfigure(0, weight=1)
        ttk.Entry(logrow, textvariable=self.set_log_dir).grid(row=0, column=0, sticky="ew")
        ttk.Button(logrow, text="…", width=4, command=self.choose_log_dir).grid(row=0, column=1, padx=(6, 0))

        savebar = ttk.Frame(right, style="Card.TFrame")
        savebar.grid(row=14, column=0, sticky="ew", pady=(18, 0))
        ttk.Button(savebar, text="Einstellungen speichern", style="Primary.TButton", command=self.save_settings).pack(side="left")

    def _settings_row(self, parent, label, var, row):
        ttk.Label(parent, text=label, style="Card.TLabel").grid(row=row, column=0, sticky="w", padx=(0,12), pady=7)
        ttk.Entry(parent, textvariable=var).grid(row=row, column=1, sticky="ew", pady=7)

    def _load_settings_to_ui(self):
        self.set_operator.set(self.db.get_setting("operator_call", ""))
        self.set_station.set(self.db.get_setting("station_call", ""))
        self.set_locator.set(self.db.get_setting("locator", ""))
        self.set_qth.set(self.db.get_setting("qth", ""))
        self.set_power.set(self.db.get_setting("default_power", ""))
        self.set_pota.set(self.db.get_setting("my_pota_ref", ""))
        self.set_sota.set(self.db.get_setting("my_sota_ref", ""))
        self.set_wwff.set(self.db.get_setting("my_wwff_ref", ""))
        self.set_url.set(self.db.get_setting("wavelog_url", ""))
        self.set_token.set(self.db.get_token())
        self.set_log_dir.set(self.db.get_setting("log_dir", str(self.store.log_dir)))
        self.time_mode_var.set(self.db.get_setting("time_mode", "UTC") or "UTC")
        self.form_vars["tx_pwr"].set(self.db.get_setting("default_power", ""))
        self._update_profile_summary()
        self._set_current_qso_time()
        self._load_cat_settings_to_ui()

        # If Wavelog was configured before, profile labels are loaded only on explicit test.
        sid = self.db.get_setting("station_profile_id", "")
        if sid:
            self.set_station_profile.set(f"Profil-ID {sid}")

    def save_settings(self):
        try:
            if self.set_power.get().strip():
                float(self.set_power.get().replace(",", "."))
            self.db.set_setting("operator_call", self.set_operator.get().strip().upper())
            self.db.set_setting("station_call", self.set_station.get().strip().upper())
            self.db.set_setting("locator", self.set_locator.get().strip().upper())
            self.db.set_setting("qth", self.set_qth.get().strip())
            self.db.set_setting("default_power", self.set_power.get().strip().replace(",", "."))
            self.db.set_setting("my_pota_ref", self.set_pota.get().strip().upper())
            self.db.set_setting("my_sota_ref", self.set_sota.get().strip().upper())
            self.db.set_setting("my_wwff_ref", self.set_wwff.get().strip().upper())
            self.db.set_setting("wavelog_url", self.set_url.get().strip())
            self.db.set_token(self.set_token.get().strip())
            self.db.set_setting("log_dir", self.set_log_dir.get().strip())
            selected = self.station_by_label.get(self.set_station_profile.get())
            if selected:
                self.db.set_setting("station_profile_id", selected.get("id"))
            # Keep an existing numeric profile id if the list wasn't loaded in this session.
            self.store.set_dir(Path(self.set_log_dir.get().strip() or self._profile_default_log_dir()))
            self.form_vars["tx_pwr"].set(self.db.get_setting("default_power", ""))
            self._update_profile_summary()
            self._update_logfile_preview()
            self.status_var.set("Einstellungen gespeichert")
            messagebox.showinfo("Einstellungen", "Einstellungen wurden gespeichert.", parent=self)
        except Exception as e:
            messagebox.showerror("Einstellungen", str(e), parent=self)

    def choose_log_dir(self):
        p = filedialog.askdirectory(initialdir=self.set_log_dir.get() or str(self._profile_default_log_dir()), parent=self)
        if p:
            self.set_log_dir.set(p)

    def test_wavelog(self):
        url = self.set_url.get().strip()
        token = self.set_token.get().strip()
        self.connection_label.configure(text="Verbindung wird geprüft …", fg=MUTED)

        def worker():
            try:
                c = WavelogClient(url, token)
                info = c.token_info()
                stations = c.stations()
                if not self.closing:
                    self.after(0, lambda: self._wavelog_test_ok(info, stations))
            except Exception as e:
                if not self.closing:
                    self.after(0, lambda: self._wavelog_test_fail(str(e)))
        threading.Thread(target=worker, name="wavelog-test", daemon=True).start()

    def _wavelog_test_ok(self, info: dict, stations: list[dict]):
        owner = str(info.get("owner") or "")
        scopes = ", ".join(info.get("scopes") or [])
        scope_list = info.get("scopes") or []
        qsl_hint = "" if "confirmation:read" in scope_list else "\n⚠ confirmation:read fehlt – Bestätigungen (✓) sind nicht verfügbar."
        club_hint = ""
        station_call = self.set_station.get().strip().upper()
        if station_call and owner.upper() == station_call and "club:read" not in scope_list:
            club_hint = "\nℹ Clubstation: Für sicheren clubweiten Operator-Abgleich einen Officer-Token mit club:read verwenden."
        warn = bool(qsl_hint)
        self.connection_label.configure(text=f"✓ Token gültig · Owner: {owner or '—'}\nScopes: {scopes or '—'}{qsl_hint}{club_hint}", fg=WARN if warn else OK)
        if not self.set_operator.get().strip() and owner:
            self.set_operator.set(owner.upper())
        self.station_rows = stations
        self.station_by_label.clear()
        labels = []
        chosen = None
        saved_id = self.db.get_setting("station_profile_id", "")
        for s in stations:
            label = f"{s.get('name') or 'Station'} · {s.get('callsign') or '?'} · {s.get('gridsquare') or '—'} [ID {s.get('id')}]"
            labels.append(label)
            self.station_by_label[label] = s
            if str(s.get("id")) == saved_id or (not saved_id and s.get("active")):
                chosen = label
        self.station_combo.configure(values=labels)
        if chosen:
            self.set_station_profile.set(chosen)
        elif labels:
            self.set_station_profile.set(labels[0])
        self._station_selection_changed()

    def _wavelog_test_fail(self, msg: str):
        self.connection_label.configure(text="✗ " + msg, fg=ERR)

    def _station_selection_changed(self):
        s = self.station_by_label.get(self.set_station_profile.get())
        if s:
            self.connection_label.configure(text=(self.connection_label.cget("text") + f"\nAusgewählt: {s.get('callsign','')} / {s.get('gridsquare','')}").strip())

    def copy_station_values(self):
        s = self.station_by_label.get(self.set_station_profile.get())
        if not s:
            messagebox.showinfo("Wavelog-Profil", "Bitte zuerst die Verbindung testen und ein Stationsprofil auswählen.", parent=self)
            return
        self.set_station.set(str(s.get("callsign") or "").upper())
        self.set_locator.set(str(s.get("gridsquare") or "").upper())
        self.set_qth.set(str(s.get("city") or ""))
        self.set_power.set(str(s.get("power") or ""))
        self.set_pota.set(str(s.get("pota") or "").upper())
        self.set_sota.set(str(s.get("sota") or "").upper())
        self.set_wwff.set(str(s.get("wwff") or "").upper())
        self.status_var.set("Stationswerte aus Wavelog übernommen · noch nicht gespeichert")

    # ---------- shutdown ----------
    def shutdown(self):
        if self.shutdown_started:
            return
        self.shutdown_started = True
        self.closing = True
        try:
            write_startup_log("Programm wird geschlossen")
            self._stop_cat_runtime(update_ui=False)
            # Every database operation is committed immediately.
            if not self.sync_busy:
                self.db.close()
        except Exception as e:
            write_startup_log("Fehler beim Shutdown: " + repr(e))

    def on_close(self):
        self.shutdown()
        self.destroy()




class ContestPresetDialog(tk.Toplevel):
    def __init__(self, app: LoggerApp, preset: dict | None, callback):
        super().__init__(app)
        self.app=app; self.callback=callback; self.old_name=(preset or {}).get("name")
        self.title("Contest-Preset")
        self.geometry("560x650"); self.resizable(False, False); self.transient(app); self.grab_set(); self.configure(bg=BG)
        box=tk.Frame(self,bg=CARD,highlightbackground=BORDER,highlightthickness=1); box.pack(fill="both",expand=True,padx=18,pady=18)
        inner=ttk.Frame(box,style="Card.TFrame",padding=18); inner.pack(fill="both",expand=True); inner.columnconfigure(1,weight=1)
        p=preset or {}
        self.name=tk.StringVar(value=str(p.get("name") or "")); self.cid=tk.StringVar(value=str(p.get("contest_id") or ""))
        self.serial=tk.BooleanVar(value=bool(p.get("use_serial",True))); self.grid=tk.BooleanVar(value=bool(p.get("use_grid",False))); self.text=tk.BooleanVar(value=bool(p.get("use_text",False)))
        self.sent=tk.StringVar(value=str(p.get("sent_exchange") or "")); self.start=tk.StringVar(value=str(p.get("start_serial") or "1"))
        self.freq=tk.StringVar(value=str(p.get("freq") or "")); self.band=tk.StringVar(value=str(p.get("band") or "2m")); self.mode=tk.StringVar(value=str(p.get("mode") or "SSB")); self.rst=tk.StringVar(value=str(p.get("rst_default") or "59"))
        ttk.Label(inner,text="Contest-Preset",style="CardTitle.TLabel").grid(row=0,column=0,columnspan=2,sticky="w",pady=(0,10))
        fields=(("Name",self.name),("ADIF Contest-ID",self.cid),("Start-Seriennummer",self.start),("Gesendeter Text-Exchange",self.sent),("Standardfrequenz (MHz)",self.freq),("Standard-RST",self.rst))
        for r,(label,var) in enumerate(fields,start=1):
            ttk.Label(inner,text=label,style="Card.TLabel").grid(row=r,column=0,sticky="w",padx=(0,12),pady=5); ttk.Entry(inner,textvariable=var).grid(row=r,column=1,sticky="ew",pady=5)
        ttk.Label(inner,text="Standardband / Mode",style="Card.TLabel").grid(row=7,column=0,sticky="w",padx=(0,12),pady=5)
        bm=ttk.Frame(inner,style="Card.TFrame"); bm.grid(row=7,column=1,sticky="ew",pady=5); bm.columnconfigure(0,weight=1); bm.columnconfigure(1,weight=1)
        ttk.Combobox(bm,textvariable=self.band,values=BANDS,state="readonly",width=10).grid(row=0,column=0,sticky="ew",padx=(0,4))
        ttk.Combobox(bm,textvariable=self.mode,values=MODES,state="readonly",width=10).grid(row=0,column=1,sticky="ew",padx=(4,0))
        ttk.Separator(inner).grid(row=8,column=0,columnspan=2,sticky="ew",pady=10)
        ttk.Label(inner,text="Exchange-Felder",style="CardTitle.TLabel").grid(row=9,column=0,columnspan=2,sticky="w")
        ttk.Checkbutton(inner,text="Seriennummer",variable=self.serial).grid(row=10,column=0,columnspan=2,sticky="w",pady=4)
        ttk.Checkbutton(inner,text="Grid Square",variable=self.grid).grid(row=11,column=0,columnspan=2,sticky="w",pady=4)
        ttk.Checkbutton(inner,text="Exchange (Text)",variable=self.text).grid(row=12,column=0,columnspan=2,sticky="w",pady=4)
        tk.Label(inner,text="Die ADIF Contest-ID muss der von Wavelog/ADIF verwendeten Contest-ID entsprechen.\nSTX/SRX sowie STX_STRING/SRX_STRING werden direkt in ADI und Wavelog geschrieben.",bg=CARD,fg=MUTED,font=("Segoe UI",9),justify="left",wraplength=440).grid(row=13,column=0,columnspan=2,sticky="w",pady=(10,0))
        b=ttk.Frame(inner,style="Card.TFrame"); b.grid(row=14,column=0,columnspan=2,sticky="e",pady=(15,0))
        ttk.Button(b,text="Abbrechen",command=self.destroy).pack(side="right"); ttk.Button(b,text="Speichern",style="Primary.TButton",command=self.save).pack(side="right",padx=8)

    def save(self):
        try:
            name=self.name.get().strip(); cid=self.cid.get().strip().upper()
            if not name: raise ValueError("Bitte einen Namen eingeben")
            if not cid: raise ValueError("Bitte die ADIF Contest-ID eingeben")
            start=int(self.start.get().strip() or "1")
            if start<1: raise ValueError("Start-Seriennummer muss mindestens 1 sein")
            freq=self.freq.get().strip().replace(",", ".")
            if freq: float(freq)
            preset={"name":name,"contest_id":cid,"use_serial":bool(self.serial.get()),"use_grid":bool(self.grid.get()),"use_text":bool(self.text.get()),"sent_exchange":self.sent.get().strip(),"start_serial":start,
                    "freq":freq,"band":self.band.get(),"mode":self.mode.get(),"rst_default":self.rst.get().strip()}
            self.callback(self.old_name,preset); self.destroy()
        except Exception as e:
            messagebox.showerror("Contest-Preset",str(e),parent=self)

class ProfileDeleteDialog(tk.Toplevel):
    """Local-only profile deletion confirmation. Never touches Wavelog."""
    def __init__(self, parent, profile_name: str):
        super().__init__(parent)
        self.result = None
        self.title("Profil lokal löschen")
        self.geometry("560x300")
        self.resizable(False, False)
        self.configure(bg=BG)
        self.transient(parent)
        self.grab_set()
        self.protocol("WM_DELETE_WINDOW", self._cancel)

        outer = ttk.Frame(self, padding=22)
        outer.pack(fill="both", expand=True)
        ttk.Label(outer, text="Profil lokal löschen", style="Title.TLabel").pack(anchor="w")
        tk.Label(outer, text=f"Profil: {profile_name}", bg=BG, fg=TEXT, font=("Segoe UI Semibold", 11)).pack(anchor="w", pady=(12, 5))
        tk.Label(outer, text="Gelöscht werden die lokalen Einstellungen und Sync-Metadaten dieses Logger-Profils.", bg=BG, fg=TEXT, font=("Segoe UI", 10), wraplength=500, justify="left").pack(anchor="w")

        warning = tk.Frame(outer, bg="#fff4e5", highlightbackground="#f0c36d", highlightthickness=1)
        warning.pack(fill="x", pady=14)
        tk.Label(warning, text="Wavelog wird NICHT verändert. Es werden weder QSOs noch Stationsprofile in Wavelog gelöscht.", bg="#fff4e5", fg="#7a4d00", font=("Segoe UI Semibold", 9), wraplength=475, justify="left", padx=12, pady=10).pack(anchor="w")

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
    def __init__(self, parent: LoggerApp):
        super().__init__(parent)
        self.parent = parent
        self.title("Profile verwalten")
        self.geometry("650x430")
        self.minsize(570, 360)
        self.configure(bg=BG)
        self.transient(parent)
        self.grab_set()
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)

        head = ttk.Frame(self, padding=(18, 16, 18, 8))
        head.grid(row=0, column=0, sticky="ew")
        ttk.Label(head, text="Logger-Profile", style="Title.TLabel").pack(anchor="w")
        tk.Label(head, text="Jedes Profil hat eigene Einstellungen, Wavelog-Zugangsdaten, ADI-Dateien und Sync-Metadaten.", bg=BG, fg=MUTED, font=("Segoe UI", 9)).pack(anchor="w", pady=(3,0))

        card = tk.Frame(self, bg=CARD, highlightbackground=BORDER, highlightthickness=1)
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
    def __init__(self, parent: LoggerApp, q: dict, callback):
        super().__init__(parent)
        self.parent = parent
        self.q = q
        self.callback = callback
        self.title(f"QSO bearbeiten · {q.get('call','')}")
        self.geometry("520x600")
        self.transient(parent)
        self.grab_set()
        self.configure(bg=BG)
        frame = ttk.Frame(self, padding=18)
        frame.pack(fill="both", expand=True)
        frame.columnconfigure(1, weight=1)
        self.vars = {}
        fields = [
            ("call","Rufzeichen"),("qso_date","Datum UTC"),("time_on","Zeit UTC HHMMSS"),("freq","Frequenz MHz"),
            ("band","Band"),("mode","Mode"),("rst_sent","RST gesendet"),("rst_rcvd","RST empfangen"),
            ("gridsquare","Locator"),("name","Name"),("qth","QTH"),("pota_ref","POTA Ref"),("sota_ref","SOTA Ref"),
            ("wwff_ref","WWFF Ref"),("tx_pwr","Leistung W"),("comment","Kommentar"),
        ]
        for i, (key, label) in enumerate(fields):
            ttk.Label(frame, text=label).grid(row=i, column=0, sticky="w", padx=(0,10), pady=4)
            v = tk.StringVar(value=str(q.get(key) or ""))
            self.vars[key] = v
            ttk.Entry(frame, textvariable=v).grid(row=i, column=1, sticky="ew", pady=4)
        ttk.Label(frame, text="Notizen").grid(row=len(fields), column=0, sticky="nw", pady=4)
        self.notes = tk.Text(frame, height=4, wrap="word", font=("Segoe UI", 9))
        self.notes.grid(row=len(fields), column=1, sticky="ew", pady=4)
        self.notes.insert("1.0", str(q.get("notes") or ""))
        btn = ttk.Frame(frame)
        btn.grid(row=len(fields)+1, column=0, columnspan=2, sticky="e", pady=(14,0))
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


def main():
    app = None
    try:
        app = LoggerApp()
        try:
            app.mainloop()
        finally:
            app.shutdown()
    except Exception:
        err = traceback.format_exc()
        write_startup_log("FATAL:\n" + err)
        try:
            root = tk.Tk(); root.withdraw()
            messagebox.showerror("DA6IT.de Logger – Startfehler", "Die Anwendung konnte nicht gestartet werden.\n\nDetails stehen in:\n" + str(app_data_dir()/"startup.log"))
            root.destroy()
        except Exception:
            pass
        raise


if __name__ == "__main__":
    main()
