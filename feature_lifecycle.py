from __future__ import annotations

import tkinter as tk
from tkinter import messagebox
from app_common import write_startup_log
from wsjtx_sync import load_wsjtx_settings, should_wsjtx_sync_for_reason


class LifecycleFeatureMixin:
    def _init_lifecycle_feature(self) -> None:
        self.closing = False
        self.shutdown_started = False
        self.close_requested = False
        self.close_services_stopped = False

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
            if self.sync_operation == "wsjtx":
                self.status_var.set("Beenden wartet auf den laufenden WSJT-X-Abgleich …")
            else:
                self.status_var.set("Beenden wartet auf die laufende Wavelog-Übertragung …")
                self._show_sync_progress(
                    "shutdown",
                    "Beenden wartet auf die laufende Wavelog-Übertragung …",
                )
            return
        settings = self._wavelog_online_settings()
        if settings.full_sync_on_exit and settings.configured and self.wavelog_online:
            self.startup_full_sync_pending = False
            self.status_var.set("Vollständiger Abschluss-Sync läuft …")
            self._start_sync(automatic=True, reason="shutdown")
            return

        try:
            wsjtx_settings = load_wsjtx_settings(self.db)
        except Exception as exc:
            write_startup_log("WSJT-X Shutdown-Sync Einstellungen: " + repr(exc))
            wsjtx_settings = None

        if (
            wsjtx_settings is not None
            and wsjtx_settings.log_path is not None
            and should_wsjtx_sync_for_reason(wsjtx_settings, "shutdown")
        ):
            self._start_wsjtx_only_sync(reason="shutdown")
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
