from __future__ import annotations

import atexit
import base64
import io
import os
import re
import subprocess
import sys
import json
import threading
import time
import traceback
import webbrowser
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk
from tkinter import font as tkfont

from logger_core import (
    APP_NAME, VERSION, BANDS, MODES, LogStore, MetadataDB, WavelogClient,
    WavelogError, SyncEngine, ContestSyncEngine, app_data_dir, default_log_dir, band_from_mhz,
    qso_hash, CountryDB, ProfileManager, WavelogOnlineSettings, build_fast_log_qso, valid_contest_adif_name,
    secure_urlopen,
)
from cat_control import (
    CAT_BAUD_RATES, CAT_DATA_BITS, CAT_HANDSHAKES, CAT_LINE_STATES,
    CAT_PARITIES, CAT_STOP_BITS, DEFAULT_FLRIG_ENDPOINT, FLRIG_MODEL_ID,
    CatConfig, CatError, HamlibManager,
    RigModel, find_hamlib_dir, format_frequency_mhz, hamlib_version, list_rig_models,
    discover_flrig, list_serial_ports, map_hamlib_mode,
)
from hamlib_update import (
    HamlibRelease, backup_hamlib_dir,
    find_latest_windows_release, install_windows_release,
    restore_previous_windows_runtime, runtime_version, usable_hamlib_dir,
    version_from_output,
)
from external_logging import (
    ExternalLogError, UdpLogConfig, UdpLogEvent, UdpLogReceiver, UdpStatusEvent,
    find_duplicate_qso,
)
from dx_cluster import (
    DEFAULT_CLUSTER_HOST, DEFAULT_CLUSTER_PORT, DEFAULT_SPOTTER_HOST,
    DEFAULT_SPOTTER_PORT, DxClusterClient, DxClusterConfig, DxSpotterConfig,
    DxClusterError, DxSpot, SPOTTER_REGION_OPTIONS, normalize_worked_mode,
    select_dx_spot_candidate, spot_comment_with_mode, spot_sort_value, spotter_region_for_continent,
    worked_flags,
)
from update_check import (
    ReleaseInfo, current_windows_launcher, download_verified_asset, find_newer_release,
    select_update_asset, windows_update_helper_script,
)
from data_backup import BackupError, create_backup, inspect_backup, restore_backup
from whats_new import notes_for_version
from callbook import (
    CALLBOOK_SOURCE_DISABLED, CALLBOOK_SOURCE_QRZ, CALLBOOK_SOURCE_WAVELOG,
    CallbookError, CallbookResult, QrzClient, lookup_candidate,
    enrich_qso_from_callbook, normalize_wavelog_result,
)
from ui_preferences import PALETTES, UiPreferences, load_ui_preferences, save_ui_preferences, translate_text
from notifications import notify_qso_logged
from xota import (
    GPSService, ActivationReferenceService, ReverseGeocodeService,
    WavelogStationService, XotaActivation, XotaRepository,
    XOTA_PROGRAMS, distance_m, initial_bearing_degrees, maidenhead_coordinates,
    maidenhead_locator, merge_candidate_references, normalize_references,
)

try:
    from PIL import Image, ImageTk
except ImportError:  # The logger stays fully usable; PNG/GIF still use Tk directly.
    Image = None
    ImageTk = None


BG = "#f6f8fb"
CARD = "#ffffff"
TEXT = "#172033"
MUTED = "#667085"
ACCENT = "#0969da"
ACCENT_DARK = "#0556b3"
BORDER = "#d8dee8"
OK = "#1a8f36"
WARN = "#9a6700"
ERR = "#b42318"
SIDEBAR = "#ffffff"
SIDEBAR_TEXT = "#253044"
ACTIVE_BG = "#eaf2ff"
SURFACE = "#f8fbff"
INPUT_BG = "#ffffff"
PHOTO_BG = "#f3f6fa"
NEUTRAL_BADGE_BG = "#edf2f7"
OK_BADGE_BG = "#e9f7ec"
WARN_BADGE_BG = "#fff4df"
NAV_HOVER = "#f1f5fb"
NAV_ACTIVE_HOVER = "#dceaff"
PROGRESS_BG = "#e9eef3"
DISABLED = "#9bb8cf"

BASE_UI_WIDTH = 1420
BASE_UI_HEIGHT = 820
MIN_UI_WIDTH = 900
MIN_UI_HEIGHT = 580


def responsive_ui_scale(width: int, height: int) -> float:
    """Return a stable, bounded zoom factor for the main application window."""
    width = max(1, int(width))
    height = max(1, int(height))
    raw = min(width / BASE_UI_WIDTH, height / BASE_UI_HEIGHT)
    # Five-percent steps prevent a complete widget relayout for every single
    # pixel while the user drags a window border.
    stepped = round(raw * 20.0) / 20.0
    return max(0.65, min(1.10, stepped))


def responsive_spacing_scale(ui_scale: float) -> float:
    """Shrink decorative spacing faster than readable text."""
    return max(0.35, min(1.10, (float(ui_scale) - 0.65) / 0.35))


def _set_palette(theme: str) -> None:
    palette = PALETTES.get(theme, PALETTES["light"])
    globals().update(palette)

CALLBOOK_SOURCE_LABELS_DE = {
    "Über Wavelog (empfohlen)": CALLBOOK_SOURCE_WAVELOG,
    "Direkt über QRZ.com": CALLBOOK_SOURCE_QRZ,
    "Deaktiviert": CALLBOOK_SOURCE_DISABLED,
}
CALLBOOK_SOURCE_LABELS_EN = {
    "Via Wavelog (recommended)": CALLBOOK_SOURCE_WAVELOG,
    "Directly via QRZ.com": CALLBOOK_SOURCE_QRZ,
    "Disabled": CALLBOOK_SOURCE_DISABLED,
}
CALLBOOK_SOURCE_LABELS = {**CALLBOOK_SOURCE_LABELS_DE, **CALLBOOK_SOURCE_LABELS_EN}


def callbook_source_labels(language: str) -> dict[str, str]:
    return CALLBOOK_SOURCE_LABELS_EN if language == "en" else CALLBOOK_SOURCE_LABELS_DE


def callbook_source_name(source: str, language: str) -> str:
    labels = callbook_source_labels(language)
    names = {value: key for key, value in labels.items()}
    return names.get(source, names[CALLBOOK_SOURCE_WAVELOG])


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


def configure_responsive_dialog(dialog: tk.Toplevel, preferred: tuple[int, int], minimum: tuple[int, int]) -> None:
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

    def __init__(self, parent: "LoggerApp", reason: str, status_text: str):
        super().__init__(parent)
        self.parent = parent
        self.reason = reason
        self.title(parent._tr("Wavelog-Synchronisierung"))
        configure_responsive_dialog(self, (640, 330), (460, 260))
        self.transient(parent)
        self.configure(bg=CARD)
        self.protocol("WM_DELETE_WINDOW", lambda: None)

        body = tk.Frame(self, bg=CARD, padx=28, pady=24)
        body.pack(fill="both", expand=True)
        self.heading = tk.Label(
            body, text=parent._tr("Wavelog wird synchronisiert"), bg=CARD, fg=TEXT,
            font=("Segoe UI Semibold", 17), anchor="w",
        )
        self.heading.pack(fill="x")
        self.explanation = tk.Label(
            body, text="", bg=CARD, fg=MUTED, font=("Segoe UI", 10),
            justify="left", anchor="w", wraplength=570,
        )
        self.explanation.pack(fill="x", pady=(8, 16))
        self.progress = ttk.Progressbar(body, mode="indeterminate", length=570)
        self.progress.pack(fill="x")
        self.progress.start(12)
        self.status_label = tk.Label(
            body, text=parent._tr(status_text), bg=CARD, fg=TEXT, font=("Segoe UI", 10),
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
        self.heading.configure(text=self.parent._tr("Wavelog wird synchronisiert"), fg=TEXT)
        self.explanation.configure(text=self.parent._tr(explanation))
        self.status_label.configure(text=self.parent._tr(status_text), fg=TEXT)
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
        self.heading.configure(text=self.parent._tr(heading), fg=(OK if success else ERR))
        self.explanation.configure(text=self.parent._tr(suffix))
        self.status_label.configure(text=self.parent._tr(details), fg=(TEXT if success else ERR))
        self.ok_button.configure(state="normal")
        self.ok_button.focus_set()


class LoggerApp(tk.Tk):
    def __init__(self):
        super().__init__()
        # Build the complete interface while hidden.  It is presented and
        # focused explicitly once all widgets have their final geometry.
        self.withdraw()
        self._ui_scale = 1.0
        self._responsive_resize_job = None
        self._responsive_fonts: list[tuple[tkfont.Font, int]] = []
        self._responsive_wraplengths: list[tuple[tk.Widget, int]] = []
        self._responsive_geometry_paddings: list[tuple[tk.Widget, str, str, tuple[int, ...]]] = []
        self._responsive_card_frames: list[ttk.Frame] = []
        self._settings_optional_help: list[tk.Widget] = []
        self._brand_logo_source = None
        self.data_dir = app_data_dir()
        self.ui_preferences = load_ui_preferences(self.data_dir)
        self.language = self.ui_preferences.language
        _set_palette(self.ui_preferences.theme)
        self.title(f"{APP_NAME} {VERSION}")
        screen_width = max(MIN_UI_WIDTH, self.winfo_screenwidth() - 80)
        screen_height = max(MIN_UI_HEIGHT, self.winfo_screenheight() - 110)
        initial_width = min(BASE_UI_WIDTH, screen_width)
        initial_height = min(BASE_UI_HEIGHT, screen_height)
        self.geometry(f"{initial_width}x{initial_height}")
        self.minsize(MIN_UI_WIDTH, MIN_UI_HEIGHT)
        self.configure(bg=BG)
        self.protocol("WM_DELETE_WINDOW", self.on_close)
        self.closing = False
        self.shutdown_started = False
        self.sync_busy = False
        self.sync_is_automatic = False
        self.sync_operation = ""
        self.sync_reason = ""
        self.sync_progress_dialog: SyncProgressDialog | None = None
        self.startup_full_sync_pending = True
        self.close_requested = False
        self.close_services_stopped = False
        self.wavelog_online = False
        self.wavelog_check_generation = 0
        self.wavelog_check_busy = False
        self.wavelog_check_job = None
        self.auto_sync_job = None
        self.external_enrichment_pending: set[tuple[str, str]] = set()
        self.station_rows: list[dict] = []
        self.station_by_label: dict[str, dict] = {}
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
        self.udp_log_receiver = UdpLogReceiver(app_version=VERSION)
        atexit.register(self.udp_log_receiver.stop)
        self.udp_log_generation = 0
        self.udp_log_received = 0
        self.wsjtx_live_form_call = ""
        self.dx_cluster = DxClusterClient()
        atexit.register(self.dx_cluster.stop)
        self.dx_cluster_generation = 0
        self.dx_spotter = DxClusterClient()
        atexit.register(self.dx_spotter.stop)
        self.dx_spotter_generation = 0
        self.dx_spotter_active_config: DxSpotterConfig | None = None
        self.dx_cluster_spots: list[tuple[str, DxSpot]] = []
        self.dx_cluster_spot_by_id: dict[str, DxSpot] = {}
        self.dx_cluster_sequence = 0
        self.dx_cluster_country_cache: dict[str, str] = {}
        self.dx_cluster_continent_cache: dict[str, str] = {}
        self.dx_cluster_worked_calls: set[tuple[str, str, str]] = set()
        self.dx_cluster_worked_countries: set[tuple[str, str, str]] = set()
        self.qso_worked_counts: Counter[tuple[str, str, str]] = Counter()
        self.qso_worked_call_totals: Counter[str] = Counter()
        self.qso_worked_history: dict[str, list[dict[str, str]]] = {}
        self.dx_cluster_filter_job = None
        self.dx_cluster_session_received = 0
        self.dx_cluster_last_spot_utc: datetime | None = None
        self.dx_cluster_seen_keys: set[tuple] = set()
        self.dx_cluster_sort_key = "time"
        self.dx_cluster_sort_descending = True
        self.fast_log_session_started = datetime.now(timezone.utc)
        self.fast_log_session_ids: list[str] = []
        self.fast_log_worked_keys: set[tuple[str, str, str]] = set()
        self.callbook_generation = 0
        self.callbook_lookup_job = None
        self.callbook_result: CallbookResult | None = None
        self.callbook_photo = None
        self.callbook_image_bytes: bytes | None = None
        self.qrz_client: QrzClient | None = None
        self.qrz_client_credentials: tuple[str, str] | None = None
        self.callbook_autofill: dict[str, str] = {}
        self.callbook_last_call = ""
        self.last_spottable_qso: dict | None = None
        self.update_busy = False
        self.update_progress_dialog: tk.Toplevel | None = None

        self.country_db = CountryDB(Path(__file__).resolve().parent / "cty.dat")
        self.current_country = None
        self.profile_manager = ProfileManager(self.data_dir)
        self.active_profile_id = self.profile_manager.active_id
        self.db = None
        self.store = None
        self.pending_adif_migration_report = None
        self._open_profile_storage(self.active_profile_id)

        self._setup_style()
        self._build_shell()
        self._build_log_page()
        self._build_fast_log_page()
        self._build_contest_page()
        self._build_xota_page()
        self._build_qsos_page()
        self._build_stats_page()
        self._build_cat_page()
        self._build_dx_cluster_page()
        self._build_udp_log_page()
        self._build_settings_page()
        self._load_settings_to_ui()
        self._install_dialog_translation()
        self._localize_widget_tree(self)
        self._capture_responsive_widgets()
        self.bind("<Configure>", self._window_configured, add="+")
        self.after(700, self._localization_tick)
        self._show_page("log")
        self._tick_clock()
        self.refresh_qsos()
        self._load_last_spottable_qso()
        self.after(90, self._present_main_window)
        self.after(350, self._show_adif_migration_report)
        self.after(600, self._autostart_udp_log)
        self.after(950, self._show_whats_new_if_needed)
        self.after(1800, self._start_update_check)
        self.after(2500, self._start_wavelog_monitor)
        write_startup_log(f"{APP_NAME} {VERSION} gestartet")

    def _tr(self, value: object) -> str:
        return translate_text(value, self.language)

    def _present_main_window(self):
        """Show the completed window and reliably bring it to the foreground."""
        if self.closing:
            return
        self.deiconify()
        self.update_idletasks()
        self._apply_responsive_scale(force=True)
        try:
            self.lift()
            # Windows may reject a normal foreground request from a freshly
            # spawned GUI process.  A short topmost pulse makes the window
            # visible without leaving it permanently above other programs.
            self.attributes("-topmost", True)
            self.focus_force()
        except tk.TclError:
            pass
        self.after(180, self._finish_window_presentation)

    def _show_adif_migration_report(self):
        report = self.pending_adif_migration_report
        self.pending_adif_migration_report = None
        if not report or self.closing:
            return
        messagebox.showinfo(
            "ADI-Logbuch zusammengeführt",
            f"{report.get('sources', 0)} bisherige ADI-Datei(en) wurden sicher in eine Datei "
            f"mit {report.get('records', 0)} QSO(s) zusammengeführt.\n\n"
            f"Neue Logdatei:\n{report.get('target', '')}\n\n"
            f"Wiederherstellungs-ZIP:\n{report.get('backup', '')}",
            parent=self,
        )

    def _finish_window_presentation(self):
        if self.closing:
            return
        try:
            self.attributes("-topmost", False)
            self.lift()
            self.focus_force()
            self.call_entry.focus_set()
        except (AttributeError, tk.TclError):
            pass

    def _window_configured(self, event=None):
        if self.closing or (event is not None and event.widget is not self):
            return
        if self._responsive_resize_job is not None:
            try:
                self.after_cancel(self._responsive_resize_job)
            except tk.TclError:
                pass
        self._responsive_resize_job = self.after(70, self._apply_responsive_scale)

    def _capture_responsive_widgets(self):
        """Remember original visual metrics so resizing can zoom without drift."""
        self._responsive_fonts.clear()
        self._responsive_wraplengths.clear()
        self._responsive_geometry_paddings.clear()

        def padding_values(value) -> tuple[int, ...]:
            try:
                parts = self.tk.splitlist(str(value))
                return tuple(int(round(float(part))) for part in parts)
            except (TypeError, ValueError, tk.TclError):
                return ()

        def visit(widget):
            try:
                children = widget.winfo_children()
            except tk.TclError:
                children = ()
            for child in children:
                visit(child)

            try:
                font_spec = widget.cget("font")
                if font_spec:
                    responsive_font = tkfont.Font(root=self, font=font_spec)
                    base_size = int(responsive_font.cget("size"))
                    if base_size:
                        widget.configure(font=responsive_font)
                        self._responsive_fonts.append((responsive_font, base_size))
            except (KeyError, TypeError, ValueError, tk.TclError):
                pass

            try:
                wraplength = int(float(widget.cget("wraplength")))
                if wraplength > 0:
                    self._responsive_wraplengths.append((widget, wraplength))
            except (KeyError, TypeError, ValueError, tk.TclError):
                pass

            try:
                manager = widget.winfo_manager()
                if manager == "grid":
                    info = widget.grid_info()
                elif manager == "pack":
                    info = widget.pack_info()
                else:
                    info = {}
                for option in ("padx", "pady", "ipadx", "ipady"):
                    values = padding_values(info.get(option, ""))
                    if values and any(values):
                        self._responsive_geometry_paddings.append((widget, manager, option, values))
            except (KeyError, TypeError, ValueError, tk.TclError):
                pass

        visit(self)

    def _apply_responsive_scale(self, force: bool = False):
        self._responsive_resize_job = None
        if self.closing:
            return
        scale = responsive_ui_scale(self.winfo_width(), self.winfo_height())
        if not force and abs(scale - self._ui_scale) < 0.001:
            self._apply_settings_responsive_layout()
            self._apply_xota_responsive_layout()
            return
        self._ui_scale = scale

        for responsive_font, base_size in self._responsive_fonts:
            magnitude = max(6, int(round(abs(base_size) * scale)))
            responsive_font.configure(size=(-magnitude if base_size < 0 else magnitude))
        for widget, base_wraplength in self._responsive_wraplengths:
            try:
                widget.configure(wraplength=max(80, int(round(base_wraplength * scale))))
            except tk.TclError:
                pass
        # Empty space must contract more quickly than text.  Otherwise a page
        # can be clipped even though every individual font was scaled down.
        spacing_scale = responsive_spacing_scale(scale)
        for widget, manager, option, base_values in self._responsive_geometry_paddings:
            try:
                scaled = tuple(max(0, int(round(value * spacing_scale))) for value in base_values)
                value = scaled[0] if len(scaled) == 1 else scaled
                if manager == "grid":
                    widget.grid_configure(**{option: value})
                elif manager == "pack":
                    widget.pack_configure(**{option: value})
            except tk.TclError:
                pass
        for card_frame in self._responsive_card_frames:
            try:
                card_frame.configure(padding=max(8, int(round(16 * scale))))
            except tk.TclError:
                pass

        self._setup_style(scale)
        if hasattr(self, "sidebar"):
            self.sidebar.configure(width=max(145, int(round(205 * scale))))
        if hasattr(self, "main"):
            self.main.configure(padding=(
                max(12, int(round(22 * scale))),
                max(9, int(round(16 * scale))),
            ))
        if hasattr(self, "clock_card"):
            self.clock_card.configure(
                width=max(150, int(round(178 * scale))),
                height=max(44, int(round(52 * scale))),
            )
        if hasattr(self, "log_page"):
            self.log_page.columnconfigure(1, minsize=max(255, int(round(370 * scale))))
        if hasattr(self, "callbook_image_frame"):
            self.callbook_image_frame.configure(height=max(105, int(round(160 * scale))))
        if hasattr(self, "qso_history_frame") and hasattr(self, "call_var"):
            self._update_qso_worked_history(self.call_var.get().strip().upper())
        self._apply_settings_responsive_layout()
        self._apply_xota_responsive_layout()
        self._render_brand_logo()
        if self.callbook_image_bytes:
            self._render_callbook_image(self.callbook_image_bytes)

    def _apply_settings_responsive_layout(self):
        """Keep every settings action reachable without a scrolling page."""
        if not self._settings_optional_help:
            return
        compact = self.winfo_height() < 810
        for widget in self._settings_optional_help:
            try:
                if compact:
                    widget.grid_remove()
                else:
                    widget.grid()
            except tk.TclError:
                pass

    def _render_brand_logo(self):
        if self._brand_logo_source is None or not hasattr(self, "brand_label") or ImageTk is None:
            return
        try:
            image = self._brand_logo_source.copy()
            image.thumbnail(
                (max(105, int(round(170 * self._ui_scale))), max(42, int(round(70 * self._ui_scale)))),
                Image.Resampling.LANCZOS,
            )
            self.brand_logo_photo = ImageTk.PhotoImage(image)
            self.brand_label.configure(image=self.brand_logo_photo)
        except Exception as exc:
            write_startup_log("Logo konnte nicht responsiv skaliert werden: " + repr(exc))

    def _canonical_choice(self, value: str, canonical_values) -> str:
        for canonical in canonical_values:
            if value in {canonical, self._tr(canonical)}:
                return canonical
        return value

    def _install_dialog_translation(self):
        if self.language != "en" or getattr(messagebox, "_da6it_translated", False):
            return
        for name in ("showinfo", "showwarning", "showerror", "askquestion", "askokcancel", "askretrycancel", "askyesno", "askyesnocancel"):
            original = getattr(messagebox, name, None)
            if not original:
                continue
            def translated(title, message, *args, _original=original, **kwargs):
                return _original(self._tr(title), self._tr(message), *args, **kwargs)
            setattr(messagebox, name, translated)
        messagebox._da6it_translated = True
        original_askstring = simpledialog.askstring
        def translated_askstring(title, prompt, *args, **kwargs):
            return original_askstring(self._tr(title), self._tr(prompt), *args, **kwargs)
        simpledialog.askstring = translated_askstring

    def _localize_widget_tree(self, parent):
        if self.language != "en":
            return
        try:
            widgets = [parent, *parent.winfo_children()]
        except Exception:
            return
        for widget in widgets:
            if widget is not parent:
                self._localize_widget_tree(widget)
            try:
                if isinstance(widget, (tk.Tk, tk.Toplevel)):
                    current_title = widget.title()
                    translated_title = self._tr(current_title)
                    if translated_title != current_title:
                        widget.title(translated_title)
                if isinstance(widget, (tk.Label, tk.Button, tk.Checkbutton, tk.Radiobutton, tk.LabelFrame,
                                       ttk.Label, ttk.Button, ttk.Checkbutton, ttk.Radiobutton, ttk.LabelFrame)):
                    variable_name = str(widget.cget("textvariable") or "")
                    if variable_name:
                        current = widget.getvar(variable_name)
                        translated = self._tr(current)
                        if translated != current:
                            widget.setvar(variable_name, translated)
                    else:
                        current = widget.cget("text")
                        translated = self._tr(current)
                        if translated != current:
                            widget.configure(text=translated)
                if isinstance(widget, ttk.Notebook):
                    for tab_id in widget.tabs():
                        current = widget.tab(tab_id, "text")
                        translated = self._tr(current)
                        if translated != current:
                            widget.tab(tab_id, text=translated)
                if isinstance(widget, ttk.Treeview):
                    for column in widget["columns"]:
                        current = widget.heading(column, "text")
                        translated = self._tr(current)
                        if translated != current:
                            widget.heading(column, text=translated)
            except (tk.TclError, RuntimeError):
                pass

    def _localization_tick(self):
        if self.closing:
            return
        self._localize_widget_tree(self)
        self.after(700, self._localization_tick)

    def _show_whats_new_if_needed(self):
        if self.closing or self.ui_preferences.last_whats_new_version == VERSION:
            return
        if notes_for_version(VERSION, self.language):
            self._show_whats_new(mark_seen=True)

    def _show_whats_new(self, *, mark_seen: bool = False):
        notes = notes_for_version(VERSION, self.language)
        if not notes:
            messagebox.showinfo("Was ist neu?", "Für diese Version liegen keine Versionshinweise vor.", parent=self)
            return
        if mark_seen:
            self.ui_preferences = UiPreferences(
                language=self.ui_preferences.language,
                theme=self.ui_preferences.theme,
                qso_notifications=self.ui_preferences.qso_notifications,
                last_whats_new_version=VERSION,
            )
            save_ui_preferences(self.data_dir, self.ui_preferences)
        dialog = tk.Toplevel(self)
        dialog.title(f"Neu in Version {VERSION}")
        dialog.transient(self)
        dialog.configure(bg=BG)
        dialog.resizable(True, True)
        dialog.minsize(480, 330)
        body = ttk.Frame(dialog, padding=24)
        body.pack(fill="both", expand=True)
        ttk.Label(body, text=f"Neu in Version {VERSION}", style="PageTitle.TLabel").pack(anchor="w")
        ttk.Label(
            body, text="Die wichtigsten Neuerungen auf einen Blick:",
            style="Muted.TLabel",
        ).pack(anchor="w", pady=(4, 16))
        for note in notes:
            ttk.Label(body, text="• " + note, wraplength=560, justify="left").pack(anchor="w", fill="x", pady=4)
        actions = ttk.Frame(body)
        actions.pack(side="bottom", fill="x", pady=(22, 0))
        ttk.Button(
            actions, text="Vollständiges Changelog",
            command=lambda: webbrowser.open(f"https://github.com/DA6IT/Wavelog-Offline-Logger/releases/tag/v{VERSION}"),
        ).pack(side="left")
        ttk.Button(actions, text="Loslegen", style="Primary.TButton", command=dialog.destroy).pack(side="right")
        dialog.update_idletasks()
        width = min(660, max(480, self.winfo_screenwidth() - 100))
        height = min(430, max(330, self.winfo_screenheight() - 120))
        x = max(0, self.winfo_rootx() + (self.winfo_width() - width) // 2)
        y = max(0, self.winfo_rooty() + (self.winfo_height() - height) // 2)
        dialog.geometry(f"{width}x{height}+{x}+{y}")
        dialog.grab_set()
        dialog.focus_force()

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
        install = messagebox.askyesno(
            "Update verfügbar",
            f"Eine neue {kind} ist verfügbar: v{release.version}\n\n"
            "Möchtest du das passende Paket automatisch herunterladen, sicher prüfen "
            "und installieren?\n\nUnter Windows wird die App anschließend neu gestartet.",
            parent=self,
        )
        if install:
            self._start_update_download(release)

    def _start_update_download(self, release: ReleaseInfo):
        if self.update_busy or self.closing:
            return
        asset = select_update_asset(release)
        if asset is None:
            if messagebox.askyesno(
                "Kein automatisches Paket gefunden",
                "Für dieses System wurde kein passendes Update-Paket gefunden. "
                "Möchtest du die Downloadseite öffnen?",
                parent=self,
            ):
                webbrowser.open(release.url)
            return
        self.update_busy = True
        dialog = tk.Toplevel(self)
        self.update_progress_dialog = dialog
        dialog.title("Update wird vorbereitet")
        dialog.transient(self)
        dialog.resizable(False, False)
        dialog.protocol("WM_DELETE_WINDOW", lambda: None)
        frame = ttk.Frame(dialog, padding=22)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text=f"Version {release.version} wird heruntergeladen …", style="CardTitle.TLabel").pack(anchor="w")
        status = ttk.Label(frame, text="Prüfsumme wird geladen …", style="Muted.TLabel")
        status.pack(anchor="w", pady=(8, 12))
        progress = ttk.Progressbar(frame, length=420, mode="indeterminate")
        progress.pack(fill="x")
        progress.start(12)
        dialog.update_idletasks()
        dialog.geometry(f"470x145+{max(0, self.winfo_rootx()+80)}+{max(0, self.winfo_rooty()+80)}")
        dialog.grab_set()

        def on_progress(received: int, total: int):
            if not self.closing:
                self.after(0, lambda: self._update_download_progress(progress, status, received, total))

        def worker():
            try:
                package, checksum = download_verified_asset(
                    release, asset, self.data_dir / "updates", progress=on_progress,
                )
                if not self.closing:
                    self.after(0, lambda: self._update_download_finished(release, package, checksum))
            except Exception as exc:
                message = str(exc)
                if not self.closing:
                    self.after(0, lambda: self._update_download_failed(message))

        threading.Thread(target=worker, name="verified-update-download", daemon=True).start()

    def _update_download_progress(self, progress: ttk.Progressbar, status: ttk.Label, received: int, total: int):
        if total > 0:
            progress.stop()
            progress.configure(mode="determinate", maximum=total, value=received)
            status.configure(text=f"{received / 1024 / 1024:.1f} von {total / 1024 / 1024:.1f} MiB geladen …")
        else:
            status.configure(text=f"{received / 1024 / 1024:.1f} MiB geladen …")

    def _close_update_progress(self):
        dialog = self.update_progress_dialog
        self.update_progress_dialog = None
        self.update_busy = False
        if dialog is not None:
            try:
                dialog.grab_release()
                dialog.destroy()
            except tk.TclError:
                pass

    def _update_download_failed(self, message: str):
        self._close_update_progress()
        messagebox.showerror(
            "Update fehlgeschlagen",
            "Das Update wurde nicht installiert. Die vorhandene Version bleibt unverändert.\n\n" + message,
            parent=self,
        )

    def _update_download_finished(self, release: ReleaseInfo, package: Path, checksum: str):
        self._close_update_progress()
        launcher = current_windows_launcher()
        launcher_pid = os.environ.get("WAVELOG_LAUNCHER_PID", "").strip()
        if os.name == "nt" and package.suffix.lower() == ".exe":
            if launcher is None or not launcher_pid.isdigit():
                messagebox.showerror(
                    "Update fehlgeschlagen",
                    "Die aktuell gestartete Programmdatei konnte nicht eindeutig bestimmt werden. "
                    "Das geprüfte Update wurde deshalb nicht automatisch installiert.\n\n"
                    f"Download: {package}",
                    parent=self,
                )
                return
            try:
                self._schedule_windows_update(package, launcher, int(launcher_pid))
            except Exception as exc:
                messagebox.showerror("Update fehlgeschlagen", str(exc), parent=self)
                return
            messagebox.showinfo(
                "Update geprüft",
                f"Version {release.version} wurde vollständig heruntergeladen und per SHA-256 geprüft.\n\n"
                "Die aktuell gestartete Programmdatei wird jetzt ersetzt und automatisch neu gestartet:\n\n"
                f"{launcher}",
                parent=self,
            )
            self.close_requested = True
            self._begin_close_sequence()
            return
        messagebox.showinfo(
            "Update heruntergeladen",
            f"Das Paket wurde per SHA-256 geprüft und gespeichert:\n\n{package}\n\n"
            "Auf diesem System muss das Paket anschließend einmal manuell installiert werden.",
            parent=self,
        )

    def _schedule_windows_update(self, package: Path, launcher: Path, launcher_pid: int):
        updates_dir = self.data_dir / "updates"
        updates_dir.mkdir(parents=True, exist_ok=True)
        helper = updates_dir / "apply-update.ps1"
        # Test the real launcher directory before closing the application. A
        # custom filename or location is preserved; only that exact file is
        # replaced after the launcher process has exited.
        probe = launcher.parent / f".wavelog-update-write-test-{os.getpid()}.tmp"
        try:
            probe.write_bytes(b"write-test")
        finally:
            probe.unlink(missing_ok=True)
        helper.write_text(windows_update_helper_script(), encoding="utf-8-sig")
        update_log = updates_dir / "update.log"
        flags = 0x00000008 | 0x00000200 | 0x01000000  # detached, new group, break away from launcher job
        subprocess.Popen(
            [
                "powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-WindowStyle", "Hidden",
                "-File", str(helper), "-ProcessId", str(launcher_pid), "-Target", str(launcher),
                "-Package", str(package), "-Log", str(update_log),
            ],
            close_fds=True,
            creationflags=flags,
        )

    # ---------- Wavelog online mode ----------
    def _wavelog_online_settings(self) -> WavelogOnlineSettings:
        return WavelogOnlineSettings.from_storage(self.db.get_setting, self.db.get_token)

    def _set_wavelog_mode_ui(self, online: bool, *, configured: bool = True):
        self.wavelog_online = bool(online)
        settings = self._wavelog_online_settings()
        if online:
            mode_text = "●  WAVELOG ONLINE"
            mode_color = OK
            hint = "Verbunden · neuer QSO-Push aktiv" if settings.auto_sync else "Verbunden · manueller Sync"
        else:
            mode_text = "●  LOCAL ONLY"
            mode_color = ACCENT
            hint = "Wavelog nicht eingerichtet." if not configured else "Offline · QSOs bleiben lokal."
        if hasattr(self, "footer_mode_label"):
            self.footer_mode_label.configure(text=self._tr(mode_text), fg=mode_color)
        if hasattr(self, "sidebar_mode_label"):
            self.sidebar_mode_label.configure(text=self._tr(mode_text), fg=mode_color)
            self.sidebar_mode_hint.configure(text=self._tr(hint))

    def _start_wavelog_monitor(self):
        self._schedule_wavelog_check(0)

    def _schedule_wavelog_check(self, delay_ms: int):
        if self.wavelog_check_job is not None:
            try:
                self.after_cancel(self.wavelog_check_job)
            except Exception:
                pass
        self.wavelog_check_job = None
        if not self.closing:
            self.wavelog_check_job = self.after(max(0, int(delay_ms)), self._wavelog_monitor_tick)

    def _reset_wavelog_monitor(self, *, delay_ms: int = 500):
        self.wavelog_check_generation += 1
        self.wavelog_check_busy = False
        if self.wavelog_check_job is not None:
            try:
                self.after_cancel(self.wavelog_check_job)
            except Exception:
                pass
            self.wavelog_check_job = None
        if self.auto_sync_job is not None:
            try:
                self.after_cancel(self.auto_sync_job)
            except Exception:
                pass
            self.auto_sync_job = None
        settings = self._wavelog_online_settings()
        self._set_wavelog_mode_ui(False, configured=settings.configured)
        self._schedule_wavelog_check(delay_ms)

    def _wavelog_monitor_tick(self):
        self.wavelog_check_job = None
        if self.closing or self.wavelog_check_busy:
            return
        settings = self._wavelog_online_settings()
        if not settings.configured:
            self.startup_full_sync_pending = False
            self._set_wavelog_mode_ui(False, configured=False)
            self._schedule_wavelog_check(60_000)
            return
        self.wavelog_check_busy = True
        generation = self.wavelog_check_generation

        def worker():
            error = ""
            try:
                WavelogClient(settings.base_url, settings.token, timeout=5).token_info()
            except Exception as exc:
                error = str(exc)
            if not self.closing:
                self.after(0, lambda: self._wavelog_check_finished(generation, not error, error))

        threading.Thread(target=worker, name="wavelog-online-check", daemon=True).start()

    def _wavelog_check_finished(self, generation: int, online: bool, error: str):
        if generation != self.wavelog_check_generation or self.closing:
            return
        self.wavelog_check_busy = False
        was_online = self.wavelog_online
        self._set_wavelog_mode_ui(online)
        if online:
            if not was_online:
                self.status_var.set("Wavelog ist wieder erreichbar · Online-Modus aktiv")
            settings = self._wavelog_online_settings()
            if settings.full_sync_on_start and self.startup_full_sync_pending and not self.sync_busy:
                self.startup_full_sync_pending = False
                self._start_sync(automatic=True, reason="startup")
            else:
                # The start option applies only to the first successful probe
                # of this app session. Enabling it later takes effect on the
                # next real application start, not immediately after saving.
                self.startup_full_sync_pending = False
            if not was_online and not self.sync_busy:
                self._request_auto_sync(delay_ms=600)
            self._schedule_wavelog_check(60_000)
        else:
            self.startup_full_sync_pending = False
            if was_online:
                self.status_var.set("Wavelog nicht erreichbar · LOCAL ONLY")
            if error:
                write_startup_log("Wavelog-Erreichbarkeitsprüfung: " + error)
            self._schedule_wavelog_check(15_000)

    def _request_auto_sync(self, *, delay_ms: int = 1200):
        if self.closing or self.close_requested or self.sync_progress_dialog is not None:
            return
        if any(profile_id == self.active_profile_id for profile_id, _local_id in self.external_enrichment_pending):
            return
        settings = self._wavelog_online_settings()
        candidate_count = len(self.db.list_new_upload_candidates())
        if not settings.should_auto_sync(
            online=self.wavelog_online,
            sync_busy=self.sync_busy,
            candidate_count=candidate_count,
        ):
            return
        if self.auto_sync_job is not None:
            try:
                self.after_cancel(self.auto_sync_job)
            except Exception:
                pass
        self.auto_sync_job = self.after(max(0, int(delay_ms)), self._run_auto_sync)

    def _run_auto_sync(self):
        self.auto_sync_job = None
        if self.closing or self.close_requested or self.sync_progress_dialog is not None:
            return
        if any(profile_id == self.active_profile_id for profile_id, _local_id in self.external_enrichment_pending):
            return
        settings = self._wavelog_online_settings()
        if settings.should_auto_sync(
            online=self.wavelog_online,
            sync_busy=self.sync_busy,
            candidate_count=len(self.db.list_new_upload_candidates()),
        ):
            self._start_new_qso_push()

    def _local_sync_change(self):
        if self.wavelog_online:
            self._request_auto_sync(delay_ms=1200)

    def _start_new_qso_push(self):
        if self.sync_busy or self.closing or self.close_requested or self.sync_progress_dialog is not None:
            return
        if any(profile_id == self.active_profile_id for profile_id, _local_id in self.external_enrichment_pending):
            return
        settings = self._wavelog_online_settings()
        if not settings.should_auto_sync(
            online=self.wavelog_online,
            sync_busy=False,
            candidate_count=len(self.db.list_new_upload_candidates()),
        ):
            return
        self.sync_busy = True
        self.sync_is_automatic = True
        self.sync_operation = "push"
        self.status_var.set("Neue LOCAL ONLY QSOs werden zu Wavelog hochgeladen …")

        def worker():
            try:
                client = WavelogClient(settings.base_url, settings.token)
                summary = SyncEngine(self.store, self.db, client).push_new_only(settings.station_id)
                ContestSyncEngine(self.store, self.db, client).link_pending()
                if not self.closing:
                    self.after(0, lambda: self._new_qso_push_finished(summary))
            except Exception as exc:
                if not self.closing:
                    message = str(exc)
                    self.after(0, lambda: self._new_qso_push_failed(message))

        threading.Thread(target=worker, name="wavelog-new-qso-push", daemon=True).start()

    def _new_qso_push_finished(self, summary):
        self.sync_busy = False
        self.sync_is_automatic = False
        self.sync_operation = ""
        if summary.errors:
            self.status_var.set(
                f"Online-Push: {summary.pushed} übertragen · {summary.errors} Fehler · Voll-Sync erforderlich"
            )
        elif summary.pushed:
            self.db.set_setting("last_online_push_at", datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S"))
            self.status_var.set(f"Online-Push: {summary.pushed} neue QSO(s) zu Wavelog übertragen")
        self.refresh_qsos()
        if self.close_requested:
            self._begin_close_sequence()
        else:
            # A QSO may have been logged while this small batch was running.
            self._request_auto_sync(delay_ms=350)

    def _new_qso_push_failed(self, message: str):
        self.sync_busy = False
        self.sync_is_automatic = False
        self.sync_operation = ""
        self.status_var.set("Online-Push fehlgeschlagen · QSOs bleiben lokal")
        write_startup_log("Online-Push fehlgeschlagen: " + message)
        self.refresh_qsos()
        self._schedule_wavelog_check(1500)
        if self.close_requested:
            self._begin_close_sequence()

    def _open_da6it_website(self, _event=None):
        self._open_external_url("https://da6it.de/", "DA6IT.de")

    def _open_external_url(self, url: str, label: str):
        try:
            webbrowser.open_new_tab(url)
        except Exception as exc:
            self.status_var.set(f"{label} konnte nicht geöffnet werden")
            write_startup_log(f"{label} konnte nicht geöffnet werden: " + repr(exc))

    # ---------- UI shell ----------
    def _setup_style(self, scale: float = 1.0):
        def size(value: int, minimum: int = 6) -> int:
            return max(minimum, int(round(value * scale)))

        def padding(horizontal: int, vertical: int) -> tuple[int, int]:
            return (size(horizontal, 4), size(vertical, 3))

        style = ttk.Style(self)
        if not getattr(self, "_style_initialized", False):
            try:
                style.theme_use("clam")
            except Exception:
                pass
            self._style_initialized = True
        # Tk's option database also controls the classic widgets and the
        # otherwise native-looking Combobox drop-down list.  Without these
        # defaults Windows can render a white list or selection with light
        # text while the rest of the application is dark.
        for pattern, value in (
            ("*Listbox.background", INPUT_BG), ("*Listbox.foreground", TEXT),
            ("*Listbox.selectBackground", ACTIVE_BG), ("*Listbox.selectForeground", TEXT),
            ("*Listbox.highlightBackground", BORDER), ("*Listbox.highlightColor", ACCENT),
            ("*Text.background", INPUT_BG), ("*Text.foreground", TEXT),
            ("*Text.insertBackground", TEXT), ("*Text.selectBackground", ACTIVE_BG),
            ("*Text.selectForeground", TEXT),
            ("*TCombobox*Listbox.background", INPUT_BG),
            ("*TCombobox*Listbox.foreground", TEXT),
            ("*TCombobox*Listbox.selectBackground", ACTIVE_BG),
            ("*TCombobox*Listbox.selectForeground", TEXT),
        ):
            self.option_add(pattern, value)
        style.configure("TFrame", background=BG)
        style.configure("Card.TFrame", background=CARD, relief="flat")
        style.configure("TLabel", background=BG, foreground=TEXT, font=("Segoe UI", size(10)))
        style.configure("Card.TLabel", background=CARD, foreground=TEXT, font=("Segoe UI", size(10)))
        style.configure("Muted.Card.TLabel", background=CARD, foreground=MUTED, font=("Segoe UI", size(9)))
        style.configure("Title.TLabel", background=BG, foreground=TEXT, font=("Segoe UI Semibold", size(20)))
        style.configure("CardTitle.TLabel", background=CARD, foreground=TEXT, font=("Segoe UI Semibold", size(12)))
        style.configure(
            "Call.TEntry", font=("Segoe UI Semibold", size(18)), padding=size(8, 4),
            fieldbackground=INPUT_BG, foreground=TEXT, insertcolor=TEXT,
            bordercolor=BORDER, lightcolor=BORDER, darkcolor=BORDER,
        )
        style.configure(
            "Worked.Call.TEntry", font=("Segoe UI Semibold", size(18)), padding=size(8, 4),
            fieldbackground=OK_BADGE_BG, foreground=OK,
        )
        style.map(
            "Worked.Call.TEntry",
            fieldbackground=[("readonly", OK_BADGE_BG), ("disabled", OK_BADGE_BG), ("focus", OK_BADGE_BG)],
            foreground=[("readonly", OK), ("disabled", OK), ("focus", OK)],
        )
        style.configure(
            "TEntry", padding=size(6, 3), fieldbackground=INPUT_BG, foreground=TEXT,
            insertcolor=TEXT, bordercolor=BORDER, lightcolor=BORDER, darkcolor=BORDER,
        )
        style.map(
            "TEntry",
            fieldbackground=[("disabled", SURFACE), ("readonly", INPUT_BG), ("focus", INPUT_BG)],
            foreground=[("disabled", MUTED), ("readonly", TEXT)],
            bordercolor=[("focus", ACCENT), ("!focus", BORDER)],
        )
        style.configure(
            "TCombobox", padding=size(5, 3), fieldbackground=INPUT_BG,
            background=INPUT_BG, foreground=TEXT, arrowcolor=TEXT,
            bordercolor=BORDER, lightcolor=BORDER, darkcolor=BORDER,
            selectbackground=INPUT_BG, selectforeground=TEXT,
        )
        style.map(
            "TCombobox",
            fieldbackground=[("disabled", SURFACE), ("readonly", INPUT_BG), ("focus", INPUT_BG)],
            background=[("disabled", SURFACE), ("active", ACTIVE_BG), ("readonly", INPUT_BG)],
            foreground=[("disabled", MUTED), ("readonly", TEXT)],
            arrowcolor=[("disabled", MUTED), ("readonly", TEXT)],
            selectbackground=[("readonly", INPUT_BG)],
            selectforeground=[("readonly", TEXT)],
            bordercolor=[("focus", ACCENT), ("!focus", BORDER)],
        )
        style.configure("Primary.TButton", background=ACCENT, foreground="white", padding=padding(14, 8), borderwidth=0, font=("Segoe UI Semibold", size(10)))
        style.map(
            "Primary.TButton",
            background=[("active", ACCENT_DARK), ("disabled", DISABLED)],
            foreground=[("disabled", MUTED), ("!disabled", "white")],
        )
        style.configure("Secondary.TButton", padding=padding(12, 7), font=("Segoe UI", size(10)), background=CARD, foreground=TEXT)
        style.map(
            "Secondary.TButton",
            background=[("disabled", SURFACE), ("active", NAV_HOVER)],
            foreground=[("disabled", MUTED), ("!disabled", TEXT)],
        )
        style.configure("Tuning.TButton", padding=padding(12, 7), font=("Segoe UI Semibold", size(10)), background=ERR, foreground="white")
        style.map("Tuning.TButton", background=[("disabled", ERR), ("active", ERR)], foreground=[("disabled", "white")])
        style.configure("Nav.TButton", background=SIDEBAR, foreground=SIDEBAR_TEXT, padding=padding(12, 9), anchor="w", borderwidth=0, font=("Segoe UI", size(9)))
        style.map("Nav.TButton", background=[("active", NAV_HOVER)], foreground=[("active", ACCENT)])
        style.configure("NavActive.TButton", background=ACTIVE_BG, foreground=ACCENT, padding=padding(12, 9), anchor="w", borderwidth=0, font=("Segoe UI Semibold", size(9)))
        style.map("NavActive.TButton", background=[("active", NAV_ACTIVE_HOVER)], foreground=[("active", ACCENT_DARK)])
        style.configure("Treeview", rowheight=size(30, 20), font=("Segoe UI", size(9)), background=INPUT_BG, fieldbackground=INPUT_BG, foreground=TEXT, bordercolor=BORDER)
        style.map("Treeview", background=[("selected", ACTIVE_BG)], foreground=[("selected", TEXT)])
        style.configure("Treeview.Heading", font=("Segoe UI Semibold", size(9)), padding=size(5, 3), background=CARD, foreground=TEXT)
        style.map("Treeview.Heading", background=[("active", NAV_HOVER)], foreground=[("active", TEXT)])
        style.configure("Stats.Horizontal.TProgressbar", troughcolor=PROGRESS_BG, background=ACCENT, borderwidth=0, thickness=size(10, 6))
        style.configure("TLabelframe", background=CARD, bordercolor=BORDER, relief="solid")
        style.configure("TLabelframe.Label", background=CARD, foreground=TEXT, font=("Segoe UI Semibold", size(10)))
        style.configure("TRadiobutton", background=CARD, foreground=TEXT)
        style.map("TRadiobutton", background=[("active", CARD), ("disabled", CARD)], foreground=[("disabled", MUTED)])
        style.configure("TCheckbutton", background=CARD, foreground=TEXT)
        style.map("TCheckbutton", background=[("active", CARD), ("disabled", CARD)], foreground=[("disabled", MUTED)])
        style.configure("TNotebook", background=BG, borderwidth=0)
        style.configure("TNotebook.Tab", padding=padding(16, 9), font=("Segoe UI", size(10)), background=SURFACE, foreground=TEXT)
        style.map("TNotebook.Tab", foreground=[("selected", ACCENT), ("!selected", TEXT)], background=[("selected", CARD), ("active", NAV_HOVER), ("!selected", SURFACE)])
        style.configure("Settings.TNotebook", background=BG, borderwidth=0)
        style.configure("Settings.TNotebook.Tab", padding=padding(10, 6), font=("Segoe UI", size(9)), background=SURFACE, foreground=TEXT)
        style.map(
            "Settings.TNotebook.Tab",
            foreground=[("selected", ACCENT), ("!selected", TEXT)],
            background=[("selected", ACTIVE_BG), ("active", NAV_HOVER), ("!selected", SURFACE)],
        )

    def _load_brand_logo(self):
        if Image is None or ImageTk is None:
            return None
        try:
            resource_root = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
            path = resource_root / "assets" / "da6it-logo.webp"
            self._brand_logo_source = Image.open(path).convert("RGB")
            image = self._brand_logo_source.copy()
            image.thumbnail((170, 70), Image.Resampling.LANCZOS)
            return ImageTk.PhotoImage(image)
        except Exception as exc:
            write_startup_log("Logo konnte nicht geladen werden: " + repr(exc))
            return None

    def _load_window_icon(self):
        """Use the square DA6IT brand mark for the window and taskbar."""
        try:
            resource_root = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
            self.app_icon_photo = tk.PhotoImage(file=str(resource_root / "assets" / "da6it-icon.png"))
            self.iconphoto(True, self.app_icon_photo)
        except Exception as exc:
            write_startup_log("App-Icon konnte nicht geladen werden: " + repr(exc))

    def _build_shell(self):
        self._load_window_icon()
        self.columnconfigure(1, weight=1)
        self.rowconfigure(0, weight=1)

        self.sidebar = tk.Frame(self, bg=SIDEBAR, width=205, highlightbackground=BORDER, highlightthickness=1)
        side = self.sidebar
        side.grid(row=0, column=0, sticky="nsew")
        side.grid_propagate(False)
        self.brand_logo_photo = self._load_brand_logo()
        if self.brand_logo_photo is not None:
            brand = tk.Label(side, image=self.brand_logo_photo, bg="#ffffff", cursor="hand2", padx=2, pady=2)
        else:
            brand = tk.Label(
                side, text="DA6IT.de", bg=SIDEBAR, fg=ACCENT,
                font=("Segoe UI Semibold", 19), cursor="hand2",
            )
        self.brand_label = brand
        brand.pack(anchor="w", padx=16, pady=(16, 0))
        brand.bind("<Button-1>", self._open_da6it_website)
        tk.Label(side, text="Wavelog Offline Logger", bg=SIDEBAR, fg=MUTED, font=("Segoe UI", 9)).pack(anchor="w", padx=16, pady=(0, 17))
        self.nav_buttons: dict[str, ttk.Button] = {}
        nav_items = (
            ("log", "▣   Logbuch"),
            ("fast_log", "ϟ   Fast Log / DXpedition"),
            ("contest", "#   Contest Logging"),
            ("xota", "⌖   xOTA"),
            ("qsos", "☁   Logbuch & Sync"),
            ("stats", "▤   Statistiken"),
            ("dx_cluster", "◎   DX Cluster"),
            ("cat", "⌁   CAT Setup"),
            ("udp_log", "◉   UDP Logging"),
            ("settings", "⚙   Einstellungen"),
        )
        for page_name, label in nav_items:
            if "   " in label:
                icon, label_text = label.split("   ", 1)
                label = icon + "   " + self._tr(label_text)
            button = ttk.Button(side, text=label, style="Nav.TButton", command=lambda target=page_name: self._show_page(target))
            button.pack(fill="x", padx=8, pady=1)
            self.nav_buttons[page_name] = button

        local_card = tk.Frame(side, bg=SURFACE, highlightbackground=BORDER, highlightthickness=1)
        local_card.pack(side="bottom", fill="x", padx=14, pady=(8, 14))
        self.sidebar_mode_label = tk.Label(local_card, text="●  LOCAL ONLY", bg=SURFACE, fg=ACCENT, font=("Segoe UI Semibold", 9))
        self.sidebar_mode_label.pack(anchor="w", padx=12, pady=(10, 3))
        self.sidebar_mode_hint = tk.Label(local_card, text="Wavelog-Status wird geprüft.", bg=SURFACE, fg=MUTED, font=("Segoe UI", 8), justify="left")
        self.sidebar_mode_hint.pack(anchor="w", padx=12, pady=(0, 10))
        tk.Label(side, text=f"Version {VERSION}", bg=SIDEBAR, fg=MUTED, font=("Segoe UI", 8)).pack(side="bottom", anchor="w", padx=20, pady=(8, 0))

        self.main = ttk.Frame(self, padding=(22, 16))
        self.main.grid(row=0, column=1, sticky="nsew")
        self.main.columnconfigure(0, weight=1)
        self.main.rowconfigure(1, weight=1)

        header = ttk.Frame(self.main)
        header.grid(row=0, column=0, sticky="ew", pady=(0, 14))
        header.columnconfigure(0, weight=1)
        title_block = ttk.Frame(header)
        title_block.grid(row=0, column=0, sticky="w")
        self.page_title = ttk.Label(title_block, text="QSO loggen", style="Title.TLabel")
        self.page_title.pack(anchor="w")
        self.page_subtitle = ttk.Label(title_block, text="Schnell, lokal und unabhängig von einer Internetverbindung.", foreground=MUTED)
        self.page_subtitle.pack(anchor="w", pady=(2, 0))

        profile_card = tk.Frame(header, bg=CARD, highlightbackground=BORDER, highlightthickness=1)
        profile_card.grid(row=0, column=1, sticky="e", padx=(10, 10))
        tk.Label(profile_card, text="PROFIL", bg=CARD, fg=MUTED, font=("Segoe UI Semibold", 8)).pack(side="left", padx=(10, 6))
        self.active_profile_var = tk.StringVar()
        self.profile_combo = ttk.Combobox(profile_card, textvariable=self.active_profile_var, state="readonly", width=22)
        self.profile_combo.pack(side="left", pady=5)
        self.profile_combo.bind("<<ComboboxSelected>>", self._profile_combo_changed)
        ttk.Button(profile_card, text="Verwalten", style="Secondary.TButton", command=self.manage_profiles).pack(side="left", padx=(6, 6), pady=4)
        self._refresh_profile_selector()

        self.clock_card = tk.Frame(header, bg=CARD, width=178, height=52, highlightbackground=BORDER, highlightthickness=1)
        self.clock_card.grid(row=0, column=2, sticky="e")
        self.clock_card.pack_propagate(False)
        self.clock_label = tk.Label(self.clock_card, text="--:--:--", width=8, anchor="center", bg=CARD, fg=TEXT, font=("Consolas", 18, "bold"), padx=8, pady=5)
        self.clock_label.pack(side="left")
        self.clock_zone_label = tk.Label(self.clock_card, text="UTC", width=5, anchor="center", bg=CARD, fg=MUTED, font=("Segoe UI Semibold", 9), padx=0, pady=5)
        self.clock_zone_label.pack(side="left", padx=(0, 12))

        self.page_container = ttk.Frame(self.main)
        self.page_container.grid(row=1, column=0, sticky="nsew")
        self.page_container.columnconfigure(0, weight=1)
        self.page_container.rowconfigure(0, weight=1)
        self.pages: dict[str, ttk.Frame] = {}

        footer = tk.Frame(self.main, bg=BG, highlightbackground=BORDER, highlightthickness=0)
        footer.grid(row=2, column=0, sticky="ew", pady=(10, 0))
        self.footer_mode_label = tk.Label(footer, text="●  LOCAL ONLY", bg=BG, fg=ACCENT, font=("Segoe UI Semibold", 9), anchor="w")
        self.footer_mode_label.pack(side="left")
        self.status_var = tk.StringVar(value="Bereit")
        tk.Label(footer, textvariable=self.status_var, bg=BG, fg=MUTED, font=("Segoe UI", 9), anchor="w").pack(side="left", padx=(14, 0))
        self.footer_qso_var = tk.StringVar(value="0 QSOs")
        self.footer_db_var = tk.StringVar(value="")
        support = tk.Frame(footer, bg=BG)
        support.pack(side="right", padx=(18, 0))
        for text, url in (
            ("☕ Buy Me a Coffee", "https://buymeacoffee.com/da6it?new=1"),
            ("PayPal", "https://paypal.me/DA6IT"),
        ):
            link = tk.Label(
                support, text=self._tr(text), bg=BG, fg=MUTED,
                font=("Segoe UI", 8), cursor="hand2", padx=4,
            )
            link.pack(side="left")
            link.bind("<Button-1>", lambda _event, target=url, name=text: self._open_external_url(target, name))
            link.bind("<Enter>", lambda _event, widget=link: widget.configure(fg=ACCENT))
            link.bind("<Leave>", lambda _event, widget=link: widget.configure(fg=MUTED))
        tk.Label(footer, textvariable=self.footer_qso_var, bg=BG, fg=MUTED, font=("Segoe UI", 9)).pack(side="right", padx=(18, 0))
        tk.Label(footer, textvariable=self.footer_db_var, bg=BG, fg=MUTED, font=("Segoe UI", 9)).pack(side="right")

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
        self.store = LogStore(Path(raw_log_dir), profile_id)
        if self.store.migration_report:
            self.pending_adif_migration_report = self.store.migration_report
        self.xota_repository = XotaRepository(self.db)
        self.xota_references = ActivationReferenceService(self.xota_repository, self.db.get_setting)
        self.xota_geocoder = ReverseGeocodeService(
            self.xota_repository,
            self.db.get_setting("xota_reverse_geocode_url", ""),
        )
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
            self.wavelog_check_generation += 1
            for job_name in ("wavelog_check_job", "auto_sync_job"):
                job = getattr(self, job_name, None)
                if job is not None:
                    try:
                        self.after_cancel(job)
                    except Exception:
                        pass
                    setattr(self, job_name, None)
            self.wavelog_check_busy = False
            self._stop_cat_runtime(update_ui=False)
            self._stop_dx_cluster_runtime(update_ui=False)
            self._stop_dx_spotter_runtime(update_ui=False)
            self._stop_udp_log_runtime(update_ui=False)
            if self.db:
                self.db.close()
            self._open_profile_storage(profile_id)
            self.station_rows = []
            self.station_by_label.clear()
            if hasattr(self, "station_combo"):
                self.station_combo.configure(values=[])
            self._load_settings_to_ui()
            self.clear_qso_form()
            self.fast_log_session_started = datetime.now(timezone.utc)
            self.fast_log_session_ids.clear()
            self.refresh_fast_log_page()
            if hasattr(self, "contest_power_var"):
                self.contest_power_var.set(self.db.get_setting("default_power", ""))
            self.refresh_contest_page()
            self.refresh_xota_page()
            self.refresh_qsos()
            self._load_last_spottable_qso()
            self.refresh_stats()
            self._refresh_profile_selector()
            self._reset_wavelog_monitor(delay_ms=500)
            self.status_var.set(f"Profil gewechselt: {old} → {self._current_profile()['name']}")
            # The previous profile's listener was stopped before its database
            # was closed. Start the newly selected profile with its own saved
            # host, port and autostart preference once the UI is idle again.
            self.after_idle(self._autostart_udp_log)
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
        titles = {"log": "QSO loggen", "fast_log": "Fast Log / DXpedition", "contest": "Contest Logging", "xota": "xOTA", "qsos": "Logbuch & Sync", "stats": "Statistiken", "cat": "CAT Setup", "dx_cluster": "DX Cluster", "udp_log": "UDP Logging", "settings": "Einstellungen"}
        subtitles = {
            "log": "Neues QSO erfassen und sicher lokal speichern.",
            "fast_log": "Pileups zügig abarbeiten: Rufzeichen und Enter.",
            "contest": "Seriennummern und Austauschdaten effizient protokollieren.",
            "xota": "Portable Aktivierungen offline vorbereiten, kombinieren und sicher protokollieren.",
            "qsos": "Lokale QSOs prüfen und Wavelog bewusst manuell synchronisieren.",
            "stats": "Das lokale Logbuch auf einen Blick.",
            "cat": "Funkgerät über das eingebettete Hamlib steuern.",
            "dx_cluster": "Live-Spots empfangen, filtern und an den TRX übergeben.",
            "udp_log": "QSOs von WSJT-X und kompatiblen Programmen empfangen.",
            "settings": "Stationsprofil, Online-Dienste und lokale Daten verwalten.",
        }
        self.page_title.configure(text=self._tr(titles[name]))
        self.page_subtitle.configure(text=self._tr(subtitles.get(name, "")))
        for page_name, button in self.nav_buttons.items():
            button.configure(style="NavActive.TButton" if page_name == name else "Nav.TButton")
        self.pages[name].tkraise()
        if name == "fast_log":
            self.refresh_fast_log_page()
            self.fast_log_call_entry.focus_set()
        elif name == "contest":
            self.refresh_contest_page()
        elif name == "xota":
            self.refresh_xota_page()
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
        self._responsive_card_frames.append(inner)
        return inner

    # ---------- log page ----------
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
            call_header, text="", bg=CARD, fg=ACCENT,
            font=("Segoe UI Semibold", 9), anchor="e", padx=8, pady=3,
        )
        self.wsjtx_live_badge.grid(row=0, column=1, sticky="e")
        self.qso_worked_badge = tk.Label(
            call_header, text="", bg=CARD, fg=MUTED, font=("Segoe UI Semibold", 9),
            anchor="e", padx=8, pady=3,
        )
        self.qso_worked_badge.grid(row=0, column=2, sticky="e")
        self.call_var = tk.StringVar()
        self.call_entry = ttk.Entry(left, textvariable=self.call_var, style="Call.TEntry")
        self.call_entry.grid(row=1, column=0, columnspan=4, sticky="ew", pady=(0, 14))
        self.call_entry.bind("<KeyRelease>", self._call_changed)
        self.call_entry.bind("<Return>", lambda e: self.save_qso())

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
                                  highlightthickness=0, bg=INPUT_BG, fg=TEXT, insertbackground=TEXT)
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
            left, bg=SURFACE, highlightbackground=BORDER, highlightthickness=1,
        )
        self.qso_history_frame.grid(row=13, column=0, columnspan=4, sticky="ew", pady=(14, 0))
        self.qso_history_frame.columnconfigure(0, weight=1)
        self.qso_history_title = tk.Label(
            self.qso_history_frame, text="", bg=SURFACE, fg=TEXT,
            font=("Segoe UI Semibold", 9), anchor="w", padx=10, pady=6,
        )
        self.qso_history_title.grid(row=0, column=0, sticky="ew")
        self.qso_history_details = tk.Label(
            self.qso_history_frame, text="", bg=SURFACE, fg=MUTED,
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
        self.callbook_source_label = tk.Label(callbook_head, text="OFFLINE", bg=NEUTRAL_BADGE_BG, fg=MUTED, font=("Segoe UI Semibold", 8), padx=8, pady=3)
        self.callbook_source_label.grid(row=0, column=1, sticky="e")

        self.callbook_image_frame = tk.Frame(right, bg=PHOTO_BG, height=160, relief="flat")
        self.callbook_image_frame.grid(row=5, column=0, sticky="ew", pady=(8, 7))
        self.callbook_image_frame.grid_propagate(False)
        self.callbook_image_frame.columnconfigure(0, weight=1)
        self.callbook_image_frame.rowconfigure(0, weight=1)
        self.callbook_image_label = tk.Label(
            self.callbook_image_frame, text="Kein Foto geladen", bg=PHOTO_BG, fg=MUTED,
            font=("Segoe UI", 9), relief="flat",
        )
        self.callbook_image_label.grid(row=0, column=0, sticky="nsew")
        self.callbook_name_label = tk.Label(right, text="Rufzeichen eingeben …", bg=CARD, fg=TEXT, font=("Segoe UI Semibold", 13), anchor="w")
        self.callbook_name_label.grid(row=6, column=0, sticky="ew")
        self.callbook_details_label = tk.Label(right, text="", bg=CARD, fg=TEXT, font=("Segoe UI", 9), justify="left", anchor="nw", wraplength=350)
        self.callbook_details_label.grid(row=7, column=0, sticky="ew", pady=(3, 0))
        self.callbook_distance_label = tk.Label(
            right, text="", bg=CARD, fg=ACCENT, font=("Segoe UI Semibold", 9),
            justify="left", anchor="w", wraplength=350,
        )
        self.callbook_distance_label.grid(row=8, column=0, sticky="ew", pady=(3, 0))
        self.callbook_status_label = tk.Label(
            right, text="Online-Abfrage optional · Offline-Logging bleibt immer verfügbar.",
            bg=CARD, fg=MUTED, font=("Segoe UI", 8), justify="left", anchor="w", wraplength=350,
        )
        self.callbook_status_label.grid(row=9, column=0, sticky="ew", pady=(5, 0))
        ttk.Button(right, text="Callbook neu laden", style="Secondary.TButton", command=self._manual_callbook_lookup).grid(row=10, column=0, sticky="w", pady=(7, 0))

        ttk.Separator(right).grid(row=11, column=0, sticky="ew", pady=12)
        ttk.Label(right, text="DXCC · offline", style="CardTitle.TLabel").grid(row=12, column=0, sticky="w")
        self.country_summary = tk.Label(right, bg=CARD, fg=TEXT, font=("Segoe UI", 9), justify="left", anchor="nw", wraplength=350)
        self.country_summary.grid(row=13, column=0, sticky="ew", pady=(5, 0))
        self.country_source = tk.Label(right, text="CTY.DAT · keine Internetverbindung nötig", bg=CARD, fg=MUTED, font=("Segoe UI", 8), justify="left", anchor="w")
        self.country_source.grid(row=14, column=0, sticky="ew", pady=(3, 0))

        # Kept for existing profile and log-file update helpers; the compact
        # footer/header now present these details instead of a second side card.
        self.profile_summary = tk.Label(right, bg=CARD)
        self.logfile_preview = tk.Label(right, bg=CARD)
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
            self.qso_worked_badge.configure(text="", bg=CARD, fg=MUTED)
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
            self.qso_worked_badge.configure(text=text, bg=OK_BADGE_BG, fg=OK)
        elif total_count:
            detail = f"{band} {mode}".strip() or "dieser Auswahl"
            text = (
                f"Worked {total_count}× · not on {detail}"
                if self.language == "en"
                else f"Schon {total_count}× gearbeitet · nicht auf {detail}"
            )
            self.call_entry.configure(style="Call.TEntry")
            self.qso_worked_badge.configure(text=text, bg=WARN_BADGE_BG, fg=WARN)
        else:
            self.call_entry.configure(style="Call.TEntry")
            self.qso_worked_badge.configure(text="", bg=CARD, fg=MUTED)
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
                self.callbook_source_label.configure(text="OFFLINE", bg=NEUTRAL_BADGE_BG, fg=MUTED)
                self.callbook_status_label.configure(text="Online-Abfrage optional · Offline-Logging bleibt immer verfügbar.", fg=MUTED)
            return
        if not force and self.db.get_setting("callbook_auto_lookup", "1") != "1":
            self.callbook_name_label.configure(text=callsign)
            self.callbook_details_label.configure(text="Automatische Abfrage ist deaktiviert.")
            return
        if self._configured_callbook_source() == CALLBOOK_SOURCE_DISABLED:
            self.callbook_name_label.configure(text=callsign)
            self.callbook_details_label.configure(text="Callbook-Abfrage ist deaktiviert.")
            return
        self.callbook_status_label.configure(text="Callbook wird abgefragt …", fg=MUTED)
        delay = 0 if force else 700
        self.callbook_lookup_job = self.after(delay, lambda: self._start_callbook_lookup(callsign, generation, force))

    def _manual_callbook_lookup(self):
        self._schedule_callbook_lookup(self.call_var.get().strip().upper(), force=True)

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
            if not any((result.name, result.qth, result.grid, result.country, result.image_url)):
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
        self.callbook_source_label.configure(text=source_text.upper(), bg=OK_BADGE_BG, fg=OK)
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
        self.callbook_status_label.configure(text="Daten automatisch übernommen" + suffix, fg=OK)
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
        self.callbook_source_label.configure(text="OFFLINE", bg=NEUTRAL_BADGE_BG, fg=MUTED)
        self.callbook_name_label.configure(text=callsign)
        self.callbook_details_label.configure(text="Keine Online-Daten verfügbar.")
        detail = (message or "Callbook ist nicht erreichbar").strip()[:240]
        self.callbook_status_label.configure(
            text=f"{detail} · Offline-Logging läuft ohne Unterbrechung weiter.", fg=MUTED,
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
                    (
                        max(220, int(round(330 * self._ui_scale))),
                        max(100, int(round(150 * self._ui_scale))),
                    ),
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

    # ---------- Fast Log / DXpedition ----------
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
            setup, text="", bg=CARD, fg=TEXT, font=("Segoe UI Semibold", 11), anchor="e",
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
            body, text="", bg=CARD, fg=MUTED, font=("Segoe UI", 9), anchor="e",
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
            entry_box, text="", bg=CARD, fg=WARN, font=("Segoe UI Semibold", 10), anchor="w",
        )
        self.fast_log_duplicate_label.grid(row=2, column=0, sticky="ew", pady=(16, 0))
        self.fast_log_stats_label = tk.Label(
            entry_box, text="", bg=CARD, fg=TEXT, font=("Segoe UI Semibold", 12),
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
            fg=(WARN if duplicate else OK),
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
        by_id = {q.get("local_id"): q for q in self.store.scan()}
        worked_keys: set[tuple[str, str, str]] = set()
        for qso in by_id.values():
            qso_call = str(qso.get("call") or "").strip().upper()
            qso_band = str(qso.get("band") or "").strip()
            qso_mode = normalize_worked_mode(
                str(qso.get("mode") or ""), band=qso_band,
            )
            if qso_call and qso_band and qso_mode:
                worked_keys.add((qso_call, qso_band, qso_mode))
        self.fast_log_worked_keys = worked_keys
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
        elapsed = max(60.0, (datetime.now(timezone.utc) - self.fast_log_session_started).total_seconds())
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
            self.fast_log_call_var.set("")
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
        qso = self.store.find(local_id)
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
            self.refresh_fast_log_page()
            self.status_var.set(f"Fast Log: {qso.get('call', 'QSO')} lokal zurückgenommen")
        self.fast_log_call_entry.focus_set()

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
        self.contest_session_status.configure(text=("● Session läuft" if running else "Keine Session"), fg=(OK if running else MUTED))
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

    # ---------- xOTA ----------
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

    # ---------- QSO list / sync ----------
    def _build_qsos_page(self):
        p = self._new_page("qsos")
        p.columnconfigure(0, weight=1)
        p.rowconfigure(1, weight=1)
        top = self._card(p, row=0, column=0, sticky="ew", pady=(0, 10))
        ttk.Button(top, text="Synchronisieren", style="Primary.TButton", command=self.sync_now).pack(side="left")
        ttk.Button(top, text="ADI-Ordner öffnen", style="Secondary.TButton", command=self.open_log_dir).pack(side="left", padx=8)
        ttk.Button(top, text="ADIF importieren", style="Secondary.TButton", command=self.import_adif).pack(side="left")
        ttk.Button(top, text="ADIF exportieren", style="Secondary.TButton", command=self.export_adif).pack(side="left", padx=8)
        self.sync_label = tk.Label(top, text="", bg=CARD, fg=MUTED, font=("Segoe UI", 9))
        self.sync_label.pack(side="right")

        card = self._card(p, row=1, column=0, sticky="nsew")
        card.columnconfigure(0, weight=1)
        card.rowconfigure(0, weight=1)
        cols = ("date", "time", "call", "operator", "contest", "band", "mode", "freq", "rst", "status", "qrz", "lotw", "eqsl", "clublog", "dcl")
        self.tree = ttk.Treeview(card, columns=cols, show="headings", selectmode="browse")
        headings = {"date":"Datum UTC", "time":"Zeit", "call":"Call", "operator":"Operator", "contest":"Contest", "band":"Band", "mode":"Mode", "freq":"MHz", "rst":"RST", "status":"Sync",
                    "qrz":"QRZ", "lotw":"LoTW", "eqsl":"eQSL", "clublog":"ClubLog", "dcl":"DCL"}
        widths = {"date":88,"time":62,"call":88,"operator":82,"contest":100,"band":52,"mode":60,"freq":80,"rst":62,"status":88,
                  "qrz":52,"lotw":52,"eqsl":52,"clublog":62,"dcl":52}
        for c in cols:
            self.tree.heading(c, text=self._tr(headings[c]))
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
        self.tree.bind("<<TreeviewSelect>>", self._sync_selection_changed)

        actions = ttk.Frame(card, style="Card.TFrame")
        actions.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(10, 0))
        ttk.Button(actions, text="QSO bearbeiten", style="Secondary.TButton", command=self.edit_selected_qso).pack(side="left")
        ttk.Button(actions, text="QSO löschen", style="Secondary.TButton", command=self.delete_selected_qso).pack(side="left", padx=8)
        self.take_wavelog_button = ttk.Button(actions, text="Wavelog-Version übernehmen", style="Secondary.TButton", command=lambda: self.resolve_conflict(False))
        self.take_wavelog_button.pack(side="right")
        self.force_local_button = ttk.Button(actions, text="Lokale Version erzwingen", style="Secondary.TButton", command=lambda: self.resolve_conflict(True))
        self.force_local_button.pack(side="right", padx=8)

        self.sync_detail_label = tk.Label(
            card, text="Keine offenen Sync-Details.", bg=CARD, fg=MUTED,
            font=("Segoe UI", 9), anchor="w", justify="left", wraplength=1050,
        )
        self.sync_detail_label.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(9, 0))

        legend = tk.Label(card, text="QSL-Status: ✓ bestätigt · ↑ gesendet/hochgeladen · … wartet · — kein Status · ? nicht verfügbar",
                          bg=CARD, fg=MUTED, font=("Segoe UI", 8), anchor="w")
        legend.grid(row=3, column=0, columnspan=2, sticky="ew", pady=(6, 0))
        self._sync_selection_changed()

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
        self._update_dx_cluster_worked_cache(qsos)
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
                self._display_qsl_status(qsl.get("eqsl")), self._display_qsl_status(qsl.get("clublog")),
                self._display_qsl_status(qsl.get("dcl")),
            ))
        metas = self.db.list_meta()
        local_only = sum(1 for m in metas if m.get("wavelog_id") is None and m.get("status") not in ("pending_delete",))
        wavelog = sum(1 for m in metas if m.get("wavelog_id") is not None and m.get("status") == "synced")
        issues = sum(1 for m in metas if m.get("status") in ("modified", "conflict", "error", "pending_delete"))
        last = self.db.get_setting("last_sync_at", "")
        suffix = f" · letzter Sync {last}" if last else " · noch nicht synchronisiert"
        issue_text = f" · {issues} offen" if issues else ""
        self.sync_label.configure(text=f"{len(qsos)} QSOs · {wavelog} WAVELOG · {local_only} LOCAL ONLY{issue_text}{suffix}")
        if hasattr(self, "footer_qso_var"):
            self.footer_qso_var.set(f"{len(qsos)} QSOs")
            profile_name = self._current_profile().get("name", "Profil")
            self.footer_db_var.set(f"{profile_name} · {Path(self.db.path).name}")
        self._sync_selection_changed()

    def selected_id(self) -> str | None:
        s = self.tree.selection() if hasattr(self, "tree") else []
        return s[0] if s else None

    def import_adif(self):
        source = filedialog.askopenfilename(
            title="ADIF importieren", filetypes=(("ADIF-Dateien", "*.adi *.adif"), ("Alle Dateien", "*.*")), parent=self,
        )
        if not source:
            return
        if not messagebox.askyesno(
            "ADIF importieren",
            "Die Datei wird geprüft und mit dem lokalen Profil-Logbuch zusammengeführt. "
            "Dubletten werden übersprungen und vorher wird automatisch ein ZIP-Backup erzeugt.\n\nFortfahren?",
            parent=self,
        ):
            return
        try:
            report = self.store.import_adif(Path(source))
            self.db.reconcile_index(self.store.scan()); self.refresh_qsos(); self.refresh_stats()
            invalid = f"\nUngültig: {len(report['invalid'])}" if report["invalid"] else ""
            messagebox.showinfo(
                "ADIF-Import abgeschlossen",
                f"Importiert: {report['imported']}\nDubletten übersprungen: {report['skipped']}{invalid}\n\nBackup: {report['backup']}",
                parent=self,
            )
        except Exception as exc:
            messagebox.showerror("ADIF-Import fehlgeschlagen", str(exc), parent=self)

    def export_adif(self):
        initial = f"wavelog-offline-{self._current_profile().get('name','profil')}.adi"
        target = filedialog.asksaveasfilename(
            title="ADIF exportieren", defaultextension=".adi", initialfile=initial,
            filetypes=(("ADIF-Datei", "*.adi"), ("Alle Dateien", "*.*")), parent=self,
        )
        if not target:
            return
        try:
            report = self.store.export_adif(Path(target))
            messagebox.showinfo("ADIF-Export abgeschlossen", f"{report['exported']} QSO(s) exportiert nach:\n{report['target']}", parent=self)
        except Exception as exc:
            messagebox.showerror("ADIF-Export fehlgeschlagen", str(exc), parent=self)

    def _sync_selection_changed(self, _event=None):
        if not hasattr(self, "sync_detail_label"):
            return
        local_id = self.selected_id()
        meta = self.db.get_meta(local_id) if local_id else None
        status = str((meta or {}).get("status") or "")
        is_conflict = status == "conflict"
        button_state = "normal" if is_conflict else "disabled"
        self.take_wavelog_button.configure(state=button_state)
        self.force_local_button.configure(state=button_state)
        if status == "error":
            detail = str((meta or {}).get("last_error") or "Kein technischer Fehlertext gespeichert.").strip()
            self.sync_detail_label.configure(text=self._tr("SYNC-FEHLER: ") + detail[:900], fg=ERR)
        elif status == "conflict":
            reason = str((meta or {}).get("last_error") or "Lokale und Wavelog-Version unterscheiden sich.")
            explanations = {
                "both_changed": "Lokale und Wavelog-Version wurden seit dem letzten gemeinsamen Stand geändert.",
                "remote_deleted": "Das QSO wurde in Wavelog gelöscht, lokal aber anschließend verändert.",
            }
            self.sync_detail_label.configure(text=self._tr("KONFLIKT: ") + self._tr(explanations.get(reason, reason))[:900], fg=ERR)
        elif local_id:
            self.sync_detail_label.configure(text=self._tr("Keine offenen Sync-Details."), fg=MUTED)
        else:
            self.sync_detail_label.configure(text=self._tr("QSO auswählen, um Sync-Details anzuzeigen."), fg=MUTED)

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
            self._local_sync_change()
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
        self._local_sync_change()

    def _client_from_settings(self) -> WavelogClient:
        return WavelogClient(self.db.get_setting("wavelog_url", ""), self.db.get_token())

    def sync_now(self):
        self._start_sync(automatic=False, reason="manual")

    def _show_sync_progress(self, reason: str, status_text: str):
        dialog = self.sync_progress_dialog
        if dialog is not None and dialog.winfo_exists():
            dialog.set_running(reason, status_text)
            dialog.lift()
            return
        self.sync_progress_dialog = SyncProgressDialog(self, reason, status_text)

    def _complete_sync_progress(self, success: bool, details: str) -> bool:
        dialog = self.sync_progress_dialog
        if dialog is None or not dialog.winfo_exists():
            return False
        dialog.complete(success, details)
        return True

    def _sync_progress_acknowledged(self):
        dialog = self.sync_progress_dialog
        reason = dialog.reason if dialog is not None else self.sync_reason
        if dialog is not None:
            try:
                dialog.grab_release()
                dialog.destroy()
            except tk.TclError:
                pass
        self.sync_progress_dialog = None
        self.sync_reason = ""
        if self.close_requested or reason == "shutdown":
            self._finalize_close()
        else:
            self._request_auto_sync(delay_ms=600)

    def _start_sync(self, *, automatic: bool, reason: str = "manual"):
        if self.sync_busy:
            return
        try:
            settings = self._wavelog_online_settings()
            station_id = settings.station_id
            if not settings.configured:
                raise ValueError("Bitte in den Einstellungen zuerst ein Wavelog-Stationsprofil auswählen")
            client = WavelogClient(settings.base_url, settings.token)
        except Exception as e:
            if not automatic:
                messagebox.showerror("Sync", str(e), parent=self)
            return
        self.sync_busy = True
        self.sync_is_automatic = automatic
        self.sync_operation = "full"
        self.sync_reason = reason
        if reason == "startup":
            progress_text = "Vollständiger Start-Sync läuft …"
        elif reason == "shutdown":
            progress_text = "Vollständiger Abschluss-Sync läuft …"
        else:
            progress_text = "Automatische Synchronisierung läuft …" if automatic else "Synchronisierung läuft …"
        self.status_var.set(progress_text)
        self.sync_label.configure(text=progress_text)
        if reason in ("startup", "shutdown"):
            self._show_sync_progress(reason, progress_text)

        def worker():
            try:
                stations = client.stations()
                smap = {int(s.get("id")): s for s in stations if s.get("id") is not None}
                engine = SyncEngine(self.store, self.db, client)
                summary = engine.sync(station_id, smap)
                contest_summary = ContestSyncEngine(self.store, self.db, client).sync(station_id)
                msg = (f"Upload {summary.pushed} · zu Wavelog geändert {summary.patched} · "
                       f"neu aus Wavelog {summary.pulled} · aus Wavelog aktualisiert {summary.remote_updated} · "
                       f"remote gelöscht {summary.remote_deleted} · verknüpft {summary.linked} · "
                       f"lokal→Wavelog gelöscht {summary.deleted} · QSL-Status {summary.qsl_updated} · "
                       f"anderes Stationsprofil übersprungen {summary.scope_skipped} · "
                       f"Konflikte {summary.conflicts} · Fehler {summary.errors} · QSL-Statusfehler {summary.qsl_errors} · "
                       f"Contests neu {contest_summary.created} / geladen {contest_summary.pulled} / "
                       f"aus QSO-Historie {contest_summary.history_imported} / "
                       f"QSO-Links {contest_summary.linked} / Fehler {contest_summary.errors}")
                if not self.closing:
                    self.after(0, lambda: self._sync_finished(msg, automatic))
            except Exception as e:
                if not self.closing:
                    error_message = str(e)
                    self.after(0, lambda message=error_message: self._sync_failed(message, automatic))

        threading.Thread(target=worker, name="wavelog-sync", daemon=True).start()

    def _sync_finished(self, msg, automatic: bool = False):
        self.sync_busy = False
        self.sync_is_automatic = False
        self.sync_operation = ""
        self.db.set_setting("last_sync_at", datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S"))
        self._set_wavelog_mode_ui(True)
        self.status_var.set(("Auto-Sync fertig · " if automatic else "Sync fertig · ") + msg)
        self.refresh_qsos()
        self.refresh_contest_page()
        self._schedule_wavelog_check(60_000)
        if self._complete_sync_progress(True, msg):
            return
        self.sync_reason = ""
        if self.close_requested:
            self._finalize_close()
        else:
            # Do not leave a QSO that was entered during the full sync behind.
            self._request_auto_sync(delay_ms=600)

    def _sync_failed(self, msg, automatic: bool = False):
        self.sync_busy = False
        self.sync_is_automatic = False
        self.sync_operation = ""
        has_progress = self.sync_progress_dialog is not None
        if automatic or has_progress:
            self.status_var.set("Auto-Sync fehlgeschlagen · QSOs bleiben LOCAL ONLY")
            write_startup_log("Auto-Sync fehlgeschlagen: " + msg)
        else:
            self.status_var.set("Sync fehlgeschlagen")
            messagebox.showerror("Wavelog Sync", msg, parent=self)
        self.refresh_qsos()
        self._schedule_wavelog_check(1500)
        safe_message = self._tr(
            "Wavelog konnte nicht vollständig synchronisiert werden. Die lokalen QSOs bleiben sicher gespeichert."
        ) + "\n\n" + msg
        if self._complete_sync_progress(False, safe_message):
            return
        self.sync_reason = ""
        if self.close_requested:
            self._finalize_close()

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
        stat_periods = ("Gesamt", "Dieses Jahr", "Dieser Monat", "Diese Woche", "Heute (UTC)")
        self.stats_period_var = tk.StringVar(value=self._tr("Gesamt"))
        period = ttk.Combobox(controls, textvariable=self.stats_period_var, state="readonly", width=18,
                              values=tuple(self._tr(value) for value in stat_periods))
        period.pack(side="left")
        period.bind("<<ComboboxSelected>>", lambda e: self.refresh_stats())
        tk.Label(controls, text="Operator:", bg=CARD, fg=MUTED, font=("Segoe UI", 9)).pack(side="left", padx=(18, 6))
        self.stats_operator_var = tk.StringVar(value=self._tr("Alle Operatoren"))
        self.stats_operator_combo = ttk.Combobox(controls, textvariable=self.stats_operator_var, state="readonly", width=18,
                                                  values=(self._tr("Alle Operatoren"),))
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
        all_operators = self._tr("Alle Operatoren")
        current = self.stats_operator_var.get() if hasattr(self, "stats_operator_var") else all_operators
        try:
            if hasattr(self, "stats_operator_var"):
                self.stats_operator_var.set(all_operators)
            return self._stats_filtered_qsos(qsos)
        finally:
            if hasattr(self, "stats_operator_var"):
                self.stats_operator_var.set(current)

    def _stats_filtered_qsos(self, qsos: list[dict]) -> list[dict]:
        periods = ("Gesamt", "Dieses Jahr", "Dieser Monat", "Diese Woche", "Heute (UTC)")
        period = self._canonical_choice(
            self.stats_period_var.get() if hasattr(self, "stats_period_var") else "Gesamt", periods,
        )
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

        all_operators = self._tr("Alle Operatoren")
        operator = self.stats_operator_var.get() if hasattr(self, "stats_operator_var") else all_operators
        if operator and operator not in {"Alle Operatoren", all_operators}:
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
        qsl = {name: Counter() for name in ("qrz", "lotw", "eqsl", "clublog", "dcl")}
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
        for svc, label in (("qrz", "QRZ"), ("lotw", "LoTW"), ("eqsl", "eQSL"), ("clublog", "ClubLog"), ("dcl", "DCL")):
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
            all_operators = self._tr("Alle Operatoren")
            values = [all_operators] + operators_all
            self.stats_operator_combo.configure(values=values)
            if self.stats_operator_var.get() not in values:
                self.stats_operator_var.set(all_operators)
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
            bg=CARD,
            fg=MUTED,
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
            bg=CARD,
            fg=MUTED,
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
            bg=CARD,
            fg=MUTED,
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
            fg=OK,
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
        self.cat_hamlib_info.configure(text="✕ " + message, fg=ERR)
        self.cat_status_label.configure(text="Hamlib ist nicht verfügbar.", fg=ERR)

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
            text=self._tr("FLRig wird lokal und im privaten Netzwerk gesucht …"), fg=MUTED,
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
                fg=WARN,
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
            fg=OK,
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
        self.cat_status_label.configure(text="CAT wird gestartet …", fg=MUTED)
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
        self.cat_status_label.configure(text="✓ CAT verbunden · warte auf Funkgerätedaten …", fg=OK)
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
        self.cat_status_label.configure(text="✕ " + message, fg=ERR)
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
            fg=OK,
        )
        if not self.tuner_busy:
            self._schedule_cat_poll(interval_ms, interval_ms)

    def _cat_poll_failed(self, generation: int, message: str, interval_ms: int):
        self.cat_poll_busy = False
        if generation != self.cat_generation or self.closing:
            return
        self.cat_status_label.configure(text="CAT-Lesefehler: " + message, fg=WARN)
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
        self.cat_starting = False
        self.tuner_busy = False
        self.tuner_start_pending = False
        self.cat_manager.stop()
        self._set_tune_button_state()
        if update_ui and hasattr(self, "cat_status_label"):
            self.cat_status_label.configure(text="CAT ist gestoppt.", fg=MUTED)

    # ---------- DX Cluster / Telnet ----------
    def _build_dx_cluster_page(self):
        p = self._new_page("dx_cluster")
        p.columnconfigure(0, weight=1)
        p.rowconfigure(2, weight=1)

        setup = self._card(p, row=0, column=0, sticky="ew", pady=(0, 10))
        setup.columnconfigure(0, weight=3)
        setup.columnconfigure(1, weight=1)
        setup.columnconfigure(2, weight=2)
        setup.columnconfigure(3, weight=3)
        ttk.Label(setup, text="Telnet-Verbindung", style="CardTitle.TLabel").grid(row=0, column=0, columnspan=4, sticky="w")
        ttk.Label(
            setup,
            text="Online-Funktion: Der Empfang funktioniert nur bei bestehender Internetverbindung. Host und Port gehören zum aktiven Profil; das Login-Rufzeichen kommt immer aus dessen Stationsdaten. Die Empfangsverbindung wird nach jedem Programmstart bewusst manuell hergestellt.",
            style="Muted.Card.TLabel", wraplength=950,
        ).grid(row=1, column=0, columnspan=4, sticky="w", pady=(3, 10))

        self.dx_cluster_host_var = tk.StringVar(value=DEFAULT_CLUSTER_HOST)
        self.dx_cluster_port_var = tk.StringVar(value=str(DEFAULT_CLUSTER_PORT))
        self.dx_cluster_call_var = tk.StringVar()
        fields = (
            ("DX-Cluster-Host", self.dx_cluster_host_var),
            ("Telnet-Port", self.dx_cluster_port_var),
            ("Login-Rufzeichen", self.dx_cluster_call_var),
        )
        for column, (label, variable) in enumerate(fields):
            ttk.Label(setup, text=label, style="Card.TLabel").grid(row=2, column=column, sticky="w", padx=(0, 10), pady=(2, 3))
            state = "readonly" if variable is self.dx_cluster_call_var else "normal"
            ttk.Entry(setup, textvariable=variable, state=state).grid(
                row=3, column=column, sticky="ew", padx=(0, 10),
            )

        buttons = ttk.Frame(setup, style="Card.TFrame")
        buttons.grid(row=3, column=3, sticky="e")
        ttk.Button(buttons, text="Einstellungen speichern", style="Secondary.TButton", command=self.save_dx_cluster_settings).pack(side="left")
        self.dx_cluster_start_button = ttk.Button(buttons, text="Verbinden", style="Primary.TButton", command=self.start_dx_cluster)
        self.dx_cluster_start_button.pack(side="left", padx=8)
        self.dx_cluster_stop_button = ttk.Button(buttons, text="Trennen", style="Secondary.TButton", command=self.stop_dx_cluster)
        self.dx_cluster_stop_button.pack(side="left")

        self.dx_cluster_status_label = tk.Label(
            setup, text="DX Cluster ist getrennt.", bg=CARD, fg=MUTED, font=("Segoe UI", 9),
            justify="left", anchor="w", wraplength=1050,
        )
        self.dx_cluster_status_label.grid(row=4, column=0, columnspan=4, sticky="ew", pady=(10, 0))

        filters = self._card(p, row=1, column=0, sticky="ew", pady=(0, 10))
        ttk.Label(filters, text="Spot-Filter", style="CardTitle.TLabel").pack(side="left", padx=(0, 18))
        tk.Label(filters, text="Band", bg=CARD, fg=MUTED, font=("Segoe UI", 9)).pack(side="left", padx=(0, 5))
        self.dx_cluster_band_filter_var = tk.StringVar(value=self._tr("Alle"))
        band_filter = ttk.Combobox(filters, textvariable=self.dx_cluster_band_filter_var, values=[self._tr("Alle"), *BANDS], state="readonly", width=10)
        band_filter.pack(side="left")
        band_filter.bind("<<ComboboxSelected>>", lambda _event: self._refresh_dx_cluster_spots())
        tk.Label(filters, text="Mode", bg=CARD, fg=MUTED, font=("Segoe UI", 9)).pack(side="left", padx=(18, 5))
        self.dx_cluster_mode_filter_var = tk.StringVar(value=self._tr("Alle"))
        mode_filter = ttk.Combobox(filters, textvariable=self.dx_cluster_mode_filter_var, values=[self._tr("Alle"), *[mode for mode in MODES if mode != "SSB"]], state="readonly", width=14)
        mode_filter.pack(side="left")
        mode_filter.bind("<<ComboboxSelected>>", lambda _event: self._refresh_dx_cluster_spots())
        tk.Label(filters, text="Spotter-Region", bg=CARD, fg=MUTED, font=("Segoe UI", 9)).pack(side="left", padx=(18, 5))
        self.dx_cluster_spotter_region_filter_var = tk.StringVar(value=self._tr("Alle"))
        region_filter = ttk.Combobox(
            filters, textvariable=self.dx_cluster_spotter_region_filter_var,
            values=tuple(self._tr(value) for value in SPOTTER_REGION_OPTIONS), state="readonly", width=16,
        )
        region_filter.pack(side="left")
        region_filter.bind("<<ComboboxSelected>>", self._dx_cluster_spotter_region_changed)
        tk.Label(filters, text="Zeitraum", bg=CARD, fg=MUTED, font=("Segoe UI", 9)).pack(side="left", padx=(18, 5))
        self.dx_cluster_time_filter_var = tk.StringVar(value=self._tr("30 Minuten"))
        time_filter = ttk.Combobox(
            filters, textvariable=self.dx_cluster_time_filter_var,
            values=tuple(self._tr(value) for value in ("15 Minuten", "30 Minuten", "60 Minuten", "2 Stunden", "Alle")),
            state="readonly", width=12,
        )
        time_filter.pack(side="left")
        time_filter.bind("<<ComboboxSelected>>", self._dx_cluster_time_filter_changed)
        ttk.Button(filters, text="Liste leeren", style="Secondary.TButton", command=self._clear_dx_cluster_spots).pack(side="right")

        table = self._card(p, row=2, column=0, sticky="nsew")
        table.columnconfigure(0, weight=1)
        table.rowconfigure(1, weight=1)
        ttk.Label(table, text="Empfangene DX-Spots", style="CardTitle.TLabel").grid(row=0, column=0, sticky="w", pady=(0, 8))
        tk.Label(
            table, text="Doppelklick stimmt den TRX auf Frequenz und Mode ab. QSO übernehmen füllt anschließend das Formular.",
            bg=CARD, fg=MUTED, font=("Segoe UI", 9), anchor="e",
        ).grid(row=0, column=1, sticky="e", pady=(0, 8))

        tree_box = ttk.Frame(table, style="Card.TFrame")
        tree_box.grid(row=1, column=0, columnspan=2, sticky="nsew")
        tree_box.columnconfigure(0, weight=1)
        tree_box.rowconfigure(0, weight=1)
        self.dx_cluster_visible_ids: list[str] = []
        self.dx_cluster_selected_id: str | None = None
        self.dx_cluster_table_columns = (
            ("time", self._tr("UTC"), 7), ("call", self._tr("DX-Rufzeichen"), 15),
            ("dx_country", self._tr("DX-Land"), 20), ("frequency", self._tr("MHz"), 11),
            ("band", self._tr("Band"), 8), ("mode", self._tr("Mode"), 10),
            ("spotter", self._tr("Spotter"), 15), ("spotter_country", self._tr("Spotter-Land"), 20),
            ("comment", self._tr("Kommentar"), 60),
        )
        self.dx_cluster_tree = tk.Text(
            tree_box, wrap="none", state="disabled", bg=INPUT_BG, fg=TEXT, insertbackground=TEXT,
            font=("Consolas", 9), relief="solid", borderwidth=1,
            highlightthickness=0, cursor="arrow", padx=4, pady=2,
        )
        self.dx_cluster_tree.tag_configure("header", background=NEUTRAL_BADGE_BG, foreground=TEXT, font=("Consolas", 9, "bold"))
        self.dx_cluster_tree.tag_configure("new", background=ACTIVE_BG)
        self.dx_cluster_tree.tag_configure("worked", foreground=OK, font=("Consolas", 9, "bold"))
        self.dx_cluster_tree.tag_configure("selected", background=NAV_ACTIVE_HOVER)
        self.dx_cluster_tree.grid(row=0, column=0, sticky="nsew")
        scroll = ttk.Scrollbar(tree_box, orient="vertical", command=self.dx_cluster_tree.yview)
        scroll.grid(row=0, column=1, sticky="ns")
        hscroll = ttk.Scrollbar(tree_box, orient="horizontal", command=self.dx_cluster_tree.xview)
        hscroll.grid(row=1, column=0, sticky="ew")
        self.dx_cluster_tree.configure(yscrollcommand=scroll.set, xscrollcommand=hscroll.set)
        self.dx_cluster_tree.bind("<Button-1>", self._dx_cluster_table_click)
        self.dx_cluster_tree.bind("<Double-1>", self._dx_cluster_table_double_click)

        actions = ttk.Frame(table, style="Card.TFrame")
        actions.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(10, 0))
        ttk.Button(actions, text="QSO übernehmen", style="Primary.TButton", command=self._use_selected_dx_spot).pack(side="left")
        tk.Label(
            actions, text="Überschriften sortieren · neu: hellblau · gleicher Mode gearbeitet: grün · Doppelklick stimmt TRX ab.",
            bg=CARD, fg=MUTED, font=("Segoe UI", 9),
        ).pack(side="right")
        self.dx_cluster_filter_job = self.after(10_000, self._dx_cluster_filter_tick)

    def _active_station_callsign(self) -> str:
        profile = self._profile_values()
        return (profile.get("station_call") or profile.get("operator_call") or "").strip().upper()

    def _load_dx_cluster_settings_to_ui(self):
        login_call = self._active_station_callsign()
        config = DxClusterConfig.from_getter(self.db.get_setting, login_call)
        self.dx_cluster_host_var.set(config.host)
        self.dx_cluster_port_var.set(str(config.port))
        self.dx_cluster_call_var.set(login_call)
        saved_window = self.db.get_setting("dx_cluster_time_window", "30 Minuten")
        if saved_window not in {"15 Minuten", "30 Minuten", "60 Minuten", "2 Stunden", "Alle"}:
            saved_window = "30 Minuten"
        self.dx_cluster_time_filter_var.set(self._tr(saved_window))
        saved_region = self.db.get_setting("dx_cluster_spotter_region", "Alle")
        if saved_region not in SPOTTER_REGION_OPTIONS:
            saved_region = "Alle"
        self.dx_cluster_spotter_region_filter_var.set(self._tr(saved_region))
        self._clear_dx_cluster_spots()
        self.dx_cluster_status_label.configure(
            text="DX Cluster ist getrennt · zum Empfangen bitte manuell verbinden.", fg=MUTED,
        )
        self.dx_cluster_start_button.configure(state="normal")
        self.dx_cluster_stop_button.configure(state="disabled")

    def _dx_cluster_config_from_ui(self) -> DxClusterConfig:
        try:
            port = int(self.dx_cluster_port_var.get().strip())
        except ValueError as exc:
            raise DxClusterError("Der DX-Cluster-Port muss eine ganze Zahl sein.") from exc
        config = DxClusterConfig(
            host=self.dx_cluster_host_var.get().strip(),
            port=port,
            callsign=self._active_station_callsign(),
        )
        config.validate()
        return config

    def _store_dx_cluster_config(self, config: DxClusterConfig):
        for key, value in config.settings().items():
            self.db.set_setting(key, value)

    def _load_dx_spotter_settings_to_ui(self):
        callsign = self._active_station_callsign()
        config = DxSpotterConfig.from_getter(self.db.get_setting, callsign)
        self.dx_spotter_host_var.set(config.host)
        self.dx_spotter_port_var.set(str(config.port))
        self.dx_spotter_call_var.set(callsign)
        self.dx_spotter_status_label.configure(
            text="Spotter-Verbindung wird erst beim Senden aufgebaut.", fg=MUTED,
        )

    def _dx_spotter_config_from_ui(self) -> DxSpotterConfig:
        try:
            port = int(self.dx_spotter_port_var.get().strip())
        except ValueError as exc:
            raise DxClusterError("Der DX-Spotter-Port muss eine ganze Zahl sein.") from exc
        config = DxSpotterConfig(
            host=self.dx_spotter_host_var.get().strip(),
            port=port,
            callsign=self._active_station_callsign(),
        )
        config.validate()
        return config

    def _store_dx_spotter_config(self, config: DxSpotterConfig):
        for key, value in config.settings().items():
            self.db.set_setting(key, value)

    def _stop_dx_spotter_runtime(self, *, update_ui: bool = True):
        self.dx_spotter_generation += 1
        self.dx_spotter.stop()
        self.dx_spotter_active_config = None
        if update_ui and hasattr(self, "dx_spotter_status_label"):
            self.dx_spotter_status_label.configure(
                text="Spotter-Verbindung ist getrennt.", fg=MUTED,
            )

    def save_dx_cluster_settings(self):
        try:
            config = self._dx_cluster_config_from_ui()
            self._store_dx_cluster_config(config)
            if self.dx_cluster.running:
                message = "DX-Cluster-Einstellungen gespeichert · Änderungen gelten nach Trennen und erneutem Verbinden."
            else:
                message = "DX-Cluster-Einstellungen gespeichert · Verbindung bleibt getrennt."
            self.dx_cluster_status_label.configure(text=message, fg=OK)
            self.status_var.set("DX-Cluster-Einstellungen gespeichert")
        except Exception as exc:
            messagebox.showerror("DX Cluster", str(exc), parent=self)

    def start_dx_cluster(self):
        try:
            config = self._dx_cluster_config_from_ui()
            self._store_dx_cluster_config(config)
            self.dx_cluster_session_received = 0
            self.dx_cluster_last_spot_utc = None
            self.dx_cluster_generation += 1
            generation = self.dx_cluster_generation
            self.dx_cluster.start(
                config,
                lambda spot: self._queue_dx_cluster_spot(generation, spot),
                lambda message: self._queue_dx_cluster_status(generation, message),
                lambda message: self._queue_dx_cluster_error(generation, message),
            )
        except Exception as exc:
            self.dx_cluster_status_label.configure(text="Verbindung fehlgeschlagen: " + str(exc), fg=ERR)
            messagebox.showerror("DX Cluster", str(exc), parent=self)
            return
        self.dx_cluster_start_button.configure(state="disabled")
        self.dx_cluster_stop_button.configure(state="normal")
        self.dx_cluster_status_label.configure(text=f"Verbinde mit {config.host}:{config.port} …", fg=MUTED)
        self.status_var.set("DX Cluster verbindet …")

    def stop_dx_cluster(self):
        self._stop_dx_cluster_runtime()
        self.status_var.set("DX Cluster getrennt")

    def _stop_dx_cluster_runtime(self, *, update_ui: bool = True):
        self.dx_cluster_generation += 1
        self.dx_cluster.stop()
        if update_ui and hasattr(self, "dx_cluster_status_label"):
            self.dx_cluster_status_label.configure(text="DX Cluster ist getrennt.", fg=MUTED)
            self.dx_cluster_start_button.configure(state="normal")
            self.dx_cluster_stop_button.configure(state="disabled")

    def _queue_dx_cluster_spot(self, generation: int, spot: DxSpot):
        if not self.closing:
            self.after(0, lambda: self._accept_dx_cluster_spot(generation, spot))

    def _queue_dx_cluster_status(self, generation: int, message: str):
        if not self.closing:
            self.after(0, lambda: self._show_dx_cluster_status(generation, message))

    def _queue_dx_cluster_error(self, generation: int, message: str):
        if not self.closing:
            self.after(0, lambda: self._show_dx_cluster_error(generation, message))

    def _show_dx_cluster_status(self, generation: int, message: str):
        if generation != self.dx_cluster_generation or self.closing:
            return
        active = "aktiv" in message.lower()
        if active:
            self._update_dx_cluster_live_status()
        else:
            self.dx_cluster_status_label.configure(text=message, fg=MUTED)
        self.status_var.set(message)

    def _update_dx_cluster_live_status(self):
        if not hasattr(self, "dx_cluster_status_label") or not self.dx_cluster.connected:
            return
        last = (
            self.dx_cluster_last_spot_utc.strftime("%H:%M:%S UTC")
            if self.dx_cluster_last_spot_utc else "noch keiner"
        )
        visible = len(getattr(self, "dx_cluster_visible_ids", []))
        host = self.dx_cluster_host_var.get().strip()
        port = self.dx_cluster_port_var.get().strip()
        self.dx_cluster_status_label.configure(
            text=(
                f"✓ Live-Telnet {host}:{port} · {self.dx_cluster_session_received} Spot(s) empfangen · "
                f"{visible} sichtbar · letzter Spot: {last}"
            ),
            fg=OK,
        )

    def _show_dx_cluster_error(self, generation: int, message: str):
        if generation != self.dx_cluster_generation or self.closing:
            return
        self.dx_cluster_status_label.configure(text="DX-Cluster-Verbindung beendet: " + message, fg=ERR)
        self.dx_cluster_start_button.configure(state="normal")
        self.dx_cluster_stop_button.configure(state="disabled")
        self.status_var.set("DX-Cluster-Verbindung beendet")

    def _accept_dx_cluster_spot(self, generation: int, spot: DxSpot):
        if generation != self.dx_cluster_generation or self.closing:
            return
        identity = (
            spot.spotter, spot.call, spot.frequency_hz, spot.time_utc, spot.comment,
        )
        if identity in self.dx_cluster_seen_keys:
            return
        self.dx_cluster_seen_keys.add(identity)
        self.dx_cluster_sequence += 1
        self.dx_cluster_session_received += 1
        self.dx_cluster_last_spot_utc = datetime.now(timezone.utc)
        item_id = f"dx-{self.dx_cluster_sequence}"
        self.dx_cluster_spots.insert(0, (item_id, spot))
        if len(self.dx_cluster_spots) > 500:
            removed = self.dx_cluster_spots[500:]
            self.dx_cluster_spots = self.dx_cluster_spots[:500]
            for _old_id, old_spot in removed:
                self.dx_cluster_seen_keys.discard((
                    old_spot.spotter, old_spot.call, old_spot.frequency_hz,
                    old_spot.time_utc, old_spot.comment,
                ))
        self._refresh_dx_cluster_spots()
        self.status_var.set(f"Neuer Live-DX-Spot: {spot.call} · {spot.frequency_mhz} MHz")

    def _clear_dx_cluster_spots(self):
        self.dx_cluster_spots.clear()
        self.dx_cluster_spot_by_id.clear()
        self.dx_cluster_visible_ids = []
        self.dx_cluster_selected_id = None
        self.dx_cluster_seen_keys.clear()
        self._refresh_dx_cluster_spots()

    def _dx_cluster_time_filter_changed(self, _event=None):
        value = self._canonical_choice(
            self.dx_cluster_time_filter_var.get(), ("15 Minuten", "30 Minuten", "60 Minuten", "2 Stunden", "Alle"),
        )
        self.db.set_setting("dx_cluster_time_window", value)
        self._refresh_dx_cluster_spots()

    def _dx_cluster_spotter_region_changed(self, _event=None):
        value = self._canonical_choice(self.dx_cluster_spotter_region_filter_var.get(), SPOTTER_REGION_OPTIONS)
        if value not in SPOTTER_REGION_OPTIONS:
            value = "Alle"
            self.dx_cluster_spotter_region_filter_var.set(self._tr(value))
        self.db.set_setting("dx_cluster_spotter_region", value)
        self._refresh_dx_cluster_spots()

    @staticmethod
    def _dx_cluster_spot_age_seconds(spot: DxSpot, now: datetime | None = None) -> float:
        current = now or datetime.now(timezone.utc)
        return max(0.0, (current - spot.spotted_at_utc).total_seconds())

    def _dx_cluster_filter_tick(self):
        self.dx_cluster_filter_job = None
        if self.closing:
            return
        self._refresh_dx_cluster_spots()
        self.dx_cluster_filter_job = self.after(10_000, self._dx_cluster_filter_tick)

    def _update_dx_cluster_worked_cache(self, qsos: list[dict]):
        calls: set[tuple[str, str, str]] = set()
        countries: set[tuple[str, str, str]] = set()
        worked_counts: Counter[tuple[str, str, str]] = Counter()
        call_totals: Counter[str] = Counter()
        worked_history: dict[str, list[dict[str, str]]] = {}
        for qso in qsos:
            call = str(qso.get("call") or "").strip().upper()
            if call:
                call_totals[call] += 1
                worked_history.setdefault(call, []).append({
                    "qso_date": str(qso.get("qso_date") or ""),
                    "time_on": str(qso.get("time_on") or ""),
                    "band": str(qso.get("band") or ""),
                    "mode": str(qso.get("mode") or ""),
                })
            country = str(qso.get("country") or "").strip()
            if not country and call:
                info = self.country_db.lookup(call)
                country = info.country if info else ""
            frequency_hz = 0
            try:
                frequency_hz = int(round(float(str(qso.get("freq") or "0").replace(",", ".")) * 1_000_000))
            except (TypeError, ValueError):
                pass
            band = str(qso.get("band") or "").strip()
            if not band and frequency_hz:
                band = band_from_mhz(frequency_hz / 1_000_000) or ""
            mode = normalize_worked_mode(
                str(qso.get("mode") or ""), frequency_hz, band,
            )
            if not band or not mode:
                continue
            if call:
                calls.add((call, band, mode))
                worked_counts[(call, band, mode)] += 1
            if country:
                countries.add((country, band, mode))
        self.dx_cluster_worked_calls = calls
        self.dx_cluster_worked_countries = countries
        self.qso_worked_counts = worked_counts
        self.qso_worked_call_totals = call_totals
        for history in worked_history.values():
            history.sort(key=lambda item: (item["qso_date"], re.sub(r"[^0-9]", "", item["time_on"])), reverse=True)
        self.qso_worked_history = worked_history
        self._update_qso_worked_status()
        if hasattr(self, "dx_cluster_tree"):
            self._refresh_dx_cluster_spots()

    def _dx_cluster_country(self, callsign: str) -> str:
        key = (callsign or "").strip().upper()
        if key in self.dx_cluster_country_cache:
            return self.dx_cluster_country_cache[key]
        lookup_call = re.sub(r"-(?:\d+|#)$", "", key)
        info = self.country_db.lookup(lookup_call)
        country = info.country if info else "—"
        self.dx_cluster_country_cache[key] = country
        self.dx_cluster_continent_cache[key] = (info.cont or "").upper() if info else ""
        return country

    def _dx_cluster_continent(self, callsign: str) -> str:
        key = (callsign or "").strip().upper()
        if key not in self.dx_cluster_continent_cache:
            self._dx_cluster_country(callsign)
        return self.dx_cluster_continent_cache.get(key, "")

    @staticmethod
    def _dx_cluster_table_cell(value: str, width: int) -> str:
        text = str(value or "—")
        if len(text) > width - 1:
            text = text[: width - 2] + "…"
        return text.ljust(width)

    def _dx_cluster_sort_value(self, row: tuple):
        _item_id, spot, dx_country, spotter_country, comment, _age = row
        return spot_sort_value(
            spot, self.dx_cluster_sort_key, dx_country, spotter_country, comment,
        )

    def _refresh_dx_cluster_spots(self):
        if not hasattr(self, "dx_cluster_tree"):
            return
        band_filter = self._canonical_choice(self.dx_cluster_band_filter_var.get(), ("Alle", *BANDS))
        mode_filter = self._canonical_choice(self.dx_cluster_mode_filter_var.get(), ("Alle", *MODES))
        spotter_region_filter = self._canonical_choice(self.dx_cluster_spotter_region_filter_var.get(), SPOTTER_REGION_OPTIONS)
        window_label = self._canonical_choice(
            self.dx_cluster_time_filter_var.get(), ("15 Minuten", "30 Minuten", "60 Minuten", "2 Stunden", "Alle"),
        )
        window_minutes = {
            "15 Minuten": 15, "30 Minuten": 30, "60 Minuten": 60, "2 Stunden": 120,
        }.get(window_label)
        now = datetime.now(timezone.utc)
        rows = []
        for item_id, spot in self.dx_cluster_spots:
            age_seconds = self._dx_cluster_spot_age_seconds(spot, now)
            if window_minutes is not None and age_seconds > window_minutes * 60:
                continue
            if band_filter != "Alle" and spot.band != band_filter:
                continue
            if mode_filter != "Alle" and spot.mode != mode_filter:
                continue
            comment = spot.comment
            if spot.locator:
                comment = (comment + " · " if comment else "") + spot.locator
            dx_country = self._dx_cluster_country(spot.call)
            spotter_country = self._dx_cluster_country(spot.spotter)
            spotter_region = spotter_region_for_continent(self._dx_cluster_continent(spot.spotter))
            if spotter_region_filter != "Alle" and spotter_region != spotter_region_filter:
                continue
            rows.append((item_id, spot, dx_country, spotter_country, comment, age_seconds))
        rows.sort(key=self._dx_cluster_sort_value, reverse=self.dx_cluster_sort_descending)

        old_y = self.dx_cluster_tree.yview()
        old_x = self.dx_cluster_tree.xview()
        selected_id = self.dx_cluster_selected_id
        self.dx_cluster_tree.configure(state="normal")
        self.dx_cluster_tree.delete("1.0", "end")
        self.dx_cluster_spot_by_id.clear()
        self.dx_cluster_visible_ids = []
        header_parts = []
        for key, label, width in self.dx_cluster_table_columns:
            if key == self.dx_cluster_sort_key:
                label += " ▼" if self.dx_cluster_sort_descending else " ▲"
            header_parts.append(self._dx_cluster_table_cell(label, width))
        self.dx_cluster_tree.insert("end", "".join(header_parts) + "\n", ("header",))

        for item_id, spot, dx_country, spotter_country, comment, age_seconds in rows:
            worked_call, worked_country = worked_flags(
                spot.call, dx_country, spot.band, spot.mode,
                self.dx_cluster_worked_calls, self.dx_cluster_worked_countries,
            )
            line_number = len(self.dx_cluster_visible_ids) + 2
            self.dx_cluster_tree.insert("end", self._dx_cluster_table_cell((spot.time_utc + "Z") if spot.time_utc else "—", 7))
            self.dx_cluster_tree.insert(
                "end", self._dx_cluster_table_cell(spot.call, 15), ("worked",) if worked_call else (),
            )
            self.dx_cluster_tree.insert(
                "end", self._dx_cluster_table_cell(dx_country, 20), ("worked",) if worked_country else (),
            )
            for value, width in (
                (spot.frequency_mhz, 11), (spot.band or "—", 8), (spot.mode or "—", 10),
                (spot.spotter, 15), (spotter_country, 20), (comment, 60),
            ):
                self.dx_cluster_tree.insert("end", self._dx_cluster_table_cell(value, width))
            self.dx_cluster_tree.insert("end", "\n")
            line_start = f"{line_number}.0"
            line_end = f"{line_number}.end"
            if age_seconds <= 120:
                self.dx_cluster_tree.tag_add("new", line_start, line_end)
            if item_id == selected_id:
                self.dx_cluster_tree.tag_add("selected", line_start, line_end)
            self.dx_cluster_visible_ids.append(item_id)
            self.dx_cluster_spot_by_id[item_id] = spot

        if selected_id not in self.dx_cluster_spot_by_id:
            self.dx_cluster_selected_id = None
        self.dx_cluster_tree.configure(state="disabled")
        if old_y:
            self.dx_cluster_tree.yview_moveto(old_y[0])
        if old_x:
            self.dx_cluster_tree.xview_moveto(old_x[0])
        self._update_dx_cluster_live_status()

    def _dx_cluster_sort_from_character(self, character: int):
        start = 0
        for key, _label, width in self.dx_cluster_table_columns:
            if start <= character < start + width:
                if self.dx_cluster_sort_key == key:
                    self.dx_cluster_sort_descending = not self.dx_cluster_sort_descending
                else:
                    self.dx_cluster_sort_key = key
                    self.dx_cluster_sort_descending = key in {"time", "frequency"}
                self._refresh_dx_cluster_spots()
                return
            start += width

    def _dx_cluster_table_click(self, event):
        line_text, character_text = self.dx_cluster_tree.index(f"@{event.x},{event.y}").split(".")
        line = int(line_text)
        if line == 1:
            self._dx_cluster_sort_from_character(int(character_text))
            return "break"
        visible_index = line - 2
        if not 0 <= visible_index < len(self.dx_cluster_visible_ids):
            return "break"
        self.dx_cluster_selected_id = self.dx_cluster_visible_ids[visible_index]
        self.dx_cluster_tree.tag_remove("selected", "1.0", "end")
        self.dx_cluster_tree.tag_add("selected", f"{line}.0", f"{line}.end")
        return "break"

    def _dx_cluster_table_double_click(self, event):
        line = int(self.dx_cluster_tree.index(f"@{event.x},{event.y}").split(".")[0])
        if line == 1:
            return "break"
        self._dx_cluster_table_click(event)
        self._tune_selected_dx_spot()
        return "break"

    def _selected_dx_cluster_spot(self) -> DxSpot | None:
        return self.dx_cluster_spot_by_id.get(self.dx_cluster_selected_id or "")

    def _use_selected_dx_spot(self):
        spot = self._selected_dx_cluster_spot()
        if spot is None:
            messagebox.showinfo("DX Cluster", "Bitte zuerst einen DX-Spot auswählen.", parent=self)
            return
        self.call_var.set(spot.call)
        self._call_changed()
        self.freq_var.set(spot.frequency_mhz)
        if spot.band:
            self.band_var.set(spot.band)
        if spot.mode in MODES:
            self.mode_var.set(spot.mode)
        self._show_page("log")
        self.call_entry.focus_set()
        self.status_var.set(f"DX-Spot als QSO übernommen: {spot.call} · noch nicht gespeichert")

    def _tune_selected_dx_spot(self):
        spot = self._selected_dx_cluster_spot()
        if spot is None:
            messagebox.showinfo("DX Cluster", "Bitte zuerst einen DX-Spot auswählen.", parent=self)
            return
        if not self.cat_manager.running:
            messagebox.showwarning(
                "CAT ist ausgeschaltet",
                "Zum Abstimmen des TRX bitte zuerst CAT im CAT Setup starten.",
                parent=self,
            )
            return
        generation = self.cat_generation
        self.status_var.set(f"CAT stimmt auf {spot.call} · {spot.frequency_mhz} MHz ab …")

        def worker():
            try:
                self.cat_manager.set_frequency_and_mode(spot.frequency_hz, spot.mode)
                if not self.closing:
                    self.after(0, lambda: self._dx_cluster_tuned(generation, spot))
            except Exception as exc:
                message = str(exc)
                if not self.closing:
                    self.after(0, lambda message=message: messagebox.showerror("CAT abstimmen", message, parent=self))

        threading.Thread(target=worker, name="dx-cluster-cat-tune", daemon=True).start()

    def _dx_cluster_tuned(self, generation: int, spot: DxSpot):
        if generation != self.cat_generation or self.closing:
            return
        mode = f" · {spot.mode}" if spot.mode else ""
        self.status_var.set(f"CAT abgestimmt: {spot.call} · {spot.frequency_mhz} MHz{mode}")

    def send_current_dx_spot(self):
        current_call = self.call_var.get().strip().upper()
        current_frequency = self.freq_var.get().strip().replace(",", ".")
        candidate, _using_last_saved = select_dx_spot_candidate({
            "call": current_call,
            "freq": current_frequency,
            "mode": self.mode_var.get().strip().upper(),
            "comment": self.form_vars["comment"].get().strip(),
        }, self.last_spottable_qso)
        try:
            call = str(candidate.get("call") or "").strip().upper()
            if not call:
                raise ValueError
            frequency_hz = int(round(float(str(candidate.get("freq") or "").replace(",", ".")) * 1_000_000))
            if frequency_hz <= 0:
                raise ValueError
        except ValueError:
            messagebox.showerror(
                "DX-Spot senden",
                "Bitte Rufzeichen und eine gültige Frequenz im QSO-Formular eintragen.",
                parent=self,
            )
            return
        try:
            config = DxSpotterConfig.from_getter(
                self.db.get_setting, self._active_station_callsign(),
            )
            config.validate()
        except Exception as exc:
            messagebox.showerror(
                "DX-Spotter-Verbindung",
                str(exc) + "\n\nBitte die Spotter-Verbindung in den Einstellungen prüfen.",
                parent=self,
            )
            return
        comment = simpledialog.askstring(
            "DX-Spot senden",
            "Optionaler Kommentar für den öffentlichen DX-Spot:",
            initialvalue=str(candidate.get("comment") or "").strip(),
            parent=self,
        )
        if comment is None:
            return
        mode = str(candidate.get("mode") or "").strip().upper()
        transmitted_comment = spot_comment_with_mode(comment, mode)
        frequency_mhz = f"{frequency_hz / 1_000_000:.6f}".rstrip("0").rstrip(".")
        if not messagebox.askyesno(
            "DX-Spot öffentlich senden",
            f"Folgenden Spot wirklich öffentlich über {config.host}:{config.port} senden?\n\n"
            f"Rufzeichen: {call}\nFrequenz: {frequency_mhz} MHz\nMode: {mode or '—'}\n"
            f"Login: {config.callsign}\nÜbertragener Kommentar: {transmitted_comment or '—'}",
            parent=self,
        ):
            return
        self.dx_spotter_generation += 1
        generation = self.dx_spotter_generation
        self.dx_spotter_status_label.configure(
            text=f"Verbinde zum Spotten mit {config.host}:{config.port} …", fg=MUTED,
        )
        self.status_var.set("DX-Spotter verbindet …")

        def worker():
            try:
                if self.dx_spotter_active_config != config or not self.dx_spotter.connected:
                    self.dx_spotter.start(config, lambda _spot: None)
                    self.dx_spotter_active_config = config
                    self.dx_spotter.wait_until_connected()
                self.dx_spotter.send_spot(call, frequency_hz, comment, mode)
                if not self.closing:
                    self.after(
                        0, lambda: self._dx_spot_sent(
                            generation, call, frequency_mhz, config,
                        ),
                    )
            except Exception as exc:
                message = str(exc)
                self.dx_spotter.stop()
                self.dx_spotter_active_config = None
                if not self.closing:
                    self.after(
                        0, lambda message=message: self._dx_spot_failed(generation, message),
                    )

        threading.Thread(target=worker, name="dx-spotter-send", daemon=True).start()

    def _dx_spot_sent(
        self, generation: int, call: str, frequency_mhz: str, config: DxSpotterConfig,
    ):
        if generation != self.dx_spotter_generation or self.closing:
            return
        self.status_var.set(f"DX-Spot gesendet: {call} · {frequency_mhz} MHz")
        self.dx_spotter_status_label.configure(
            text=(
                f"✓ DX-Spot gesendet: {call} · {frequency_mhz} MHz · "
                f"{config.host}:{config.port} als {config.callsign}"
            ),
            fg=OK,
        )

    def _dx_spot_failed(self, generation: int, message: str):
        if generation != self.dx_spotter_generation or self.closing:
            return
        self.dx_spotter_status_label.configure(
            text="DX-Spot konnte nicht gesendet werden: " + message, fg=ERR,
        )
        self.status_var.set("DX-Spot konnte nicht gesendet werden")
        messagebox.showerror("DX-Spot senden", message, parent=self)


    # ---------- WSJT-X / external UDP logging ----------
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
            values=("127.0.0.1", "0.0.0.0"),
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
            bg=CARD,
            fg=MUTED,
            font=("Segoe UI", 10),
            justify="left",
            anchor="nw",
            wraplength=470,
        )
        self.udp_log_status_label.grid(row=11, column=0, sticky="ew", pady=(6, 10))
        self.udp_log_live_label = tk.Label(
            left,
            text="WSJT-X Live: kein aktives QSO.",
            bg=SURFACE, fg=MUTED, font=("Segoe UI Semibold", 9),
            justify="left", anchor="nw", wraplength=470, padx=9, pady=7,
        )
        self.udp_log_live_label.grid(row=12, column=0, sticky="ew", pady=(0, 10))
        self.udp_log_last_label = tk.Label(
            left,
            text="Noch kein QSO empfangen.",
            bg=CARD,
            fg=MUTED,
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
            right, text=wsjtx_help, bg=CARD, fg=TEXT, font=("Segoe UI", 10),
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
            bg=CARD, fg=TEXT, font=("Segoe UI", 10), justify="left", anchor="nw", wraplength=480,
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
            bg=CARD, fg=TEXT, font=("Segoe UI", 10), justify="left", anchor="nw", wraplength=480,
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
        self.wsjtx_live_badge.configure(text="", bg=CARD, fg=ACCENT)
        self.udp_log_status_label.configure(
            text="UDP-Logging ist ausgeschaltet · zum Empfangen bitte UDP starten.", fg=MUTED,
        )
        self.udp_log_live_label.configure(text="WSJT-X Live: kein aktives QSO.", fg=MUTED)
        self.udp_log_last_label.configure(text="Noch kein QSO empfangen.", fg=MUTED)
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
            self.udp_log_status_label.configure(text=message, fg=OK)
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
            self.udp_log_status_label.configure(text="UDP konnte nicht gestartet werden: " + str(exc), fg=ERR)
            self.status_var.set("UDP Logging konnte nicht gestartet werden")
            write_startup_log("UDP Logging konnte nicht gestartet werden: " + repr(exc))
            if show_error:
                messagebox.showerror("UDP Logging", str(exc), parent=self)
            return
        self.udp_log_start_button.configure(state="disabled")
        self.udp_log_stop_button.configure(state="normal")
        self.udp_log_status_label.configure(
            text=f"✓ UDP aktiv auf {config.bind_host}:{config.port} · warte auf QSOs …", fg=OK,
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
            self.udp_log_status_label.configure(text="UDP-Logging ist ausgeschaltet.", fg=MUTED)
            self.udp_log_live_label.configure(text="WSJT-X Live: kein aktives QSO.", fg=MUTED)
            self.wsjtx_live_badge.configure(text="", bg=CARD, fg=ACCENT)
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
        self.udp_log_status_label.configure(text="UDP-Datagramm konnte nicht gelesen werden: " + message, fg=WARN)
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
            self.wsjtx_live_badge.configure(text="", bg=CARD, fg=ACCENT)
            self.udp_log_live_label.configure(text="WSJT-X Live: kein aktives QSO.", fg=MUTED)
            if previous and self.call_var.get().strip().upper() == previous:
                self.clear_qso_form()
            return

        qso_frequency_hz = status.qso_frequency_hz
        frequency = format_frequency_mhz(qso_frequency_hz)
        mode = status.tx_mode or status.mode
        band = band_from_mhz(qso_frequency_hz / 1_000_000) or ""
        state = "TX" if status.transmitting else ("Dekodierung" if status.decoding else "RX")
        self.wsjtx_live_badge.configure(text="● WSJT-X LIVE", bg=ACTIVE_BG, fg=ACCENT)
        self.udp_log_live_label.configure(
            text=(
                f"WSJT-X Live: {call} · {status.dx_grid or 'Locator —'} · "
                f"{band or 'Band —'} · {mode or 'Mode —'} · {state}"
            ),
            fg=ACCENT,
        )

        current_call = self.call_var.get().strip().upper()
        if current_call and current_call not in {call, self.wsjtx_live_form_call}:
            self.udp_log_live_label.configure(
                text=self.udp_log_live_label.cget("text") + " · manuelle Formulareingabe bleibt unverändert",
                fg=WARN,
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
                    self.wsjtx_live_badge.configure(text="", bg=CARD, fg=ACCENT)
                self.udp_log_last_label.configure(
                    text=f"Duplikat ignoriert: {qso['call']} · {qso['qso_date']} {qso['time_on']} · {event.source}",
                    fg=WARN,
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
                self.wsjtx_live_badge.configure(text="", bg=CARD, fg=ACCENT)
            self.refresh_qsos()
            self.udp_log_last_label.configure(
                text=(
                    f"Zuletzt gespeichert: {saved['call']} · {saved.get('band') or '—'} · "
                    f"{saved['mode']} · {event.source}\n"
                    f"Callbook-Ergänzung wird geprüft · in dieser Sitzung: {self.udp_log_received}"
                ),
                fg=OK,
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
            fg=OK,
        )
        self.status_var.set(f"UDP-QSO gespeichert: {current['call']} · {enrichment}")
        self.refresh_qsos()
        self._local_sync_change()

    def create_data_backup(self):
        stamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        destination = filedialog.asksaveasfilename(
            parent=self,
            title="Logger-Backup speichern",
            defaultextension=".zip",
            initialfile=f"Wavelog-Offline-Logger-Backup_{stamp}.zip",
            filetypes=(("ZIP-Backup", "*.zip"), ("Alle Dateien", "*.*")),
        )
        if not destination:
            return
        self.backup_status_label.configure(text="Backup wird erstellt …", foreground=MUTED)
        self.update_idletasks()
        try:
            result = create_backup(self.data_dir, Path(destination), app_version=VERSION)
        except Exception as exc:
            self.backup_status_label.configure(text="Backup fehlgeschlagen", foreground=ERR)
            messagebox.showerror("Backup fehlgeschlagen", str(exc), parent=self)
            return
        self.backup_status_label.configure(
            text=f"Backup erstellt · {result['profiles']} Profil(e) · {result['adi_files']} ADI-Datei(en)",
            foreground=OK,
        )
        messagebox.showinfo(
            "Backup erstellt",
            f"Profile, Einstellungen und ADI-Logbücher wurden gesichert:\n\n{result['path']}\n\n"
            "Hinweis: Das ZIP enthält auch gespeicherte Zugangsdaten und sollte geschützt aufbewahrt werden.",
            parent=self,
        )

    def restore_data_backup(self):
        source = filedialog.askopenfilename(
            parent=self,
            title="Logger-Backup auswählen",
            filetypes=(("ZIP-Backup", "*.zip"), ("Alle Dateien", "*.*")),
        )
        if not source:
            return
        try:
            manifest = inspect_backup(Path(source))
        except Exception as exc:
            messagebox.showerror("Backup ungültig", str(exc), parent=self)
            return
        profile_count = len(manifest.get("profiles") or [])
        created = str(manifest.get("created_utc") or "—").replace("T", " ")
        if not messagebox.askyesno(
            "Backup wiederherstellen",
            f"Backup vom {created}\nVersion: {manifest.get('app_version') or '—'}\n"
            f"Profile: {profile_count}\n\n"
            "Die aktuellen Profile, Einstellungen und ADI-Logbücher werden ersetzt. "
            "Vorher wird automatisch ein Sicherheitsbackup des jetzigen Stands erstellt.\n\nFortfahren?",
            icon="warning",
            parent=self,
        ):
            return
        recovery_dir = self.data_dir / "backups"
        recovery = recovery_dir / f"Vor-Wiederherstellung_{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}.zip"
        progress = tk.Toplevel(self)
        progress.title("Backup wird wiederhergestellt")
        progress.transient(self)
        progress.resizable(False, False)
        progress.protocol("WM_DELETE_WINDOW", lambda: None)
        frame = ttk.Frame(progress, padding=22)
        frame.pack(fill="both", expand=True)
        progress_label = ttk.Label(frame, text="Sicherheitsbackup wird erstellt …")
        progress_label.pack(anchor="w", pady=(0, 10))
        bar = ttk.Progressbar(frame, mode="indeterminate", length=390)
        bar.pack(fill="x")
        bar.start(12)
        progress.geometry(f"440x120+{max(0, self.winfo_rootx()+100)}+{max(0, self.winfo_rooty()+100)}")
        progress.grab_set()
        progress.update()
        storage_closed = False
        try:
            create_backup(self.data_dir, recovery, app_version=VERSION)
            progress_label.configure(text="Daten werden sicher wiederhergestellt …")
            progress.update()
            self.wavelog_check_generation += 1
            self._stop_cat_runtime(update_ui=False)
            self._stop_dx_cluster_runtime(update_ui=False)
            self._stop_dx_spotter_runtime(update_ui=False)
            self._stop_udp_log_runtime(update_ui=False)
            self.db.close()
            storage_closed = True
            result = restore_backup(Path(source), self.data_dir)
        except Exception as exc:
            try:
                progress.grab_release()
                progress.destroy()
            except tk.TclError:
                pass
            messagebox.showerror(
                "Wiederherstellung fehlgeschlagen",
                f"Das Backup konnte nicht vollständig wiederhergestellt werden.\n\n{exc}\n\n"
                f"Sicherheitsbackup des vorherigen Stands:\n{recovery}",
                parent=self,
            )
            if storage_closed:
                self.shutdown_started = True
                self.closing = True
                self.destroy()
            return
        try:
            progress.grab_release()
            progress.destroy()
        except tk.TclError:
            pass
        messagebox.showinfo(
            "Backup wiederhergestellt",
            f"{result['profiles']} Profil(e) wurden wiederhergestellt.\n\n"
            f"Sicherheitsbackup des vorherigen Stands:\n{recovery}\n\n"
            "Die App wird jetzt geschlossen. Bitte anschließend neu starten.",
            parent=self,
        )
        self.shutdown_started = True
        self.closing = True
        self.destroy()

    # ---------- settings ----------
    def _build_settings_page(self):
        p = self._new_page("settings")
        p.columnconfigure(0, weight=1)
        p.rowconfigure(0, weight=1)

        notebook = ttk.Notebook(p, style="Settings.TNotebook")
        notebook.grid(row=0, column=0, sticky="nsew")
        general_tab = ttk.Frame(notebook, padding=(2, 12))
        station_tab = ttk.Frame(notebook, padding=(2, 12))
        online_tab = ttk.Frame(notebook, padding=(2, 12))
        data_tab = ttk.Frame(notebook, padding=(2, 12))
        notebook.add(general_tab, text="Allgemein")
        notebook.add(station_tab, text="Station & Wavelog")
        notebook.add(online_tab, text="Callbook & Online-Dienste")
        notebook.add(data_tab, text="Daten & Verbindungen")
        for tab in (general_tab, station_tab, online_tab, data_tab):
            tab.columnconfigure(0, weight=1)
            tab.columnconfigure(1, weight=1)
            tab.rowconfigure(0, weight=1)

        general_left = self._card(general_tab, row=0, column=0, sticky="nsew", padx=(0, 8))
        general_left.columnconfigure(1, weight=1)
        ttk.Label(general_left, text="App-weite Einstellungen", style="CardTitle.TLabel").grid(
            row=0, column=0, columnspan=2, sticky="w",
        )
        ttk.Label(
            general_left,
            text="Sprache und Darstellung gelten für alle Stationsprofile. Die Änderung wird nach einem Neustart der App aktiv.",
            style="Muted.Card.TLabel", wraplength=470,
        ).grid(row=1, column=0, columnspan=2, sticky="w", pady=(3, 14))
        self.set_ui_language = tk.StringVar(value="English" if self.language == "en" else "Deutsch")
        self.set_ui_theme = tk.StringVar(value="Dunkel / Dark" if self.ui_preferences.theme == "dark" else "Hell / Light")
        self.set_qso_notifications = tk.BooleanVar(value=self.ui_preferences.qso_notifications)
        ttk.Label(general_left, text="Sprache", style="Card.TLabel").grid(row=2, column=0, sticky="w", padx=(0, 12), pady=7)
        ttk.Combobox(
            general_left, textvariable=self.set_ui_language, values=("Deutsch", "English"), state="readonly",
        ).grid(row=2, column=1, sticky="ew", pady=7)
        ttk.Label(general_left, text="Theme", style="Card.TLabel").grid(row=3, column=0, sticky="w", padx=(0, 12), pady=7)
        ttk.Combobox(
            general_left, textvariable=self.set_ui_theme, values=("Hell / Light", "Dunkel / Dark"), state="readonly",
        ).grid(row=3, column=1, sticky="ew", pady=7)
        ttk.Checkbutton(
            general_left,
            text="Systemhinweis nach gespeichertem QSO",
            variable=self.set_qso_notifications,
        ).grid(row=4, column=0, columnspan=2, sticky="w", pady=(10, 0))
        ttk.Button(
            general_left, text="Was ist neu?", command=lambda: self._show_whats_new(mark_seen=False),
        ).grid(row=5, column=0, columnspan=2, sticky="w", pady=(14, 0))

        general_right = self._card(general_tab, row=0, column=1, sticky="nsew", padx=(8, 0))
        ttk.Label(general_right, text="Daten & Backup", style="CardTitle.TLabel").pack(anchor="w")
        ttk.Label(
            general_right,
            text=(
                "Ein ZIP sichert alle Logger-Profile, Einstellungen, Sync-Metadaten und ADI-Logbücher. "
                "Gespeicherte Zugangsdaten sind ebenfalls enthalten – das Backup bitte geschützt aufbewahren."
            ),
            style="Muted.Card.TLabel", wraplength=450,
        ).pack(anchor="w", pady=(4, 16))
        backup_actions = ttk.Frame(general_right, style="Card.TFrame")
        backup_actions.pack(anchor="w", fill="x")
        ttk.Button(
            backup_actions, text="Backup erstellen", style="Primary.TButton", command=self.create_data_backup,
        ).pack(side="left")
        ttk.Button(
            backup_actions, text="Backup wiederherstellen", command=self.restore_data_backup,
        ).pack(side="left", padx=(8, 0))
        self.backup_status_label = ttk.Label(general_right, text="Noch kein Backup in dieser Sitzung erstellt.", style="Muted.Card.TLabel")
        self.backup_status_label.pack(anchor="w", pady=(14, 0))

        left = self._card(station_tab, row=0, column=0, sticky="nsew", padx=(0, 8))
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

        right = self._card(station_tab, row=0, column=1, sticky="nsew", padx=(8, 0))
        right.columnconfigure(0, weight=1)
        ttk.Label(right, text="Wavelog Sync", style="CardTitle.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(right, text="API v2 (wl2_… Token). Manueller Sync bleibt immer möglich; optional wechselt die App automatisch in den Online-Modus. Für Callbook-Daten wird zusätzlich lookup:read benötigt.", style="Muted.Card.TLabel", wraplength=450).grid(row=1, column=0, sticky="w", pady=(3, 10))
        self.set_url = tk.StringVar()
        self.set_token = tk.StringVar()
        self.set_station_profile = tk.StringVar()
        self.set_auto_sync_online = tk.BooleanVar(value=False)
        self.set_full_sync_on_start = tk.BooleanVar(value=False)
        self.set_full_sync_on_exit = tk.BooleanVar(value=False)
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
        ttk.Label(
            right,
            text="Dieses Logger-Profil synchronisiert ausschließlich QSOs des ausgewählten Wavelog-Stationsprofils.",
            style="Muted.Card.TLabel", wraplength=450,
        ).grid(row=10, column=0, sticky="w", pady=(4, 6))
        ttk.Button(right, text="Werte aus Wavelog-Profil übernehmen", style="Secondary.TButton", command=self.copy_station_values).grid(row=11, column=0, sticky="w", pady=(4, 12))
        ttk.Separator(right).grid(row=12, column=0, sticky="ew", pady=(2, 10))
        ttk.Checkbutton(
            right,
            text="Online-Modus: neue QSOs automatisch zu Wavelog pushen",
            variable=self.set_auto_sync_online,
        ).grid(row=13, column=0, sticky="w")
        ttk.Checkbutton(
            right,
            text="Vollständigen Sync beim App-Start ausführen",
            variable=self.set_full_sync_on_start,
        ).grid(row=14, column=0, sticky="w", pady=(6, 0))
        ttk.Checkbutton(
            right,
            text="Vollständigen Sync beim Beenden ausführen",
            variable=self.set_full_sync_on_exit,
        ).grid(row=15, column=0, sticky="w", pady=(6, 0))
        ttk.Label(
            right,
            text="Alle Optionen gelten pro Profil und sind unabhängig wählbar. Offline werden QSOs weiter sicher lokal gespeichert.",
            style="Muted.Card.TLabel", wraplength=450,
        ).grid(row=16, column=0, sticky="w", pady=(5, 0))

        callbook_card = self._card(online_tab, row=0, column=0, sticky="nsew", padx=(0, 8))
        callbook_card.columnconfigure(0, weight=1)
        callbook_card.columnconfigure(1, weight=1)
        ttk.Label(callbook_card, text="Rufzeichen-Lookup", style="CardTitle.TLabel").grid(row=0, column=0, columnspan=2, sticky="w")
        ttk.Label(
            callbook_card,
            text="Name, Locator, QTH und – falls vorhanden – das Stationsfoto werden beim Tippen geladen. Ohne Internet läuft das Logging still weiter.",
            style="Muted.Card.TLabel", wraplength=480,
        ).grid(row=1, column=0, columnspan=2, sticky="w", pady=(3, 12))
        self.set_callbook_source = tk.StringVar(value=callbook_source_name(CALLBOOK_SOURCE_WAVELOG, self.language))
        self.set_callbook_auto = tk.BooleanVar(value=True)
        ttk.Label(callbook_card, text="Datenquelle", style="Card.TLabel").grid(row=2, column=0, columnspan=2, sticky="w", pady=(3, 3))
        ttk.Combobox(
            callbook_card, textvariable=self.set_callbook_source,
            values=tuple(callbook_source_labels(self.language)), state="readonly",
        ).grid(row=3, column=0, columnspan=2, sticky="ew")
        ttk.Checkbutton(
            callbook_card, text="Bei vollständigem Rufzeichen automatisch abfragen",
            variable=self.set_callbook_auto,
        ).grid(row=4, column=0, columnspan=2, sticky="w", pady=(10, 10))
        ttk.Separator(callbook_card).grid(row=5, column=0, columnspan=2, sticky="ew", pady=(2, 10))
        ttk.Label(callbook_card, text="Direkter QRZ.com-Zugang", style="CardTitle.TLabel").grid(row=6, column=0, columnspan=2, sticky="w")
        ttk.Label(
            callbook_card,
            text="QRZ.com wird bei direkter Auswahl unabhängig von Wavelog abgefragt. Benutzername und Passwort sind dann erforderlich. QRZ kann ein XML-Abonnement voraussetzen.",
            style="Muted.Card.TLabel", wraplength=480,
        ).grid(row=7, column=0, columnspan=2, sticky="w", pady=(3, 8))
        self.set_qrz_username = tk.StringVar()
        self.set_qrz_password = tk.StringVar()
        ttk.Label(callbook_card, text="QRZ.com Benutzername", style="Card.TLabel").grid(row=8, column=0, sticky="w", padx=(0, 6), pady=(3, 3))
        ttk.Label(callbook_card, text="QRZ.com Passwort", style="Card.TLabel").grid(row=8, column=1, sticky="w", padx=(6, 0), pady=(3, 3))
        ttk.Entry(callbook_card, textvariable=self.set_qrz_username).grid(row=9, column=0, sticky="ew", padx=(0, 6))
        ttk.Entry(callbook_card, textvariable=self.set_qrz_password, show="●").grid(row=9, column=1, sticky="ew", padx=(6, 0))
        ttk.Button(callbook_card, text="Callbook-Verbindung testen", style="Secondary.TButton", command=self.test_callbook).grid(row=10, column=0, columnspan=2, sticky="w", pady=(12, 7))
        self.callbook_test_label = tk.Label(callbook_card, text="", bg=CARD, fg=MUTED, font=("Segoe UI", 9), justify="left", anchor="w", wraplength=470)
        self.callbook_test_label.grid(row=11, column=0, columnspan=2, sticky="ew")

        eqsl_card = self._card(online_tab, row=0, column=1, sticky="nsew", padx=(8, 0))
        eqsl_card.columnconfigure(0, weight=1)
        ttk.Label(eqsl_card, text="eQSL.cc", style="CardTitle.TLabel").grid(row=0, column=0, sticky="w")
        coming = tk.Label(eqsl_card, text="COMING SOON", bg=WARN_BADGE_BG, fg=WARN, font=("Segoe UI Semibold", 8), padx=8, pady=3)
        coming.grid(row=0, column=1, sticky="e")
        ttk.Label(
            eqsl_card,
            text="Die Zugangsdaten können bereits profilspezifisch hinterlegt werden. Derzeit findet noch keine Verbindung, kein Download und kein Upload statt.",
            style="Muted.Card.TLabel", wraplength=450,
        ).grid(row=1, column=0, columnspan=2, sticky="w", pady=(5, 14))
        self.set_eqsl_username = tk.StringVar()
        self.set_eqsl_password = tk.StringVar()
        ttk.Label(eqsl_card, text="eQSL.cc Benutzername", style="Card.TLabel").grid(row=2, column=0, columnspan=2, sticky="w", pady=(4, 3))
        ttk.Entry(eqsl_card, textvariable=self.set_eqsl_username).grid(row=3, column=0, columnspan=2, sticky="ew")
        ttk.Label(eqsl_card, text="eQSL.cc Passwort", style="Card.TLabel").grid(row=4, column=0, columnspan=2, sticky="w", pady=(10, 3))
        ttk.Entry(eqsl_card, textvariable=self.set_eqsl_password, show="●").grid(row=5, column=0, columnspan=2, sticky="ew")
        tk.Label(
            eqsl_card, text="Coming soon – derzeit noch ohne Funktion.",
            bg=WARN_BADGE_BG, fg=WARN, font=("Segoe UI Semibold", 10),
            padx=12, pady=10, anchor="w",
        ).grid(row=6, column=0, columnspan=2, sticky="ew", pady=(16, 0))

        data_left = self._card(data_tab, row=0, column=0, sticky="nsew", padx=(0, 8))
        data_left.columnconfigure(0, weight=1)
        ttk.Label(data_left, text="Lokale Logdateien", style="CardTitle.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(
            data_left,
            text="ADI bleibt das primäre Logbuchformat. Die SQLite-Datei enthält nur Einstellungen, Sync-Metadaten und den Callbook-Cache.",
            style="Muted.Card.TLabel", wraplength=450,
        ).grid(row=1, column=0, sticky="w", pady=(3, 12))
        self.set_log_dir = tk.StringVar()
        logrow = ttk.Frame(data_left, style="Card.TFrame")
        logrow.grid(row=2, column=0, sticky="ew", pady=(6, 0))
        logrow.columnconfigure(0, weight=1)
        ttk.Entry(logrow, textvariable=self.set_log_dir).grid(row=0, column=0, sticky="ew")
        ttk.Button(logrow, text="…", width=4, command=self.choose_log_dir).grid(row=0, column=1, padx=(6, 0))
        ttk.Separator(data_left).grid(row=3, column=0, sticky="ew", pady=14)
        ttk.Label(data_left, text="xOTA-Datenquellen", style="CardTitle.TLabel").grid(row=4, column=0, sticky="w")
        ttk.Label(
            data_left,
            text="POTA, SOTA und WWFF verwenden die eingebauten Quellen. Für IOTA und COTA/WCA kann optional eine eigene CSV-URL hinterlegt werden; ohne Quelle bleibt die manuelle Eingabe verfügbar.",
            style="Muted.Card.TLabel", wraplength=450,
        ).grid(row=5, column=0, sticky="w", pady=(3, 8))
        self.set_xota_iota_url = tk.StringVar()
        self.set_xota_cota_url = tk.StringVar()
        self.set_xota_geocode_url = tk.StringVar()
        for row, label, variable in (
            (6, "IOTA CSV-URL (optional)", self.set_xota_iota_url),
            (8, "COTA/WCA CSV-URL (optional)", self.set_xota_cota_url),
            (10, "Reverse-Geocoding-URL", self.set_xota_geocode_url),
        ):
            ttk.Label(data_left, text=label, style="Card.TLabel").grid(row=row, column=0, sticky="w", pady=(5, 2))
            ttk.Entry(data_left, textvariable=variable).grid(row=row+1, column=0, sticky="ew")

        spotter = self._card(data_tab, row=0, column=1, sticky="nsew", padx=(8, 0))
        spotter.columnconfigure(0, weight=2)
        spotter.columnconfigure(1, weight=1)
        spotter.columnconfigure(2, weight=2)
        ttk.Label(spotter, text="DX-Spotter-Verbindung", style="CardTitle.TLabel").grid(
            row=0, column=0, columnspan=3, sticky="w",
        )
        ttk.Label(
            spotter,
            text=(
                "Getrennt vom reinen Empfangs-Cluster. Beim öffentlichen Spotten wird diese "
                "DXSpider-Verbindung automatisch aufgebaut. Sie benötigt Internet; ohne Verbindung "
                "wird nichts gesendet. Das Login-Rufzeichen kommt immer aus dem aktiven Stationsprofil."
            ),
            style="Muted.Card.TLabel", wraplength=1050,
        ).grid(row=1, column=0, columnspan=3, sticky="w", pady=(3, 8))
        self.dx_spotter_host_var = tk.StringVar(value=DEFAULT_SPOTTER_HOST)
        self.dx_spotter_port_var = tk.StringVar(value=str(DEFAULT_SPOTTER_PORT))
        self.dx_spotter_call_var = tk.StringVar()
        for column, (label, variable) in enumerate((
            ("DXSpider-Host zum Spotten", self.dx_spotter_host_var),
            ("Telnet-Port", self.dx_spotter_port_var),
            ("Login-Rufzeichen aus Logbuch", self.dx_spotter_call_var),
        )):
            ttk.Label(spotter, text=label, style="Card.TLabel").grid(
                row=2, column=column, sticky="w", padx=(0, 10), pady=(2, 3),
            )
            state = "readonly" if variable is self.dx_spotter_call_var else "normal"
            ttk.Entry(spotter, textvariable=variable, state=state).grid(
                row=3, column=column, sticky="ew", padx=(0, 10),
            )
        self.dx_spotter_status_label = tk.Label(
            spotter, text="Spotter-Verbindung wird erst beim Senden aufgebaut.",
            bg=CARD, fg=MUTED, font=("Segoe UI", 9), anchor="w",
        )
        self.dx_spotter_status_label.grid(row=4, column=0, columnspan=3, sticky="ew", pady=(10, 0))

        # Descriptive copy remains visible at normal size.  In compact
        # windows it yields space to the actual fields and buttons instead of
        # pushing them beyond the lower edge of the page.
        self._settings_optional_help.clear()
        def collect_optional_help(widget):
            for child in widget.winfo_children():
                collect_optional_help(child)
                if isinstance(child, ttk.Label):
                    try:
                        if child.cget("style") == "Muted.Card.TLabel":
                            self._settings_optional_help.append(child)
                    except tk.TclError:
                        pass
        collect_optional_help(notebook)
        self._settings_optional_help.append(hint)

        savebar = ttk.Frame(p)
        savebar.grid(row=1, column=0, sticky="ew", pady=(10, 0))
        ttk.Label(savebar, text="Stationsdaten sind profilspezifisch; Sprache und Theme gelten app-weit.", foreground=MUTED).pack(side="left")
        ttk.Button(savebar, text="Einstellungen speichern", style="Primary.TButton", command=self.save_settings).pack(side="right")

    def _settings_row(self, parent, label, var, row):
        ttk.Label(parent, text=label, style="Card.TLabel").grid(row=row, column=0, sticky="w", padx=(0,12), pady=4)
        ttk.Entry(parent, textvariable=var).grid(row=row, column=1, sticky="ew", pady=4)

    def _load_settings_to_ui(self):
        self.set_ui_language.set("English" if self.ui_preferences.language == "en" else "Deutsch")
        self.set_ui_theme.set("Dunkel / Dark" if self.ui_preferences.theme == "dark" else "Hell / Light")
        self.set_qso_notifications.set(self.ui_preferences.qso_notifications)
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
        self.set_auto_sync_online.set(self.db.get_setting("auto_sync_online", "0") == "1")
        self.set_full_sync_on_start.set(self.db.get_setting("full_sync_on_start", "0") == "1")
        self.set_full_sync_on_exit.set(self.db.get_setting("full_sync_on_exit", "0") == "1")
        source = self.db.get_setting("callbook_source", CALLBOOK_SOURCE_WAVELOG).strip().lower()
        self.set_callbook_source.set(callbook_source_name(source, self.language))
        self.set_callbook_auto.set(self.db.get_setting("callbook_auto_lookup", "1") == "1")
        self.set_qrz_username.set(self.db.get_setting("qrz_username", ""))
        self.set_qrz_password.set(self.db.get_secret("qrz_password"))
        self.set_eqsl_username.set(self.db.get_setting("eqsl_username", ""))
        self.set_eqsl_password.set(self.db.get_secret("eqsl_password"))
        self.set_log_dir.set(self.db.get_setting("log_dir", str(self.store.log_dir)))
        self.set_xota_iota_url.set(self.db.get_setting("xota_iota_data_url", ""))
        self.set_xota_cota_url.set(self.db.get_setting("xota_cota_wca_data_url", ""))
        self.set_xota_geocode_url.set(self.db.get_setting("xota_reverse_geocode_url", "https://nominatim.openstreetmap.org/reverse"))
        self.time_mode_var.set(self.db.get_setting("time_mode", "UTC") or "UTC")
        self.form_vars["tx_pwr"].set(self.db.get_setting("default_power", ""))
        self._update_profile_summary()
        self._set_current_qso_time()
        self._load_cat_settings_to_ui()
        self._load_dx_cluster_settings_to_ui()
        self._load_dx_spotter_settings_to_ui()
        self._load_udp_log_settings_to_ui()
        self._update_callbook_distance()

        # If Wavelog was configured before, profile labels are loaded only on explicit test.
        sid = self.db.get_setting("station_profile_id", "")
        if sid:
            logbook_id = self.db.get_setting("station_logbook_id", "")
            suffix = f" · Logbuch-ID {logbook_id}" if logbook_id else ""
            self.set_station_profile.set(f"Profil-ID {sid}{suffix}")

    def save_settings(self):
        try:
            if self.set_power.get().strip():
                float(self.set_power.get().replace(",", "."))
            old_station_call = self._active_station_callsign()
            proposed_station_call = (
                self.set_station.get().strip().upper()
                or self.set_operator.get().strip().upper()
            )
            try:
                spotter_port = int(self.dx_spotter_port_var.get().strip())
            except ValueError as exc:
                raise ValueError("Der DX-Spotter-Port muss eine ganze Zahl sein.") from exc
            spotter_config = DxSpotterConfig(
                self.dx_spotter_host_var.get().strip(),
                spotter_port,
                proposed_station_call,
            )
            if proposed_station_call:
                spotter_config.validate()
            else:
                DxClusterConfig(spotter_config.host, spotter_config.port, "N0CALL").validate()
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
            self.db.set_setting("auto_sync_online", "1" if self.set_auto_sync_online.get() else "0")
            self.db.set_setting("full_sync_on_start", "1" if self.set_full_sync_on_start.get() else "0")
            self.db.set_setting("full_sync_on_exit", "1" if self.set_full_sync_on_exit.get() else "0")
            source = CALLBOOK_SOURCE_LABELS.get(self.set_callbook_source.get(), CALLBOOK_SOURCE_WAVELOG)
            self.db.set_setting("callbook_source", source)
            self.db.set_setting("callbook_auto_lookup", "1" if self.set_callbook_auto.get() else "0")
            self.db.set_setting("qrz_username", self.set_qrz_username.get().strip())
            self.db.set_secret("qrz_password", self.set_qrz_password.get())
            self.db.set_setting("eqsl_username", self.set_eqsl_username.get().strip())
            self.db.set_secret("eqsl_password", self.set_eqsl_password.get())
            self.db.set_setting("log_dir", self.set_log_dir.get().strip())
            self.db.set_setting("xota_iota_data_url", self.set_xota_iota_url.get().strip())
            self.db.set_setting("xota_cota_wca_data_url", self.set_xota_cota_url.get().strip())
            self.db.set_setting("xota_reverse_geocode_url", self.set_xota_geocode_url.get().strip())
            new_ui_preferences = UiPreferences(
                language="en" if self.set_ui_language.get() == "English" else "de",
                theme="dark" if self.set_ui_theme.get() == "Dunkel / Dark" else "light",
                qso_notifications=self.set_qso_notifications.get(),
                last_whats_new_version=self.ui_preferences.last_whats_new_version,
            )
            restart_required = (
                new_ui_preferences.language != self.ui_preferences.language
                or new_ui_preferences.theme != self.ui_preferences.theme
            )
            save_ui_preferences(self.data_dir, new_ui_preferences)
            # Notification changes take effect immediately. Language and theme
            # still use the existing controlled restart path.
            self.ui_preferences = new_ui_preferences
            self._store_dx_spotter_config(spotter_config)
            selected = self.station_by_label.get(self.set_station_profile.get())
            if selected:
                self.db.set_setting("station_profile_id", selected.get("id"))
                logbook_id, logbook_name = self._station_logbook_details(selected)
                self.db.set_setting("station_logbook_id", logbook_id)
                self.db.set_setting("station_logbook_name", logbook_name)
            # Keep an existing numeric profile id if the list wasn't loaded in this session.
            self.store.set_dir(Path(self.set_log_dir.get().strip() or self._profile_default_log_dir()))
            self.xota_references = ActivationReferenceService(self.xota_repository, self.db.get_setting)
            self.xota_geocoder = ReverseGeocodeService(self.xota_repository, self.db.get_setting("xota_reverse_geocode_url", ""))
            self.form_vars["tx_pwr"].set(self.db.get_setting("default_power", ""))
            self._update_profile_summary()
            self._update_callbook_distance()
            self._update_logfile_preview()
            self.dx_cluster_call_var.set(self._active_station_callsign())
            self.dx_spotter_call_var.set(self._active_station_callsign())
            if self._active_station_callsign() != old_station_call:
                self._stop_dx_cluster_runtime(update_ui=True)
                self._stop_dx_spotter_runtime(update_ui=True)
            elif self.dx_spotter_active_config != spotter_config:
                self._stop_dx_spotter_runtime(update_ui=True)
            self.refresh_fast_log_page()
            self.qrz_client = None
            self.qrz_client_credentials = None
            if self.call_var.get().strip():
                self._schedule_callbook_lookup(self.call_var.get().strip().upper(), force=True)
            self._reset_wavelog_monitor(delay_ms=300)
            self.status_var.set("Einstellungen gespeichert")
            message = "Einstellungen wurden gespeichert."
            if restart_required:
                message += "\n\nSprache oder Theme werden nach dem nächsten Programmstart aktiv."
            messagebox.showinfo("Einstellungen", message, parent=self)
        except Exception as e:
            messagebox.showerror("Einstellungen", str(e), parent=self)

    def choose_log_dir(self):
        p = filedialog.askdirectory(initialdir=self.set_log_dir.get() or str(self._profile_default_log_dir()), parent=self)
        if p:
            self.set_log_dir.set(p)

    def test_callbook(self):
        call = (self.set_station.get().strip() or self.set_operator.get().strip()).upper()
        if not lookup_candidate(call):
            self.callbook_test_label.configure(text="Bitte zuerst ein gültiges Operator- oder Stationsrufzeichen eintragen.", fg=WARN)
            return
        selected = CALLBOOK_SOURCE_LABELS.get(self.set_callbook_source.get(), CALLBOOK_SOURCE_WAVELOG)
        qrz_user = self.set_qrz_username.get().strip()
        qrz_password = self.set_qrz_password.get()
        source = selected
        if source == CALLBOOK_SOURCE_DISABLED:
            self.callbook_test_label.configure(text="Callbook-Abfrage ist deaktiviert.", fg=MUTED)
            return
        self.callbook_test_label.configure(text="Verbindung wird geprüft …", fg=MUTED)
        url = self.set_url.get().strip()
        token = self.set_token.get().strip()

        def worker():
            try:
                if source == CALLBOOK_SOURCE_QRZ:
                    result = QrzClient(qrz_user, qrz_password, timeout=8).lookup(call)
                else:
                    payload = WavelogClient(url, token, timeout=8).lookup_callsign(call, include_callbook=True)
                    result = normalize_wavelog_result(payload, call)
                if not any((result.name, result.qth, result.grid, result.country, result.image_url)):
                    raise CallbookError("Keine Callbook-Daten gefunden")
                summary = " · ".join(part for part in (result.callsign, result.name, result.grid, result.qth) if part)
                if not self.closing:
                    self.after(0, lambda text=summary: self.callbook_test_label.configure(text="✓ " + text, fg=OK))
            except Exception as exc:
                if not self.closing:
                    error_message = str(exc)
                    self.after(0, lambda message=error_message: self.callbook_test_label.configure(text="✕ " + message, fg=ERR))

        threading.Thread(target=worker, name="callbook-test", daemon=True).start()

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
                    error_message = str(e)
                    self.after(0, lambda message=error_message: self._wavelog_test_fail(message))
        threading.Thread(target=worker, name="wavelog-test", daemon=True).start()

    @staticmethod
    def _station_logbook_details(station: dict) -> tuple[str, str]:
        nested = station.get("logbook")
        nested = nested if isinstance(nested, dict) else {}
        logbook_id = next((
            station.get(key) for key in ("station_logbook_id", "logbook_id")
            if station.get(key) not in (None, "")
        ), nested.get("id", ""))
        logbook_name = next((
            station.get(key) for key in ("station_logbook_name", "logbook_name")
            if station.get(key) not in (None, "")
        ), nested.get("name", ""))
        return str(logbook_id or ""), str(logbook_name or "")

    def _wavelog_test_ok(self, info: dict, stations: list[dict]):
        owner = str(info.get("owner") or "")
        scopes = ", ".join(info.get("scopes") or [])
        scope_list = info.get("scopes") or []
        qsl_hint = "" if "confirmation:read" in scope_list else "\n⚠ confirmation:read fehlt – Bestätigungen (✓) sind nicht verfügbar."
        lookup_hint = "" if "lookup:read" in scope_list else "\n⚠ lookup:read fehlt – Rufzeichen-/Callbook-Daten über Wavelog sind nicht verfügbar."
        club_hint = ""
        station_call = self.set_station.get().strip().upper()
        if station_call and owner.upper() == station_call and "club:read" not in scope_list:
            club_hint = "\nℹ Clubstation: Für sicheren clubweiten Operator-Abgleich einen Officer-Token mit club:read verwenden."
        warn = bool(qsl_hint or lookup_hint)
        self.connection_label.configure(text=f"✓ Token gültig · Owner: {owner or '—'}\nScopes: {scopes or '—'}{qsl_hint}{lookup_hint}{club_hint}", fg=WARN if warn else OK)
        if not self.set_operator.get().strip() and owner:
            self.set_operator.set(owner.upper())
        self.station_rows = stations
        self.station_by_label.clear()
        labels = []
        chosen = None
        saved_id = self.db.get_setting("station_profile_id", "")
        for s in stations:
            logbook_id, logbook_name = self._station_logbook_details(s)
            logbook = ""
            if logbook_name or logbook_id:
                logbook = f" · Logbuch {logbook_name or logbook_id}"
                if logbook_name and logbook_id:
                    logbook += f" [ID {logbook_id}]"
            label = f"{s.get('name') or 'Station'} · {s.get('callsign') or '?'} · {s.get('gridsquare') or '—'}{logbook} [Profil-ID {s.get('id')}]"
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
    def _begin_close_sequence(self):
        if self.closing:
            return
        if not self.close_services_stopped:
            self.close_services_stopped = True
            # Freeze external input before the final sync so UDP cannot append
            # another QSO while the completion dialog is waiting for OK.
            self._stop_cat_runtime(update_ui=False)
            self._stop_dx_cluster_runtime(update_ui=False)
            self._stop_dx_spotter_runtime(update_ui=False)
            self._stop_udp_log_runtime(update_ui=False)
        if self.sync_busy:
            self.status_var.set("Beenden wartet auf die laufende Wavelog-Übertragung …")
            self._show_sync_progress("shutdown", "Beenden wartet auf die laufende Wavelog-Übertragung …")
            return
        settings = self._wavelog_online_settings()
        if settings.full_sync_on_exit and settings.configured and self.wavelog_online:
            self.startup_full_sync_pending = False
            self.status_var.set("Vollständiger Abschluss-Sync läuft …")
            self._start_sync(automatic=True, reason="shutdown")
            return
        self._finalize_close()

    def _finalize_close(self):
        self.shutdown()
        try:
            self.destroy()
        except tk.TclError:
            pass

    def shutdown(self):
        if self.shutdown_started:
            return
        self.shutdown_started = True
        self.closing = True
        self.wavelog_check_generation += 1
        for job_name in ("wavelog_check_job", "auto_sync_job"):
            job = getattr(self, job_name, None)
            if job is not None:
                try:
                    self.after_cancel(job)
                except Exception:
                    pass
                setattr(self, job_name, None)
        try:
            write_startup_log("Programm wird geschlossen")
            self._stop_cat_runtime(update_ui=False)
            self._stop_dx_cluster_runtime(update_ui=False)
            self._stop_dx_spotter_runtime(update_ui=False)
            self._stop_udp_log_runtime(update_ui=False)
            # Every database operation is committed immediately.
            if not self.sync_busy:
                self.db.close()
        except Exception as e:
            write_startup_log("Fehler beim Shutdown: " + repr(e))

    def on_close(self):
        if self.close_requested:
            return
        if self.hamlib_update_busy:
            messagebox.showinfo(
                "Hamlib-Update" if self.language != "en" else "Hamlib update",
                ("Bitte warte, bis das Hamlib-Update abgeschlossen ist."
                 if self.language != "en" else
                 "Please wait until the Hamlib update has finished."),
                parent=self,
            )
            return
        self.close_requested = True
        self._begin_close_sequence()




class ContestPresetDialog(tk.Toplevel):
    def __init__(self, app: LoggerApp, preset: dict | None, callback):
        super().__init__(app)
        self.app=app; self.callback=callback; self.old_name=(preset or {}).get("name")
        self.title("Contest-Preset")
        configure_responsive_dialog(self, (720, 540), (500, 420)); self.transient(app); self.grab_set(); self.configure(bg=BG)
        box=tk.Frame(self,bg=CARD,highlightbackground=BORDER,highlightthickness=1); box.pack(fill="both",expand=True,padx=18,pady=18)
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
        self.help_label=tk.Label(form,text=help_text,bg=CARD,fg=(WARN if api_status and api_status != "ok" else MUTED),font=("Segoe UI",9),justify="left",anchor="w",wraplength=620)
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
        self.configure(bg=BG)
        self.transient(parent)
        self.grab_set()
        self.protocol("WM_DELETE_WINDOW", self._cancel)

        outer = ttk.Frame(self, padding=22)
        outer.pack(fill="both", expand=True)
        ttk.Label(outer, text="Profil lokal löschen", style="Title.TLabel").pack(anchor="w")
        tk.Label(outer, text=f"Profil: {profile_name}", bg=BG, fg=TEXT, font=("Segoe UI Semibold", 11)).pack(anchor="w", pady=(12, 5))
        tk.Label(outer, text="Gelöscht werden die lokalen Einstellungen und Sync-Metadaten dieses Logger-Profils.", bg=BG, fg=TEXT, font=("Segoe UI", 10), wraplength=500, justify="left").pack(anchor="w")

        warning = tk.Frame(outer, bg=WARN_BADGE_BG, highlightbackground=WARN, highlightthickness=1)
        warning.pack(fill="x", pady=14)
        tk.Label(warning, text="Wavelog wird NICHT verändert. Es werden weder QSOs noch Stationsprofile in Wavelog gelöscht.", bg=WARN_BADGE_BG, fg=WARN, font=("Segoe UI Semibold", 9), wraplength=475, justify="left", padx=12, pady=10).pack(anchor="w")

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
        configure_responsive_dialog(self, (650, 430), (500, 350))
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
        configure_responsive_dialog(self, (760, 520), (520, 420))
        self.transient(parent)
        self.grab_set()
        self.configure(bg=BG)
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
        self.notes = tk.Text(frame, height=4, wrap="word", font=("Segoe UI", 9), bg=INPUT_BG, fg=TEXT, insertbackground=TEXT)
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
