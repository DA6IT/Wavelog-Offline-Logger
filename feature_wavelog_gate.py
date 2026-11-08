from __future__ import annotations

import atexit
import threading
import time
import tkinter as tk
from tkinter import messagebox, ttk

from app_common import write_startup_log
from logger_core import WavelogClient
from ui_theme import theme
from wavelog_gate import (
    DEFAULT_QSY_PORT, DEFAULT_RADIO_NAME, DEFAULT_WS_PORT, GateConfig, GateError, RadioState,
    WavelogGate, parse_origins,
)

# Rotor follow: ignore tiny changes and do not flood rotctld.
ROTOR_FOLLOW_MIN_DEGREES = 2.0
ROTOR_FOLLOW_MIN_SECONDS = 1.5


class WavelogGateFeatureMixin:
    """CAT-page section that replaces the separate WaveLogGate program."""

    def _init_wavelog_gate_feature(self) -> None:
        self.wavelog_gate = WavelogGate(
            on_qsy=self._gate_qsy,
            on_bearing=self._gate_bearing_from_thread,
            client_factory=self._gate_client,
            on_log=self._gate_log_from_thread,
            on_status=self._gate_status_from_thread,
        )
        atexit.register(self.wavelog_gate.stop)
        self.gate_client_settings: tuple[str, str] | None = None
        self.gate_last_rotor_target: tuple[float, float | None] | None = None
        self.gate_last_rotor_move = 0.0
        self.gate_rotor_busy = False

    # -- UI ------------------------------------------------------------------
    def _build_wavelog_gate_controls(self, parent, *, row: int):
        frame = ttk.LabelFrame(parent, text="Wavelog-Verbindung für Funkgerät (ersetzt WaveLogGate)", padding=10)
        frame.grid(row=row, column=0, sticky="ew", pady=(14, 0))
        frame.columnconfigure(1, weight=1)
        ttk.Label(
            frame,
            text=(
                "Der Logger übernimmt die Aufgaben von WaveLogGate: Wavelog sieht Frequenz und Modus, "
                "ein Klick auf einen DX-Spot in Wavelog stellt das Funkgerät ein, und der Rotor kann "
                "der Peilung aus Wavelog folgen. WaveLogGate bitte vorher beenden."
            ),
            style="Muted.Card.TLabel",
            wraplength=430,
        ).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 8))

        self.gate_radio_push_var = tk.BooleanVar(value=False)
        self.gate_qsy_var = tk.BooleanVar(value=False)
        self.gate_qsy_mode_var = tk.BooleanVar(value=True)
        self.gate_ws_var = tk.BooleanVar(value=False)
        self.gate_rotor_var = tk.BooleanVar(value=False)
        self.gate_radio_name_var = tk.StringVar(value=DEFAULT_RADIO_NAME)
        self.gate_qsy_port_var = tk.StringVar(value=str(DEFAULT_QSY_PORT))
        self.gate_ws_port_var = tk.StringVar(value=str(DEFAULT_WS_PORT))
        self.gate_origins_var = tk.StringVar(value="")

        checks = (
            (self.gate_radio_push_var, "Frequenz und Modus an Wavelog senden (Token mit radio:write)"),
            (self.gate_qsy_var, "QSY aus Wavelog annehmen (Klick auf Spot/Bandmap)"),
            (self.gate_qsy_mode_var, "Beim QSY auch den Modus setzen"),
            (self.gate_ws_var, "Live-Verbindung für Wavelog (in Wavelog Funkgerät „Live - WebSocket“ wählen)"),
            (self.gate_rotor_var, "Rotor folgt der Peilung aus Wavelog"),
        )
        for index, (variable, label) in enumerate(checks, start=1):
            ttk.Checkbutton(frame, text=label, variable=variable).grid(
                row=index, column=0, columnspan=2, sticky="w", pady=1,
            )

        fields = (
            ("Name in Wavelog", self.gate_radio_name_var),
            ("QSY-Port", self.gate_qsy_port_var),
            ("WebSocket-Port", self.gate_ws_port_var),
            ("Weitere Wavelog-Adressen", self.gate_origins_var),
        )
        base = len(checks) + 1
        for offset, (label, variable) in enumerate(fields):
            ttk.Label(frame, text=label, style="Card.TLabel").grid(
                row=base + offset, column=0, sticky="w", padx=(0, 10), pady=3,
            )
            ttk.Entry(frame, textvariable=variable).grid(row=base + offset, column=1, sticky="ew", pady=3)
        ttk.Label(
            frame,
            text=(
                "Anfragen werden nur von der eingetragenen Wavelog-URL angenommen. Wird Wavelog auch unter einer "
                "anderen Adresse geöffnet (z. B. LAN-IP), diese kommagetrennt bei „Weitere Wavelog-Adressen“ ergänzen."
            ),
            style="Muted.Card.TLabel",
            wraplength=430,
        ).grid(row=base + len(fields), column=0, columnspan=2, sticky="w", pady=(2, 6))

        self.gate_status_label = tk.Label(
            frame, text="Wavelog-Verbindung ist ausgeschaltet.", bg=theme.CARD, fg=theme.MUTED,
            font=("Segoe UI", 9), justify="left", anchor="w", wraplength=430,
        )
        self.gate_status_label.grid(row=base + len(fields) + 1, column=0, columnspan=2, sticky="ew", pady=(0, 8))
        buttons = ttk.Frame(frame, style="Card.TFrame")
        buttons.grid(row=base + len(fields) + 2, column=0, columnspan=2, sticky="ew")
        ttk.Button(
            buttons, text="Speichern & starten", style="Primary.TButton", command=self.save_and_start_wavelog_gate,
        ).pack(side="left")
        ttk.Button(
            buttons, text="Stoppen", style="Secondary.TButton", command=self.stop_wavelog_gate,
        ).pack(side="left", padx=(8, 0))

    def _gate_config_from_ui(self) -> GateConfig:
        def port(variable: tk.StringVar, label: str) -> int:
            try:
                return int(str(variable.get()).strip())
            except ValueError as exc:
                raise GateError(f"Ungültiger {label}") from exc

        settings = self._wavelog_online_settings()
        extra = self.gate_origins_var.get().strip()
        return GateConfig(
            radio_push=bool(self.gate_radio_push_var.get()),
            radio_name=(self.gate_radio_name_var.get().strip() or DEFAULT_RADIO_NAME)[:60],
            qsy=bool(self.gate_qsy_var.get()),
            qsy_port=port(self.gate_qsy_port_var, "QSY-Port"),
            qsy_set_mode=bool(self.gate_qsy_mode_var.get()),
            websocket=bool(self.gate_ws_var.get()),
            ws_port=port(self.gate_ws_port_var, "WebSocket-Port"),
            rotor_follow=bool(self.gate_rotor_var.get()),
            allowed_origins=parse_origins([settings.base_url, *parse_origins(extra)]),
        )

    def _load_wavelog_gate_settings_to_ui(self):
        if not hasattr(self, "gate_radio_push_var"):
            return
        settings = self._wavelog_online_settings()
        config = GateConfig.from_getter(self.db.get_setting, settings.base_url)
        self.gate_radio_push_var.set(config.radio_push)
        self.gate_qsy_var.set(config.qsy)
        self.gate_qsy_mode_var.set(config.qsy_set_mode)
        self.gate_ws_var.set(config.websocket)
        self.gate_rotor_var.set(config.rotor_follow)
        self.gate_radio_name_var.set(config.radio_name)
        self.gate_qsy_port_var.set(str(config.qsy_port))
        self.gate_ws_port_var.set(str(config.ws_port))
        self.gate_origins_var.set(self.db.get_setting("gate_allowed_origins", ""))

    def save_and_start_wavelog_gate(self):
        try:
            config = self._gate_config_from_ui()
            config.validate()
        except GateError as exc:
            messagebox.showerror("Wavelog-Verbindung", str(exc), parent=self)
            return
        extra = ", ".join(parse_origins(self.gate_origins_var.get()))
        for key, value in config.settings(extra).items():
            self.db.set_setting(key, value)
        self.gate_origins_var.set(extra)
        if not config.any_enabled:
            self._stop_wavelog_gate_runtime()
            self.status_var.set("Wavelog-Verbindung ausgeschaltet")
            return
        self._start_wavelog_gate(config, show_error=True)

    def _start_wavelog_gate(self, config: GateConfig, *, show_error: bool):
        settings = self._wavelog_online_settings()
        self.gate_client_settings = (settings.base_url, settings.token) if settings.base_url and settings.token else None
        try:
            self.wavelog_gate.start(config)
        except GateError as exc:
            write_startup_log("Wavelog-Verbindung: " + str(exc))
            if show_error:
                messagebox.showerror("Wavelog-Verbindung", str(exc), parent=self)
        self._refresh_gate_status()
        if config.radio_push and not self.gate_client_settings and show_error:
            messagebox.showwarning(
                "Wavelog-Verbindung",
                "Für das Senden von Frequenz und Modus bitte zuerst Wavelog-URL und API-v2-Token eintragen.",
                parent=self,
            )
        if (config.qsy or config.radio_push) and not self.cat_manager.running:
            self.status_var.set("Wavelog-Verbindung aktiv · CAT starten, damit Wavelog das Funkgerät sieht")
        else:
            self.status_var.set("Wavelog-Verbindung aktiv")

    def _autostart_wavelog_gate(self):
        if self.closing or self.wavelog_gate.running:
            return
        settings = self._wavelog_online_settings()
        config = GateConfig.from_getter(self.db.get_setting, settings.base_url)
        if not config.any_enabled:
            return
        try:
            config.validate()
        except GateError as exc:
            write_startup_log("Wavelog-Verbindung nicht gestartet: " + str(exc))
            return
        self._start_wavelog_gate(config, show_error=False)

    def stop_wavelog_gate(self):
        self._stop_wavelog_gate_runtime()
        self.status_var.set("Wavelog-Verbindung gestoppt")

    def _stop_wavelog_gate_runtime(self, *, update_ui: bool = True):
        try:
            self.wavelog_gate.stop()
        except Exception:
            pass
        if update_ui:
            self._refresh_gate_status()

    def _refresh_gate_status(self, status: dict | None = None):
        if not hasattr(self, "gate_status_label"):
            return
        status = status or dict(self.wavelog_gate.status)
        if not self.wavelog_gate.running:
            text, colour = "Wavelog-Verbindung ist ausgeschaltet.", theme.MUTED
        else:
            lines = [
                f"Senden an Wavelog: {status.get('radio_push')}"
                + (f" · zuletzt {status.get('last_push')}" if status.get("last_push") else ""),
                f"QSY: {status.get('qsy')}" + (f" · zuletzt {status.get('last_qsy')}" if status.get("last_qsy") else ""),
                f"WebSocket: {status.get('websocket')} · verbundene Browser: {status.get('ws_clients', 0)}",
            ]
            if status.get("push_error"):
                lines.append("Fehler: " + str(status.get("push_error"))[:240])
            text = "\n".join(lines)
            colour = theme.WARN if status.get("push_error") or "belegt" in text else theme.OK
        try:
            self.gate_status_label.configure(text=text, fg=colour)
        except tk.TclError:
            pass

    # -- callbacks from worker threads --------------------------------------
    def _gate_status_from_thread(self, status: dict):
        if not self.closing:
            try:
                self.after(0, lambda: self._refresh_gate_status(status))
            except (RuntimeError, tk.TclError):
                pass

    def _gate_log_from_thread(self, message: str):
        write_startup_log("Wavelog-Verbindung: " + message)

    def _gate_client(self):
        settings = self.gate_client_settings
        if not settings:
            return None
        return WavelogClient(settings[0], settings[1], timeout=8)

    def _gate_qsy(self, frequency_hz: int, hamlib_mode: str):
        """HTTP thread: tune the radio, then let the CAT poll show it."""
        if not self.cat_manager.running:
            raise GateError("CAT ist nicht gestartet")
        self.cat_manager.set_frequency_and_raw_mode(frequency_hz, hamlib_mode)
        if not self.closing:
            mhz = frequency_hz / 1_000_000
            self.after(0, lambda: self.status_var.set(f"QSY aus Wavelog: {mhz:.4f} MHz {hamlib_mode}".strip()))

    def _gate_bearing_from_thread(self, azimuth: float, elevation: float | None):
        if not self.closing:
            self.after(0, lambda: self._gate_follow_rotor(azimuth, elevation))

    def _gate_follow_rotor(self, azimuth: float, elevation: float | None):
        if self.closing or not self.rotor_manager.running or self.gate_rotor_busy or self.rotor_motion_busy:
            return
        last = self.gate_last_rotor_target
        if last is not None:
            delta_az = abs(((azimuth - last[0]) + 180) % 360 - 180)
            delta_el = abs((elevation or 0.0) - (last[1] or 0.0))
            if delta_az < ROTOR_FOLLOW_MIN_DEGREES and delta_el < ROTOR_FOLLOW_MIN_DEGREES:
                return
        if time.monotonic() - self.gate_last_rotor_move < ROTOR_FOLLOW_MIN_SECONDS:
            return
        target_el = elevation if elevation is not None else (self.rotor_current_elevation or 0.0)
        self.gate_last_rotor_target = (azimuth, elevation)
        self.gate_last_rotor_move = time.monotonic()
        self.gate_rotor_busy = True

        def worker():
            error = ""
            try:
                self.rotor_manager.set_position(azimuth, target_el)
            except Exception as exc:
                error = str(exc)
            if not self.closing:
                self.after(0, lambda: self._gate_rotor_done(azimuth, error))

        threading.Thread(target=worker, name="gate-rotor", daemon=True).start()

    def _gate_rotor_done(self, azimuth: float, error: str):
        self.gate_rotor_busy = False
        if error:
            self.status_var.set("Rotor (Wavelog-Peilung) fehlgeschlagen: " + error)
        else:
            self.status_var.set(f"Rotor folgt Wavelog: {azimuth:.0f}°")

    # -- called by the CAT poll (UI thread) -----------------------------------
    def _gate_radio_update(self, reading):
        gate = getattr(self, "wavelog_gate", None)
        if gate is None or not gate.running:
            return
        power = None
        try:
            raw_power = str(self.form_vars["tx_pwr"].get()).strip().replace(",", ".")
            power = float(raw_power) if raw_power else None
        except (KeyError, ValueError, AttributeError):
            power = None
        mode = (reading.raw_mode or "").strip().upper()
        gate.update_radio(RadioState(frequency_hz=int(reading.frequency_hz), mode=mode, power_w=power))
