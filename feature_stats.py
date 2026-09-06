from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
import threading
import tkinter as tk
from tkinter import ttk
from ui_theme import theme


class StatsFeatureMixin:
    def _init_stats_feature(self) -> None:
        self._stats_refresh_running = False
        self._stats_request_generation = 0
        self._stats_rendered_key = None
        self._stats_pending_key = None

    def _build_stats_page(self):
        p = self._new_page("stats")
        for c in range(4):
            p.columnconfigure(c, weight=1, uniform="stats")

        controls = self._card(p, row=0, column=0, columnspan=4, sticky="ew", pady=(0, 10))
        ttk.Label(controls, text="Auswertung", style="CardTitle.TLabel").pack(side="left")
        tk.Label(controls, text="Zeitraum", bg=theme.CARD, fg=theme.MUTED, font=("Segoe UI", 9)).pack(side="left", padx=(24, 7))
        stat_periods = ("Gesamt", "Dieses Jahr", "Dieser Monat", "Diese Woche", "Heute (UTC)")
        self.stats_period_var = tk.StringVar(value=self._tr("Gesamt"))
        period = ttk.Combobox(controls, textvariable=self.stats_period_var, state="readonly", width=18,
                              values=tuple(self._tr(value) for value in stat_periods))
        period.pack(side="left")
        period.bind("<<ComboboxSelected>>", lambda e: self.refresh_stats())
        tk.Label(controls, text="Operator:", bg=theme.CARD, fg=theme.MUTED, font=("Segoe UI", 9)).pack(side="left", padx=(18, 6))
        self.stats_operator_var = tk.StringVar(value=self._tr("Alle Operatoren"))
        self.stats_operator_combo = ttk.Combobox(controls, textvariable=self.stats_operator_var, state="readonly", width=18,
                                                  values=(self._tr("Alle Operatoren"),))
        self.stats_operator_combo.pack(side="left")
        self.stats_operator_combo.bind("<<ComboboxSelected>>", lambda e: self.refresh_stats())
        self.stats_hint = tk.Label(controls, text="", bg=theme.CARD, fg=theme.MUTED, font=("Segoe UI", 9))
        self.stats_hint.pack(side="right")

        self.stats_metric_vars = []
        for idx, title in enumerate(("QSOs", "DXCC-Entities", "Bänder", "Modes")):
            card = self._card(p, row=1, column=idx, sticky="nsew", padx=(0 if idx == 0 else 5, 0 if idx == 3 else 5), pady=(0, 10))
            var = tk.StringVar(value="0")
            self.stats_metric_vars.append(var)
            tk.Label(card, text=title.upper(), bg=theme.CARD, fg=theme.MUTED, font=("Segoe UI Semibold", 8)).pack(anchor="w")
            tk.Label(card, textvariable=var, bg=theme.CARD, fg=theme.TEXT, font=("Segoe UI Semibold", 25)).pack(anchor="w", pady=(4, 0))

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

    @staticmethod
    def _stats_filter_period(qsos: list[dict], period: str, now: datetime) -> list[dict]:
        if period == "Heute (UTC)":
            key = now.strftime("%Y-%m-%d")
            return [q for q in qsos if q.get("qso_date") == key]
        if period == "Dieser Monat":
            key = now.strftime("%Y-%m")
            return [
                q for q in qsos
                if str(q.get("qso_date", "")).startswith(key)
            ]
        if period == "Diese Woche":
            current_week = now.date().isocalendar()[:2]
            out = []
            for q in qsos:
                try:
                    d = datetime.strptime(
                        str(q.get("qso_date", "")), "%Y-%m-%d",
                    ).date()
                    if d.isocalendar()[:2] == current_week:
                        out.append(q)
                except Exception:
                    pass
            return out
        if period == "Dieses Jahr":
            key = now.strftime("%Y")
            return [
                q for q in qsos
                if str(q.get("qso_date", "")).startswith(key)
            ]
        return list(qsos)

    @staticmethod
    def _stats_filter_operator(
        qsos: list[dict],
        operator: str,
        all_operators_label: str,
    ) -> list[dict]:
        if operator and operator not in {"Alle Operatoren", all_operators_label}:
            wanted = operator.upper()
            return [
                q for q in qsos
                if str(q.get("operator_call") or "").upper() == wanted
            ]
        return list(qsos)


    def _render_stat_bars(self, parent, counts: Counter, total: int, max_rows: int = 7):
        for w in parent.winfo_children():
            w.destroy()
        rows = [(str(k), int(v)) for k, v in counts.most_common(max_rows) if str(k).strip()]
        if not rows:
            tk.Label(parent, text="Noch keine Daten", bg=theme.CARD, fg=theme.MUTED, font=("Segoe UI", 9)).pack(anchor="w", pady=8)
            return
        maximum = max(v for _, v in rows) or 1
        parent.columnconfigure(1, weight=1)
        for r, (name, count) in enumerate(rows):
            label = name if len(name) <= 24 else name[:22] + "…"
            tk.Label(parent, text=label, bg=theme.CARD, fg=theme.TEXT, font=("Segoe UI", 9), anchor="w", width=15).grid(row=r, column=0, sticky="w", pady=2)
            bar = ttk.Progressbar(parent, style="Stats.Horizontal.TProgressbar", orient="horizontal", mode="determinate", maximum=maximum, value=count)
            bar.grid(row=r, column=1, sticky="ew", padx=(7, 8), pady=4)
            pct = (count / total * 100.0) if total else 0.0
            tk.Label(parent, text=f"{count}  ·  {pct:.0f}%", bg=theme.CARD, fg=theme.MUTED, font=("Segoe UI", 8), width=11, anchor="e").grid(row=r, column=2, sticky="e")

    def _render_stat_rank(self, parent, counts: Counter, max_rows: int = 8):
        for w in parent.winfo_children():
            w.destroy()
        rows = [(str(k), int(v)) for k, v in counts.most_common(max_rows) if str(k).strip()]
        if not rows:
            tk.Label(parent, text="Noch keine Daten", bg=theme.CARD, fg=theme.MUTED, font=("Segoe UI", 9)).pack(anchor="w", pady=8)
            return
        for i, (name, count) in enumerate(rows, 1):
            row = tk.Frame(parent, bg=theme.CARD)
            row.pack(fill="x", pady=2)
            tk.Label(row, text=f"{i}.", bg=theme.CARD, fg=theme.MUTED, font=("Segoe UI", 8), width=3, anchor="w").pack(side="left")
            tk.Label(row, text=name if len(name) <= 23 else name[:21] + "…", bg=theme.CARD, fg=theme.TEXT, font=("Segoe UI", 9), anchor="w").pack(side="left", fill="x", expand=True)
            tk.Label(row, text=str(count), bg=theme.CARD, fg=theme.TEXT, font=("Segoe UI Semibold", 9), anchor="e").pack(side="right")

    def _render_sync_stats(self, result: dict):
        parent = self.stats_sync_frame
        for w in parent.winfo_children():
            w.destroy()

        linked = int(result.get("linked") or 0)
        local = int(result.get("local") or 0)
        issues = int(result.get("issues") or 0)
        qsl = result.get("qsl") or {}
        pota = int(result.get("pota") or 0)
        sota = int(result.get("sota") or 0)
        wwff = int(result.get("wwff") or 0)

        def add_row(label, value, color=theme.TEXT):
            r = tk.Frame(parent, bg=theme.CARD)
            r.pack(fill="x", pady=2)
            tk.Label(
                r, text=label, bg=theme.CARD, fg=theme.MUTED,
                font=("Segoe UI", 9), anchor="w",
            ).pack(side="left")
            tk.Label(
                r, text=value, bg=theme.CARD, fg=color,
                font=("Segoe UI Semibold", 9), anchor="e",
            ).pack(side="right")

        add_row("WAVELOG", str(linked), theme.OK)
        add_row("LOCAL ONLY", str(local), theme.MUTED)
        if issues:
            add_row("Offene Sync-Themen", str(issues), theme.WARN)
        ttk.Separator(parent, orient="horizontal").pack(fill="x", pady=6)

        for svc, label in (
            ("qrz", "QRZ"),
            ("lotw", "LoTW"),
            ("eqsl", "eQSL"),
            ("clublog", "ClubLog"),
            ("dcl", "DCL"),
        ):
            c = qsl.get(svc) or Counter()
            parts = []
            if c.get("confirmed"):
                parts.append(f"{c['confirmed']} ✓")
            if c.get("sent"):
                parts.append(f"{c['sent']} ↑")
            if c.get("pending"):
                parts.append(f"{c['pending']} …")
            if c.get("unknown"):
                parts.append(f"{c['unknown']} ?")
            if c.get("none"):
                parts.append(f"{c['none']} —")
            add_row(label, " · ".join(parts) if parts else "—")

        ttk.Separator(parent, orient="horizontal").pack(fill="x", pady=6)
        add_row("Aktivitäten", f"POTA {pota}  ·  SOTA {sota}  ·  WWFF {wwff}")


    def refresh_stats(self):
        if not hasattr(self, "stats_metric_vars"):
            return

        # Statistics depend on the shared QSO cache. If it is still loading or
        # dirty, keep the page responsive and wait for the fresh snapshot.
        if (
            not getattr(self, "_qso_view_loaded", False)
            or getattr(self, "_qso_view_dirty", False)
        ):
            self.stats_hint.configure(text="Statistiken werden im Hintergrund aktualisiert …")
            self.refresh_qsos(force=False, immediate=True)
            return

        periods = ("Gesamt", "Dieses Jahr", "Dieser Monat", "Diese Woche", "Heute (UTC)")
        period = self._canonical_choice(self.stats_period_var.get(), periods)
        all_operators_label = self._tr("Alle Operatoren")
        operator = self.stats_operator_var.get() or all_operators_label
        cache_generation = int(getattr(self, "_qso_cache_generation", 0))
        key = (cache_generation, period, operator)

        if self._stats_rendered_key == key:
            return

        # If the exact same request is already running, there is nothing else
        # to do. A changed filter increments the request generation so the old
        # worker result is discarded.
        if self._stats_refresh_running and self._stats_pending_key == key:
            return

        self._stats_request_generation += 1
        request_generation = self._stats_request_generation
        self._stats_refresh_running = True
        self._stats_pending_key = key
        self.stats_hint.configure(text="Statistiken werden berechnet …")

        qsos = [dict(q) for q in getattr(self, "_qso_cached_qsos", [])]
        meta_by_id = dict(getattr(self, "_qso_cached_meta_by_id", {}))
        qsl_by_wid = dict(getattr(self, "_qso_cached_qsl_by_wid", {}))
        now = datetime.now(timezone.utc)
        country_db = self.country_db

        def worker():
            try:
                operators_all = sorted({
                    str(q.get("operator_call") or "").upper()
                    for q in qsos
                    if str(q.get("operator_call") or "").strip()
                })

                period_qsos = self._stats_filter_period(qsos, period, now)
                operator_counts = Counter(
                    (q.get("operator_call") or "Unbekannt").upper()
                    for q in period_qsos
                )
                filtered = self._stats_filter_operator(
                    period_qsos,
                    operator,
                    all_operators_label,
                )

                enriched = []
                for original in filtered:
                    q = dict(original)
                    if not q.get("country") and q.get("call"):
                        info = country_db.lookup(q.get("call", ""))
                        if info:
                            q["country"] = info.country
                            q["cont"] = info.cont
                            q["cqz"] = info.cqz
                            q["ituz"] = info.ituz
                    enriched.append(q)

                countries = Counter(
                    q.get("country", "") for q in enriched if q.get("country")
                )
                bands = Counter(
                    q.get("band", "") for q in enriched if q.get("band")
                )
                modes = Counter(
                    q.get("mode", "") for q in enriched if q.get("mode")
                )
                calls = Counter(
                    q.get("call", "") for q in enriched if q.get("call")
                )

                linked = local = issues = 0
                qsl = {
                    name: Counter()
                    for name in ("qrz", "lotw", "eqsl", "clublog", "dcl")
                }
                pota = sota = wwff = 0

                for q in enriched:
                    local_id = str(q.get("local_id") or "")
                    meta = meta_by_id.get(local_id)
                    wid = meta.get("wavelog_id") if meta else None
                    if wid is not None:
                        linked += 1
                        try:
                            st = qsl_by_wid.get(int(wid), {})
                        except (TypeError, ValueError):
                            st = {}
                        for svc in qsl:
                            qsl[svc][str(st.get(svc, "unknown"))] += 1
                    else:
                        local += 1
                    if meta and meta.get("status") in (
                        "modified", "conflict", "error", "pending_delete",
                    ):
                        issues += 1
                    pota += 1 if q.get("pota_ref") or q.get("my_pota_ref") else 0
                    sota += 1 if q.get("sota_ref") or q.get("my_sota_ref") else 0
                    wwff += 1 if q.get("wwff_ref") or q.get("my_wwff_ref") else 0

                result = {
                    "key": key,
                    "operators_all": operators_all,
                    "count": len(enriched),
                    "countries": countries,
                    "bands": bands,
                    "modes": modes,
                    "calls": calls,
                    "operator_counts": operator_counts,
                    "sync": {
                        "linked": linked,
                        "local": local,
                        "issues": issues,
                        "qsl": qsl,
                        "pota": pota,
                        "sota": sota,
                        "wwff": wwff,
                    },
                }
                if not self.closing:
                    self.after(
                        0,
                        lambda: self._stats_refresh_ready(
                            request_generation, result,
                        ),
                    )
            except Exception as exc:
                if not self.closing:
                    message = repr(exc)
                    self.after(
                        0,
                        lambda: self._stats_refresh_failed(
                            request_generation, message,
                        ),
                    )

        threading.Thread(
            target=worker,
            name="stats-refresh",
            daemon=True,
        ).start()

    def _stats_refresh_ready(self, request_generation: int, result: dict):
        if request_generation != self._stats_request_generation:
            return

        self._stats_refresh_running = False
        self._stats_pending_key = None

        # The QSO cache may have been refreshed while the stats worker was
        # running. Never render statistics calculated from an old snapshot.
        if result.get("key", (None,))[0] != getattr(self, "_qso_cache_generation", 0):
            self.refresh_stats()
            return

        operators_all = list(result.get("operators_all") or [])
        all_operators = self._tr("Alle Operatoren")
        values = [all_operators] + operators_all
        self.stats_operator_combo.configure(values=values)
        if self.stats_operator_var.get() not in values:
            self.stats_operator_var.set(all_operators)

        count = int(result.get("count") or 0)
        countries = result.get("countries") or Counter()
        bands = result.get("bands") or Counter()
        modes = result.get("modes") or Counter()
        calls = result.get("calls") or Counter()
        operator_counts = result.get("operator_counts") or Counter()

        self.stats_metric_vars[0].set(str(count))
        self.stats_metric_vars[1].set(str(len(countries)))
        self.stats_metric_vars[2].set(str(len(bands)))
        self.stats_metric_vars[3].set(str(len(modes)))
        self.stats_hint.configure(
            text=(
                f"{self.stats_period_var.get()} · "
                f"{self.stats_operator_var.get()} · lokale ADI-Daten"
            )
        )

        self._render_stat_bars(self.stats_bands_frame, bands, count, 8)
        self._render_stat_bars(self.stats_modes_frame, modes, count, 8)
        self._render_stat_rank(self.stats_countries_frame, countries, 8)
        self._render_stat_rank(self.stats_calls_frame, calls, 8)
        self._render_stat_rank(self.stats_operators_frame, operator_counts, 8)
        self._render_sync_stats(result.get("sync") or {})
        self._stats_rendered_key = result["key"]

    def _stats_refresh_failed(self, request_generation: int, message: str):
        if request_generation != self._stats_request_generation:
            return
        self._stats_refresh_running = False
        self._stats_pending_key = None
        self.stats_hint.configure(text="Statistiken konnten nicht aktualisiert werden")
        try:
            from app_common import write_startup_log
            write_startup_log("Statistik-Refresh fehlgeschlagen: " + message)
        except Exception:
            pass
