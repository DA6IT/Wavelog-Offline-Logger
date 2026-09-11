from __future__ import annotations

import threading
import tkinter as tk
from tkinter import messagebox, ttk

from logger_core import VERSION
from ui_theme import theme
from usage_stats import UsageStatsError, UsageStatsService


class UsageStatsFeatureMixin:
    def _init_usage_stats_feature(self) -> None:
        self.usage_stats = UsageStatsService(self.data_dir)
        self.usage_stats_retry_job = None
        self.usage_stats_notice_dialog: tk.Toplevel | None = None

    def _show_startup_notices(self) -> None:
        if self.closing:
            return
        if self.usage_stats.notice_seen:
            self._start_usage_stats_heartbeat()
            self._show_whats_new_if_needed()
            return
        self._show_usage_stats_notice()

    def _show_usage_stats_notice(self) -> None:
        if self.closing or self.usage_stats_notice_dialog is not None:
            return

        dialog = tk.Toplevel(self)
        self.usage_stats_notice_dialog = dialog
        dialog.title(
            "Hilf uns, den Offline Logger besser zu machen"
            if self.language != "en"
            else "Help us improve the Offline Logger"
        )
        dialog.transient(self)
        dialog.configure(bg=theme.BG)
        dialog.resizable(True, True)
        dialog.minsize(560, 470)

        body = ttk.Frame(dialog, padding=24)
        body.pack(fill="both", expand=True)

        title = (
            "Hilf uns, den Offline Logger besser zu machen"
            if self.language != "en"
            else "Help us improve the Offline Logger"
        )
        ttk.Label(body, text=title, style="PageTitle.TLabel").pack(anchor="w")

        if self.language == "en":
            text = (
                "We would like to know whether the Wavelog Offline Logger is actually being used "
                "and which versions are still active.\n\n"
                "For this purpose the app sends, at most once per day, a randomly generated "
                "installation ID, the app version and the operating system to DA6IT.de. The "
                "random ID stays stable on this installation so we can distinguish a regularly "
                "used installation from a one-time start.\n\n"
                "No callsigns. No QSOs. No logbook data. No Wavelog addresses. No credentials.\n\n"
                "We do not know who you are, who you contact or what you do with the app. "
                "We only see that someone is using this hopefully great app. 😊\n\n"
                "This helps us improve stability, identify outdated versions and plan further "
                "development. You can view your installation ID at any time in Settings, disable "
                "the statistics there or delete the statistics stored for this ID."
            )
            keep_text = "Continue & keep statistics enabled"
            disable_text = "Disable usage statistics"
        else:
            text = (
                "Wir würden gerne wissen, ob der Wavelog Offline Logger tatsächlich genutzt wird "
                "und welche Versionen noch im Einsatz sind.\n\n"
                "Dafür sendet die App höchstens einmal pro Tag eine zufällig erzeugte "
                "Installations-ID, die App-Version und das verwendete Betriebssystem an DA6IT.de. "
                "Die zufällige ID bleibt auf dieser Installation stabil, damit wir erkennen "
                "können, ob eine Installation regelmäßig genutzt wird oder nur einmal gestartet wurde.\n\n"
                "Keine Rufzeichen. Keine QSOs. Keine Logbuchdaten. Keine Wavelog-Adressen. "
                "Keine Zugangsdaten.\n\n"
                "Wir wissen dadurch nicht, wer du bist, mit wem du funkst oder was du mit der App "
                "machst. Wir sehen nur, dass jemand diese hoffentlich tolle App nutzt. 😊\n\n"
                "Damit hilfst du uns, die Stabilität zu verbessern, veraltete Versionen zu erkennen "
                "und die Weiterentwicklung sinnvoll zu planen. Die Installations-ID kannst du "
                "jederzeit in den Einstellungen ansehen. Dort kannst du die Statistik abschalten "
                "oder die zu dieser ID gespeicherten Statistikdaten löschen lassen."
            )
            keep_text = "Weiter & Statistik aktiviert lassen"
            disable_text = "Statistik deaktivieren"

        ttk.Label(
            body,
            text=text,
            wraplength=650,
            justify="left",
        ).pack(anchor="w", fill="x", pady=(16, 18))

        actions = ttk.Frame(body)
        actions.pack(side="bottom", fill="x", pady=(10, 0))
        ttk.Button(
            actions,
            text=disable_text,
            command=lambda: self._finish_usage_stats_notice(dialog, False),
        ).pack(side="left")
        ttk.Button(
            actions,
            text=keep_text,
            style="Primary.TButton",
            command=lambda: self._finish_usage_stats_notice(dialog, True),
        ).pack(side="right")

        dialog.protocol("WM_DELETE_WINDOW", lambda: self._dismiss_usage_stats_notice(dialog))
        dialog.update_idletasks()
        width = min(720, max(560, self.winfo_screenwidth() - 120))
        height = min(610, max(470, self.winfo_screenheight() - 140))
        x = max(0, self.winfo_rootx() + (self.winfo_width() - width) // 2)
        y = max(0, self.winfo_rooty() + (self.winfo_height() - height) // 2)
        dialog.geometry(f"{width}x{height}+{x}+{y}")
        dialog.grab_set()
        dialog.focus_force()

    def _dismiss_usage_stats_notice(self, dialog: tk.Toplevel) -> None:
        self._close_usage_stats_notice(dialog)
        if not self.closing:
            self.after(250, self._show_whats_new_if_needed)

    def _finish_usage_stats_notice(self, dialog: tk.Toplevel, enabled: bool) -> None:
        self.usage_stats.mark_notice_seen(enabled=enabled)
        self._refresh_usage_stats_settings_ui()
        self._close_usage_stats_notice(dialog)
        if enabled:
            self._start_usage_stats_heartbeat()
        if not self.closing:
            self.after(250, self._show_whats_new_if_needed)

    def _close_usage_stats_notice(self, dialog: tk.Toplevel) -> None:
        if self.usage_stats_notice_dialog is dialog:
            self.usage_stats_notice_dialog = None
        try:
            dialog.grab_release()
        except tk.TclError:
            pass
        try:
            dialog.destroy()
        except tk.TclError:
            pass

    def _start_usage_stats_heartbeat(self, attempt: int = 0) -> None:
        if self.closing or not self.usage_stats.should_send_today():
            return

        def worker():
            try:
                self.usage_stats.send_heartbeat(VERSION)
            except UsageStatsError:
                if self.closing:
                    return
                delay = 15 * 60 * 1000 if attempt == 0 else 60 * 60 * 1000
                if attempt < 2:
                    self.after(
                        0,
                        lambda: self._schedule_usage_stats_retry(delay, attempt + 1),
                    )

        threading.Thread(
            target=worker,
            name="usage-stats-heartbeat",
            daemon=True,
        ).start()

    def _schedule_usage_stats_retry(self, delay_ms: int, attempt: int) -> None:
        if self.closing or not self.usage_stats.enabled:
            return
        if self.usage_stats_retry_job is not None:
            try:
                self.after_cancel(self.usage_stats_retry_job)
            except Exception:
                pass
        self.usage_stats_retry_job = self.after(
            delay_ms,
            lambda: self._usage_stats_retry_fire(attempt),
        )

    def _usage_stats_retry_fire(self, attempt: int) -> None:
        self.usage_stats_retry_job = None
        self._start_usage_stats_heartbeat(attempt)

    def _save_usage_stats_enabled(self, enabled: bool) -> None:
        self.usage_stats.set_enabled(bool(enabled))
        if not enabled and self.usage_stats_retry_job is not None:
            try:
                self.after_cancel(self.usage_stats_retry_job)
            except Exception:
                pass
            self.usage_stats_retry_job = None
        elif enabled and self.usage_stats.notice_seen:
            self._start_usage_stats_heartbeat()
        self._refresh_usage_stats_settings_ui()

    def _refresh_usage_stats_settings_ui(self) -> None:
        if hasattr(self, "set_usage_stats"):
            self.set_usage_stats.set(self.usage_stats.enabled)
        if hasattr(self, "usage_stats_id_var"):
            self.usage_stats_id_var.set(self.usage_stats.installation_id)

    def _copy_usage_stats_installation_id(self) -> None:
        installation_id = self.usage_stats.installation_id
        self.clipboard_clear()
        self.clipboard_append(installation_id)
        self.status_var.set(
            "Installations-ID kopiert"
            if self.language != "en"
            else "Installation ID copied"
        )

    def _delete_usage_stats_from_settings(self) -> None:
        installation_id = self.usage_stats.installation_id
        if self.language == "en":
            title = "Delete usage statistics"
            question = (
                "Delete all usage-statistics data stored on DA6IT.de for this installation?\n\n"
                "Your local logbooks and settings are not affected. After deletion this app "
                "receives a new random installation ID. If statistics remain enabled, collection "
                "starts again under the new ID on a later day."
            )
        else:
            title = "Nutzungsstatistik löschen"
            question = (
                "Alle auf DA6IT.de gespeicherten Nutzungsstatistiken für diese Installation löschen?\n\n"
                "Deine lokalen Logbücher und Einstellungen sind davon nicht betroffen. Nach dem "
                "Löschen erhält diese App eine neue zufällige Installations-ID. Bleibt die Statistik "
                "aktiviert, beginnt sie an einem späteren Tag unter der neuen ID wieder bei null."
            )
        if not messagebox.askyesno(title, question, parent=self):
            return

        self.status_var.set(
            "Statistikdaten werden gelöscht …"
            if self.language != "en"
            else "Deleting statistics data …"
        )

        def worker():
            try:
                new_id = self.usage_stats.forget_remote_data(VERSION)
            except UsageStatsError as exc:
                message = str(exc)
                if not self.closing:
                    self.after(
                        0,
                        lambda: messagebox.showerror(title, message, parent=self),
                    )
                return
            if not self.closing:
                self.after(0, lambda: self._usage_stats_deleted(new_id))

        threading.Thread(
            target=worker,
            name="usage-stats-forget",
            daemon=True,
        ).start()

    def _usage_stats_deleted(self, new_id: str) -> None:
        self._refresh_usage_stats_settings_ui()
        self.status_var.set(
            "Statistikdaten gelöscht · neue Installations-ID erstellt"
            if self.language != "en"
            else "Statistics data deleted · new installation ID created"
        )
        messagebox.showinfo(
            "Nutzungsstatistik" if self.language != "en" else "Usage statistics",
            (
                "Die gespeicherten Statistikdaten wurden gelöscht.\n\n"
                f"Neue Installations-ID:\n{new_id}"
                if self.language != "en"
                else
                "The stored statistics data has been deleted.\n\n"
                f"New installation ID:\n{new_id}"
            ),
            parent=self,
        )
