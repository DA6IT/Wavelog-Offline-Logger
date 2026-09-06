from __future__ import annotations

import atexit
import math
import threading
import tkinter as tk
from tkinter import messagebox, ttk

from cat_control import list_serial_ports
from rotor_control import (
    DUMMY_ROTOR_MODEL_ID,
    ROTOR_BAUD_RATES,
    RotorConfig,
    RotorModel,
    RotatorManager,
    list_rotor_models,
    rotctld_version,
)
from ui_theme import theme


class RotorFeatureMixin:
    def _init_rotor_feature(self) -> None:
        self.rotor_manager = RotatorManager()
        atexit.register(self.rotor_manager.stop)
        self.rotor_models: list[RotorModel] = []
        self.rotor_model_by_label: dict[str, RotorModel] = {}
        self.rotor_saved_config = RotorConfig()
        self.rotor_active_config: RotorConfig | None = None
        self.rotor_generation = 0
        self.rotor_poll_job = None
        self.rotor_poll_busy = False
        self.rotor_starting = False
        self.rotor_motion_busy = False
        self.rotor_runtime_loading = False
        self.rotor_current_azimuth: float | None = None
        self.rotor_current_elevation: float | None = None
        self.rotor_target_azimuth: float | None = None
        self._rotor_setup_window = None

    def _build_rotor_cat_controls(self, parent, *, row: int):
        frame = ttk.LabelFrame(parent, text="Rotorsteuerung", padding=10)
        frame.grid(row=row, column=0, sticky="ew", pady=(14, 0))
        frame.columnconfigure(0, weight=1)
        self.rotor_cat_status_label = ttk.Label(
            frame,
            text="Rotor ist ausgeschaltet.",
            style="Muted.Card.TLabel",
            wraplength=430,
        )
        self.rotor_cat_status_label.grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 8))
        buttons = ttk.Frame(frame, style="Card.TFrame")
        buttons.grid(row=1, column=0, columnspan=3, sticky="ew")
        ttk.Button(
            buttons,
            text="Rotor einrichten …",
            style="Secondary.TButton",
            command=self._open_rotor_setup,
        ).pack(side="left")
        self.rotor_start_button = ttk.Button(
            buttons,
            text="Rotor starten",
            style="Primary.TButton",
            command=self.start_rotor,
        )
        self.rotor_start_button.pack(side="left", padx=(8, 0))
        self.rotor_stop_button = ttk.Button(
            buttons,
            text="Rotor stoppen",
            style="Secondary.TButton",
            command=self.stop_rotor,
            state="disabled",
        )
        self.rotor_stop_button.pack(side="left", padx=(8, 0))
        self.after(120, self._load_rotor_runtime_info)

    def _load_rotor_runtime_info(self):
        if self.rotor_runtime_loading or self.closing:
            return
        self.rotor_runtime_loading = True

        def worker():
            try:
                models = list_rotor_models()
                version = rotctld_version()
                error = ""
            except Exception as exc:
                models = []
                version = ""
                error = str(exc)
            if not self.closing:
                self.after(0, lambda: self._rotor_runtime_loaded(models, version, error))

        threading.Thread(target=worker, name="rotor-runtime-info", daemon=True).start()

    def _rotor_runtime_loaded(self, models: list[RotorModel], version: str, error: str):
        self.rotor_runtime_loading = False
        if error:
            if hasattr(self, "rotor_cat_status_label"):
                self.rotor_cat_status_label.configure(text="rotctld nicht verfügbar · " + error)
            return
        self.rotor_models = models
        if hasattr(self, "rotor_cat_status_label") and not self.rotor_manager.running:
            self.rotor_cat_status_label.configure(
                text=f"✓ {version} · {len(models)} Rotormodelle verfügbar · Rotor ausgeschaltet"
            )
        self._refresh_rotor_setup_models()

    def _load_rotor_settings_to_ui(self):
        self.rotor_saved_config = RotorConfig.from_getter(self.db.get_setting)
        self.rotor_active_config = None
        self.rotor_current_azimuth = None
        self.rotor_current_elevation = None
        self._load_rotor_config_into_dialog()
        self._refresh_rotor_controls()
        self._draw_rotor_compass()

    def _rotor_setup_is_open(self) -> bool:
        window = self._rotor_setup_window
        if window is None:
            return False
        try:
            return bool(window.winfo_exists())
        except tk.TclError:
            return False

    def _close_rotor_setup(self):
        window = self._rotor_setup_window
        self._rotor_setup_window = None
        if window is not None:
            try:
                window.destroy()
            except tk.TclError:
                pass

    def _open_rotor_setup(self):
        if self._rotor_setup_is_open():
            existing = self._rotor_setup_window
            existing.deiconify()
            existing.lift()
            existing.focus_force()
            return
        self._rotor_setup_window = None

        window = tk.Toplevel(self)
        self._rotor_setup_window = window
        window.title("Rotor Setup")
        window.transient(self)
        window.resizable(False, False)
        window.configure(bg=theme.BG)

        body = ttk.Frame(window, padding=18)
        body.grid(row=0, column=0, sticky="nsew")
        body.columnconfigure(1, weight=1)

        ttk.Label(body, text="Rotor über Hamlib / rotctld", style="CardTitle.TLabel").grid(
            row=0, column=0, columnspan=3, sticky="w"
        )
        ttk.Label(
            body,
            text=(
                "Zum Entwickeln und Testen kannst du Hamlib Dummy [ID 1] verwenden. "
                "Dabei wird keine echte Hardware bewegt. Ein realer Rotor wird später über "
                "seinen Hamlib-Treiber und die passende Schnittstelle verbunden."
            ),
            style="Muted.Card.TLabel",
            wraplength=560,
        ).grid(row=1, column=0, columnspan=3, sticky="w", pady=(4, 14))

        self.rotor_setup_model_var = tk.StringVar()
        self.rotor_setup_device_var = tk.StringVar()
        self.rotor_setup_baud_var = tk.StringVar(value="9600")
        self.rotor_setup_port_var = tk.StringVar(value="4533")
        self.rotor_setup_poll_var = tk.StringVar(value="750")

        ttk.Label(body, text="Hamlib-Rotormodell", style="Card.TLabel").grid(
            row=2, column=0, sticky="w", padx=(0, 12), pady=5
        )
        self.rotor_setup_model_combo = ttk.Combobox(
            body, textvariable=self.rotor_setup_model_var, state="readonly", width=46
        )
        self.rotor_setup_model_combo.grid(row=2, column=1, sticky="ew", pady=5)
        self.rotor_setup_model_combo.bind("<<ComboboxSelected>>", self._rotor_setup_model_selected)
        ttk.Button(
            body, text="Neu laden", command=self._load_rotor_runtime_info
        ).grid(row=2, column=2, padx=(8, 0), pady=5)

        ttk.Label(body, text="Rotor-/COM-Schnittstelle", style="Card.TLabel").grid(
            row=3, column=0, sticky="w", padx=(0, 12), pady=5
        )
        self.rotor_setup_device_combo = ttk.Combobox(
            body, textvariable=self.rotor_setup_device_var, state="normal", width=32
        )
        self.rotor_setup_device_combo.grid(row=3, column=1, sticky="ew", pady=5)
        ttk.Button(
            body, text="Ports laden", command=self._refresh_rotor_ports
        ).grid(row=3, column=2, padx=(8, 0), pady=5)

        ttk.Label(body, text="Baudrate", style="Card.TLabel").grid(
            row=4, column=0, sticky="w", padx=(0, 12), pady=5
        )
        self.rotor_setup_baud_combo = ttk.Combobox(
            body,
            textvariable=self.rotor_setup_baud_var,
            values=[str(value) for value in ROTOR_BAUD_RATES],
            state="readonly",
        )
        self.rotor_setup_baud_combo.grid(row=4, column=1, sticky="ew", pady=5)

        ttk.Label(body, text="Lokaler rotctld-Port", style="Card.TLabel").grid(
            row=5, column=0, sticky="w", padx=(0, 12), pady=5
        )
        ttk.Entry(body, textvariable=self.rotor_setup_port_var).grid(
            row=5, column=1, sticky="ew", pady=5
        )

        ttk.Label(body, text="Abfrageintervall (ms)", style="Card.TLabel").grid(
            row=6, column=0, sticky="w", padx=(0, 12), pady=5
        )
        ttk.Combobox(
            body,
            textvariable=self.rotor_setup_poll_var,
            values=("250", "500", "750", "1000", "1500", "2000"),
            state="readonly",
        ).grid(row=6, column=1, sticky="ew", pady=5)

        ttk.Label(
            body,
            text="rotctld lauscht ausschließlich lokal auf 127.0.0.1. Bewegung erfolgt nur nach einem ausdrücklichen Klick.",
            style="Muted.Card.TLabel",
            wraplength=560,
        ).grid(row=7, column=0, columnspan=3, sticky="w", pady=(10, 10))

        self.rotor_setup_status_label = ttk.Label(
            body, text="", style="Muted.Card.TLabel", wraplength=560
        )
        self.rotor_setup_status_label.grid(row=8, column=0, columnspan=3, sticky="w", pady=(0, 10))

        actions = ttk.Frame(body)
        actions.grid(row=9, column=0, columnspan=3, sticky="ew")
        ttk.Button(
            actions,
            text="Einstellungen speichern",
            style="Primary.TButton",
            command=self.save_rotor_settings,
        ).pack(side="left")
        ttk.Button(
            actions,
            text="Verbindung testen",
            style="Secondary.TButton",
            command=self.test_rotor_connection,
        ).pack(side="left", padx=(8, 0))
        ttk.Button(
            actions,
            text="Schließen",
            style="Secondary.TButton",
            command=self._close_rotor_setup,
        ).pack(side="right")

        window.protocol("WM_DELETE_WINDOW", self._close_rotor_setup)
        self._refresh_rotor_setup_models()
        self._load_rotor_config_into_dialog()
        self._refresh_rotor_ports()
        self._update_rotor_setup_device_state()
        window.update_idletasks()
        try:
            x = self.winfo_rootx() + max(20, (self.winfo_width() - window.winfo_reqwidth()) // 2)
            y = self.winfo_rooty() + max(20, (self.winfo_height() - window.winfo_reqheight()) // 2)
            window.geometry(f"+{x}+{y}")
        except tk.TclError:
            pass

    def _refresh_rotor_setup_models(self):
        if not self._rotor_setup_is_open() or not hasattr(self, "rotor_setup_model_combo"):
            return
        models = self.rotor_models or [
            RotorModel(DUMMY_ROTOR_MODEL_ID, "Hamlib", "Dummy", "", "Stable")
        ]
        self.rotor_model_by_label = {model.label: model for model in models}
        self.rotor_setup_model_combo.configure(values=list(self.rotor_model_by_label))
        self._select_rotor_model_id(self.rotor_saved_config.model_id)

    def _select_rotor_model_id(self, model_id: int):
        if not self._rotor_setup_is_open() or not hasattr(self, "rotor_setup_model_var"):
            return
        for label, model in self.rotor_model_by_label.items():
            if model.model_id == model_id:
                self.rotor_setup_model_var.set(label)
                return
        if self.rotor_model_by_label:
            self.rotor_setup_model_var.set(next(iter(self.rotor_model_by_label)))

    def _selected_rotor_model_id(self) -> int:
        if not self._rotor_setup_is_open() or not hasattr(self, "rotor_setup_model_var"):
            return self.rotor_saved_config.model_id
        model = self.rotor_model_by_label.get(self.rotor_setup_model_var.get())
        if model:
            return model.model_id
        return self.rotor_saved_config.model_id

    def _rotor_setup_model_selected(self, _event=None):
        self._update_rotor_setup_device_state()

    def _update_rotor_setup_device_state(self):
        if not self._rotor_setup_is_open() or not hasattr(self, "rotor_setup_device_combo"):
            return
        dummy = self._selected_rotor_model_id() == DUMMY_ROTOR_MODEL_ID
        self.rotor_setup_device_combo.configure(state="disabled" if dummy else "normal")
        self.rotor_setup_baud_combo.configure(state="disabled" if dummy else "readonly")

    def _refresh_rotor_ports(self):
        if not self._rotor_setup_is_open() or not hasattr(self, "rotor_setup_device_combo"):
            return
        ports = list_serial_ports()
        current = self.rotor_setup_device_var.get().strip()
        if current and current not in ports:
            ports.append(current)
        self.rotor_setup_device_combo.configure(values=ports)
        if not current and len(ports) == 1:
            self.rotor_setup_device_var.set(ports[0])

    def _load_rotor_config_into_dialog(self):
        if not self._rotor_setup_is_open() or not hasattr(self, "rotor_setup_device_var"):
            return
        config = self.rotor_saved_config
        self.rotor_setup_device_var.set(config.device)
        self.rotor_setup_baud_var.set(str(config.baud))
        self.rotor_setup_port_var.set(str(config.port))
        self.rotor_setup_poll_var.set(str(config.poll_interval_ms))
        self._select_rotor_model_id(config.model_id)
        self._update_rotor_setup_device_state()

    def _rotor_config_from_ui(self) -> RotorConfig:
        if not self._rotor_setup_is_open() or not hasattr(self, "rotor_setup_device_var"):
            return self.rotor_saved_config
        return RotorConfig(
            model_id=self._selected_rotor_model_id(),
            device=self.rotor_setup_device_var.get().strip(),
            baud=int(self.rotor_setup_baud_var.get().strip()),
            port=int(self.rotor_setup_port_var.get().strip()),
            poll_interval_ms=int(self.rotor_setup_poll_var.get().strip()),
        )

    def _store_rotor_config(self, config: RotorConfig):
        for key, value in config.settings().items():
            self.db.set_setting(key, value)
        self.rotor_saved_config = config

    def save_rotor_settings(self):
        try:
            config = self._rotor_config_from_ui()
            config.validate()
            self._store_rotor_config(config)
            text = "Rotor-Einstellungen gespeichert."
            if self.rotor_manager.running:
                text += " Änderungen gelten nach Rotor stoppen und erneut starten."
            if self._rotor_setup_is_open() and hasattr(self, "rotor_setup_status_label"):
                self.rotor_setup_status_label.configure(text="✓ " + text)
            if hasattr(self, "rotor_cat_status_label") and not self.rotor_manager.running:
                self.rotor_cat_status_label.configure(text=text + " Rotor ist ausgeschaltet.")
            self.status_var.set("Rotor-Einstellungen gespeichert")
        except Exception as exc:
            messagebox.showerror("Rotor Setup", str(exc), parent=self)

    def start_rotor(self):
        if self.rotor_starting or self.rotor_manager.running:
            return
        try:
            config = self._rotor_config_from_ui()
            config.validate()
            self._store_rotor_config(config)
        except Exception as exc:
            messagebox.showerror("Rotor starten", str(exc), parent=self)
            return

        self.rotor_generation += 1
        generation = self.rotor_generation
        self.rotor_starting = True
        self._refresh_rotor_controls()
        if hasattr(self, "rotor_cat_status_label"):
            self.rotor_cat_status_label.configure(text="Rotor wird gestartet …")
        self.status_var.set("Rotor wird gestartet …")

        def worker():
            try:
                self.rotor_manager.start(config)
                if not self.closing:
                    self.after(0, lambda: self._rotor_started(generation, config))
            except Exception as exc:
                if not self.closing:
                    message = str(exc)
                    self.after(0, lambda: self._rotor_start_failed(generation, message))

        threading.Thread(target=worker, name="rotor-start", daemon=True).start()

    def _rotor_started(self, generation: int, config: RotorConfig):
        if generation != self.rotor_generation or self.closing:
            return
        self.rotor_starting = False
        self.rotor_active_config = config
        self.status_var.set("Rotor verbunden")
        if hasattr(self, "rotor_cat_status_label"):
            self.rotor_cat_status_label.configure(text="✓ Rotor verbunden · Position wird gelesen …")
        self._refresh_rotor_controls()
        self._schedule_rotor_poll(0, config.poll_interval_ms)

    def _rotor_start_failed(self, generation: int, message: str):
        if generation != self.rotor_generation or self.closing:
            return
        self.rotor_starting = False
        self.rotor_active_config = None
        if hasattr(self, "rotor_cat_status_label"):
            self.rotor_cat_status_label.configure(text="✕ " + message)
        self.status_var.set("Rotor-Verbindung fehlgeschlagen")
        self._refresh_rotor_controls()
        messagebox.showerror("Rotor-Verbindung", message, parent=self)

    def _schedule_rotor_poll(self, delay_ms: int, interval_ms: int):
        self._cancel_rotor_poll()
        if not self.closing and self.rotor_manager.running:
            self.rotor_poll_job = self.after(
                delay_ms, lambda: self._rotor_poll(interval_ms)
            )

    def _cancel_rotor_poll(self):
        if self.rotor_poll_job is not None:
            try:
                self.after_cancel(self.rotor_poll_job)
            except Exception:
                pass
            self.rotor_poll_job = None

    def _rotor_poll(self, interval_ms: int):
        self.rotor_poll_job = None
        if self.closing or not self.rotor_manager.running:
            return
        if self.rotor_poll_busy:
            self._schedule_rotor_poll(interval_ms, interval_ms)
            return
        self.rotor_poll_busy = True
        generation = self.rotor_generation

        def worker():
            try:
                reading = self.rotor_manager.read()
                if not self.closing:
                    self.after(0, lambda: self._rotor_poll_ok(generation, reading, interval_ms))
            except Exception as exc:
                if not self.closing:
                    message = str(exc)
                    self.after(
                        0,
                        lambda: self._rotor_poll_failed(
                            generation, message, interval_ms
                        ),
                    )

        threading.Thread(target=worker, name="rotor-poll", daemon=True).start()

    def _rotor_poll_ok(self, generation: int, reading, interval_ms: int):
        self.rotor_poll_busy = False
        if generation != self.rotor_generation or self.closing:
            return
        self.rotor_current_azimuth = float(reading.azimuth) % 360.0
        self.rotor_current_elevation = float(reading.elevation)
        if hasattr(self, "rotor_cat_status_label"):
            self.rotor_cat_status_label.configure(
                text=(
                    f"✓ Rotor verbunden · Azimut {self.rotor_current_azimuth:.1f}°"
                    f" · Elevation {self.rotor_current_elevation:.1f}°"
                )
            )
        self._draw_rotor_compass()
        self._refresh_rotor_controls()
        self._schedule_rotor_poll(interval_ms, interval_ms)

    def _rotor_poll_failed(self, generation: int, message: str, interval_ms: int):
        self.rotor_poll_busy = False
        if generation != self.rotor_generation or self.closing:
            return
        if hasattr(self, "rotor_cat_status_label"):
            self.rotor_cat_status_label.configure(text="Rotor-Lesefehler: " + message)
        self._schedule_rotor_poll(max(interval_ms, 1500), interval_ms)

    def stop_rotor(self):
        self._stop_rotor_runtime(update_ui=True)
        self.status_var.set("Rotor gestoppt")

    def _stop_rotor_runtime(self, *, update_ui: bool = True):
        self.rotor_generation += 1
        self._cancel_rotor_poll()
        self.rotor_poll_busy = False
        self.rotor_starting = False
        self.rotor_motion_busy = False
        self.rotor_manager.stop()
        self.rotor_active_config = None
        self.rotor_current_azimuth = None
        self.rotor_current_elevation = None
        if update_ui and hasattr(self, "rotor_cat_status_label"):
            self.rotor_cat_status_label.configure(text="Rotor ist ausgeschaltet.")
        self._refresh_rotor_controls()
        self._draw_rotor_compass()

    def test_rotor_connection(self):
        try:
            config = self._rotor_config_from_ui()
            config.validate()
        except Exception as exc:
            messagebox.showerror("Rotor-Test", str(exc), parent=self)
            return

        running = self.rotor_manager.running
        if running and config != self.rotor_active_config:
            messagebox.showinfo(
                "Rotor-Test",
                "Der Rotor läuft bereits mit anderen Einstellungen. Bitte zuerst Rotor stoppen und die geänderte Konfiguration danach testen.",
                parent=self,
            )
            return

        if self._rotor_setup_is_open() and hasattr(self, "rotor_setup_status_label"):
            self.rotor_setup_status_label.configure(text="Rotor-Verbindung wird geprüft …")

        def worker():
            manager = self.rotor_manager if running else RotatorManager()
            temporary = not running
            try:
                if temporary:
                    manager.start(config)
                reading = manager.read()
                if temporary:
                    manager.stop()
                if not self.closing:
                    self.after(
                        0,
                        lambda: self._rotor_test_finished(
                            f"✓ Verbindung erfolgreich · Azimut {reading.azimuth:.1f}° · "
                            f"Elevation {reading.elevation:.1f}°"
                        ),
                    )
            except Exception as exc:
                if temporary:
                    manager.stop()
                if not self.closing:
                    message = str(exc)
                    self.after(0, lambda: self._rotor_test_finished("✕ " + message))

        threading.Thread(target=worker, name="rotor-test", daemon=True).start()

    def _rotor_test_finished(self, text: str):
        if self._rotor_setup_is_open() and hasattr(self, "rotor_setup_status_label"):
            self.rotor_setup_status_label.configure(text=text)
        self.status_var.set(text)

    def _build_rotor_log_controls(self, parent):
        parent.columnconfigure(0, weight=1)

        self.rotor_disconnected_frame = ttk.Frame(parent)
        self.rotor_disconnected_frame.grid(row=0, column=0, sticky="ew", padx=8, pady=6)
        self.rotor_disconnected_frame.columnconfigure(0, weight=1)
        tk.Label(
            self.rotor_disconnected_frame,
            text="Rotor nicht verbunden",
            bg=theme.SURFACE,
            fg=theme.MUTED,
            font=("Segoe UI", 8),
            anchor="w",
        ).grid(row=0, column=0, sticky="w")
        ttk.Button(
            self.rotor_disconnected_frame,
            text="Rotor Setup",
            style="Secondary.TButton",
            command=self._open_rotor_setup,
        ).grid(row=0, column=1, sticky="e", padx=(8, 0))

        self.rotor_live_frame = ttk.Frame(parent)
        self.rotor_live_frame.grid(row=1, column=0, sticky="ew")
        self.rotor_live_frame.columnconfigure(1, weight=1)

        self.rotor_compass = tk.Canvas(
            self.rotor_live_frame,
            width=72,
            height=72,
            bg=theme.SURFACE,
            highlightthickness=0,
        )
        self.rotor_compass.grid(row=0, column=0, rowspan=2, padx=(8, 8), pady=4)

        self.rotor_qso_info = tk.Label(
            self.rotor_live_frame,
            text="Rotor: —\nZiel: —",
            bg=theme.SURFACE,
            fg=theme.TEXT,
            font=("Segoe UI Semibold", 8),
            justify="left",
            anchor="w",
        )
        self.rotor_qso_info.grid(row=0, column=1, sticky="sw", pady=(7, 1))

        action = ttk.Frame(self.rotor_live_frame)
        action.grid(row=1, column=1, sticky="nw", pady=(1, 6))
        self.rotor_turn_button = ttk.Button(
            action,
            text="Rotor drehen",
            style="Primary.TButton",
            command=self.turn_rotor_to_qso,
            state="disabled",
        )
        self.rotor_turn_button.pack(side="left")
        self.rotor_qso_stop_button = ttk.Button(
            action,
            text="STOP",
            style="Secondary.TButton",
            command=self.stop_rotor_motion,
            state="disabled",
        )
        self.rotor_qso_stop_button.pack(side="left", padx=(6, 0))

        self._draw_rotor_compass()
        self._refresh_rotor_controls()

    def _set_rotor_target(self, bearing: float | None):
        self.rotor_target_azimuth = None if bearing is None else float(bearing) % 360.0
        self._draw_rotor_compass()
        self._refresh_rotor_controls()

    @staticmethod
    def _compass_endpoint(cx: float, cy: float, radius: float, angle: float):
        radians = math.radians(angle)
        return cx + radius * math.sin(radians), cy - radius * math.cos(radians)

    def _draw_rotor_compass(self):
        if not hasattr(self, "rotor_compass"):
            return
        canvas = self.rotor_compass
        canvas.delete("all")
        try:
            width = max(60, int(float(canvas.cget("width"))))
            height = max(60, int(float(canvas.cget("height"))))
        except (TypeError, ValueError, tk.TclError):
            width = height = 72
        cx = width / 2.0
        cy = height / 2.0
        radius = min(width, height) * 0.31
        canvas.create_oval(
            cx - radius, cy - radius, cx + radius, cy + radius,
            outline=theme.BORDER, width=2,
        )
        for angle in range(0, 360, 45):
            inner = self._compass_endpoint(cx, cy, radius - 5, angle)
            outer = self._compass_endpoint(cx, cy, radius, angle)
            canvas.create_line(*inner, *outer, fill=theme.MUTED, width=1)
        for text, angle in (("N", 0), ("O", 90), ("S", 180), ("W", 270)):
            x, y = self._compass_endpoint(cx, cy, radius + 12, angle)
            canvas.create_text(
                x, y, text=text, fill=theme.TEXT, font=("Segoe UI Semibold", 6),
            )

        if self.rotor_target_azimuth is not None:
            x, y = self._compass_endpoint(cx, cy, radius - 9, self.rotor_target_azimuth)
            canvas.create_line(
                cx, cy, x, y, fill=theme.ACCENT, width=3, arrow=tk.LAST, dash=(4, 2)
            )
        if self.rotor_current_azimuth is not None:
            x, y = self._compass_endpoint(cx, cy, radius - 14, self.rotor_current_azimuth)
            canvas.create_line(
                cx, cy, x, y, fill=theme.OK, width=4, arrow=tk.LAST
            )
        canvas.create_oval(cx - 3, cy - 3, cx + 3, cy + 3, fill=theme.TEXT, outline="")

    def _refresh_rotor_controls(self):
        running = self.rotor_manager.running
        if hasattr(self, "rotor_start_button"):
            self.rotor_start_button.configure(
                state="disabled" if running or self.rotor_starting else "normal"
            )
        if hasattr(self, "rotor_stop_button"):
            self.rotor_stop_button.configure(state="normal" if running else "disabled")
        if hasattr(self, "rotor_turn_button"):
            self.rotor_turn_button.configure(
                state=(
                    "normal"
                    if running and self.rotor_target_azimuth is not None and not self.rotor_motion_busy
                    else "disabled"
                )
            )
        if hasattr(self, "rotor_qso_stop_button"):
            self.rotor_qso_stop_button.configure(state="normal" if running else "disabled")
        if hasattr(self, "rotor_qso_info"):
            target = (
                f"{self.rotor_target_azimuth:.0f}°"
                if self.rotor_target_azimuth is not None else "—"
            )
            current = (
                f"{self.rotor_current_azimuth:.1f}°"
                if self.rotor_current_azimuth is not None else
                ("verbunden · Position wird gelesen" if running else "nicht verbunden")
            )
            self.rotor_qso_info.configure(text=f"Rotor: {current}\nZiel: {target}")
        if hasattr(self, "rotor_disconnected_frame") and hasattr(self, "rotor_live_frame"):
            try:
                if running:
                    self.rotor_disconnected_frame.grid_remove()
                    self.rotor_live_frame.grid()
                else:
                    self.rotor_live_frame.grid_remove()
                    self.rotor_disconnected_frame.grid()
            except tk.TclError:
                pass

    def turn_rotor_to_qso(self):
        if self.rotor_target_azimuth is None:
            messagebox.showinfo(
                "Rotor",
                "Für die Gegenstation konnte noch keine Peilung berechnet werden.",
                parent=self,
            )
            return
        if not self.rotor_manager.running:
            messagebox.showinfo(
                "Rotor",
                "Bitte den Rotor zuerst unter CAT → Rotorsteuerung verbinden.",
                parent=self,
            )
            return
        if self.rotor_motion_busy:
            return

        target = self.rotor_target_azimuth
        elevation = (
            self.rotor_current_elevation
            if self.rotor_current_elevation is not None
            else 0.0
        )
        generation = self.rotor_generation
        self.rotor_motion_busy = True
        self._refresh_rotor_controls()
        self.status_var.set(f"Rotor dreht auf {target:.0f}° …")

        def worker():
            try:
                # A bearing-only command preserves the last known elevation.
                self.rotor_manager.set_position(target, elevation)
                error = ""
            except Exception as exc:
                error = str(exc)
            if not self.closing:
                self.after(0, lambda: self._rotor_motion_sent(generation, target, error))

        threading.Thread(target=worker, name="rotor-set-position", daemon=True).start()

    def _rotor_motion_sent(self, generation: int, target: float, error: str):
        self.rotor_motion_busy = False
        if generation != self.rotor_generation or self.closing:
            return
        self._refresh_rotor_controls()
        if error:
            self.status_var.set("Rotor konnte nicht gedreht werden")
            messagebox.showerror("Rotor", error, parent=self)
            return
        self.status_var.set(f"Rotor-Ziel {target:.0f}° gesetzt")
        interval = self.rotor_active_config.poll_interval_ms if self.rotor_active_config else 750
        self._schedule_rotor_poll(100, interval)

    def stop_rotor_motion(self):
        if not self.rotor_manager.running:
            return
        generation = self.rotor_generation
        self.status_var.set("Rotor wird gestoppt …")

        def worker():
            try:
                self.rotor_manager.stop_motion()
                error = ""
            except Exception as exc:
                error = str(exc)
            if not self.closing:
                self.after(0, lambda: self._rotor_stop_motion_finished(generation, error))

        threading.Thread(target=worker, name="rotor-stop-motion", daemon=True).start()

    def _rotor_stop_motion_finished(self, generation: int, error: str):
        if generation != self.rotor_generation or self.closing:
            return
        if error:
            self.status_var.set("Rotor-STOP fehlgeschlagen")
            messagebox.showerror("Rotor STOP", error, parent=self)
        else:
            self.status_var.set("Rotor gestoppt")
