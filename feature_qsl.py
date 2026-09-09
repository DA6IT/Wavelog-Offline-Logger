from __future__ import annotations

import io
import threading
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk

from PIL import Image, ImageTk

from qsl_background import (
    QSL_BACKGROUND_INTERVAL_MS,
    QSL_BACKGROUND_NEW_QSO_MS,
    QSL_BACKGROUND_RETRY_MS,
    QslBackgroundResult,
    run_qsl_background_sync,
)
from qsl_client import QslClient
from qsl_recipient import (
    DEFAULT_RECIPIENT_BATCH,
    QslRecipientResult,
    queue_recipient_check,
    resolve_pending_recipients,
)
from qsl_delivery import (
    QslDeliveryResult,
    QslQueueResult,
    queue_qsl_batch,
    render_selected_qsl,
    send_single_qsl,
)
from qsl_renderer import (
    latest_qso,
    qso_designer_values,
)
from qsl_storage import QslStorage
from qsl_sync import QslSyncResult, sync_qsos
from qsl_templates import (
    QslTemplateCatalog,
    QslTemplateError,
    choose_template_profile_response,
    normalize_station_profile,
)
from ui_theme import theme


class QslFeatureMixin:
    def _init_qsl_feature(self) -> None:
        self.qsl_sync_busy = False
        self.qsl_last_bootstrap: dict | None = None
        self.qsl_last_result: QslSyncResult | None = None
        self.qsl_last_recipient_result: QslRecipientResult | None = None
        self.qsl_template_busy = False
        self.qsl_template_items: dict[str, dict] = {}
        self.qsl_template_profile = ""
        self.qsl_preview_busy = False
        self.qsl_preview_window = None
        self.qsl_preview_photo = None
        self.qsl_mail_busy = False
        self.qsl_background_busy = False
        self.qsl_background_job = None
        self.qsl_background_reason = ""

    @staticmethod
    def _qsl_recipient_email_valid(value: str) -> bool:
        email = str(value or "").strip()

        if not email or len(email) > 320 or email.count("@") != 1:
            return False

        local, domain = email.rsplit("@", 1)

        return bool(
            local
            and domain
            and "." in domain
            and not any(character.isspace() for character in email)
        )

    def _remember_qsl_recipient_hint(
        self,
        qso: dict,
    ) -> None:
        result = getattr(self, "callbook_result", None)

        if result is None:
            return

        local_id = str(qso.get("local_id") or "").strip()
        qso_call = str(qso.get("call") or "").strip().upper()
        result_call = str(
            getattr(result, "callsign", "") or ""
        ).strip().upper()

        if (
            not local_id
            or not qso_call
            or result_call != qso_call
        ):
            return

        email = str(
            getattr(result, "email", "") or ""
        ).strip()

        source = str(
            getattr(result, "source", "") or ""
        ).strip()

        source_lower = source.casefold()
        trusted_source = (
            source_lower.startswith("qrz.com")
            or source_lower.startswith("wavelog")
        )

        if (
            not trusted_source
            or not self._qsl_recipient_email_valid(email)
        ):
            return

        QslStorage(self.db).set_recipient_hint(
            local_id,
            email,
            source,
        )

    def _queue_qsl_recipient_check(
        self,
        qso: dict,
    ) -> None:
        local_id = str(
            qso.get("local_id") or ""
        ).strip()

        if not local_id:
            return

        queue_recipient_check(
            QslStorage(self.db),
            local_id,
        )

    def _cancel_qsl_background_sync(self) -> None:
        job = getattr(self, "qsl_background_job", None)

        if job is not None:
            try:
                self.after_cancel(job)
            except Exception:
                pass

        self.qsl_background_job = None

    def _schedule_qsl_background_sync(
        self,
        delay_ms: int = QSL_BACKGROUND_INTERVAL_MS,
        *,
        reason: str = "periodic",
    ) -> None:
        self._cancel_qsl_background_sync()

        if getattr(self, "closing", False):
            return

        db = getattr(self, "db", None)
        if db is None:
            return

        try:
            has_key = bool(
                db.get_secret("qsl_connection_key").strip()
            )
        except Exception:
            return

        if not has_key:
            return

        self.qsl_background_reason = str(reason or "periodic")
        self.qsl_background_job = self.after(
            max(0, int(delay_ms)),
            lambda: self._start_qsl_background_sync(
                self.qsl_background_reason
            ),
        )

    def _start_qsl_background_sync(
        self,
        reason: str = "periodic",
    ) -> None:
        self.qsl_background_job = None

        if getattr(self, "closing", False):
            return

        if (
            self.qsl_background_busy
            or self.qsl_sync_busy
            or self.qsl_template_busy
            or self.qsl_mail_busy
        ):
            self._schedule_qsl_background_sync(
                5000,
                reason=reason,
            )
            return

        connection_key = self.db.get_secret(
            "qsl_connection_key"
        ).strip()

        if not connection_key:
            return

        self.qsl_background_busy = True

        db = self.db
        store = self.store
        profile_id = self.active_profile_id
        template_candidates = self._qsl_station_profile_candidates()

        def worker() -> None:
            try:
                qsos = store.scan()
                client = QslClient(
                    connection_key,
                    timeout=20,
                )
                result = run_qsl_background_sync(
                    client,
                    QslStorage(db),
                    db,
                    qsos,
                    template_candidates=template_candidates,
                )

                if not self.closing:
                    self.after(
                        0,
                        lambda: self._qsl_background_ok(
                            profile_id,
                            reason,
                            result,
                        ),
                    )
            except Exception as exc:
                error = str(exc)
                if not self.closing:
                    self.after(
                        0,
                        lambda message=error: self._qsl_background_failed(
                            profile_id,
                            reason,
                            message,
                        ),
                    )

        threading.Thread(
            target=worker,
            name="qsl-background-sync",
            daemon=True,
        ).start()

    def _qsl_background_ok(
        self,
        profile_id: str,
        reason: str,
        result: QslBackgroundResult,
    ) -> None:
        self.qsl_background_busy = False

        if profile_id != self.active_profile_id:
            self._schedule_qsl_background_sync(
                500,
                reason="profile",
            )
            return

        self.qsl_last_bootstrap = dict(result.bootstrap)

        if result.sync.total:
            self.qsl_last_result = result.sync

        self.qsl_last_recipient_result = result.recipient

        if hasattr(self, "qsl_sync_status_var"):
            if self.language == "en":
                status = (
                    f"Automatic QSL sync: {result.sync.total} new · "
                    f"{result.statuses_refreshed} status · "
                    f"{result.template_count} motifs"
                )
            else:
                status = (
                    f"Automatischer QSL-Sync: {result.sync.total} neu · "
                    f"{result.statuses_refreshed} Status · "
                    f"{result.template_count} Motive"
                )

            if result.errors:
                status += " · " + "; ".join(result.errors)

            self.qsl_sync_status_var.set(status)

            if hasattr(self, "qsl_sync_status_label"):
                self.qsl_sync_status_label.configure(
                    fg=theme.WARN if result.errors else theme.OK
                )

        self.refresh_qsl_page()
        self.refresh_qsos(
            force=True,
            immediate=False,
        )

        retry_needed = bool(
            result.errors
            or result.recipient.failed
            or result.recipient.pending_after
        )

        self._schedule_qsl_background_sync(
            QSL_BACKGROUND_RETRY_MS
            if retry_needed
            else QSL_BACKGROUND_INTERVAL_MS,
            reason="retry" if retry_needed else "periodic",
        )

    def _qsl_background_failed(
        self,
        profile_id: str,
        reason: str,
        message: str,
    ) -> None:
        self.qsl_background_busy = False

        if profile_id != self.active_profile_id:
            return

        if hasattr(self, "qsl_sync_status_var"):
            text = (
                "Automatic QSL sync waits for server connection."
                if self.language == "en"
                else "Automatischer QSL-Sync wartet auf Serververbindung."
            )
            self.qsl_sync_status_var.set(text)
            if hasattr(self, "qsl_sync_status_label"):
                self.qsl_sync_status_label.configure(fg=theme.MUTED)

        self._schedule_qsl_background_sync(
            QSL_BACKGROUND_RETRY_MS,
            reason="retry",
        )

    def _build_qsl_page(self) -> None:
        page = self._new_page("qsl")
        page.columnconfigure(0, weight=1)
        page.columnconfigure(1, weight=1)
        page.rowconfigure(2, weight=1)

        local_card = self._card(
            page,
            row=0,
            column=0,
            sticky="nsew",
            padx=(0, 8),
            pady=(0, 10),
        )
        local_card.columnconfigure(0, weight=1)

        ttk.Label(
            local_card,
            text="Lokale QSL-Synchronisierung",
            style="CardTitle.TLabel",
        ).grid(row=0, column=0, sticky="w")

        ttk.Label(
            local_card,
            text=(
                "Lokale QSOs werden zum DA6IT.de QSL Card Manager "
                "übertragen. Der Server liefert die stabile qsoUid; "
                "der Logger berechnet diese Kennung niemals selbst."
            ),
            style="Muted.Card.TLabel",
            wraplength=500,
        ).grid(row=1, column=0, sticky="ew", pady=(4, 14))

        self.qsl_local_status_var = tk.StringVar(
            value="QSL-Status wird geladen …"
        )
        ttk.Label(
            local_card,
            textvariable=self.qsl_local_status_var,
            style="Card.TLabel",
            wraplength=500,
        ).grid(row=2, column=0, sticky="ew", pady=(0, 14))

        self.qsl_sync_button = ttk.Button(
            local_card,
            text="Jetzt mit QSL Card Manager synchronisieren",
            style="Primary.TButton",
            command=self.sync_qsl_now,
        )
        self.qsl_sync_button.grid(row=3, column=0, sticky="w")

        self.qsl_sync_status_var = tk.StringVar(
            value="Noch kein QSL-Sync in dieser Sitzung."
        )
        self.qsl_sync_status_label = tk.Label(
            local_card,
            textvariable=self.qsl_sync_status_var,
            bg=theme.CARD,
            fg=theme.MUTED,
            font=("Segoe UI", 9),
            justify="left",
            anchor="w",
            wraplength=500,
        )
        self.qsl_sync_status_label.grid(
            row=4,
            column=0,
            sticky="ew",
            pady=(12, 0),
        )

        server_card = self._card(
            page,
            row=0,
            column=1,
            sticky="nsew",
            padx=(8, 0),
            pady=(0, 10),
        )
        server_card.columnconfigure(0, weight=1)

        ttk.Label(
            server_card,
            text="Serverstatus",
            style="CardTitle.TLabel",
        ).grid(row=0, column=0, sticky="w")

        ttk.Label(
            server_card,
            text=(
                "Contract, API-Version und Versandlimits werden beim "
                "manuellen QSL-Sync direkt vom Server geladen."
            ),
            style="Muted.Card.TLabel",
            wraplength=500,
        ).grid(row=1, column=0, sticky="ew", pady=(4, 14))

        self.qsl_server_status_var = tk.StringVar(
            value="Noch kein Serverstatus in dieser Sitzung."
        )
        self.qsl_server_status_label = tk.Label(
            server_card,
            textvariable=self.qsl_server_status_var,
            bg=theme.CARD,
            fg=theme.MUTED,
            font=("Segoe UI", 9),
            justify="left",
            anchor="nw",
            wraplength=500,
        )
        self.qsl_server_status_label.grid(
            row=2,
            column=0,
            sticky="nsew",
        )

        template_card = self._card(
            page,
            row=1,
            column=0,
            columnspan=2,
            sticky="ew",
            pady=(0, 10),
        )
        template_card.columnconfigure(1, weight=1)

        ttk.Label(
            template_card,
            text="QSL-Motive",
            style="CardTitle.TLabel",
        ).grid(
            row=0,
            column=0,
            columnspan=3,
            sticky="w",
        )

        ttk.Label(
            template_card,
            text=(
                "Community-Motive und eigene Vorlagen werden vom "
                "QSL Card Manager geladen und lokal gecacht. "
                "Die Auswahl gilt für das aktuelle Stationsprofil."
            ),
            style="Muted.Card.TLabel",
            wraplength=1040,
        ).grid(
            row=1,
            column=0,
            columnspan=3,
            sticky="ew",
            pady=(4, 12),
        )

        ttk.Label(
            template_card,
            text="Stationsprofil",
            style="Card.TLabel",
        ).grid(
            row=2,
            column=0,
            sticky="w",
            padx=(0, 10),
        )

        self.qsl_template_profile_var = tk.StringVar(
            value="—"
        )
        ttk.Label(
            template_card,
            textvariable=self.qsl_template_profile_var,
            style="Card.TLabel",
        ).grid(
            row=2,
            column=1,
            sticky="w",
        )

        self.qsl_template_refresh_button = ttk.Button(
            template_card,
            text="Motive vom Server laden",
            style="Secondary.TButton",
            command=self.load_qsl_templates,
        )
        self.qsl_template_refresh_button.grid(
            row=2,
            column=2,
            sticky="e",
        )

        ttk.Label(
            template_card,
            text="Aktives Motiv",
            style="Card.TLabel",
        ).grid(
            row=3,
            column=0,
            sticky="w",
            pady=(12, 0),
            padx=(0, 10),
        )

        self.qsl_template_var = tk.StringVar()
        self.qsl_template_combo = ttk.Combobox(
            template_card,
            textvariable=self.qsl_template_var,
            state="readonly",
        )
        self.qsl_template_combo.grid(
            row=3,
            column=1,
            sticky="ew",
            pady=(12, 0),
        )

        self.qsl_preview_button = ttk.Button(
            template_card,
            text="Vorschau",
            style="Secondary.TButton",
            command=self.preview_qsl_template,
        )
        self.qsl_preview_button.grid(
            row=3,
            column=2,
            sticky="e",
            padx=(10, 0),
            pady=(12, 0),
        )
        self.qsl_template_combo.bind(
            "<<ComboboxSelected>>",
            self._qsl_template_selected,
        )

        self.qsl_template_detail_var = tk.StringVar(
            value="Noch keine Motive lokal geladen."
        )
        self.qsl_template_detail_label = tk.Label(
            template_card,
            textvariable=self.qsl_template_detail_var,
            bg=theme.CARD,
            fg=theme.MUTED,
            font=("Segoe UI", 9),
            justify="left",
            anchor="nw",
            wraplength=1040,
        )
        self.qsl_template_detail_label.grid(
            row=4,
            column=0,
            columnspan=3,
            sticky="ew",
            pady=(10, 0),
        )

        result_card = self._card(
            page,
            row=2,
            column=0,
            columnspan=2,
            sticky="nsew",
        )
        result_card.columnconfigure(0, weight=1)

        ttk.Label(
            result_card,
            text="Letzter QSL-Sync",
            style="CardTitle.TLabel",
        ).grid(row=0, column=0, sticky="w")

        ttk.Label(
            result_card,
            text=(
                "Der Sync ist idempotent: bereits bekannte QSOs werden "
                "vom Server als unchanged erkannt. Neue oder geänderte QSOs "
                "erhalten bzw. behalten ihre serverseitige qsoUid."
            ),
            style="Muted.Card.TLabel",
            wraplength=1040,
        ).grid(row=1, column=0, sticky="ew", pady=(4, 14))

        self.qsl_result_var = tk.StringVar(
            value="Noch keine Sync-Ergebnisse vorhanden."
        )
        self.qsl_result_label = tk.Label(
            result_card,
            textvariable=self.qsl_result_var,
            bg=theme.CARD,
            fg=theme.MUTED,
            font=("Segoe UI", 10),
            justify="left",
            anchor="nw",
            wraplength=1040,
        )
        self.qsl_result_label.grid(
            row=2,
            column=0,
            sticky="nsew",
        )

        self.refresh_qsl_page()

    def _qsl_station_profile_candidates(
        self,
    ) -> list[str]:
        values: list[str] = []

        try:
            profile_name = str(
                self._current_profile().get(
                    "name",
                    "",
                )
                or ""
            ).strip()
        except Exception:
            profile_name = ""

        values.extend(
            [
                profile_name,
                self.db.get_setting(
                    "station_call",
                    "",
                ).strip(),
                self.db.get_setting(
                    "operator_call",
                    "",
                ).strip(),
            ]
        )

        result: list[str] = []

        for raw in values:
            if not raw:
                continue

            try:
                profile = normalize_station_profile(
                    raw
                )
            except QslTemplateError:
                continue

            if profile not in result:
                result.append(
                    profile
                )

        return result

    def _current_qsl_station_profile(
        self,
    ) -> str:
        candidates = (
            self._qsl_station_profile_candidates()
        )

        saved = self.db.get_setting(
            "qsl_layout_profile_key",
            "",
        ).strip()

        if saved:
            try:
                saved = normalize_station_profile(
                    saved
                )
            except QslTemplateError:
                saved = ""

        if (
            saved
            and saved in candidates
        ):
            return saved

        return (
            candidates[0]
            if candidates
            else ""
        )

    def _refresh_qsl_template_catalog(
        self,
    ) -> None:
        if not hasattr(
            self,
            "qsl_template_combo",
        ):
            return

        profile = self._current_qsl_station_profile()
        self.qsl_template_profile = profile
        self.qsl_template_profile_var.set(
            profile or "—"
        )

        if not profile:
            self.qsl_template_items = {}
            self.qsl_template_combo.configure(
                values=(),
            )
            self.qsl_template_var.set("")
            self.qsl_template_detail_var.set(
                "Kein Stationsrufzeichen für die Motivauswahl konfiguriert."
            )
            return

        try:
            catalog = QslTemplateCatalog(
                self.db
            )
            templates = catalog.cached_templates(
                profile
            )
            selected_id = catalog.selected_template_id(
                profile
            )
        except Exception as exc:
            self.qsl_template_detail_var.set(
                "Lokaler Motiv-Katalog konnte nicht geladen werden: "
                + str(exc)
            )
            return

        labels: list[str] = []
        items: dict[str, dict] = {}

        for item in templates:
            kind = (
                "Community"
                if item.get("isSystem")
                else "Eigene Vorlage"
            )
            label = (
                f"{item['name']} · {kind} · #{item['id']}"
            )
            labels.append(label)
            items[label] = item

        self.qsl_template_items = items
        self.qsl_template_combo.configure(
            values=labels,
        )

        selected_label = ""

        if selected_id is not None:
            for label, item in items.items():
                if int(item["id"]) == int(selected_id):
                    selected_label = label
                    break

        if not selected_label and labels:
            selected_label = labels[0]

            try:
                catalog.set_selected_template(
                    profile,
                    int(
                        items[
                            selected_label
                        ]["id"]
                    ),
                )
            except Exception:
                pass

        self.qsl_template_var.set(
            selected_label
        )

        self._update_qsl_template_details()

    def _update_qsl_template_details(
        self,
    ) -> None:
        if not hasattr(
            self,
            "qsl_template_detail_var",
        ):
            return

        label = self.qsl_template_var.get()
        item = self.qsl_template_items.get(
            label
        )

        if not item:
            self.qsl_template_detail_var.set(
                "Noch keine Motive lokal geladen."
            )
            return

        canvas = item.get("canvas")
        canvas = (
            canvas
            if isinstance(canvas, dict)
            else {}
        )

        kind = (
            "Community-Motiv"
            if item.get("isSystem")
            else "Eigene Vorlage"
        )

        layout = (
            " · persönliches Layout"
            if item.get("hasPersonalLayout")
            else ""
        )

        background = canvas.get("background")
        background = (
            background
            if isinstance(background, dict)
            else {}
        )

        bg_text = (
            "Bild"
            if background.get("url")
            else "Farbe"
        )

        self.qsl_template_detail_var.set(
            f"{kind}{layout}\n"
            f"Template-ID: {item['id']} · Revision: {item['revision']} · "
            f"{canvas.get('width', '—')}×{canvas.get('height', '—')} px · "
            f"{len(item.get('fields') or [])} Felder · Hintergrund: {bg_text}"
        )
        self.qsl_template_detail_label.configure(
            fg=theme.TEXT,
        )

    def _selected_qsos_for_qsl(
        self,
    ) -> list[dict]:
        if not hasattr(self, "tree"):
            return []

        selected = list(
            self.tree.selection()
        )

        if not selected:
            return []

        cached = getattr(
            self,
            "_qso_cached_by_id",
            {},
        )

        result: list[dict] = []
        missing: set[str] = set()

        for local_id in selected:
            qso = cached.get(
                str(local_id)
            )
            if isinstance(qso, dict):
                result.append(qso)
            else:
                missing.add(str(local_id))

        if missing:
            try:
                for item in self.store.scan():
                    local_id = str(
                        item.get("local_id") or ""
                    )
                    if local_id in missing:
                        result.append(item)
                        missing.discard(local_id)
            except Exception:
                pass

        by_id = {
            str(item.get("local_id") or ""): item
            for item in result
        }

        return [
            by_id[local_id]
            for local_id in selected
            if local_id in by_id
        ]

    def _queue_selected_qsl_emails(
        self,
        qsos: list[dict],
    ) -> None:
        profile = self._current_qsl_station_profile()

        if not profile:
            messagebox.showwarning(
                "QSL Card Manager",
                "Für das aktive Logger-Profil konnte kein QSL-Stationsprofil ermittelt werden.",
                parent=self,
            )
            return

        try:
            template = self._selected_qsl_template(
                profile
            )
        except Exception as exc:
            messagebox.showerror(
                "QSL Card Manager",
                str(exc),
                parent=self,
            )
            return

        if not template:
            messagebox.showwarning(
                "QSL Card Manager",
                "Für dieses Stationsprofil ist noch kein QSL-Motiv ausgewählt.",
                parent=self,
            )
            return

        connection_key = self.db.get_secret(
            "qsl_connection_key"
        ).strip()

        if not connection_key:
            messagebox.showwarning(
                "QSL Card Manager",
                "Bitte zuerst den QSL Connection Key konfigurieren.",
                parent=self,
            )
            return

        count = len(qsos)
        template_name = str(
            template.get("name", "QSL Template")
        )

        confirmed = messagebox.askyesno(
            "QSLs in Mail-Queue einreihen",
            (
                f"{count} ausgewählte QSOs als QSL-Mail vorbereiten?\n\n"
                f"Motiv: {template_name}\n\n"
                "Die Karten werden lokal erzeugt und hochgeladen. "
                "Danach übernimmt die serverseitige DA6IT.de Mail-Queue "
                "Empfängerprüfung, Limits und Duplikatschutz."
            ),
            parent=self,
        )

        if not confirmed:
            return

        self.qsl_mail_busy = True
        self._set_qsl_mail_button_state()
        self.status_var.set(
            f"{count} QSL-Karten werden für die Mail-Queue vorbereitet …"
        )

        db = self.db
        cache_root = (
            Path(self.data_dir)
            / "qsl-cache"
            / "template-assets"
        )

        def worker() -> None:
            try:
                client = QslClient(
                    connection_key,
                    timeout=30,
                )

                bootstrap = client.bootstrap()
                usage = (
                    bootstrap.get("mailUsage")
                    if isinstance(bootstrap, dict)
                    else {}
                )
                usage = usage if isinstance(usage, dict) else {}

                max_batch = int(
                    usage.get("queueBatchMax") or 1
                )

                result = queue_qsl_batch(
                    client,
                    QslStorage(db),
                    qsos,
                    template,
                    cache_root=cache_root,
                    max_batch=max_batch,
                )

                if not self.closing:
                    self.after(
                        0,
                        lambda: self._qsl_batch_queued(
                            result,
                            connection_key,
                        ),
                    )
            except Exception as exc:
                message = str(exc)
                if not self.closing:
                    self.after(
                        0,
                        lambda error=message: self._qsl_batch_failed(
                            error
                        ),
                    )

        threading.Thread(
            target=worker,
            name="qsl-batch-queue",
            daemon=True,
        ).start()

    def _qsl_batch_queued(
        self,
        result: QslQueueResult,
        connection_key: str,
    ) -> None:
        self.qsl_mail_busy = False
        self._set_qsl_mail_button_state()
        self.refresh_qsos(
            force=True,
            immediate=True,
        )

        self.status_var.set(
            f"QSL-Queue {result.job_id}: {result.queued} eingereiht."
        )

        details = [
            f"Vorbereitet: {result.prepared} von {result.requested}",
            f"In Queue: {result.queued}",
        ]

        if result.recipient_pending:
            details.append(
                f"Empfänger wird serverseitig geprüft: {result.recipient_pending}"
            )
        if result.no_email:
            details.append(
                f"Ohne QRZ-Mail: {result.no_email}"
            )
        if result.cooldown:
            details.append(
                f"Duplikatsperre: {result.cooldown}"
            )
        if result.failed:
            details.append(
                f"Lokal nicht vorbereitet: {result.failed}"
            )

        messagebox.showinfo(
            "QSL Card Manager",
            (
                "QSL-Mailauftrag wurde an die Server-Queue übergeben.\n\n"
                + "\n".join(details)
                + "\n\nDie Queue läuft auf DA6IT.de weiter."
            ),
            parent=self,
        )

        # One short follow-up only; no permanent polling/background service.
        self.after(
            15000,
            lambda: self._qsl_check_queue_once(
                result.job_id,
                list(result.qso_uids),
                connection_key,
            ),
        )

    def _qsl_batch_failed(
        self,
        message: str,
    ) -> None:
        self.qsl_mail_busy = False
        self._set_qsl_mail_button_state()
        self.refresh_qsos(
            force=True,
            immediate=True,
        )
        self.status_var.set(
            "QSL-Mail-Queue konnte nicht erstellt werden."
        )
        messagebox.showerror(
            "QSL Card Manager",
            str(message),
            parent=self,
        )

    def _qsl_check_queue_once(
        self,
        job_id: str,
        qso_uids: list[str],
        connection_key: str,
    ) -> None:
        if self.closing:
            return

        db = self.db

        def worker() -> None:
            try:
                client = QslClient(
                    connection_key,
                    timeout=20,
                )
                queue = client.queue_status(
                    job_id=job_id,
                    limit=min(500, max(1, len(qso_uids))),
                )

                status_response = client.qso_status(
                    qso_uids[:1000]
                )

                statuses = (
                    status_response.get("statuses")
                    if isinstance(status_response, dict)
                    else {}
                )
                statuses = statuses if isinstance(statuses, dict) else {}

                storage = QslStorage(db)
                for uid, payload in statuses.items():
                    if isinstance(payload, dict):
                        storage.set_status_snapshot(
                            uid,
                            payload,
                        )

                summary = (
                    queue.get("summary")
                    if isinstance(queue, dict)
                    else {}
                )
                summary = summary if isinstance(summary, dict) else {}

                if not self.closing:
                    self.after(
                        0,
                        lambda: self._qsl_queue_checked(
                            job_id,
                            summary,
                        ),
                    )
            except Exception:
                # Queue itself continues server-side; a one-time UI refresh
                # failure must not turn into repeated polling.
                return

        threading.Thread(
            target=worker,
            name="qsl-queue-status-once",
            daemon=True,
        ).start()

    def _qsl_queue_checked(
        self,
        job_id: str,
        summary: dict,
    ) -> None:
        self.refresh_qsos(
            force=True,
            immediate=True,
        )
        self.refresh_qsl_page()

        queued = int(summary.get("queued") or 0)
        sent = int(summary.get("sent") or 0)
        skipped = int(summary.get("skipped") or 0)
        failed = int(summary.get("failed") or 0)

        self.status_var.set(
            f"QSL-Queue {job_id}: {sent} versendet · {queued} offen · "
            f"{skipped} übersprungen · {failed} fehlgeschlagen"
        )

    def _selected_qso_for_qsl(
        self,
    ) -> dict | None:
        if not hasattr(
            self,
            "tree",
        ):
            return None

        selected = self.tree.selection()

        if not selected:
            return None

        local_id = str(
            selected[0]
        ).strip()

        qso = getattr(
            self,
            "_qso_cached_by_id",
            {},
        ).get(
            local_id
        )

        if isinstance(
            qso,
            dict,
        ):
            return qso

        try:
            for item in self.store.scan():
                if (
                    str(
                        item.get(
                            "local_id",
                            "",
                        )
                    )
                    == local_id
                ):
                    return item
        except Exception:
            pass

        return None

    def _selected_qsl_template(
        self,
        profile: str,
    ) -> dict | None:
        catalog = QslTemplateCatalog(
            self.db
        )

        template_id = (
            catalog.selected_template_id(
                profile
            )
        )

        if template_id is None:
            return None

        for item in catalog.cached_templates(
            profile
        ):
            if (
                int(
                    item.get(
                        "id",
                        0,
                    )
                )
                == int(
                    template_id
                )
            ):
                return item

        return None

    def _set_qsl_mail_button_state(
        self,
    ) -> None:
        if not hasattr(
            self,
            "qsl_mail_button",
        ):
            return

        self.qsl_mail_button.configure(
            state=(
                "disabled"
                if self.qsl_mail_busy
                else "normal"
            )
        )

    def send_selected_qsl_email(
        self,
    ) -> None:
        if self.qsl_mail_busy:
            return

        selected_qsos = self._selected_qsos_for_qsl()

        if len(selected_qsos) > 1:
            self._queue_selected_qsl_emails(
                selected_qsos
            )
            return

        qso = self._selected_qso_for_qsl()

        if not qso:
            messagebox.showwarning(
                "QSL Card Manager",
                "Bitte im Logbuch zuerst ein QSO auswählen.",
                parent=self,
            )
            return

        profile = self._current_qsl_station_profile()

        if not profile:
            messagebox.showwarning(
                "QSL Card Manager",
                "Für das aktive Logger-Profil konnte kein QSL-Stationsprofil ermittelt werden.",
                parent=self,
            )
            return

        try:
            template = self._selected_qsl_template(
                profile
            )
        except Exception as exc:
            messagebox.showerror(
                "QSL Card Manager",
                str(exc),
                parent=self,
            )
            return

        if not template:
            messagebox.showwarning(
                "QSL Card Manager",
                "Für dieses Stationsprofil ist noch kein QSL-Motiv ausgewählt. "
                "Bitte zuerst im QSL Card Manager ein Motiv laden und auswählen.",
                parent=self,
            )
            return

        connection_key = self.db.get_secret(
            "qsl_connection_key"
        ).strip()

        if not connection_key:
            messagebox.showwarning(
                "QSL Card Manager",
                "Bitte zuerst den QSL Connection Key konfigurieren.",
                parent=self,
            )
            return

        call = str(
            qso.get(
                "call",
                "",
            )
            or "—"
        ).strip().upper()

        qso_date = str(
            qso.get(
                "qso_date",
                "",
            )
            or ""
        ).strip()

        if len(qso_date) == 8:
            date_text = (
                f"{qso_date[6:8]}."
                f"{qso_date[4:6]}."
                f"{qso_date[0:4]}"
            )
        else:
            date_text = qso_date or "—"

        template_name = str(
            template.get(
                "name",
                "QSL Template",
            )
        )

        confirmed = messagebox.askyesno(
            "QSL per E-Mail senden",
            (
                f"QSL für {call} vom {date_text} wirklich senden?\n\n"
                f"Motiv: {template_name}\n"
                "Empfänger: wird serverseitig über QRZ.com geprüft\n\n"
                "Die Karte wird lokal erzeugt, zu DA6IT.de hochgeladen "
                "und anschließend genau eine QSL-Mail versendet."
            ),
            parent=self,
        )

        if not confirmed:
            return

        self.qsl_mail_busy = True
        self._set_qsl_mail_button_state()

        self.status_var.set(
            f"QSL für {call} wird erzeugt und versendet …"
        )

        db = self.db
        cache_root = (
            Path(self.data_dir)
            / "qsl-cache"
            / "template-assets"
        )

        def worker() -> None:
            try:
                client = QslClient(
                    connection_key,
                    timeout=30,
                )

                result = send_single_qsl(
                    client,
                    QslStorage(db),
                    qso,
                    template,
                    cache_root=cache_root,
                )

                if not self.closing:
                    self.after(
                        0,
                        lambda: self._qsl_mail_sent(
                            call,
                            result,
                        ),
                    )

            except Exception as exc:
                message = str(exc)

                if not self.closing:
                    self.after(
                        0,
                        lambda error=message: self._qsl_mail_failed(
                            call,
                            error,
                        ),
                    )

        threading.Thread(
            target=worker,
            name="qsl-single-mail-send",
            daemon=True,
        ).start()

    def _qsl_mail_sent(
        self,
        call: str,
        result: QslDeliveryResult,
    ) -> None:
        self.qsl_mail_busy = False
        self._set_qsl_mail_button_state()

        self.refresh_qsos(
            force=True,
            immediate=True,
        )
        self.refresh_qsl_page()

        self.status_var.set(
            f"QSL-Mail für {call} versendet."
        )

        recipient = (
            result.recipient
            or "QRZ-Empfänger"
        )

        messagebox.showinfo(
            "QSL Card Manager",
            (
                f"QSL-Mail für {call} wurde an den Mailtransport übergeben.\n\n"
                f"Empfänger: {recipient}\n"
                f"Motiv: {result.template_name}"
                + (
                    f"\nServer-Zeit: {result.sent_at}"
                    if result.sent_at
                    else ""
                )
            ),
            parent=self,
        )

    def _qsl_mail_failed(
        self,
        call: str,
        message: str,
    ) -> None:
        self.qsl_mail_busy = False
        self._set_qsl_mail_button_state()

        self.refresh_qsos(
            force=True,
            immediate=True,
        )
        self.refresh_qsl_page()

        self.status_var.set(
            f"QSL-Mail für {call} fehlgeschlagen."
        )

        messagebox.showerror(
            "QSL Card Manager",
            (
                f"QSL für {call} konnte nicht versendet werden.\n\n"
                + str(message)
            ),
            parent=self,
        )

    def preview_qsl_template(
        self,
    ) -> None:
        if self.qsl_preview_busy:
            return

        label = self.qsl_template_var.get()
        template = self.qsl_template_items.get(
            label
        )

        if not template:
            messagebox.showwarning(
                "QSL Card Manager",
                "Bitte zuerst ein QSL-Motiv auswählen.",
                parent=self,
            )
            return

        qsos = list(
            getattr(
                self,
                "_qso_cached_qsos",
                [],
            )
        )

        if not qsos:
            try:
                qsos = self.store.scan()
            except Exception as exc:
                messagebox.showerror(
                    "QSL Card Manager",
                    "Lokale QSOs konnten nicht geladen werden: "
                    + str(exc),
                    parent=self,
                )
                return

        qso = latest_qso(
            qsos
        )

        if not qso:
            messagebox.showwarning(
                "QSL Card Manager",
                "Für die Vorschau ist mindestens ein lokales QSO erforderlich.",
                parent=self,
            )
            return

        self.qsl_preview_busy = True
        self.qsl_preview_button.configure(
            state="disabled"
        )

        self.qsl_template_detail_var.set(
            "QSL-Vorschau wird erzeugt …"
        )
        self.qsl_template_detail_label.configure(
            fg=theme.MUTED,
        )

        cache_root = (
            Path(self.data_dir)
            / "qsl-cache"
            / "template-assets"
        )

        def worker() -> None:
            try:
                # Use the exact same PNG generation path as single-send and
                # batch preparation.  The preview therefore decodes the same
                # bytes that would later be uploaded to the QSL Card Manager.
                png_bytes = render_selected_qsl(
                    template,
                    qso,
                    cache_root=cache_root,
                )

                with Image.open(
                    io.BytesIO(
                        png_bytes
                    )
                ) as rendered:
                    rendered.load()
                    preview = rendered.convert(
                        "RGB"
                    )

                preview.thumbnail(
                    (760, 490),
                )

                values = qso_designer_values(
                    qso
                )

                qso_label = (
                    f"{values.get('qso.call', '—')} · "
                    f"{values.get('qso.date', '—')} · "
                    f"{values.get('qso.time_utc', '—')} UTC"
                )

                if not self.closing:
                    self.after(
                        0,
                        lambda: self._show_qsl_preview(
                            preview,
                            str(
                                template.get(
                                    "name",
                                    "QSL",
                                )
                            ),
                            qso_label,
                        ),
                    )

            except Exception as exc:
                message = str(exc)

                if not self.closing:
                    self.after(
                        0,
                        lambda error=message: self._qsl_preview_failed(
                            error
                        ),
                    )

        threading.Thread(
            target=worker,
            name="qsl-preview-render",
            daemon=True,
        ).start()

    def _show_qsl_preview(
        self,
        image,
        template_name: str,
        qso_label: str,
    ) -> None:
        self.qsl_preview_busy = False
        self.qsl_preview_button.configure(
            state="normal"
        )
        self._update_qsl_template_details()

        window = self.qsl_preview_window

        if (
            window is None
            or not window.winfo_exists()
        ):
            window = tk.Toplevel(
                self
            )
            window.title(
                "QSL Vorschau"
            )
            window.transient(
                self
            )
            window.resizable(
                True,
                True,
            )
            window.configure(
                bg=theme.BG,
            )
            self.qsl_preview_window = window

            frame = tk.Frame(
                window,
                bg=theme.BG,
                padx=14,
                pady=14,
            )
            frame.pack(
                fill="both",
                expand=True,
            )

            self.qsl_preview_title_label = tk.Label(
                frame,
                bg=theme.BG,
                fg=theme.TEXT,
                font=(
                    "Segoe UI Semibold",
                    11,
                ),
                anchor="w",
            )
            self.qsl_preview_title_label.pack(
                fill="x",
                pady=(0, 8),
            )

            self.qsl_preview_image_label = tk.Label(
                frame,
                bg=theme.PHOTO_BG,
                bd=1,
                relief="solid",
            )
            self.qsl_preview_image_label.pack(
                fill="both",
                expand=True,
            )

            ttk.Button(
                frame,
                text="Schließen",
                style="Secondary.TButton",
                command=window.destroy,
            ).pack(
                anchor="e",
                pady=(10, 0),
            )

        self.qsl_preview_photo = ImageTk.PhotoImage(
            image
        )

        self.qsl_preview_image_label.configure(
            image=self.qsl_preview_photo,
        )

        self.qsl_preview_title_label.configure(
            text=(
                f"{template_name} · {qso_label}"
            )
        )

        width, height = image.size

        window.geometry(
            f"{max(520, width + 30)}x"
            f"{max(390, height + 105)}"
        )

        window.lift()
        window.focus_set()

    def _qsl_preview_failed(
        self,
        message: str,
    ) -> None:
        self.qsl_preview_busy = False

        if hasattr(
            self,
            "qsl_preview_button",
        ):
            self.qsl_preview_button.configure(
                state="normal"
            )

        self.qsl_template_detail_var.set(
            "QSL-Vorschau konnte nicht erzeugt werden: "
            + str(message)
        )
        self.qsl_template_detail_label.configure(
            fg=theme.ERR,
        )

    def _qsl_template_selected(
        self,
        _event=None,
    ) -> None:
        profile = self._current_qsl_station_profile()
        label = self.qsl_template_var.get()
        item = self.qsl_template_items.get(
            label
        )

        if not profile or not item:
            return

        try:
            QslTemplateCatalog(
                self.db
            ).set_selected_template(
                profile,
                int(item["id"]),
            )
        except Exception as exc:
            self.qsl_template_detail_var.set(
                "Motivauswahl konnte nicht gespeichert werden: "
                + str(exc)
            )
            self.qsl_template_detail_label.configure(
                fg=theme.ERR,
            )
            return

        self._update_qsl_template_details()

    def load_qsl_templates(
        self,
    ) -> None:
        if self.qsl_template_busy:
            return

        profile_candidates = (
            self._qsl_station_profile_candidates()
        )
        profile = (
            profile_candidates[0]
            if profile_candidates
            else ""
        )

        if not profile:
            messagebox.showwarning(
                "QSL Card Manager",
                "Bitte zuerst ein Stationsrufzeichen im aktiven Profil konfigurieren.",
                parent=self,
            )
            return

        connection_key = self.db.get_secret(
            "qsl_connection_key"
        ).strip()

        if not connection_key:
            messagebox.showwarning(
                "QSL Card Manager",
                "Bitte zuerst den Connection Key konfigurieren.",
                parent=self,
            )
            return

        self.qsl_template_busy = True
        self.qsl_template_refresh_button.configure(
            state="disabled"
        )
        self.qsl_template_detail_var.set(
            "Motive werden vom QSL Card Manager geladen …"
        )
        self.qsl_template_detail_label.configure(
            fg=theme.MUTED,
        )

        db = self.db

        def worker() -> None:
            try:
                client = QslClient(
                    connection_key,
                    timeout=20,
                )

                responses: dict[str, dict] = {}
                last_error: Exception | None = None

                for candidate in profile_candidates:
                    try:
                        responses[candidate] = (
                            client.templates(
                                candidate
                            )
                        )
                    except Exception as exc:
                        last_error = exc

                if not responses:
                    if last_error is not None:
                        raise last_error
                    raise QslTemplateError(
                        "Kein Stationsprofil konnte geladen werden"
                    )

                (
                    resolved_profile,
                    response,
                    personal_count,
                ) = choose_template_profile_response(
                    profile_candidates,
                    responses,
                )

                catalog = QslTemplateCatalog(
                    db
                )

                templates = catalog.cache_response(
                    resolved_profile,
                    response,
                )

                db.set_setting(
                    "qsl_layout_profile_key",
                    resolved_profile,
                )

                if not self.closing:
                    self.after(
                        0,
                        lambda: self._qsl_templates_loaded(
                            resolved_profile,
                            len(templates),
                            personal_count,
                        ),
                    )

            except Exception as exc:
                message = str(exc)

                if not self.closing:
                    self.after(
                        0,
                        lambda error=message: self._qsl_templates_failed(
                            error
                        ),
                    )

        threading.Thread(
            target=worker,
            name="qsl-template-catalog",
            daemon=True,
        ).start()

    def _qsl_templates_loaded(
        self,
        profile: str,
        count: int,
        personal_count: int,
    ) -> None:
        self.qsl_template_busy = False

        if (
            profile
            != self._current_qsl_station_profile()
        ):
            self.refresh_qsl_page()
            return

        self._refresh_qsl_template_catalog()

        suffix = (
            "Motiv"
            if count == 1
            else "Motive"
        )

        current = self.qsl_template_detail_var.get()

        if current:
            layout_text = (
                f" · {personal_count} mit persönlicher Feldanordnung"
                if personal_count
                else ""
            )
            self.qsl_template_detail_var.set(
                f"{count} {suffix} vom Server geladen"
                f"{layout_text} · Profil: {profile}.\n"
                + current
            )

        self.qsl_template_refresh_button.configure(
            state="normal"
        )

    def _qsl_templates_failed(
        self,
        message: str,
    ) -> None:
        self.qsl_template_busy = False
        self.qsl_template_detail_var.set(
            "Motive konnten nicht vom Server geladen werden: "
            + str(message)
            + "\nEin vorhandener lokaler Cache bleibt erhalten."
        )
        self.qsl_template_detail_label.configure(
            fg=theme.ERR,
        )
        self.qsl_template_refresh_button.configure(
            state="normal"
        )

    def refresh_qsl_page(self) -> None:
        if not hasattr(self, "qsl_local_status_var"):
            return

        try:
            storage = QslStorage(self.db)
            mappings = len(storage.list_mappings())
            pending = len(
                storage.list_pending_actions(limit=5000)
            )
        except Exception as exc:
            self.qsl_local_status_var.set(
                "Lokaler QSL-Status konnte nicht geladen werden: "
                + str(exc)
            )
            return

        if getattr(self, "_qso_view_loaded", False):
            qso_text = str(
                len(getattr(self, "_qso_cached_qsos", []))
            )
        else:
            qso_text = (
                "loading"
                if self.language == "en"
                else "wird noch geladen"
            )

        has_key = bool(
            self.db.get_secret("qsl_connection_key").strip()
        )

        if self.language == "en":
            key_text = "configured" if has_key else "not configured"
            self.qsl_local_status_var.set(
                f"Local QSOs: {qso_text}\n"
                f"qsoUid mappings: {mappings}\n"
                f"Pending offline actions: {pending}\n"
                f"Connection key: {key_text}"
            )
        else:
            key_text = "eingerichtet" if has_key else "nicht eingerichtet"
            self.qsl_local_status_var.set(
                f"Lokale QSOs: {qso_text}\n"
                f"qsoUid-Mappings: {mappings}\n"
                f"Offene Offline-Aktionen: {pending}\n"
                f"Connection Key: {key_text}"
            )

        if hasattr(self, "qsl_sync_button"):
            self.qsl_sync_button.configure(
                state=(
                    "disabled"
                    if self.qsl_sync_busy
                    or self.qsl_background_busy
                    or not has_key
                    else "normal"
                )
            )

        if hasattr(
            self,
            "qsl_template_refresh_button",
        ):
            self.qsl_template_refresh_button.configure(
                state=(
                    "disabled"
                    if self.qsl_template_busy
                    or self.qsl_background_busy
                    or not has_key
                    else "normal"
                )
            )

        if hasattr(
            self,
            "qsl_preview_button",
        ):
            self.qsl_preview_button.configure(
                state=(
                    "disabled"
                    if self.qsl_preview_busy
                    or not self.qsl_template_items
                    else "normal"
                )
            )

        self._refresh_qsl_server_status()
        self._refresh_qsl_template_catalog()

    def _refresh_qsl_server_status(self) -> None:
        if not hasattr(self, "qsl_server_status_var"):
            return

        bootstrap = self.qsl_last_bootstrap
        if not isinstance(bootstrap, dict):
            return

        contract = str(bootstrap.get("contract") or "—")
        core = str(bootstrap.get("coreVersion") or "—")
        api = str(bootstrap.get("apiVersion") or "—")

        usage = bootstrap.get("mailUsage")
        usage = usage if isinstance(usage, dict) else {}

        lines = [
            f"Contract: {contract}",
            f"Core: {core} · API: {api}",
        ]

        hour_limit = usage.get("hourLimit")
        hour_remaining = usage.get("hourRemaining")
        day_limit = usage.get("dayLimit")
        day_remaining = usage.get("dayRemaining")
        queued = usage.get("queued")
        mail_enabled = usage.get("mailEnabled")

        if hour_limit is not None:
            if self.language == "en":
                lines.append(
                    f"Hour: {hour_remaining if hour_remaining is not None else '—'} "
                    f"of {hour_limit} available"
                )
            else:
                lines.append(
                    f"Stunde: {hour_remaining if hour_remaining is not None else '—'} "
                    f"von {hour_limit} verfügbar"
                )

        if day_limit is not None:
            if self.language == "en":
                lines.append(
                    f"Day: {day_remaining if day_remaining is not None else '—'} "
                    f"of {day_limit} available"
                )
            else:
                lines.append(
                    f"Tag: {day_remaining if day_remaining is not None else '—'} "
                    f"von {day_limit} verfügbar"
                )

        if queued is not None:
            lines.append(f"Queue: {queued}")

        if mail_enabled is not None:
            if self.language == "en":
                lines.append(
                    "Mail sending: "
                    + ("enabled" if bool(mail_enabled) else "disabled")
                )
            else:
                lines.append(
                    "Mailversand: "
                    + ("aktiv" if bool(mail_enabled) else "deaktiviert")
                )

        self.qsl_server_status_var.set("\n".join(lines))
        self.qsl_server_status_label.configure(fg=theme.OK)

    def sync_qsl_now(self) -> None:
        if (
            self.qsl_sync_busy
            or self.qsl_background_busy
        ):
            return

        connection_key = self.db.get_secret(
            "qsl_connection_key"
        ).strip()

        if not connection_key:
            messagebox.showwarning(
                "QSL Card Manager",
                (
                    "Bitte zuerst unter Einstellungen → QSL Card Manager "
                    "einen Connection Key eintragen und speichern."
                ),
                parent=self,
            )
            return

        self.qsl_sync_busy = True
        self.qsl_sync_button.configure(state="disabled")

        running_text = (
            "QSL synchronization is running …"
            if self.language == "en"
            else "QSL-Synchronisierung läuft …"
        )
        self.qsl_sync_status_var.set(running_text)
        self.qsl_sync_status_label.configure(fg=theme.MUTED)
        self.status_var.set(running_text)

        db = self.db
        store = self.store

        def worker() -> None:
            try:
                qsos = store.scan()

                if not qsos:
                    raise RuntimeError(
                        "No local QSOs available."
                        if self.language == "en"
                        else "Keine lokalen QSOs vorhanden."
                    )

                client = QslClient(
                    connection_key,
                    timeout=20,
                )
                bootstrap = client.bootstrap()
                storage = QslStorage(db)

                result = sync_qsos(
                    client,
                    storage,
                    qsos,
                )

                recipient_result = resolve_pending_recipients(
                    client,
                    storage,
                    limit=DEFAULT_RECIPIENT_BATCH,
                )

                if not self.closing:
                    self.after(
                        0,
                        lambda: self._qsl_sync_ok(
                            bootstrap,
                            result,
                            recipient_result,
                        ),
                    )

            except Exception as exc:
                error = str(exc)
                if not self.closing:
                    self.after(
                        0,
                        lambda message=error: self._qsl_sync_failed(
                            message
                        ),
                    )

        threading.Thread(
            target=worker,
            name="qsl-card-manager-sync",
            daemon=True,
        ).start()

    def _qsl_sync_ok(
        self,
        bootstrap: dict,
        result: QslSyncResult,
        recipient_result: QslRecipientResult,
    ) -> None:
        self.qsl_sync_busy = False
        self.qsl_last_bootstrap = dict(bootstrap)
        self.qsl_last_result = result
        self.qsl_last_recipient_result = recipient_result

        if self.language == "en":
            summary = (
                f"Processed: {result.total}\n"
                f"Created: {result.created} · Updated: {result.updated} · "
                f"Unchanged: {result.unchanged} · Ignored: {result.ignored}\n"
                f"qsoUid mappings written: {result.mapped}"
            )
            if result.synced_at:
                summary += f"\nServer sync time: {result.synced_at}"

            summary += (
                f"\nRecipient checks: {recipient_result.processed} · "
                f"email: {recipient_result.email} · "
                f"no email: {recipient_result.no_email} · "
                f"not found: {recipient_result.not_found} · "
                f"cached: {recipient_result.cached} · "
                f"errors: {recipient_result.failed} · "
                f"pending: {recipient_result.pending_after}"
            )

            status = f"QSL sync completed: {result.total} QSO(s)"
        else:
            summary = (
                f"Verarbeitet: {result.total}\n"
                f"Neu: {result.created} · Aktualisiert: {result.updated} · "
                f"Unverändert: {result.unchanged} · Ignoriert: {result.ignored}\n"
                f"qsoUid-Mappings gespeichert: {result.mapped}"
            )
            if result.synced_at:
                summary += f"\nServer-Synczeit: {result.synced_at}"

            summary += (
                f"\nEmpfänger geprüft: {recipient_result.processed} · "
                f"mit Mail: {recipient_result.email} · "
                f"ohne Mail: {recipient_result.no_email} · "
                f"nicht gefunden: {recipient_result.not_found} · "
                f"aus Cache: {recipient_result.cached} · "
                f"Fehler: {recipient_result.failed} · "
                f"noch offen: {recipient_result.pending_after}"
            )

            status = f"QSL-Sync abgeschlossen: {result.total} QSO(s)"

        self.qsl_result_var.set(summary)
        self.qsl_result_label.configure(fg=theme.OK)
        self.qsl_sync_status_var.set(status)
        self.qsl_sync_status_label.configure(fg=theme.OK)
        self.status_var.set(status)
        self.refresh_qsl_page()
        self.refresh_qsos(
            force=True,
            immediate=False,
        )

    def _qsl_sync_failed(self, message: str) -> None:
        self.qsl_sync_busy = False
        prefix = (
            "QSL synchronization failed: "
            if self.language == "en"
            else "QSL-Synchronisierung fehlgeschlagen: "
        )
        text = prefix + str(message)
        self.qsl_sync_status_var.set(text)
        self.qsl_sync_status_label.configure(fg=theme.ERR)
        self.status_var.set(text)
        self.refresh_qsl_page()
