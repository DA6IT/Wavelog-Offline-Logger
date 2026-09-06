from __future__ import annotations

from datetime import datetime
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from data_backup import create_backup, inspect_backup, restore_backup
from logger_core import VERSION
from ui_theme import theme


class BackupFeatureMixin:
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
        self.backup_status_label.configure(text="Backup wird erstellt …", foreground=theme.MUTED)
        self.update_idletasks()
        try:
            result = create_backup(self.data_dir, Path(destination), app_version=VERSION)
        except Exception as exc:
            self.backup_status_label.configure(text="Backup fehlgeschlagen", foreground=theme.ERR)
            messagebox.showerror("Backup fehlgeschlagen", str(exc), parent=self)
            return
        self.backup_status_label.configure(
            text=f"Backup erstellt · {result['profiles']} Profil(e) · {result['adi_files']} ADI-Datei(en)",
            foreground=theme.OK,
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
