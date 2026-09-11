from __future__ import annotations

import threading
from datetime import datetime
from app_common import write_startup_log
from logger_core import ContestSyncEngine, SyncEngine, WavelogClient, WavelogOnlineSettings
from ui_theme import theme


class WavelogOnlineFeatureMixin:
    def _init_wavelog_online_feature(self) -> None:
        self.wavelog_online = False
        self.wavelog_check_generation = 0
        self.wavelog_check_busy = False
        self.wavelog_check_job = None
        self.auto_sync_job = None

    def _wavelog_online_settings(self) -> WavelogOnlineSettings:
        return WavelogOnlineSettings.from_storage(self.db.get_setting, self.db.get_token)

    def _set_wavelog_mode_ui(self, online: bool, *, configured: bool = True):
        self.wavelog_online = bool(online)
        settings = self._wavelog_online_settings()
        if online:
            mode_text = "●  WAVELOG ONLINE"
            mode_color = theme.OK
            hint = "Verbunden · neuer QSO-Push aktiv" if settings.auto_sync else "Verbunden · manueller Sync"
        else:
            mode_text = "●  LOCAL ONLY"
            mode_color = theme.ACCENT
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
                self._request_auto_sync()
            self._schedule_wavelog_check(60_000)
        else:
            self.startup_full_sync_pending = False
            if was_online:
                self.status_var.set("Wavelog nicht erreichbar · LOCAL ONLY")
            if error:
                write_startup_log("Wavelog-Erreichbarkeitsprüfung: " + error)
            self._schedule_wavelog_check(15_000)

    def _request_auto_sync(self, *, delay_ms: int | None = None):
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
        # Batch semantics: the first new QSO starts the timer. Further QSOs
        # join the same batch instead of postponing the upload indefinitely.
        if self.auto_sync_job is not None:
            return
        if delay_ms is None:
            delay_ms = settings.auto_sync_delay_seconds * 1000
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
            self._request_auto_sync()

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
            # Start a fresh configured batch window for those newer records.
            self._request_auto_sync()

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
