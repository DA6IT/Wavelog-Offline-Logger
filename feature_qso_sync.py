from __future__ import annotations

import os
import shutil
import subprocess
import sys
import threading
from datetime import datetime
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from app_common import write_startup_log
from dialogs import EditDialog, SyncProgressDialog
from dx_cluster import normalize_worked_mode
from logger_core import ContestSyncEngine, SyncEngine, WavelogClient, qso_hash
from qsl_storage import QslStorage
from wsjtx_sync import format_wsjtx_result, load_wsjtx_settings, should_wsjtx_sync_for_reason, sync_wsjtx_with_local
from ui_theme import theme


class QsoSyncFeatureMixin:
    def _init_qso_sync_feature(self) -> None:
        self.sync_busy = False
        self.sync_is_automatic = False
        self.sync_operation = ""
        self.sync_reason = ""
        self.sync_progress_dialog: SyncProgressDialog | None = None
        self.startup_full_sync_pending = True
        self.external_enrichment_pending: set[tuple[str, str]] = set()
        self.last_spottable_qso: dict | None = None

        # Logbook view/cache state. ADIF parsing and metadata collection are
        # intentionally kept off the Tk main thread so navigation stays fluid.
        self._qso_view_dirty = True
        self._qso_view_loaded = False
        self._qso_refresh_running = False
        self._qso_refresh_job = None
        self._qso_refresh_generation = 0
        self._qso_cache_generation = 0
        self._qso_tree_generation = -1
        self._qso_render_generation = 0
        self._qso_restore_selection: str | None = None
        self._qso_cached_qsos: list[dict] = []
        self._qso_cached_by_id: dict[str, dict] = {}
        self._qso_cached_meta_by_id: dict[str, dict] = {}
        self._qso_cached_qsl_by_wid: dict[int, dict] = {}
        self._qso_cached_fastlog_worked_keys: set[tuple[str, str, str]] = set()
        self._qso_cached_rows: list[tuple[str, str, tuple]] = []
        self._qso_cached_summary: dict[str, object] = {}

    def _build_qsos_page(self):
        p = self._new_page("qsos")
        p.columnconfigure(0, weight=1)
        p.rowconfigure(1, weight=1)
        top = self._card(p, row=0, column=0, sticky="ew", pady=(0, 10))
        ttk.Button(top, text="Synchronisieren", style="Primary.TButton", command=self.sync_now).pack(side="left")
        ttk.Button(top, text="ADI-Ordner öffnen", style="Secondary.TButton", command=self.open_log_dir).pack(side="left", padx=8)
        ttk.Button(top, text="ADIF importieren", style="Secondary.TButton", command=self.import_adif).pack(side="left")
        ttk.Button(top, text="ADIF exportieren", style="Secondary.TButton", command=self.export_adif).pack(side="left", padx=8)
        self.sync_label = tk.Label(top, text="", bg=theme.CARD, fg=theme.MUTED, font=("Segoe UI", 9))
        self.sync_label.pack(side="right")

        card = self._card(p, row=1, column=0, sticky="nsew")
        card.columnconfigure(0, weight=1)
        card.rowconfigure(0, weight=1)
        cols = ("date", "time", "call", "operator", "contest", "band", "mode", "freq", "rst", "status", "email_qsl", "qrz", "lotw", "eqsl", "clublog", "dcl")
        self.tree = ttk.Treeview(card, columns=cols, show="headings", selectmode="extended")
        headings = {"date":"Datum UTC", "time":"Zeit", "call":"Call", "operator":"Operator", "contest":"Contest", "band":"Band", "mode":"Mode", "freq":"MHz", "rst":"RST", "status":"Sync", "email_qsl":"E-Mail QSL",
                    "qrz":"QRZ", "lotw":"LoTW", "eqsl":"eQSL", "clublog":"ClubLog", "dcl":"DCL"}
        widths = {"date":88,"time":62,"call":88,"operator":82,"contest":100,"band":52,"mode":60,"freq":80,"rst":62,"status":88,"email_qsl":78,
                  "qrz":52,"lotw":52,"eqsl":52,"clublog":62,"dcl":52}
        for c in cols:
            self.tree.heading(c, text=self._tr(headings[c]))
            self.tree.column(c, width=widths[c], minwidth=45, stretch=(c in ("call", "contest")))
        self.tree.grid(row=0, column=0, sticky="nsew")
        sb = ttk.Scrollbar(card, orient="vertical", command=self.tree.yview)
        sb.grid(row=0, column=1, sticky="ns")
        self.tree.configure(yscrollcommand=sb.set)
        self.tree.tag_configure("local", foreground=theme.MUTED)
        self.tree.tag_configure("wavelog", foreground=theme.OK)
        self.tree.tag_configure("modified", foreground=theme.WARN)
        self.tree.tag_configure("conflict", foreground=theme.ERR)
        self.tree.tag_configure("error", foreground=theme.ERR)
        self.tree.bind("<Double-1>", lambda e: self.edit_selected_qso())
        self.tree.bind("<<TreeviewSelect>>", self._sync_selection_changed)

        actions = ttk.Frame(card, style="Card.TFrame")
        actions.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(10, 0))
        ttk.Button(actions, text="QSO bearbeiten", style="Secondary.TButton", command=self.edit_selected_qso).pack(side="left")
        self.delete_qso_button = ttk.Button(
            actions,
            text="QSO löschen",
            style="Secondary.TButton",
            command=self.delete_selected_qso,
        )
        self.delete_qso_button.pack(side="left", padx=8)
        self.qsl_mail_button = ttk.Button(
            actions,
            text="QSL E-Mail senden",
            style="Secondary.TButton",
            command=self.send_selected_qsl_email,
        )
        self.qsl_mail_button.pack(side="left")
        self.take_wavelog_button = ttk.Button(actions, text="Wavelog-Version übernehmen", style="Secondary.TButton", command=lambda: self.resolve_conflict(False))
        self.take_wavelog_button.pack(side="right")
        self.force_local_button = ttk.Button(actions, text="Lokale Version erzwingen", style="Secondary.TButton", command=lambda: self.resolve_conflict(True))
        self.force_local_button.pack(side="right", padx=8)

        self.sync_detail_label = tk.Label(
            card, text="Keine offenen Sync-Details.", bg=theme.CARD, fg=theme.MUTED,
            font=("Segoe UI", 9), anchor="w", justify="left", wraplength=1050,
        )
        self.sync_detail_label.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(9, 0))

        legend = tk.Label(card, text="QSL-Status: ✓ bestätigt · ↑ gesendet/hochgeladen · … wartet · — kein Status · ? nicht verfügbar · E-Mail QSL: ✅ versendet · — nicht versendet",
                          bg=theme.CARD, fg=theme.MUTED, font=("Segoe UI", 8), anchor="w")
        legend.grid(row=3, column=0, columnspan=2, sticky="ew", pady=(6, 0))
        self._sync_selection_changed()

    @staticmethod
    def _display_qsl_status(value: str | None) -> str:
        return {"confirmed":"✓", "sent":"↑", "pending":"…", "none":"—", "unknown":"?"}.get((value or "unknown").lower(), "?")

    @staticmethod
    def _display_email_qsl_status(
        payload: dict | None,
    ) -> str:
        if not isinstance(payload, dict):
            return "—"

        mail_status = str(
            payload.get("mailStatus")
            or payload.get("mail_status")
            or ""
        ).strip().lower()

        sent_at = str(
            payload.get("emailSentAt")
            or payload.get("email_sent_at")
            or ""
        ).strip()

        if mail_status == "sent" or sent_at:
            return "✅"

        return "—"

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

    def refresh_qsos(self, *, force: bool = True, immediate: bool = False):
        """Invalidate/schedule the logbook view without blocking Tk.

        ``force`` means the underlying data may have changed. Normal page
        navigation uses ``force=False`` and therefore reuses the existing cache.
        """
        if not hasattr(self, "tree"):
            return

        if force:
            self._qso_view_dirty = True
            self._qso_refresh_generation += 1

        # Cached data is current: showing the page only needs a render if the
        # current Treeview has not yet seen this cache generation.
        if self._qso_view_loaded and not self._qso_view_dirty:
            self._apply_qso_summary()
            if getattr(self, "current_page", "") == "qsos":
                self._ensure_qso_tree_rendered()
            return

        # One worker at a time. A data change during a running worker bumps the
        # generation; the stale result is discarded and a new pass is queued.
        if self._qso_refresh_running:
            return

        if self._qso_refresh_job is not None:
            if not immediate:
                return
            try:
                self.after_cancel(self._qso_refresh_job)
            except tk.TclError:
                pass
            self._qso_refresh_job = None

        delay = 0 if immediate else (50 if getattr(self, "current_page", "") == "qsos" else 180)
        self._qso_refresh_job = self.after(delay, self._start_qso_refresh)

    def _start_qso_refresh(self):
        self._qso_refresh_job = None
        if self.closing or self._qso_refresh_running:
            return
        if self._qso_view_loaded and not self._qso_view_dirty:
            self._ensure_qso_tree_rendered()
            return

        self._qso_refresh_running = True
        generation = self._qso_refresh_generation
        store = self.store
        db = self.db
        try:
            profile_id = str(self._current_profile().get("id") or "")
        except Exception:
            profile_id = ""

        if getattr(self, "current_page", "") == "qsos" and not self._qso_view_loaded:
            self.sync_label.configure(text=self._tr("Logbuch wird geladen …"))

        def worker():
            try:
                qsos = store.scan()

                # Keep sync metadata consistent, but do this away from the Tk
                # thread. MetadataDB uses check_same_thread=False + its own lock.
                db.reconcile_index(qsos)

                # One bulk query for sync_meta instead of get_meta() per QSO.
                metas = db.list_meta()
                meta_by_id = {
                    str(meta.get("local_id") or ""): meta
                    for meta in metas
                    if meta.get("local_id")
                }

                # QSL metadata is read in the worker as well. Even with many
                # linked QSOs this can no longer freeze navigation.
                qsl_by_wid: dict[int, dict] = {}
                for meta in metas:
                    wid = meta.get("wavelog_id")
                    if wid is None:
                        continue
                    try:
                        wid_int = int(wid)
                    except (TypeError, ValueError):
                        continue
                    if wid_int not in qsl_by_wid:
                        qsl_by_wid[wid_int] = db.get_qsl_status(wid_int)

                qsl_card_status_by_local = (
                    QslStorage(
                        db
                    ).list_status_snapshots_by_local()
                )

                rows: list[tuple[str, str, tuple]] = []
                fastlog_worked_keys: set[tuple[str, str, str]] = set()
                for q in qsos:
                    local_id = str(q.get("local_id") or "")
                    qso_call = str(q.get("call") or "").strip().upper()
                    qso_band = str(q.get("band") or "").strip()
                    qso_mode = normalize_worked_mode(
                        str(q.get("mode") or ""), band=qso_band,
                    )
                    if qso_call and qso_band and qso_mode:
                        fastlog_worked_keys.add((qso_call, qso_band, qso_mode))
                    meta = meta_by_id.get(local_id)
                    status_text, tag = self._display_sync_status(meta)

                    tm = str(q.get("time_on") or "")
                    if len(tm) >= 6:
                        tm = f"{tm[:2]}:{tm[2:4]}:{tm[4:6]}"

                    wid = meta.get("wavelog_id") if meta else None
                    try:
                        qsl = qsl_by_wid.get(int(wid)) if wid is not None else None
                    except (TypeError, ValueError):
                        qsl = None
                    qsl = qsl or {
                        "qrz": "unknown",
                        "lotw": "unknown",
                        "eqsl": "unknown",
                        "clublog": "unknown",
                        "dcl": "unknown",
                    }

                    rows.append((
                        local_id,
                        tag,
                        (
                            q.get("qso_date", ""),
                            tm,
                            q.get("call", ""),
                            q.get("operator_call", "") or "—",
                            q.get("contest_id", "") or "—",
                            q.get("band", ""),
                            q.get("mode", ""),
                            q.get("freq", ""),
                            f"{q.get('rst_sent','')}/{q.get('rst_rcvd','')}",
                            status_text,
                            self._display_email_qsl_status(
                                (
                                    qsl_card_status_by_local.get(
                                        local_id
                                    )
                                    or {}
                                ).get("payload")
                            ),
                            self._display_qsl_status(qsl.get("qrz")),
                            self._display_qsl_status(qsl.get("lotw")),
                            self._display_qsl_status(qsl.get("eqsl")),
                            self._display_qsl_status(qsl.get("clublog")),
                            self._display_qsl_status(qsl.get("dcl")),
                        ),
                    ))

                local_only = sum(
                    1 for meta in metas
                    if meta.get("wavelog_id") is None
                    and meta.get("status") not in ("pending_delete",)
                )
                wavelog = sum(
                    1 for meta in metas
                    if meta.get("wavelog_id") is not None
                    and meta.get("status") == "synced"
                )
                issues = sum(
                    1 for meta in metas
                    if meta.get("status") in ("modified", "conflict", "error", "pending_delete")
                )
                last = db.get_setting("last_sync_at", "")

                result = {
                    "qsos": qsos,
                    "rows": rows,
                    "meta_by_id": meta_by_id,
                    "qsl_by_wid": qsl_by_wid,
                    "fastlog_worked_keys": fastlog_worked_keys,
                    "local_only": local_only,
                    "wavelog": wavelog,
                    "issues": issues,
                    "last_sync": last,
                    "profile_id": profile_id,
                    "db": db,
                }
                if not self.closing:
                    self.after(0, lambda: self._qso_refresh_ready(generation, result))
            except Exception as exc:
                message = repr(exc)
                if not self.closing:
                    self.after(0, lambda: self._qso_refresh_failed(generation, message))

        threading.Thread(
            target=worker,
            name="logbook-view-refresh",
            daemon=True,
        ).start()

    def _qso_refresh_ready(self, generation: int, result: dict):
        self._qso_refresh_running = False
        if self.closing:
            return

        # Profile changed or data changed while the worker was running.
        if (
            generation != self._qso_refresh_generation
            or result.get("db") is not self.db
            or str(result.get("profile_id") or "") != str(self._current_profile().get("id") or "")
        ):
            self.refresh_qsos(force=False, immediate=getattr(self, "current_page", "") == "qsos")
            return

        qsos = list(result["qsos"])
        self._qso_cached_qsos = qsos
        self._qso_cached_by_id = {
            str(q.get("local_id") or ""): q
            for q in qsos
            if q.get("local_id")
        }
        self._qso_cached_rows = list(result["rows"])
        self._qso_cached_meta_by_id = dict(result["meta_by_id"])
        self._qso_cached_qsl_by_wid = dict(result["qsl_by_wid"])
        self._qso_cached_fastlog_worked_keys = set(result["fastlog_worked_keys"])
        self._qso_cached_summary = {
            "count": len(qsos),
            "local_only": int(result["local_only"]),
            "wavelog": int(result["wavelog"]),
            "issues": int(result["issues"]),
            "last_sync": str(result["last_sync"] or ""),
        }
        self._qso_view_dirty = False
        self._qso_view_loaded = True
        self._qso_cache_generation += 1

        # These caches are useful to the logging/DX-cluster pages too. Updating
        # them from the already parsed QSO list avoids another ADIF scan.
        self._update_dx_cluster_worked_cache(qsos)
        self._remember_last_spottable_from_cache(qsos)
        self._apply_qso_summary()

        if hasattr(self, "_refresh_qsl_recommendations"):
            self._refresh_qsl_recommendations()

        current_page = getattr(self, "current_page", "")
        if current_page == "qsos":
            self._ensure_qso_tree_rendered()
        elif current_page == "fast_log":
            self.refresh_fast_log_page()
        elif current_page == "stats":
            self.refresh_stats()

    def _qso_refresh_failed(self, generation: int, message: str):
        self._qso_refresh_running = False
        write_startup_log("Logbuch-Refresh fehlgeschlagen: " + message)
        if generation != self._qso_refresh_generation:
            self.refresh_qsos(force=False)
            return
        if getattr(self, "current_page", "") == "qsos":
            self.sync_label.configure(text=self._tr("Logbuch konnte nicht aktualisiert werden"))

    def _remember_last_spottable_from_cache(self, qsos: list[dict]):
        latest = next(
            (
                q for q in qsos
                if q.get("call") and (q.get("freq") or q.get("frequency"))
            ),
            None,
        )
        self.last_spottable_qso = None
        self._remember_last_spottable_qso(latest)

    def _apply_qso_summary(self):
        if not self._qso_cached_summary:
            return
        summary = self._qso_cached_summary
        last = str(summary.get("last_sync") or "")
        suffix = f" · letzter Sync {last}" if last else " · noch nicht synchronisiert"
        issues = int(summary.get("issues") or 0)
        issue_text = f" · {issues} offen" if issues else ""
        count = int(summary.get("count") or 0)

        self.sync_label.configure(
            text=(
                f"{count} QSOs · {int(summary.get('wavelog') or 0)} WAVELOG · "
                f"{int(summary.get('local_only') or 0)} LOCAL ONLY"
                f"{issue_text}{suffix}"
            )
        )
        if hasattr(self, "footer_qso_var"):
            self.footer_qso_var.set(f"{count} QSOs")
            profile_name = self._current_profile().get("name", "Profil")
            self.footer_db_var.set(f"{profile_name} · {Path(self.db.path).name}")

    def _ensure_qso_tree_rendered(self):
        if not self._qso_view_loaded:
            return
        if self._qso_tree_generation == self._qso_cache_generation:
            return

        selected = self._qso_restore_selection or self.selected_id()
        try:
            yview = self.tree.yview()
        except tk.TclError:
            yview = ()

        self._qso_render_generation += 1
        render_generation = self._qso_render_generation
        self.tree.delete(*self.tree.get_children())

        # Render in chunks. Tk gets control back between chunks, so even a
        # very large logbook does not turn the window "Not responding".
        self._render_qso_tree_batch(
            render_generation,
            0,
            selected,
            yview,
        )

    def _render_qso_tree_batch(
        self,
        render_generation: int,
        start: int,
        selected: str | None,
        yview: tuple,
    ):
        if self.closing or render_generation != self._qso_render_generation:
            return

        rows = self._qso_cached_rows
        batch_size = 200
        end = min(len(rows), start + batch_size)

        for local_id, tag, values in rows[start:end]:
            if not local_id:
                continue
            try:
                self.tree.insert("", "end", iid=local_id, tags=(tag,), values=values)
            except tk.TclError:
                # A duplicate/corrupt id should not make the complete view fail.
                continue

        if end < len(rows):
            self.after_idle(
                lambda: self._render_qso_tree_batch(
                    render_generation,
                    end,
                    selected,
                    yview,
                )
            )
            return

        self._qso_tree_generation = self._qso_cache_generation
        if selected and self.tree.exists(selected):
            self.tree.selection_set(selected)
            self.tree.focus(selected)
            self.tree.see(selected)
        elif yview:
            try:
                self.tree.yview_moveto(float(yview[0]))
            except (tk.TclError, ValueError, TypeError):
                pass
        self._qso_restore_selection = None
        self._sync_selection_changed()

    def _cached_qso(self, local_id: str | None) -> dict | None:
        if not local_id:
            return None
        cached = self._qso_cached_by_id.get(str(local_id))
        if cached is not None and not self._qso_view_dirty:
            return dict(cached)
        return self.store.find(str(local_id))

    def selected_ids(self) -> tuple[str, ...]:
        if not hasattr(self, "tree"):
            return ()
        return tuple(str(value) for value in self.tree.selection())

    def selected_id(self) -> str | None:
        selected = self.selected_ids()
        return selected[0] if selected else None

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
        selection_count = len(self.selected_ids())
        if hasattr(self, "delete_qso_button"):
            self.delete_qso_button.configure(
                text=(
                    f"{selection_count} QSOs löschen"
                    if selection_count > 1
                    else "QSO löschen"
                )
            )
        local_id = self.selected_id()
        meta = self.db.get_meta(local_id) if local_id else None
        status = str((meta or {}).get("status") or "")
        is_conflict = status == "conflict"
        button_state = "normal" if is_conflict else "disabled"
        self.take_wavelog_button.configure(state=button_state)
        self.force_local_button.configure(state=button_state)
        if status == "error":
            detail = str((meta or {}).get("last_error") or "Kein technischer Fehlertext gespeichert.").strip()
            self.sync_detail_label.configure(text=self._tr("SYNC-FEHLER: ") + detail[:900], fg=theme.ERR)
        elif status == "conflict":
            reason = str((meta or {}).get("last_error") or "Lokale und Wavelog-Version unterscheiden sich.")
            explanations = {
                "both_changed": "Lokale und Wavelog-Version wurden seit dem letzten gemeinsamen Stand geändert.",
                "remote_deleted": "Das QSO wurde in Wavelog gelöscht, lokal aber anschließend verändert.",
            }
            self.sync_detail_label.configure(text=self._tr("KONFLIKT: ") + self._tr(explanations.get(reason, reason))[:900], fg=theme.ERR)
        elif local_id:
            self.sync_detail_label.configure(text=self._tr("Keine offenen Sync-Details."), fg=theme.MUTED)
        else:
            self.sync_detail_label.configure(text=self._tr("QSO auswählen, um Sync-Details anzuzeigen."), fg=theme.MUTED)

    def edit_selected_qso(self):
        lid = self.selected_id()
        if not lid:
            return
        q = self._cached_qso(lid)
        if not q:
            return
        EditDialog(self, q, self._save_edited_qso)

    def _save_edited_qso(self, local_id: str, q: dict):
        try:
            old = self._cached_qso(local_id)
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
        local_ids = list(self.selected_ids())
        if not local_ids:
            return

        cached = self._qso_cached_by_id
        qsos = [dict(cached[lid]) for lid in local_ids if lid in cached]
        if len(qsos) != len(local_ids):
            by_id = {
                str(row.get("local_id") or ""): row
                for row in self.store.scan()
                if row.get("local_id")
            }
            qsos = [dict(by_id[lid]) for lid in local_ids if lid in by_id]
        if not qsos:
            return

        meta_by_id = self._qso_cached_meta_by_id
        if not meta_by_id:
            meta_by_id = {
                str(meta.get("local_id") or ""): meta
                for meta in self.db.list_meta()
                if meta.get("local_id")
            }
        remote_count = sum(
            1
            for lid in local_ids
            if (meta_by_id.get(lid) or {}).get("wavelog_id") is not None
        )
        local_only_count = len(local_ids) - remote_count

        if len(local_ids) == 1:
            q = qsos[0]
            intro = f"{q.get('call', '')} vom {q.get('qso_date', '')} wirklich löschen?"
        else:
            intro = f"{len(local_ids)} ausgewählte QSOs wirklich löschen?"

        if remote_count:
            remote_warning = (
                f"ACHTUNG: {remote_count} QSO(s) sind bereits mit Wavelog verknüpft. "
                "Diese QSOs werden beim nächsten vollständigen Sync auch aus Wavelog gelöscht."
            )
        else:
            remote_warning = (
                "Die ausgewählten QSOs sind derzeit nicht mit Wavelog verknüpft "
                "und werden nur lokal gelöscht."
            )

        details = (
            f"{intro}\n\n{remote_warning}\n\n"
            f"Ausgewählt: {len(local_ids)} · Wavelog: {remote_count} · Nur lokal: {local_only_count}\n\n"
            "Diese Aktion bitte nur ausführen, wenn die QSOs tatsächlich gelöscht werden sollen."
        )
        if not messagebox.askokcancel(
            "QSOs löschen",
            details,
            icon="warning",
            parent=self,
        ):
            return

        children = list(self.tree.get_children())
        selected_set = set(local_ids)
        positions = [
            index for index, item_id in enumerate(children)
            if item_id in selected_set
        ]
        anchor = None
        if positions:
            for item_id in children[max(positions) + 1:]:
                if item_id not in selected_set:
                    anchor = item_id
                    break
            if anchor is None:
                for item_id in reversed(children[:min(positions)]):
                    if item_id not in selected_set:
                        anchor = item_id
                        break

        try:
            # First persist the local ADIF removal. Only after that do linked
            # QSOs become explicit remote-delete candidates.
            deleted_ids = self.store.delete_many(local_ids)
            self.db.mark_pending_delete_many(deleted_ids)
        except Exception as exc:
            self.refresh_qsos()
            messagebox.showerror("QSOs löschen", str(exc), parent=self)
            return

        if not deleted_ids:
            return
        self._qso_restore_selection = anchor
        self.refresh_qsos()
        self.status_var.set(f"{len(deleted_ids)} QSO(s) lokal gelöscht")
        self._local_sync_change()

    def configure_wsjtx_sync(self):
        if hasattr(self, "settings_notebook") and hasattr(self, "settings_wsjtx_tab"):
            self.settings_notebook.select(self.settings_wsjtx_tab)
            return
        self._show_page("settings")

    def _maybe_startup_wsjtx_sync(self):
        if self.closing or self.close_requested:
            return
        try:
            wsjtx_settings = load_wsjtx_settings(self.db)
        except Exception as exc:
            write_startup_log("WSJT-X Startup-Sync Einstellungen: " + repr(exc))
            return
        if (
            not should_wsjtx_sync_for_reason(wsjtx_settings, "startup")
            or wsjtx_settings.log_path is None
        ):
            return

        # Läuft ohnehin ein vollständiger Wavelog-Startsync, wird WSJT-X dort
        # an der richtigen Stelle nach Wavelog -> LOCAL eingebunden.
        wavelog_settings = self._wavelog_online_settings()
        if wavelog_settings.configured and wavelog_settings.full_sync_on_start:
            return

        if self.sync_busy:
            self.after(700, self._maybe_startup_wsjtx_sync)
            return
        self._start_wsjtx_only_sync(reason="startup")

    def sync_wsjtx_now(self):
        if self.sync_busy:
            messagebox.showwarning(
                "WSJT-X Sync",
                "Es läuft bereits eine Synchronisierung.",
                parent=self,
            )
            return

        wsjtx_settings = load_wsjtx_settings(self.db)
        if wsjtx_settings.log_path is None:
            self.configure_wsjtx_sync()
            return

        # Wenn Wavelog verfügbar ist, führt "jetzt abgleichen" bewusst den
        # vollständigen Drei-Wege-Abgleich aus:
        # Wavelog -> LOCAL -> WSJT-X -> LOCAL -> Wavelog.
        wavelog_settings = self._wavelog_online_settings()
        if wavelog_settings.configured and self.wavelog_online:
            self._start_sync(
                automatic=False,
                reason="manual",
                force_wsjtx=True,
            )
            return

        # Offline bleibt der WSJT-X-Abgleich trotzdem lokal nutzbar.
        self._start_wsjtx_only_sync(reason="manual")

    def _start_wsjtx_only_sync(self, *, reason: str):
        if self.sync_busy or self.closing:
            return

        try:
            wsjtx_settings = load_wsjtx_settings(self.db)
            if wsjtx_settings.log_path is None:
                raise ValueError("Kein WSJT-X Profil bzw. keine wsjtx_log.adi ausgewählt.")
        except Exception as exc:
            if reason == "manual":
                messagebox.showerror("WSJT-X Sync", str(exc), parent=self)
            else:
                write_startup_log("WSJT-X Sync konnte nicht gestartet werden: " + repr(exc))
            if reason == "shutdown" and self.close_requested:
                self._finalize_close()
            return

        self.sync_busy = True
        self.sync_is_automatic = reason != "manual"
        self.sync_operation = "wsjtx"
        self.sync_reason = reason

        if reason == "startup":
            progress_text = "WSJT-X Start-Sync läuft …"
        elif reason == "shutdown":
            progress_text = "WSJT-X Abschluss-Sync läuft …"
        else:
            progress_text = "WSJT-X wird mit dem lokalen Logbuch abgeglichen …"

        self.status_var.set(progress_text)
        if hasattr(self, "sync_label"):
            self.sync_label.configure(text=progress_text)

        def worker():
            try:
                result = sync_wsjtx_with_local(
                    self.store,
                    self.db,
                    wsjtx_settings,
                )
                if not self.closing:
                    self.after(
                        0,
                        lambda: self._wsjtx_only_sync_finished(result, reason),
                    )
            except Exception as exc:
                if not self.closing:
                    message = str(exc)
                    self.after(
                        0,
                        lambda error=message: self._wsjtx_only_sync_failed(error, reason),
                    )

        threading.Thread(
            target=worker,
            name=f"wsjtx-sync-{reason}",
            daemon=True,
        ).start()

    def _wsjtx_only_sync_finished(self, result, reason: str):
        self.sync_busy = False
        self.sync_is_automatic = False
        self.sync_operation = ""
        self.sync_reason = ""

        self.refresh_qsos()
        self.refresh_stats()

        self.status_var.set(
            f"WSJT-X Sync fertig · lokal +{result.imported_to_local} · "
            f"WSJT-X +{result.appended_to_wsjtx}"
        )

        # Neu aus WSJT-X übernommene QSOs dürfen den bestehenden Online-Push
        # nutzen, aber nur wenn der Nutzer diesen ohnehin aktiviert hat.
        if result.imported_to_local:
            self._local_sync_change()

        if reason == "manual" and not self.close_requested:
            messagebox.showinfo(
                "WSJT-X Sync",
                format_wsjtx_result(result, self.language),
                parent=self,
            )

        if self.close_requested:
            if reason == "shutdown":
                self._finalize_close()
            else:
                self._begin_close_sequence()

    def _wsjtx_only_sync_failed(self, message: str, reason: str):
        self.sync_busy = False
        self.sync_is_automatic = False
        self.sync_operation = ""
        self.sync_reason = ""
        self.status_var.set("WSJT-X Sync fehlgeschlagen")
        write_startup_log("WSJT-X Sync fehlgeschlagen: " + message)

        if reason == "manual" and not self.close_requested:
            messagebox.showerror("WSJT-X Sync", message, parent=self)

        if self.close_requested:
            if reason == "shutdown":
                self._finalize_close()
            else:
                self._begin_close_sequence()

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

    def _start_sync(
        self,
        *,
        automatic: bool,
        reason: str = "manual",
        force_wsjtx: bool = False,
    ):
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
                wsjtx_note = ""
                try:
                    wsjtx_settings = load_wsjtx_settings(self.db)
                    if (
                        force_wsjtx
                        or should_wsjtx_sync_for_reason(wsjtx_settings, reason)
                    ) and wsjtx_settings.log_path is not None:
                        wsjtx_result = sync_wsjtx_with_local(self.store, self.db, wsjtx_settings)
                        pushed_from_wsjtx = 0
                        push_errors = 0
                        if wsjtx_result.imported_to_local:
                            followup = engine.push_new_only(station_id)
                            pushed_from_wsjtx = followup.pushed
                            push_errors = followup.errors
                            ContestSyncEngine(self.store, self.db, client).link_pending()
                        wsjtx_note = (
                            f" · WSJT-X: lokal +{wsjtx_result.imported_to_local}"
                            f" / WSJT-X +{wsjtx_result.appended_to_wsjtx}"
                            f" / danach Wavelog +{pushed_from_wsjtx}"
                        )
                        if push_errors:
                            wsjtx_note += f" / Push-Fehler {push_errors}"
                except Exception as wsjtx_exc:
                    # WSJT-X darf einen ansonsten erfolgreichen Wavelog-Sync nicht kaputt machen.
                    wsjtx_note = f" · WSJT-X Fehler: {wsjtx_exc}"
                msg = (f"Upload {summary.pushed} · zu Wavelog geändert {summary.patched} · "
                       f"neu aus Wavelog {summary.pulled} · aus Wavelog aktualisiert {summary.remote_updated} · "
                       f"remote gelöscht {summary.remote_deleted} · verknüpft {summary.linked} · "
                       f"lokal→Wavelog gelöscht {summary.deleted} · QSL-Status {summary.qsl_updated} · "
                       f"anderes Stationsprofil übersprungen {summary.scope_skipped} · "
                       f"Konflikte {summary.conflicts} · Fehler {summary.errors} · QSL-Statusfehler {summary.qsl_errors} · "
                       f"Contests neu {contest_summary.created} / geladen {contest_summary.pulled} / "
                       f"aus QSO-Historie {contest_summary.history_imported} / "
                       f"QSO-Links {contest_summary.linked} / Fehler {contest_summary.errors}")
                msg += wsjtx_note
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
        q = self._cached_qso(lid)
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
            else:
                command = "open" if sys.platform == "darwin" else "xdg-open"
                executable = shutil.which(command)
                if not executable:
                    raise RuntimeError(f"{command} wurde auf diesem System nicht gefunden")
                subprocess.Popen(
                    [executable, p],
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    start_new_session=True,
                )
        except Exception as e:
            messagebox.showerror("Ordner öffnen", str(e), parent=self)
