"""Active DXpeditions (v0.24.0).

Shows only DXpeditions spotted within the last 30 minutes, with band, mode
and frequency of every active band, the worked status from the local logbook
(callsign and DXCC entity per band and mode), beam heading and distance from
the station locator.

Sources:
* DA6IT.de DXpedition calendar (public REST API of the website plugin)
  ``https://da6it.de/wp-json/da6it/v1/dxpeditions`` – callsigns, aliases,
  dates, QSL route, info.
* DA6IT.de spot summary ``…/dxpeditions/spots`` – per DXpedition the latest
  spot and the latest spot per band of the last 60 minutes.
* The logger's own DX Cluster connection, when it is running.

Network access happens only while this page is open (and can be switched
off); nothing is sent except the HTTP request itself.
"""
from __future__ import annotations

import json
import threading
import time
import urllib.request
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import tkinter as tk
from tkinter import ttk

from app_common import write_startup_log
from dx_cluster import DxSpot, normalize_worked_mode
from logger_core import APP_NAME, VERSION, app_data_dir, band_from_mhz, secure_urlopen
from qso_tree_view import apply_row_diff, insert_row, plan_row_diff
from ui_theme import theme
from xota import distance_m, initial_bearing_degrees, maidenhead_coordinates

DXPED_CALENDAR_URL = "https://da6it.de/wp-json/da6it/v1/dxpeditions"
DXPED_SPOTS_URL = "https://da6it.de/wp-json/da6it/v1/dxpeditions/spots"
# "Active" = spotted within this window (decision DA6IT 21.11.2026).
DXPED_ACTIVE_SECONDS = 30 * 60
DXPED_SPOTS_REFRESH_MS = 60_000
DXPED_RENDER_TICK_MS = 15_000
DXPED_CALENDAR_MAX_AGE_SECONDS = 3 * 3600
DXPED_MAX_RESPONSE_BYTES = 2_000_000
DXPED_CACHE_FILE = "dxpeditions-calendar.json"
SETTING_DXPED_AUTO = "dxped_auto_refresh"

# Status keys in priority order (most interesting first) with German labels.
DXPED_STATUS_LABELS = {
    "new_country": "Neues Land!",
    "new_slot": "Neu auf Band/Mode",
    "new_call": "Land ✓, Call neu",
    "worked": "✓ gearbeitet",
}
DXPED_STATUS_ORDER = {key: index for index, key in enumerate(DXPED_STATUS_LABELS)}

DXPED_COLUMNS = (
    # key, German heading, width, anchor, stretch
    ("call", "Rufzeichen", 96, "w", False),
    ("country", "Land", 130, "w", False),
    ("band", "Band", 50, "center", False),
    ("mode", "Mode", 52, "center", False),
    ("frequency", "MHz", 76, "e", False),
    ("age", "Spot vor", 66, "e", False),
    ("status", "Status", 124, "w", False),
    ("worked", "Gearbeitet", 130, "w", True),
    ("heading", "Richtung", 80, "e", False),
    ("distance", "Entfernung", 92, "e", False),
    ("until", "bis", 56, "center", False),
)

_DIRECTIONS_DE = ("N", "NNO", "NO", "ONO", "O", "OSO", "SO", "SSO", "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW")
_DIRECTIONS_EN = ("N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE", "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW")


# --------------------------------------------------------------------------
# Data model and pure logic (unit tested without Tk or network)
# --------------------------------------------------------------------------
@dataclass(frozen=True)
class Dxpedition:
    id: str
    callsign: str
    aliases: tuple[str, ...] = ()
    dxcc: str = ""
    start: str = ""
    end: str = ""
    qsl: str = ""
    info: str = ""
    iota: str = ""
    grid: str = ""

    @property
    def calls(self) -> frozenset[str]:
        values = {self.callsign, *self.aliases}
        return frozenset(value.strip().upper() for value in values if value and value.strip())


@dataclass
class ActiveSlot:
    """One band/mode on which a DXpedition was spotted recently."""

    dxpedition: Dxpedition
    call: str
    band: str
    mode: str
    frequency_hz: int
    spotted_ts: float  # local epoch seconds
    spotter: str = ""
    source: str = "da6it"  # or "cluster"
    extra_calls: set[str] = field(default_factory=set)

    @property
    def key(self) -> str:
        return f"{self.dxpedition.id}|{self.band}|{self.mode}"


def _text(value: Any, limit: int = 400) -> str:
    return str(value if value is not None else "").strip()[:limit]


def parse_calendar(payload: Any) -> list[Dxpedition]:
    """Calendar JSON -> DXpeditions (invalid entries are skipped)."""
    items = payload.get("items") if isinstance(payload, dict) else None
    result: list[Dxpedition] = []
    if not isinstance(items, list):
        return result
    for item in items[:2000]:
        if not isinstance(item, dict):
            continue
        ident = _text(item.get("id"), 80)
        callsign = _text(item.get("callsign"), 40).upper()
        if not ident or not callsign:
            continue
        aliases_value = item.get("aliases")
        aliases_raw: list = aliases_value if isinstance(aliases_value, list) else []
        aliases = tuple(_text(alias, 40).upper() for alias in aliases_raw[:30] if _text(alias, 40))
        result.append(Dxpedition(
            id=ident, callsign=callsign, aliases=aliases,
            dxcc=_text(item.get("dxcc"), 80), start=_text(item.get("start"), 10), end=_text(item.get("end"), 10),
            qsl=_text(item.get("qsl"), 120), info=_text(item.get("info"), 600),
            iota=_text(item.get("iota"), 20), grid=_text(item.get("grid"), 10).upper(),
        ))
    return result


def _frequency_hz(khz: Any) -> int:
    try:
        return int(round(float(khz) * 1000))
    except (TypeError, ValueError):
        return 0


def active_slots(
    calendar: Iterable[Dxpedition],
    spots_payload: Any,
    local_spots: Iterable[DxSpot] = (),
    *,
    now: float | None = None,
    window_seconds: int = DXPED_ACTIVE_SECONDS,
) -> list[ActiveSlot]:
    """All band/mode slots of DXpeditions spotted within ``window_seconds``.

    DA6IT.de timestamps are compared with its ``server_time`` (so a wrong
    local clock does not matter) and converted to local time; spots of the
    logger's own DX Cluster connection are compared with ``now``.
    """
    now = time.time() if now is None else float(now)
    by_id = {dxped.id: dxped for dxped in calendar}
    slots: dict[str, ActiveSlot] = {}

    def offer(slot: ActiveSlot) -> None:
        if not slot.band or not slot.mode:
            return
        current = slots.get(slot.key)
        if current is None or slot.spotted_ts > current.spotted_ts:
            if current is not None:
                slot.extra_calls |= current.extra_calls | {current.call}
            slots[slot.key] = slot
        else:
            current.extra_calls.add(slot.call)

    if isinstance(spots_payload, dict) and isinstance(spots_payload.get("items"), dict):
        try:
            server_time = float(spots_payload.get("server_time") or now)
        except (TypeError, ValueError):
            server_time = now
        skew = now - server_time
        for ident, item in list(spots_payload["items"].items())[:2000]:
            dxped = by_id.get(str(ident))
            if dxped is None or not isinstance(item, dict):
                continue
            candidates = [item]
            bands_60m = item.get("bands_60m")
            if isinstance(bands_60m, list):
                candidates.extend(entry for entry in bands_60m[:40] if isinstance(entry, dict))
            for entry in candidates:
                try:
                    last_ts = float(entry.get("last_ts") or 0)
                except (TypeError, ValueError):
                    continue
                if not last_ts or server_time - last_ts > window_seconds or last_ts - server_time > 300:
                    continue
                band = _text(entry.get("band"), 10).lower()
                mode = _text(entry.get("mode"), 12).upper()
                frequency_hz = _frequency_hz(entry.get("frequency_khz"))
                if not band and frequency_hz:
                    band = band_from_mhz(frequency_hz / 1_000_000) or ""
                offer(ActiveSlot(
                    dxpedition=dxped,
                    call=_text(entry.get("call") or item.get("call") or dxped.callsign, 40).upper(),
                    band=band, mode=mode, frequency_hz=frequency_hz,
                    spotted_ts=last_ts + skew, spotter=_text(entry.get("spotter"), 20).upper(),
                ))

    alias_index: dict[str, Dxpedition] = {}
    for dxped in by_id.values():
        for call in dxped.calls:
            alias_index.setdefault(call, dxped)
    for spot in local_spots:
        call = (spot.call or "").strip().upper()
        dxped = alias_index.get(call)
        if dxped is None:
            continue
        try:
            spotted_ts = spot.spotted_at_utc.timestamp()
        except (AttributeError, OverflowError, OSError, ValueError):
            continue
        if now - spotted_ts > window_seconds or spotted_ts - now > 300:
            continue
        mode = normalize_worked_mode(spot.mode, spot.frequency_hz, spot.band)
        if mode in {"LSB", "USB"}:
            mode = "SSB"
        offer(ActiveSlot(
            dxpedition=dxped, call=call, band=(spot.band or "").lower(), mode=mode,
            frequency_hz=int(spot.frequency_hz or 0), spotted_ts=spotted_ts,
            spotter=(spot.spotter or "").upper(), source="cluster",
        ))
    return list(slots.values())


def build_worked_index(
    worked_calls: Iterable[tuple[str, str, str]],
    worked_countries: Iterable[tuple[str, str, str]],
) -> tuple[dict[str, set[tuple[str, str]]], dict[str, set[tuple[str, str]]]]:
    """(call -> {(band, mode)}, country -> {(band, mode)}) from the worked sets."""
    calls: dict[str, set[tuple[str, str]]] = {}
    countries: dict[str, set[tuple[str, str]]] = {}
    for call, band, mode in worked_calls:
        calls.setdefault(call, set()).add((band, mode))
    for country, band, mode in worked_countries:
        countries.setdefault(country, set()).add((band, mode))
    return calls, countries


def _slot_mode(mode: str, band: str, frequency_hz: int) -> str:
    return normalize_worked_mode(mode, frequency_hz, band)


def worked_status(
    slot: ActiveSlot,
    country: str,
    call_index: dict[str, set[tuple[str, str]]],
    country_index: dict[str, set[tuple[str, str]]],
) -> tuple[str, list[tuple[str, str]]]:
    """Status key and the (band, mode) pairs already worked with this DXpedition."""
    calls = set(slot.dxpedition.calls) | {slot.call} | slot.extra_calls
    worked: set[tuple[str, str]] = set()
    for call in calls:
        worked |= call_index.get(call, set())
    current = (slot.band, _slot_mode(slot.mode, slot.band, slot.frequency_hz))
    entity = country_index.get(country, set()) if country else set()
    if country and not entity:
        status = "new_country"
    elif current in worked:
        status = "worked"
    elif country and current not in entity:
        status = "new_slot"
    elif country:
        status = "new_call"
    else:
        status = "new_slot"
    return status, sorted(worked, key=lambda pair: (_band_order(pair[0]), pair[1]))


def _band_order(band: str) -> float:
    text = (band or "").strip().lower()
    try:
        if text.endswith("cm"):
            return -float(text[:-2]) / 100.0
        if text.endswith("m"):
            return -float(text[:-1])
    except ValueError:
        pass
    return 0.0


def format_worked(pairs: list[tuple[str, str]], limit: int = 6) -> str:
    if not pairs:
        return "—"
    shown = [f"{band} {mode}" for band, mode in pairs[:limit]]
    more = len(pairs) - limit
    return " · ".join(shown) + (f" · +{more}" if more > 0 else "")


def format_age(seconds: float, language: str = "de") -> str:
    minutes = max(0, int(seconds // 60))
    if minutes < 1:
        return "jetzt" if language != "en" else "now"
    return f"{minutes} Min." if language != "en" else f"{minutes} min"


def format_until(end: str, today: date | None = None, language: str = "de") -> str:
    try:
        end_date = date.fromisoformat(end[:10])
    except (TypeError, ValueError):
        return "—"
    return end_date.strftime("%d.%m." if language != "en" else "%m-%d")


def beam(
    own_locator: str,
    dxped: Dxpedition,
    fallback: tuple[float | None, float | None] | None,
) -> tuple[float, float, bool] | None:
    """(bearing °, distance km, approximate) from the own locator, or None.

    The DXpedition grid is used when known; otherwise the CTY.DAT centre of
    the DXCC entity (``fallback``), which is marked as approximate.
    """
    try:
        own_lat, own_lon = maidenhead_coordinates((own_locator or "").strip().upper())
    except ValueError:
        return None
    approx = False
    try:
        target = maidenhead_coordinates(dxped.grid) if dxped.grid else None
    except ValueError:
        target = None
    if target is None:
        if not fallback or fallback[0] is None or fallback[1] is None:
            return None
        target = (float(fallback[0]), float(fallback[1]))
        approx = True
    kilometres = distance_m(own_lat, own_lon, target[0], target[1]) / 1000.0
    bearing = initial_bearing_degrees(own_lat, own_lon, target[0], target[1])
    return bearing, kilometres, approx


def format_heading(bearing: float, approx: bool, language: str = "de") -> str:
    directions = _DIRECTIONS_EN if language == "en" else _DIRECTIONS_DE
    text = f"{bearing:.0f}° {directions[int((bearing + 11.25) // 22.5) % 16]}"
    return ("ca. " if approx and language != "en" else "~" if approx else "") + text


def format_distance(kilometres: float, approx: bool, language: str = "de") -> str:
    text = f"{kilometres:,.0f} km"
    if language != "en":
        text = text.replace(",", ".")
    return ("ca. " if approx and language != "en" else "~" if approx else "") + text


def fetch_json(url: str, *, timeout: int = 12) -> Any:
    request = urllib.request.Request(
        url, headers={"User-Agent": f"{APP_NAME}/{VERSION}", "Accept": "application/json"},
    )
    with secure_urlopen(request, timeout=timeout) as response:
        data = response.read(DXPED_MAX_RESPONSE_BYTES + 1)
    if len(data) > DXPED_MAX_RESPONSE_BYTES:
        raise ValueError("Antwort von da6it.de ist unerwartet groß")
    return json.loads(data.decode("utf-8"))


# --------------------------------------------------------------------------
# Tk page
# --------------------------------------------------------------------------
class DxpeditionsFeatureMixin:
    def _init_dxpeditions_feature(self) -> None:
        self.dxped_calendar: list[Dxpedition] = []
        self.dxped_calendar_fetched = 0.0
        self.dxped_spots_payload: dict | None = None
        self.dxped_spots_fetched = 0.0
        self.dxped_fetch_running = False
        self.dxped_last_error = ""
        self.dxped_refresh_job = None
        self.dxped_render_job = None
        self.dxped_rows_shown: list[tuple[str, str, tuple]] | None = None
        self.dxped_slot_by_id: dict[str, ActiveSlot] = {}
        self.dxped_selected_id: str | None = None
        self._dxped_index_source = None
        self._dxped_index: tuple[dict, dict] = ({}, {})
        self._dxped_load_cached_calendar()

    # -- persistence of the calendar (offline start) -------------------------
    def _dxped_cache_path(self) -> Path:
        return Path(getattr(self, "data_dir", None) or app_data_dir()) / DXPED_CACHE_FILE

    def _dxped_load_cached_calendar(self) -> None:
        try:
            raw = json.loads(self._dxped_cache_path().read_text(encoding="utf-8"))
            self.dxped_calendar = parse_calendar(raw.get("payload"))
            self.dxped_calendar_fetched = float(raw.get("fetched_at") or 0)
        except (OSError, ValueError, TypeError, AttributeError):
            self.dxped_calendar = []
            self.dxped_calendar_fetched = 0.0

    def _dxped_store_calendar(self, payload: Any, fetched_at: float) -> None:
        path = self._dxped_cache_path()
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_suffix(".tmp")
            tmp.write_text(json.dumps({"fetched_at": fetched_at, "payload": payload}), encoding="utf-8")
            tmp.replace(path)
        except OSError as exc:
            write_startup_log("DXpeditionen-Cache konnte nicht gespeichert werden: " + repr(exc))

    # -- page ------------------------------------------------------------------
    def _build_dxpeditions_page(self):
        p = self._new_page("dxpeditions")
        p.columnconfigure(0, weight=1)
        p.rowconfigure(1, weight=1)

        top = self._card(p, row=0, column=0, sticky="ew", pady=(0, 10))
        top.columnconfigure(1, weight=1)
        ttk.Label(top, text="Aktive DXpeditionen", style="CardTitle.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(
            top,
            text=(
                "Nur DXpeditionen, die in den letzten 30 Minuten gespottet wurden – je Band und Mode eine Zeile. "
                "Quelle: DXpedition-Kalender und DX-Cluster-Spots von DA6IT.de, zusätzlich die eigene "
                "DX-Cluster-Verbindung. Abgerufen wird nur, solange diese Seite offen ist."
            ),
            style="Muted.Card.TLabel", wraplength=900,
        ).grid(row=1, column=0, columnspan=3, sticky="ew", pady=(3, 8))
        controls = ttk.Frame(top, style="Card.TFrame")
        controls.grid(row=2, column=0, columnspan=3, sticky="ew")
        ttk.Button(controls, text="Jetzt aktualisieren", style="Primary.TButton", command=lambda: self._dxped_fetch(force_calendar=True)).pack(side="left")
        self.dxped_auto_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(
            controls, text="Jede Minute automatisch aktualisieren", variable=self.dxped_auto_var,
            command=self._dxped_auto_changed,
        ).pack(side="left", padx=(12, 0))
        self.dxped_only_new_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            controls, text="Nur noch nicht gearbeitete", variable=self.dxped_only_new_var,
            command=self._dxped_render,
        ).pack(side="left", padx=(12, 0))
        self.dxped_status_label = tk.Label(
            top, text="", bg=theme.CARD, fg=theme.MUTED, font=("Segoe UI", 9), anchor="w", justify="left",
        )
        self.dxped_status_label.grid(row=3, column=0, columnspan=3, sticky="ew", pady=(8, 0))

        table = self._card(p, row=1, column=0, sticky="nsew")
        table.columnconfigure(0, weight=1)
        table.rowconfigure(0, weight=1)
        box = ttk.Frame(table, style="Card.TFrame")
        box.grid(row=0, column=0, sticky="nsew")
        box.columnconfigure(0, weight=1)
        box.rowconfigure(0, weight=1)
        style = ttk.Style(self)
        style.map("Dxped.Treeview", background=[("selected", theme.ACCENT)], foreground=[("selected", theme.INPUT_BG)])
        self.dxped_tree = ttk.Treeview(
            box, columns=tuple(column[0] for column in DXPED_COLUMNS), show="headings",
            selectmode="browse", style="Dxped.Treeview",
        )
        for key, label, width, anchor, stretch in DXPED_COLUMNS:
            self.dxped_tree.heading(key, text=self._tr(label), anchor=anchor)
            self.dxped_tree.column(key, width=width, minwidth=40, anchor=anchor, stretch=stretch)
        self.dxped_bold_font = ("Segoe UI Semibold", 9)
        self.dxped_tree.tag_configure("new_country", foreground=theme.ERR, font=self.dxped_bold_font)
        self.dxped_tree.tag_configure("new_slot", foreground=theme.WARN, font=self.dxped_bold_font)
        self.dxped_tree.tag_configure("new_call", foreground=theme.ACCENT)
        self.dxped_tree.tag_configure("worked", foreground=theme.OK)
        self.dxped_tree.grid(row=0, column=0, sticky="nsew")
        scroll = ttk.Scrollbar(box, orient="vertical", command=self.dxped_tree.yview)
        scroll.grid(row=0, column=1, sticky="ns")
        hscroll = ttk.Scrollbar(box, orient="horizontal", command=self.dxped_tree.xview)
        hscroll.grid(row=1, column=0, sticky="ew")
        self.dxped_tree.configure(yscrollcommand=scroll.set, xscrollcommand=hscroll.set)
        self.dxped_tree.bind("<<TreeviewSelect>>", self._dxped_selection_changed)
        self.dxped_tree.bind("<Double-1>", self._dxped_double_click)
        self.dxped_tree.bind("<Return>", lambda _e: (self._dxped_tune(), "break")[1])

        self.dxped_detail_label = tk.Label(
            table, text="", bg=theme.CARD, fg=theme.MUTED, font=("Segoe UI", 9), anchor="w", justify="left",
        )
        self.dxped_detail_label.grid(row=1, column=0, sticky="ew", pady=(8, 0))
        self.dxped_detail_label.bind(
            "<Configure>", lambda event: self.dxped_detail_label.configure(wraplength=max(200, event.width - 10)),
        )

        actions = ttk.Frame(table, style="Card.TFrame")
        actions.grid(row=2, column=0, sticky="ew", pady=(8, 0))
        actions.columnconfigure(3, weight=1)
        self.dxped_buttons = [
            ttk.Button(actions, text="TRX abstimmen", style="Primary.TButton", command=self._dxped_tune),
            ttk.Button(actions, text="QSO übernehmen", style="Secondary.TButton", command=self._dxped_use),
            ttk.Button(actions, text="QRZ.com öffnen", style="Secondary.TButton", command=self._dxped_qrz),
        ]
        for column, button in enumerate(self.dxped_buttons):
            button.grid(row=0, column=column, sticky="w", padx=(0 if column == 0 else 8, 0))
        legend = tk.Label(
            table,
            text="Doppelklick/Enter: TRX abstimmen · rot: neues Land · orange: neu auf Band/Mode · blau: Land schon, Call neu · grün: gearbeitet",
            bg=theme.CARD, fg=theme.MUTED, font=("Segoe UI", 8), anchor="w", justify="left",
        )
        legend.grid(row=3, column=0, sticky="ew", pady=(6, 0))
        legend.bind("<Configure>", lambda event: legend.configure(wraplength=max(200, event.width - 10)))
        self._dxped_selection_changed()

    def _dxped_settings_ready(self) -> bool:
        return getattr(self, "db", None) is not None

    def _dxped_page_shown(self):
        if self._dxped_settings_ready():
            self.dxped_auto_var.set(self.db.get_setting(SETTING_DXPED_AUTO, "1") != "0")
        self._dxped_render()
        # Switching pages back and forth must not hammer da6it.de.
        if self.dxped_auto_var.get() and time.time() - self.dxped_spots_fetched > 30:
            self._dxped_fetch()
        self._dxped_schedule()

    def _dxped_auto_changed(self):
        if self._dxped_settings_ready():
            self.db.set_setting(SETTING_DXPED_AUTO, "1" if self.dxped_auto_var.get() else "0")
        if self.dxped_auto_var.get():
            self._dxped_fetch()
        self._dxped_schedule()
        self._dxped_update_status()

    def _dxped_page_visible(self) -> bool:
        return getattr(self, "current_page", "") == "dxpeditions" and not getattr(self, "closing", False)

    def _dxped_schedule(self):
        for attr in ("dxped_refresh_job", "dxped_render_job"):
            job = getattr(self, attr)
            if job is not None:
                try:
                    self.after_cancel(job)
                except tk.TclError:
                    pass
                setattr(self, attr, None)
        if not self._dxped_page_visible():
            return
        # Ages, DX Cluster spots and the 30-minute window change without a
        # download; re-render regularly while the page is open.
        self.dxped_render_job = self.after(DXPED_RENDER_TICK_MS, self._dxped_render_tick)
        if self.dxped_auto_var.get():
            self.dxped_refresh_job = self.after(DXPED_SPOTS_REFRESH_MS, self._dxped_refresh_tick)

    def _dxped_render_tick(self):
        self.dxped_render_job = None
        if not self._dxped_page_visible():
            return
        self._dxped_render()
        self.dxped_render_job = self.after(DXPED_RENDER_TICK_MS, self._dxped_render_tick)

    def _dxped_refresh_tick(self):
        self.dxped_refresh_job = None
        if not self._dxped_page_visible() or not self.dxped_auto_var.get():
            return
        self._dxped_fetch()
        self.dxped_refresh_job = self.after(DXPED_SPOTS_REFRESH_MS, self._dxped_refresh_tick)

    def _dxped_fetch(self, *, force_calendar: bool = False):
        if self.dxped_fetch_running or getattr(self, "closing", False):
            return
        need_calendar = (
            force_calendar
            or not self.dxped_calendar
            or time.time() - self.dxped_calendar_fetched > DXPED_CALENDAR_MAX_AGE_SECONDS
        )
        self.dxped_fetch_running = True
        self._dxped_update_status(loading=True)

        def worker():
            calendar_payload = None
            spots_payload = None
            error = ""
            try:
                if need_calendar:
                    calendar_payload = fetch_json(DXPED_CALENDAR_URL)
                spots_payload = fetch_json(DXPED_SPOTS_URL)
            except Exception as exc:  # network, TLS, JSON
                error = str(exc) or exc.__class__.__name__
            if not getattr(self, "closing", False):
                self.after(0, lambda: self._dxped_fetch_done(calendar_payload, spots_payload, error))

        threading.Thread(target=worker, name="dxpeditions-fetch", daemon=True).start()

    def _dxped_fetch_done(self, calendar_payload, spots_payload, error: str):
        self.dxped_fetch_running = False
        now = time.time()
        if calendar_payload is not None:
            calendar = parse_calendar(calendar_payload)
            if calendar:
                self.dxped_calendar = calendar
                self.dxped_calendar_fetched = now
                self._dxped_store_calendar(calendar_payload, now)
        if isinstance(spots_payload, dict):
            self.dxped_spots_payload = spots_payload
            self.dxped_spots_fetched = now
        self.dxped_last_error = error
        if error:
            write_startup_log("DXpeditionen konnten nicht geladen werden: " + error)
        self._dxped_render()

    # -- rendering ---------------------------------------------------------------
    def _dxped_worked_index(self):
        calls = getattr(self, "dx_cluster_worked_calls", None) or set()
        countries = getattr(self, "dx_cluster_worked_countries", None) or set()
        source = (id(calls), len(calls), id(countries), len(countries))
        if source != self._dxped_index_source:
            self._dxped_index = build_worked_index(calls, countries)
            self._dxped_index_source = source
        return self._dxped_index

    def _dxped_country_info(self, call: str):
        country_db = getattr(self, "country_db", None)
        if country_db is None:
            return None
        try:
            return country_db.lookup(call)
        except Exception:
            return None

    def _dxped_rows(self) -> tuple[list[tuple[str, str, tuple]], dict[str, ActiveSlot]]:
        local_spots = [spot for _id, spot in getattr(self, "dx_cluster_spots", [])]
        now = time.time()
        slots = active_slots(self.dxped_calendar, self.dxped_spots_payload, local_spots, now=now)
        call_index, country_index = self._dxped_worked_index()
        own_locator = self.db.get_setting("locator", "") if self._dxped_settings_ready() else ""
        language = getattr(self, "language", "de")
        entries = []
        for slot in slots:
            info = self._dxped_country_info(slot.call) or self._dxped_country_info(slot.dxpedition.callsign)
            country = info.country if info else ""
            status, worked = worked_status(slot, country, call_index, country_index)
            if self.dxped_only_new_var.get() and status == "worked":
                continue
            heading = distance = "—"
            result = beam(own_locator, slot.dxpedition, (info.lat, info.lon) if info else None)
            if result is not None:
                heading = format_heading(result[0], result[2], language)
                distance = format_distance(result[1], result[2], language)
            entries.append((status, now - slot.spotted_ts, slot, country, worked, heading, distance))
        entries.sort(key=lambda entry: (DXPED_STATUS_ORDER.get(entry[0], 9), entry[2].dxpedition.callsign, _band_order(entry[2].band)))
        rows = []
        by_id = {}
        for status, age, slot, country, worked, heading, distance in entries:
            frequency = f"{slot.frequency_hz / 1_000_000:.4f}" if slot.frequency_hz else "—"
            rows.append((
                slot.key, status,
                (
                    slot.call, country or slot.dxpedition.dxcc or "—", slot.band, slot.mode, frequency,
                    format_age(age, language), self._tr(DXPED_STATUS_LABELS[status]), format_worked(worked),
                    heading, distance, format_until(slot.dxpedition.end, language=language),
                ),
            ))
            by_id[slot.key] = slot
        return rows, by_id

    def _dxped_render(self):
        if not hasattr(self, "dxped_tree"):
            return
        rows, by_id = self._dxped_rows()
        tree = self.dxped_tree
        ops = plan_row_diff(self.dxped_rows_shown, rows) if self.dxped_rows_shown is not None else None
        if ops:
            try:
                apply_row_diff(tree, ops)
            except tk.TclError:
                ops = None
        if ops is None:
            tree.delete(*tree.get_children())
            for row in rows:
                try:
                    insert_row(tree, "end", row)
                except tk.TclError:
                    continue
        self.dxped_rows_shown = rows
        self.dxped_slot_by_id = by_id
        if self.dxped_selected_id in by_id:
            if tuple(tree.selection()) != (self.dxped_selected_id,):
                tree.selection_set(self.dxped_selected_id)
        else:
            self.dxped_selected_id = None
        self._dxped_selection_changed()
        self._dxped_update_status()

    def _dxped_update_status(self, *, loading: bool = False):
        label = getattr(self, "dxped_status_label", None)
        if label is None:
            return
        count_calls = len({slot.dxpedition.id for slot in self.dxped_slot_by_id.values()})
        parts = []
        if loading:
            parts.append(self._tr("Wird geladen …"))
        if self.dxped_spots_fetched:
            stamp = datetime.fromtimestamp(self.dxped_spots_fetched, timezone.utc).strftime("%H:%M")
            parts.append(f"{self._tr('Stand')} {stamp} UTC")
        parts.append(
            f"{count_calls} {self._tr('aktive DXpeditionen')} · {len(self.dxped_slot_by_id)} {self._tr('Band/Mode-Kombinationen')}"
        )
        if self.dxped_calendar:
            parts.append(f"{len(self.dxped_calendar)} {self._tr('im Kalender')}")
        color = theme.MUTED
        if self.dxped_last_error:
            parts.append(self._tr("da6it.de nicht erreichbar – letzter Stand wird gezeigt"))
            color = theme.WARN
        if isinstance(self.dxped_spots_payload, dict) and self.dxped_spots_payload.get("collector_stale"):
            parts.append(self._tr("Spot-Daten von DA6IT.de sind veraltet"))
            color = theme.WARN
        if not self.dxped_auto_var.get():
            parts.append(self._tr("automatisches Aktualisieren aus"))
        own_locator = self.db.get_setting("locator", "") if self._dxped_settings_ready() else ""
        if not own_locator:
            parts.append(self._tr("für Richtung/Entfernung eigenen Locator in den Einstellungen eintragen"))
        if self.dxped_spots_payload is None and not self.dxped_slot_by_id and not loading:
            parts.append(self._tr("noch keine Spot-Daten"))
        label.configure(text=" · ".join(parts), fg=color)

    # -- selection and actions ------------------------------------------------
    def _dxped_selected_slot(self) -> ActiveSlot | None:
        return self.dxped_slot_by_id.get(self.dxped_selected_id or "")

    def _dxped_selection_changed(self, _event=None):
        if not hasattr(self, "dxped_tree"):
            return
        selection = self.dxped_tree.selection()
        if selection:
            self.dxped_selected_id = str(selection[0])
        slot = self._dxped_selected_slot()
        for button in getattr(self, "dxped_buttons", []):
            button.state(["!disabled"] if slot else ["disabled"])
        if slot is None:
            self.dxped_detail_label.configure(text=self._tr("Zeile auswählen, um Details zur DXpedition zu sehen."))
            return
        dxped = slot.dxpedition
        language = getattr(self, "language", "de")
        bits = [dxped.callsign + (f" ({', '.join(sorted(dxped.calls - {dxped.callsign}))})" if len(dxped.calls) > 1 else "")]
        if dxped.dxcc:
            bits.append(dxped.dxcc)
        if dxped.iota:
            bits.append(f"IOTA {dxped.iota}")
        if dxped.start or dxped.end:
            bits.append(f"{format_until(dxped.start, language=language)}–{format_until(dxped.end, language=language)}")
        spotter = f"{self._tr('Spot von')} {slot.spotter}" if slot.spotter else ""
        source = self._tr("eigener DX Cluster") if slot.source == "cluster" else "DA6IT.de"
        bits.append(f"{spotter} ({source})".strip())
        if dxped.qsl:
            bits.append(f"QSL: {dxped.qsl}")
        text = " · ".join(bit for bit in bits if bit)
        if dxped.info:
            text += "\n" + dxped.info
        self.dxped_detail_label.configure(text=text)

    def _dxped_double_click(self, event):
        if self.dxped_tree.identify_region(event.x, event.y) != "cell":
            return None
        self._dxped_tune()
        return "break"

    def _dxped_spot(self) -> DxSpot | None:
        slot = self._dxped_selected_slot()
        if slot is None or not slot.frequency_hz:
            return None
        mode = slot.mode
        if mode == "SSB":
            mode = normalize_worked_mode("SSB", slot.frequency_hz, slot.band)
        return DxSpot(
            spotter=slot.spotter, call=slot.call, frequency_hz=slot.frequency_hz, band=slot.band, mode=mode,
            comment="DXpedition", time_utc=datetime.fromtimestamp(slot.spotted_ts, timezone.utc).strftime("%H%M"),
            spotted_at_utc=datetime.fromtimestamp(slot.spotted_ts, timezone.utc),
        )

    def _dxped_tune(self):
        spot = self._dxped_spot()
        if spot is not None:
            self._tune_dx_spot(spot)

    def _dxped_use(self):
        spot = self._dxped_spot()
        if spot is not None:
            self._use_dx_spot(spot)

    def _dxped_qrz(self):
        slot = self._dxped_selected_slot()
        if slot is not None:
            self._open_qrz_callsign(slot.call)
