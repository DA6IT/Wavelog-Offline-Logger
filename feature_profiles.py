from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from tkinter import messagebox, simpledialog
from dialogs import ProfileDeleteDialog, ProfileManagerDialog
from logger_core import LogStore, MetadataDB, ProfileManager
from xota import ActivationReferenceService, ReverseGeocodeService, XotaRepository


class ProfilesFeatureMixin:
    def _init_profiles_feature(self) -> None:
        self.profile_manager = ProfileManager(self.data_dir)
        self.active_profile_id = self.profile_manager.active_id
        self.db = None
        self.store = None
        self.pending_adif_migration_report = None
        self._open_profile_storage(self.active_profile_id)

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
        if (
            self.sync_busy
            or getattr(self, "qsl_sync_busy", False)
            or getattr(self, "qsl_mail_busy", False)
            or getattr(self, "qsl_background_busy", False)
        ):
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
            self._cancel_qsl_background_sync()
            self._stop_cat_runtime(update_ui=False)
            self._stop_rotor_runtime(update_ui=False)
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
            self.refresh_qsl_page()
            self.refresh_stats()
            self._refresh_profile_selector()
            self._reset_wavelog_monitor(delay_ms=500)
            self.status_var.set(f"Profil gewechselt: {old} → {self._current_profile()['name']}")
            # The previous profile's listener was stopped before its database
            # was closed. Start the newly selected profile with its own saved
            # host, port and autostart preference once the UI is idle again.
            self.after_idle(self._autostart_udp_log)
            self._schedule_qsl_background_sync(
                500,
                reason="profile",
            )
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
