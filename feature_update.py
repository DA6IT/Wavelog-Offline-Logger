from __future__ import annotations

import os
import threading
import webbrowser
from datetime import datetime
import tkinter as tk
from tkinter import messagebox, ttk
from logger_core import VERSION
from ui_preferences import UiPreferences, save_ui_preferences
from update_check import (
    current_windows_launcher, download_verified_asset, find_newer_release, select_update_asset, windows_update_helper_script,
)
from whats_new import notes_for_version
from ui_theme import theme


class UpdateFeatureMixin:
    def _init_update_feature(self) -> None:
        self.update_busy = False
        self.update_progress_dialog: tk.Toplevel | None = None

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
        dialog.configure(bg=theme.BG)
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
        update_log = updates_dir / "update.log"
        pending = updates_dir / "pending-update.txt"
        pending_tmp = updates_dir / "pending-update.txt.tmp"

        probe = launcher.parent / f".wavelog-update-write-test-{os.getpid()}.tmp"
        try:
            probe.write_bytes(b"write-test")
        finally:
            probe.unlink(missing_ok=True)

        package_full = package.resolve()
        if not package_full.is_file() or package_full.stat().st_size <= 0:
            raise RuntimeError("Das heruntergeladene Update-Paket fehlt.")

        helper.write_text(windows_update_helper_script(), encoding="utf-8-sig")

        with update_log.open("a", encoding="utf-8") as log_file:
            log_file.write(
                datetime.now().astimezone().isoformat()
                + " Python prepared updater hand-off"
                + " | LauncherPID="
                + str(launcher_pid)
                + " | Target="
                + str(launcher)
                + " | Package="
                + str(package_full)
                + "\n"
            )

        pending_tmp.write_text(str(package_full), encoding="utf-8")
        pending_tmp.replace(pending)
