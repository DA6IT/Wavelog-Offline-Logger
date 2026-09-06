from __future__ import annotations

import atexit
import re
import sys
import threading
import time
import tkinter as tk
from tkinter import messagebox, ttk
from cat_control import (
    CAT_BAUD_RATES, CAT_DATA_BITS, CAT_HANDSHAKES, CAT_LINE_STATES, CAT_PARITIES, CAT_STOP_BITS, CatConfig, DEFAULT_FLRIG_ENDPOINT, FLRIG_MODEL_ID, HamlibManager, discover_flrig, find_hamlib_dir, format_frequency_mhz, hamlib_version, list_rig_models, list_serial_ports, map_hamlib_mode,
)
from hamlib_update import (
    backup_hamlib_dir, find_latest_windows_release, install_windows_release, restore_previous_windows_runtime, runtime_version, usable_hamlib_dir, version_from_output,
)
from logger_core import MODES, band_from_mhz, secure_urlopen
from ui_theme import theme


class CatFeatureMixin:
    def _init_cat_feature(self) -> None:
        self.cat_manager = HamlibManager()
        atexit.register(self.cat_manager.stop)
        self.cat_models: list[RigModel] = []
        self.cat_model_by_label: dict[str, RigModel] = {}
        self.cat_generation = 0
        self.cat_poll_job = None
        self.cat_poll_busy = False
        self.cat_starting = False
        self.hamlib_update_busy = False
        self.tuner_busy = False
        self.tuner_start_pending = False

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
        self.cat_ui_model_id = 0
        self.cat_serial_device = ""
        self.cat_flrig_endpoint = DEFAULT_FLRIG_ENDPOINT
        self.flrig_search_generation = 0
        ttk.Label(left, text="Funkgerät suchen", style="Card.TLabel").grid(row=3, column=0, sticky="w", pady=(5, 3))
        model_search = ttk.Entry(left, textvariable=self.cat_model_search_var)
        model_search.grid(row=4, column=0, sticky="ew")
        model_search.bind("<KeyRelease>", lambda _event: self._filter_cat_models())
        ttk.Label(left, text="Hamlib-Funkgerät", style="Card.TLabel").grid(row=5, column=0, sticky="w", pady=(8, 3))
        self.cat_model_combo = ttk.Combobox(left, textvariable=self.cat_model_var, state="readonly")
        self.cat_model_combo.grid(row=6, column=0, sticky="ew")
        self.cat_model_combo.bind("<<ComboboxSelected>>", self._cat_model_selected)

        self.cat_device_label = ttk.Label(left, text="CAT-/COM-Schnittstelle", style="Card.TLabel")
        self.cat_device_label.grid(row=7, column=0, sticky="w", pady=(10, 3))
        port_row = ttk.Frame(left, style="Card.TFrame")
        port_row.grid(row=8, column=0, sticky="ew")
        port_row.columnconfigure(0, weight=1)
        self.cat_device_var = tk.StringVar()
        self.cat_device_combo = ttk.Combobox(port_row, textvariable=self.cat_device_var, state="normal")
        self.cat_device_combo.grid(row=0, column=0, sticky="ew")
        self.cat_device_action_button = ttk.Button(
            port_row, text="Neu laden", style="Secondary.TButton", command=self._refresh_cat_ports,
        )
        self.cat_device_action_button.grid(row=0, column=1, padx=(6, 0))

        self.cat_baud_label = ttk.Label(left, text="Baudrate", style="Card.TLabel")
        self.cat_baud_label.grid(row=9, column=0, sticky="w", pady=(10, 3))
        self.cat_baud_var = tk.StringVar(value="9600")
        self.cat_baud_combo = ttk.Combobox(
            left,
            textvariable=self.cat_baud_var,
            values=[str(x) for x in CAT_BAUD_RATES],
            state="readonly",
        )
        self.cat_baud_combo.grid(row=10, column=0, sticky="ew")

        self.cat_serial_frame = ttk.LabelFrame(left, text="Serielle Parameter", padding=10)
        self.cat_serial_frame.grid(row=11, column=0, sticky="ew", pady=(14, 0))
        serial = self.cat_serial_frame
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
            bg=theme.CARD,
            fg=theme.MUTED,
            font=("Segoe UI", 9),
            justify="left",
            anchor="w",
            wraplength=470,
        )
        self.cat_hamlib_info.grid(row=1, column=0, sticky="ew", pady=(4, 12))

        self.hamlib_update_frame = ttk.LabelFrame(right, text="Hamlib-Updates", padding=10)
        self.hamlib_update_frame.grid(row=2, column=0, sticky="ew", pady=(0, 12))
        self.hamlib_update_frame.columnconfigure(0, weight=1)
        self.hamlib_update_status = ttk.Label(
            self.hamlib_update_frame,
            text="Die Update-Prüfung wird nur von Hand gestartet.",
            style="Muted.Card.TLabel",
            wraplength=450,
        )
        self.hamlib_update_status.grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 8))
        update_actions = ttk.Frame(self.hamlib_update_frame, style="Card.TFrame")
        update_actions.grid(row=1, column=0, columnspan=2, sticky="ew")
        self.hamlib_update_button = ttk.Button(
            update_actions, text="Nach Update suchen", style="Secondary.TButton",
            command=self._check_hamlib_update,
        )
        self.hamlib_update_button.pack(side="left")
        self.hamlib_restore_button = ttk.Button(
            update_actions, text="Vorherige Version wiederherstellen", style="Secondary.TButton",
            command=self._restore_previous_hamlib,
        )
        self.hamlib_restore_button.pack(side="left", padx=(8, 0))
        self.hamlib_update_progress = ttk.Progressbar(
            self.hamlib_update_frame, mode="indeterminate", length=120,
        )

        advanced = ttk.LabelFrame(right, text="Erweitert", padding=10)
        advanced.grid(row=3, column=0, sticky="ew")
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

        ttk.Separator(right).grid(row=4, column=0, sticky="ew", pady=16)
        ttk.Label(right, text="CAT-Status", style="CardTitle.TLabel").grid(row=5, column=0, sticky="w")
        self.cat_status_label = tk.Label(
            right,
            text="CAT ist deaktiviert.",
            bg=theme.CARD,
            fg=theme.MUTED,
            font=("Segoe UI", 10),
            justify="left",
            anchor="nw",
            wraplength=470,
        )
        self.cat_status_label.grid(row=6, column=0, sticky="ew", pady=(6, 12))

        buttons = ttk.Frame(right, style="Card.TFrame")
        buttons.grid(row=7, column=0, sticky="ew")
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
            bg=theme.CARD,
            fg=theme.MUTED,
            font=("Segoe UI", 9),
            justify="left",
            wraplength=470,
        )
        hint.grid(row=8, column=0, sticky="w", pady=(16, 0))
        self._refresh_hamlib_update_controls()
        self.after(50, self._load_cat_runtime_info)

    def _load_cat_runtime_info(self):
        def worker():
            try:
                models = list_rig_models()
                version = hamlib_version()
                backup_version = ""
                backup = backup_hamlib_dir(self.data_dir)
                if sys.platform == "win32" and usable_hamlib_dir(backup):
                    try:
                        backup_version = runtime_version(backup)
                    except Exception:
                        backup_version = "unlesbar"
                if not self.closing:
                    self.after(0, lambda: self._cat_runtime_loaded(models, version, backup_version))
            except Exception as exc:
                if not self.closing:
                    error_message = str(exc)
                    self.after(0, lambda message=error_message: self._cat_runtime_failed(message))

        threading.Thread(target=worker, name="cat-runtime-info", daemon=True).start()

    def _cat_runtime_loaded(self, models: list[RigModel], version: str, backup_version: str = ""):
        self.cat_models = models
        self.cat_hamlib_info.configure(
            text=f"✓ {version}\n{len(models)} Funkgerätemodelle · vollständig lokal gebündelt · keine separate Installation",
            fg=theme.OK,
        )
        self._filter_cat_models()
        self._select_cat_model_id(self.cat_saved_model_id)
        self._update_cat_device_controls()
        if sys.platform == "win32" and not self.hamlib_update_busy:
            active = version_from_output(version) or version
            backup = version_from_output(backup_version) or backup_version or "noch keine"
            if self.language == "en":
                backup = "none yet" if not backup_version else backup
                self.hamlib_update_status.configure(
                    text=f"In use: Hamlib {active} · Backed up: {backup}. Update checks are manual only."
                )
            else:
                self.hamlib_update_status.configure(
                    text=f"Aktiv: Hamlib {active} · Sicherung: {backup}. Die Update-Prüfung startet nur von Hand."
                )
        self._refresh_hamlib_update_controls()

    def _cat_runtime_failed(self, message: str):
        self.cat_hamlib_info.configure(text="✕ " + message, fg=theme.ERR)
        self.cat_status_label.configure(text="Hamlib ist nicht verfügbar.", fg=theme.ERR)

    def _refresh_hamlib_update_controls(self):
        if not hasattr(self, "hamlib_update_button"):
            return
        is_windows = sys.platform == "win32"
        backup_available = is_windows and usable_hamlib_dir(backup_hamlib_dir(self.data_dir))
        state = "disabled" if self.hamlib_update_busy else "normal"
        self.hamlib_update_button.configure(state=state)
        self.hamlib_restore_button.configure(
            state=("normal" if backup_available and not self.hamlib_update_busy else "disabled")
        )
        if not is_windows and not self.hamlib_update_busy:
            self.hamlib_update_status.configure(
                text="Linux und macOS erhalten Hamlib zusammen mit einem App-Update."
            )

    def _set_hamlib_update_busy(self, busy: bool, text: str = ""):
        self.hamlib_update_busy = busy
        if text:
            self.hamlib_update_status.configure(text=text)
        if busy:
            self.hamlib_update_progress.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(8, 0))
            self.hamlib_update_progress.start(12)
        else:
            self.hamlib_update_progress.stop()
            self.hamlib_update_progress.grid_remove()
        self._refresh_hamlib_update_controls()

    def _check_hamlib_update(self):
        if self.hamlib_update_busy or self.closing:
            return
        if sys.platform != "win32":
            if self.language == "en":
                messagebox.showinfo(
                    "Hamlib updates",
                    "On Linux and macOS, Hamlib is updated together with the signed application package. "
                    "A separate binary download is therefore not installed.", parent=self,
                )
            else:
                messagebox.showinfo(
                    "Hamlib-Updates",
                    "Unter Linux und macOS wird Hamlib zusammen mit dem signierten Anwendungspaket aktualisiert. "
                    "Ein separates Binärpaket wird deshalb nicht installiert.", parent=self,
                )
            return
        self._set_hamlib_update_busy(True, (
            "Checking the latest stable Hamlib version …" if self.language == "en" else
            "Neueste stabile Hamlib-Version wird geprüft …"
        ))

        def worker():
            try:
                current_output = hamlib_version()
                release = find_latest_windows_release(
                    current_output, opener=lambda request, timeout=20: secure_urlopen(request, timeout=timeout),
                )
                current = version_from_output(current_output)
                if not self.closing:
                    self.after(0, lambda: self._hamlib_update_checked(current, release))
            except Exception as exc:
                if not self.closing:
                    message = str(exc)
                    self.after(0, lambda: self._hamlib_update_failed(message))

        threading.Thread(target=worker, name="hamlib-update-check", daemon=True).start()

    def _hamlib_update_checked(self, current: str, release: HamlibRelease | None):
        self._set_hamlib_update_busy(False)
        if release is None:
            status = (
                f"Hamlib {current}: latest stable version."
                if self.language == "en" else
                f"Hamlib {current}: aktuellste stabile Version."
            )
            self.hamlib_update_status.configure(text=status)
            messagebox.showinfo(
                "Hamlib updates" if self.language == "en" else "Hamlib-Updates",
                f"Hamlib {current} is already up to date." if self.language == "en" else
                f"Hamlib {current} ist bereits aktuell.", parent=self,
            )
            return
        if self.language == "en":
            prompt = (
                f"Hamlib {release.version} is available (installed: {current}).\n\n"
                "Download it from the official Hamlib GitHub release, verify its SHA-256 checksum and install it? "
                "CAT will be stopped first. The previous version remains available for rollback."
            )
        else:
            prompt = (
                f"Hamlib {release.version} ist verfügbar (installiert: {current}).\n\n"
                "Soll das Paket aus dem offiziellen Hamlib-GitHub-Release heruntergeladen, per SHA-256 geprüft "
                "und installiert werden? CAT wird vorher gestoppt. Die vorige Version bleibt zur Wiederherstellung erhalten."
            )
        if messagebox.askyesno("Hamlib-Update", prompt, parent=self):
            self._install_hamlib_release(release)
        else:
            self.hamlib_update_status.configure(text=(
                f"Hamlib {current} · Update not installed." if self.language == "en" else
                f"Hamlib {current} · Update nicht installiert."
            ))

    def _install_hamlib_release(self, release: HamlibRelease):
        try:
            active_runtime = find_hamlib_dir()
        except Exception as exc:
            self._hamlib_update_failed(str(exc))
            return
        self._stop_cat_runtime()
        self._set_hamlib_update_busy(True, (
            f"Downloading, verifying and installing Hamlib {release.version} …"
            if self.language == "en" else
            f"Hamlib {release.version} wird geladen, geprüft und installiert …"
        ))

        def worker():
            try:
                version = install_windows_release(
                    release, self.data_dir, active_runtime,
                    opener=lambda request, timeout=180: secure_urlopen(request, timeout=timeout),
                )
                if not self.closing:
                    self.after(0, lambda: self._hamlib_update_installed(version))
            except Exception as exc:
                if not self.closing:
                    message = str(exc)
                    self.after(0, lambda: self._hamlib_update_failed(message))

        threading.Thread(target=worker, name="hamlib-update-install", daemon=True).start()

    def _hamlib_update_installed(self, version: str):
        success = (
            f"✓ Hamlib {version} was installed. CAT can now be started again."
            if self.language == "en" else
            f"✓ Hamlib {version} wurde installiert. CAT kann wieder gestartet werden."
        )
        self._set_hamlib_update_busy(False, success)
        self.status_var.set(
            f"Hamlib {version} installed" if self.language == "en" else f"Hamlib {version} installiert"
        )
        self._load_cat_runtime_info()
        messagebox.showinfo(
            "Hamlib update" if self.language == "en" else "Hamlib-Update",
            (f"Hamlib {version} was installed and verified successfully.\n\nCAT can now be started again."
             if self.language == "en" else
             f"Hamlib {version} wurde erfolgreich installiert und geprüft.\n\n"
             "Die CAT-Verbindung kann jetzt wieder gestartet werden."), parent=self,
        )

    def _hamlib_update_failed(self, message: str):
        message = self._tr(message)
        failure = (
            "✕ Hamlib update failed: " + message if self.language == "en" else
            "✕ Hamlib-Update fehlgeschlagen: " + message
        )
        self._set_hamlib_update_busy(False, failure)
        messagebox.showerror(
            "Hamlib update" if self.language == "en" else "Hamlib-Update",
            (("The Hamlib update was not installed.\n\n" if self.language == "en" else
              "Das Hamlib-Update wurde nicht installiert.\n\n") + message), parent=self,
        )

    def _restore_previous_hamlib(self):
        if self.hamlib_update_busy or self.closing:
            return
        restore_prompt = (
            "The active Hamlib version will be swapped with the previously backed-up version. "
            "CAT will be stopped first. Continue?"
            if self.language == "en" else
            "Die aktuell verwendete Hamlib-Version wird mit der zuvor gesicherten Version getauscht. "
            "CAT wird vorher gestoppt. Fortfahren?"
        )
        if not messagebox.askyesno(
            "Restore Hamlib" if self.language == "en" else "Hamlib wiederherstellen",
            restore_prompt, parent=self,
        ):
            return
        self._stop_cat_runtime()
        self._set_hamlib_update_busy(True, (
            "Restoring the previous Hamlib version …" if self.language == "en" else
            "Vorherige Hamlib-Version wird wiederhergestellt …"
        ))

        def worker():
            try:
                version = restore_previous_windows_runtime(self.data_dir)
                if not self.closing:
                    self.after(0, lambda: self._hamlib_restore_finished(version))
            except Exception as exc:
                if not self.closing:
                    message = str(exc)
                    self.after(0, lambda: self._hamlib_update_failed(message))

        threading.Thread(target=worker, name="hamlib-update-restore", daemon=True).start()

    def _hamlib_restore_finished(self, version: str):
        self._set_hamlib_update_busy(False, (
            f"✓ Hamlib {version} was restored." if self.language == "en" else
            f"✓ Hamlib {version} wurde wiederhergestellt."
        ))
        self.status_var.set(
            f"Hamlib {version} restored" if self.language == "en" else
            f"Hamlib {version} wiederhergestellt"
        )
        self._load_cat_runtime_info()
        messagebox.showinfo(
            "Restore Hamlib" if self.language == "en" else "Hamlib wiederherstellen",
            f"Hamlib {version} is now in use." if self.language == "en" else
            f"Hamlib {version} wird jetzt verwendet.", parent=self,
        )

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
            current = self.cat_device_var.get().strip()
            if self.cat_ui_model_id == FLRIG_MODEL_ID:
                self.cat_flrig_endpoint = current or DEFAULT_FLRIG_ENDPOINT
            elif self.cat_ui_model_id:
                self.cat_serial_device = current
            self.cat_saved_model_id = selected_id
            self.cat_ui_model_id = selected_id
            self.cat_device_var.set(
                self.cat_flrig_endpoint if selected_id == FLRIG_MODEL_ID else self.cat_serial_device
            )
            self._update_cat_device_controls()

    def _update_cat_device_controls(self):
        if not hasattr(self, "cat_device_combo"):
            return
        is_flrig = (self._selected_cat_model_id() or self.cat_saved_model_id) == FLRIG_MODEL_ID
        if is_flrig:
            current = self.cat_device_var.get().strip() or self.cat_flrig_endpoint or DEFAULT_FLRIG_ENDPOINT
            self.cat_device_var.set(current)
            self.cat_device_combo.configure(values=[current] if current else [DEFAULT_FLRIG_ENDPOINT])
            self.cat_device_label.configure(text=self._tr("FLRig-Adresse (IP/Hostname:Port)"))
            self.cat_device_action_button.configure(text=self._tr("FLRig suchen"), command=self._detect_flrig)
            self.cat_baud_label.grid_remove()
            self.cat_baud_combo.grid_remove()
            self.cat_serial_frame.grid_remove()
        else:
            self.cat_device_label.configure(text=self._tr("CAT-/COM-Schnittstelle"))
            self.cat_device_action_button.configure(text=self._tr("Neu laden"), command=self._refresh_cat_ports)
            self.cat_baud_label.grid()
            self.cat_baud_combo.grid()
            self.cat_serial_frame.grid()
            self._refresh_cat_ports()

    def _refresh_cat_ports(self):
        if not hasattr(self, "cat_device_combo"):
            return
        if (self._selected_cat_model_id() or self.cat_saved_model_id) == FLRIG_MODEL_ID:
            current = self.cat_device_var.get().strip() or DEFAULT_FLRIG_ENDPOINT
            self.cat_device_combo.configure(values=[current])
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
        self.cat_ui_model_id = config.model_id
        self.cat_serial_device = self.db.get_setting("cat_device", "").strip()
        self.cat_flrig_endpoint = self.db.get_setting("cat_flrig_endpoint", DEFAULT_FLRIG_ENDPOINT).strip() or DEFAULT_FLRIG_ENDPOINT
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
        self._update_cat_device_controls()
        self.cat_status_label.configure(
            text="CAT ist ausgeschaltet · zum Verbinden bitte CAT starten.",
            fg=theme.MUTED,
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
        if config.model_id == FLRIG_MODEL_ID:
            self.cat_flrig_endpoint = config.device
        else:
            self.cat_serial_device = config.device

    def _detect_flrig(self):
        if (self._selected_cat_model_id() or self.cat_saved_model_id) != FLRIG_MODEL_ID:
            return
        self.flrig_search_generation += 1
        generation = self.flrig_search_generation
        current = self.cat_device_var.get().strip()
        self.cat_device_action_button.configure(state="disabled", text=self._tr("FLRig wird gesucht …"))
        self.cat_status_label.configure(
            text=self._tr("FLRig wird lokal und im privaten Netzwerk gesucht …"), fg=theme.MUTED,
        )

        def worker():
            try:
                results = discover_flrig(current)
                error_message = ""
            except Exception as exc:
                results = []
                error_message = str(exc)
            if not self.closing:
                self.after(
                    0,
                    lambda: self._flrig_detected(
                        generation, current, results, error_message,
                    ),
                )

        threading.Thread(target=worker, name="flrig-discovery", daemon=True).start()

    def _flrig_detected(
        self, generation: int, current: str, results: list[tuple[str, str]],
        error_message: str = "",
    ):
        if generation != self.flrig_search_generation or self.closing:
            return
        self.cat_device_action_button.configure(state="normal", text=self._tr("FLRig suchen"))
        if not results:
            suffix = f" ({error_message})" if error_message else ""
            self.cat_status_label.configure(
                text=self._tr(
                    "Kein FLRig automatisch gefunden. IP/Hostname:Port kann weiterhin von Hand eingetragen werden."
                ) + suffix,
                fg=theme.WARN,
            )
            return
        endpoints = [endpoint for endpoint, _version in results]
        selected = current if current in endpoints else endpoints[0]
        self.cat_device_combo.configure(values=endpoints)
        self.cat_device_var.set(selected)
        self.cat_flrig_endpoint = selected
        version = next((value for endpoint, value in results if endpoint == selected), "FLRig")
        more = f" · +{len(results) - 1}" if len(results) > 1 else ""
        self.cat_status_label.configure(
            text=self._tr("FLRig gefunden") + f": {selected} · {version}{more}\n" +
                 self._tr("Bitte Einstellungen speichern oder die Verbindung direkt testen."),
            fg=theme.OK,
        )

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
            self.cat_status_label.configure(text=message, fg=theme.OK)
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

    def _set_tune_button_state(self):
        if hasattr(self, "tune_button"):
            enabled = not self.tuner_busy and not self.cat_starting and not self.closing
            self.tune_button.configure(
                state="normal" if enabled else "disabled",
                style="Tuning.TButton" if self.tuner_busy else "Secondary.TButton",
                text="TUNE läuft …" if self.tuner_busy else "TUNE (ATU)",
            )

    def start_tuner_from_qso(self):
        if self.tuner_busy or self.cat_starting:
            return
        confirmed = messagebox.askyesno(
            "TUNE / Antennentuner",
            "Der automatische Tuner des Funkgeräts wird gestartet. Das Funkgerät kann dabei kurz senden.\n\n"
            "Antenne und Leistungsgrenzen geprüft – TUNE jetzt ausführen?",
            parent=self,
        )
        if not confirmed:
            return
        if not self.cat_manager.running:
            try:
                config = self._cat_config_from_ui(enabled=True)
                config.validate()
            except Exception as exc:
                messagebox.showerror("TUNE / Antennentuner", str(exc), parent=self)
                return
            self.tuner_busy = True
            self.tuner_start_pending = True
            self._set_tune_button_state()
            self.status_var.set("CAT wird für den Antennentuner gestartet …")
            self._start_cat_runtime(config, notify=False)
            return
        self._begin_tuner_operation()

    def _begin_tuner_operation(self):
        # Do not let the periodic frequency/mode poll open another rigctld
        # connection while the tuner command is being issued.
        self._cancel_cat_poll()
        self.tuner_busy = True
        self.tuner_start_pending = False
        self.tuner_started_monotonic = time.monotonic()
        generation = self.cat_generation
        self._set_tune_button_state()
        self.status_var.set("Antennentuner wird gestartet …")

        def worker():
            try:
                self.cat_manager.start_tuner()
                if not self.closing:
                    self.after(0, lambda: self._tuner_finished(generation, ""))
            except Exception as exc:
                if not self.closing:
                    message = str(exc)
                    self.after(0, lambda error=message: self._tuner_finished(generation, error))

        threading.Thread(target=worker, name="cat-tuner", daemon=True).start()

    def _tuner_finished(self, generation: int, error: str):
        minimum_display = 0.8
        remaining = minimum_display - (time.monotonic() - getattr(self, "tuner_started_monotonic", 0.0))
        if remaining > 0 and not self.closing:
            self.after(int(remaining * 1000), lambda: self._tuner_finished(generation, error))
            return
        self.tuner_busy = False
        self._set_tune_button_state()
        if generation != self.cat_generation or self.closing:
            return
        if self.cat_manager.running:
            try:
                poll_interval = max(250, int(self.cat_poll_var.get()))
            except (TypeError, ValueError, tk.TclError):
                poll_interval = 1000
            self._schedule_cat_poll(400, poll_interval)
        if error:
            self.status_var.set("Antennentuner konnte nicht gestartet werden")
            messagebox.showerror(
                "TUNE / Antennentuner",
                "Der TUNE-Befehl wurde vom Funkgerät oder Hamlib nicht unterstützt:\n\n" + error,
                parent=self,
            )
            return
        self.status_var.set("Antennentuner gestartet")

    def _start_cat_runtime(self, config: CatConfig, *, notify: bool):
        self.cat_generation += 1
        generation = self.cat_generation
        self._cancel_cat_poll()
        self.cat_starting = True
        self.cat_start_button.configure(state="disabled")
        self._set_tune_button_state()
        self.cat_status_label.configure(text="CAT wird gestartet …", fg=theme.MUTED)
        self.status_var.set("CAT wird gestartet …")

        def worker():
            try:
                self.cat_manager.start(config)
                if not self.closing:
                    self.after(0, lambda: self._cat_started(generation, config, notify))
            except Exception as exc:
                if not self.closing:
                    error_message = str(exc)
                    self.after(
                        0,
                        lambda message=error_message: self._cat_start_failed(generation, message, notify),
                    )

        threading.Thread(target=worker, name="cat-start", daemon=True).start()

    def _cat_started(self, generation: int, config: CatConfig, notify: bool):
        if generation != self.cat_generation or self.closing:
            return
        self.cat_starting = False
        self.cat_start_button.configure(state="normal")
        self.cat_status_label.configure(text="✓ CAT verbunden · warte auf Funkgerätedaten …", fg=theme.OK)
        self.status_var.set("CAT verbunden")
        self._set_tune_button_state()
        if self.tuner_start_pending:
            self._begin_tuner_operation()
        else:
            self._schedule_cat_poll(0, config.poll_interval_ms)
        if notify:
            messagebox.showinfo("CAT Setup", "CAT wurde erfolgreich gestartet.", parent=self)

    def _cat_start_failed(self, generation: int, message: str, notify: bool):
        if generation != self.cat_generation or self.closing:
            return
        tuner_was_waiting = self.tuner_start_pending
        self.cat_starting = False
        self.tuner_start_pending = False
        self.tuner_busy = False
        self.cat_start_button.configure(state="normal")
        self.cat_status_label.configure(text="✕ " + message, fg=theme.ERR)
        self.status_var.set("CAT-Verbindung fehlgeschlagen")
        self._set_tune_button_state()
        if tuner_was_waiting:
            messagebox.showerror(
                "TUNE / Antennentuner",
                "CAT konnte für den Antennentuner nicht gestartet werden:\n\n" + message,
                parent=self,
            )
        elif notify:
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
                    error_message = str(exc)
                    self.after(
                        0,
                        lambda message=error_message: self._cat_poll_failed(generation, message, interval_ms),
                    )

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
            fg=theme.OK,
        )
        if not self.tuner_busy:
            self._schedule_cat_poll(interval_ms, interval_ms)

    def _cat_poll_failed(self, generation: int, message: str, interval_ms: int):
        self.cat_poll_busy = False
        if generation != self.cat_generation or self.closing:
            return
        self.cat_status_label.configure(text="CAT-Lesefehler: " + message, fg=theme.WARN)
        if not self.tuner_busy:
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
        self.cat_status_label.configure(text="CAT-Test läuft …", fg=theme.MUTED)

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
                    error_message = str(exc)
                    self.after(
                        0,
                        lambda message=error_message: self._cat_start_failed(generation, message, True),
                    )

        threading.Thread(target=worker, name="cat-test", daemon=True).start()

    def _cat_test_ok(self, generation: int, reading):
        if generation != self.cat_generation or self.closing:
            return
        frequency = format_frequency_mhz(reading.frequency_hz)
        self.cat_status_label.configure(
            text=f"✓ CAT-Test erfolgreich\nFrequenz: {frequency} MHz\nModus: {reading.raw_mode}",
            fg=theme.OK,
        )
        messagebox.showinfo(
            "CAT-Verbindung",
            f"Verbindung erfolgreich.\n\nFrequenz: {frequency} MHz\nHamlib-Modus: {reading.raw_mode}\n\nCAT bleibt nach dem Test ausgeschaltet.",
            parent=self,
        )
        self.cat_status_label.configure(
            text=f"✓ CAT-Test erfolgreich · CAT ist ausgeschaltet\nFrequenz: {frequency} MHz\nModus: {reading.raw_mode}",
            fg=theme.OK,
        )

    def stop_cat(self):
        self._stop_cat_runtime()
        self.cat_status_label.configure(text="CAT ist ausgeschaltet.", fg=theme.MUTED)
        self.status_var.set("CAT gestoppt")

    def _stop_cat_runtime(self, *, update_ui: bool = True):
        self.cat_generation += 1
        self._cancel_cat_poll()
        self.cat_poll_busy = False
        self.cat_starting = False
        self.tuner_busy = False
        self.tuner_start_pending = False
        self.cat_manager.stop()
        self._set_tune_button_state()
        if update_ui and hasattr(self, "cat_status_label"):
            self.cat_status_label.configure(text="CAT ist gestoppt.", fg=theme.MUTED)
