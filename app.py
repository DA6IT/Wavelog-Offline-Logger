from __future__ import annotations

import traceback
import tkinter as tk
from tkinter import messagebox

from app_common import (
    BASE_UI_HEIGHT,
    BASE_UI_WIDTH,
    MIN_UI_HEIGHT,
    MIN_UI_WIDTH,
    write_startup_log,
)
from feature_backup import BackupFeatureMixin
from feature_cat import CatFeatureMixin
from feature_contest import ContestFeatureMixin
from feature_dxcluster import DxClusterFeatureMixin
from feature_fastlog import FastLogFeatureMixin
from feature_lifecycle import LifecycleFeatureMixin
from feature_logbook import LogbookFeatureMixin
from feature_profiles import ProfilesFeatureMixin
from feature_rotor import RotorFeatureMixin
from feature_qso_sync import QsoSyncFeatureMixin
from feature_qsl import QslFeatureMixin
from feature_settings import SettingsFeatureMixin
from feature_stats import StatsFeatureMixin
from feature_udp import UdpFeatureMixin
from feature_ui_shell import UiShellFeatureMixin
from feature_update import UpdateFeatureMixin
from feature_usage import UsageStatsFeatureMixin
from feature_wavelog_online import WavelogOnlineFeatureMixin
from feature_xota import XotaFeatureMixin
from logger_core import APP_NAME, VERSION, app_data_dir
from ui_preferences import load_ui_preferences
from ui_theme import set_theme, theme


class LoggerApp(
    UiShellFeatureMixin,
    UpdateFeatureMixin,
    UsageStatsFeatureMixin,
    WavelogOnlineFeatureMixin,
    ProfilesFeatureMixin,
    LifecycleFeatureMixin,
    LogbookFeatureMixin,
    FastLogFeatureMixin,
    ContestFeatureMixin,
    XotaFeatureMixin,
    QsoSyncFeatureMixin,
    QslFeatureMixin,
    StatsFeatureMixin,
    CatFeatureMixin,
    RotorFeatureMixin,
    DxClusterFeatureMixin,
    UdpFeatureMixin,
    BackupFeatureMixin,
    SettingsFeatureMixin,
    tk.Tk,
):
    """Compose the desktop application from independent feature mixins."""

    def __init__(self) -> None:
        super().__init__()

        # Shared application context.
        self._vars: dict[str, tk.StringVar] = {}
        self.data_dir = app_data_dir()
        self.ui_preferences = load_ui_preferences(self.data_dir)
        self.language = self.ui_preferences.language
        set_theme(self.ui_preferences.theme)

        # Each feature owns and initializes its own runtime state.
        self._initialize_features()

        # Build the complete interface while hidden. It is presented only
        # after every page has its final geometry.
        self.withdraw()
        self.title(f"{APP_NAME} {VERSION}")
        screen_width = max(MIN_UI_WIDTH, self.winfo_screenwidth() - 80)
        screen_height = max(MIN_UI_HEIGHT, self.winfo_screenheight() - 110)
        initial_width = min(BASE_UI_WIDTH, screen_width)
        initial_height = min(BASE_UI_HEIGHT, screen_height)
        self.geometry(f"{initial_width}x{initial_height}")
        self.minsize(MIN_UI_WIDTH, MIN_UI_HEIGHT)
        self.configure(bg=theme.BG)
        self.protocol("WM_DELETE_WINDOW", self.on_close)

        self._build_interface()
        self._schedule_startup_tasks()
        write_startup_log(f"{APP_NAME} {VERSION} gestartet")

    def _initialize_features(self) -> None:
        """Initialize feature-owned state before any widgets are built."""
        self._init_ui_shell_feature()
        self._init_lifecycle_feature()
        self._init_usage_stats_feature()
        self._init_qso_sync_feature()
        self._init_qsl_feature()
        self._init_wavelog_online_feature()
        self._init_settings_feature()
        self._init_cat_feature()
        self._init_rotor_feature()
        self._init_udp_feature()
        self._init_dxcluster_feature()
        self._init_fastlog_feature()
        self._init_stats_feature()
        self._init_logbook_feature()
        self._init_update_feature()

        # Profiles are initialized last because opening a profile creates the
        # per-profile database, LogStore and xOTA services used by other pages.
        self._init_profiles_feature()

    def _build_interface(self) -> None:
        self._setup_style()
        self._build_shell()
        self._build_log_page()
        self._build_fast_log_page()
        self._build_contest_page()
        self._build_xota_page()
        self._build_qsos_page()
        self._build_qsl_page()
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
        self._show_page("log")
        self._tick_clock()

    def _schedule_startup_tasks(self) -> None:
        self.after(90, self._present_main_window)
        # Prime the QSO/cache index after the window is already responsive.
        # The expensive ADIF/SQLite work itself runs in a worker thread.
        self.after(180, lambda: self.refresh_qsos(force=True))
        self.after(350, self._show_adif_migration_report)
        self.after(600, self._autostart_udp_log)
        self.after(700, self._localization_tick)
        self.after(950, self._show_startup_notices)
        self.after(1300, self._maybe_startup_wsjtx_sync)
        self.after(1800, self._start_update_check)
        self.after(2500, self._start_wavelog_monitor)
        self.after(
            3200,
            lambda: self._schedule_qsl_background_sync(
                0,
                reason="startup",
            ),
        )


def main() -> None:
    app: LoggerApp | None = None
    try:
        app = LoggerApp()
        try:
            app.mainloop()
        finally:
            app.shutdown()
    except Exception:
        error = traceback.format_exc()
        write_startup_log("FATAL:\n" + error)
        try:
            root = tk.Tk()
            root.withdraw()
            messagebox.showerror(
                "DA6IT.de Logger – Startfehler",
                "Die Anwendung konnte nicht gestartet werden.\n\n"
                "Details stehen in:\n"
                + str(app_data_dir() / "startup.log"),
            )
            root.destroy()
        except Exception:
            pass
        raise


if __name__ == "__main__":
    main()
