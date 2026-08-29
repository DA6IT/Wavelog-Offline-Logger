#!/usr/bin/env python3
"""Capture a complete documentation screenshot set from isolated demo data.

The real user profile, ADI files, API tokens, radios, sockets, and network are
never touched.  The script is intended to run from an interactive Windows
desktop because the Windows screen capture needs access to the visible Tk
window.
"""

from __future__ import annotations

import argparse
import ctypes
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timedelta, timezone


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Wavelog Offline Logger documentation screenshots")
    parser.add_argument("--output", type=Path, required=True, help="Target directory for PNG files")
    parser.add_argument("--keep-demo-data", action="store_true", help="Keep and print the isolated demo directory")
    return parser.parse_args()


def set_isolated_environment(root: Path) -> None:
    for name, child in (
        ("LOCALAPPDATA", "LocalAppData"),
        ("APPDATA", "AppData"),
        ("USERPROFILE", "UserProfile"),
        ("HOME", "UserProfile"),
    ):
        path = root / child
        path.mkdir(parents=True, exist_ok=True)
        os.environ[name] = str(path)


def main() -> int:
    args = parse_args()
    repo_root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(repo_root))

    demo_root = Path(tempfile.mkdtemp(prefix="wavelog-doc-demo-"))
    set_isolated_environment(demo_root)
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)

    # Keep Tk coordinates and ImageGrab pixels aligned on scaled Windows
    # desktops. Failure is harmless on older Windows versions.
    if os.name == "nt":
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except Exception:
            try:
                ctypes.windll.user32.SetProcessDPIAware()
            except Exception:
                pass

    # Imports intentionally happen after the isolated environment is active.
    import tkinter as tk
    from tkinter import ttk

    import app as app_module
    from app import LoggerApp, SyncProgressDialog
    from dx_cluster import DxSpot
    from logger_core import app_data_dir, qso_hash
    from xota import ReferenceCandidate

    # Scheduled callbacks that would contact the network or bind a socket are
    # replaced before LoggerApp is instantiated.  CAT is never started either.
    LoggerApp._start_update_check = lambda self: None
    LoggerApp._start_wavelog_monitor = lambda self: None
    LoggerApp._autostart_udp_log = lambda self: None
    LoggerApp._load_cat_runtime_info = lambda self: None
    # The one-time release dialog is tested separately.  During the responsive
    # page sweep it would otherwise open on its timer and its buttons would be
    # mistaken for clipped controls belonging to the current main page.
    LoggerApp._show_whats_new_if_needed = lambda self: None

    created: list[Path] = []
    root: LoggerApp | None = None

    def settle(widget: tk.Misc, delay: float = 0.22) -> None:
        widget.update_idletasks()
        widget.update()
        time.sleep(delay)
        widget.update_idletasks()
        widget.update()

    def cancel_all_after(widget: tk.Misc) -> None:
        """Cancel pending Tk timers before destroying a documentation window."""
        try:
            jobs = widget.tk.call("after", "info")
        except tk.TclError:
            return
        for job in jobs:
            try:
                widget.after_cancel(job)
            except tk.TclError:
                pass

    def capture(widget: tk.Misc, filename: str) -> None:
        settle(widget)
        x = widget.winfo_rootx()
        y = widget.winfo_rooty()
        width = widget.winfo_width()
        height = widget.winfo_height()
        if width < 10 or height < 10:
            raise RuntimeError(f"Widget for {filename} has no usable size: {width}x{height}")
        target = output / filename
        # Use Windows' built-in System.Drawing instead of Pillow. This keeps
        # documentation capture independent from a system Python/Pillow
        # installation and avoids ACL differences in sandbox-built packages.
        capture_command = r"""
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Drawing
$left = [int]$env:WAVELOG_CAPTURE_LEFT
$top = [int]$env:WAVELOG_CAPTURE_TOP
$width = [int]$env:WAVELOG_CAPTURE_WIDTH
$height = [int]$env:WAVELOG_CAPTURE_HEIGHT
$target = [string]$env:WAVELOG_CAPTURE_TARGET
$bitmap = New-Object System.Drawing.Bitmap($width, $height)
$graphics = [System.Drawing.Graphics]::FromImage($bitmap)
try {
    $graphics.CopyFromScreen($left, $top, 0, 0, $bitmap.Size)
    $bitmap.Save($target, [System.Drawing.Imaging.ImageFormat]::Png)
} finally {
    $graphics.Dispose()
    $bitmap.Dispose()
}
"""
        capture_environment = os.environ.copy()
        capture_environment.update({
            "WAVELOG_CAPTURE_LEFT": str(x),
            "WAVELOG_CAPTURE_TOP": str(y),
            "WAVELOG_CAPTURE_WIDTH": str(width),
            "WAVELOG_CAPTURE_HEIGHT": str(height),
            "WAVELOG_CAPTURE_TARGET": str(target),
        })
        completed = subprocess.run(
            [
                "powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
                "-Command", capture_command,
            ],
            check=False,
            capture_output=True,
            text=True,
            env=capture_environment,
        )
        if completed.returncode != 0:
            message = (completed.stderr or completed.stdout or "Windows screen capture failed").strip()
            raise RuntimeError(f"Screenshot {filename} fehlgeschlagen: {message}")
        created.append(target)

    def notebook_below(widget: tk.Misc) -> ttk.Notebook | None:
        if isinstance(widget, ttk.Notebook):
            return widget
        for child in widget.winfo_children():
            found = notebook_below(child)
            if found is not None:
                return found
        return None

    def assert_actions_visible(window: LoggerApp, context: str) -> None:
        """Fail the release if a visible action is clipped by the app window."""
        settle(window, 0.03)
        left = window.winfo_rootx() - 2
        top = window.winfo_rooty() - 2
        right = left + window.winfo_width() + 4
        bottom = top + window.winfo_height() + 4
        clipped: list[str] = []

        def visit(widget: tk.Misc) -> None:
            for child in widget.winfo_children():
                visit(child)
                if not isinstance(child, (ttk.Button, tk.Button)) or not child.winfo_ismapped():
                    continue
                x = child.winfo_rootx()
                y = child.winfo_rooty()
                x2 = x + child.winfo_width()
                y2 = y + child.winfo_height()
                clip_left, clip_top, clip_right, clip_bottom = left, top, right, bottom
                ancestor = child.master
                while ancestor is not None and ancestor is not window:
                    if ancestor.winfo_ismapped():
                        ax = ancestor.winfo_rootx()
                        ay = ancestor.winfo_rooty()
                        clip_left = max(clip_left, ax)
                        clip_top = max(clip_top, ay)
                        clip_right = min(clip_right, ax + ancestor.winfo_width())
                        clip_bottom = min(clip_bottom, ay + ancestor.winfo_height())
                    ancestor = getattr(ancestor, "master", None)
                if x < clip_left or y < clip_top or x2 > clip_right or y2 > clip_bottom:
                    try:
                        label = str(child.cget("text"))
                    except tk.TclError:
                        label = child.winfo_name()
                    clipped.append(f"{label} [{x},{y},{x2},{y2}]")

        visit(window)
        if clipped:
            raise RuntimeError(f"Responsive UI check failed ({context}): " + "; ".join(clipped))

    def validate_responsive_pages(window: LoggerApp) -> None:
        """Exercise every main page at representative supported sizes."""
        page_names = ("log", "fast_log", "contest", "xota", "qsos", "stats", "cat", "dx_cluster", "udp_log", "settings")
        for width, height in ((900, 580), (1100, 680), (1355, 790), (1420, 820)):
            window.geometry(f"{width}x{height}+20+20")
            settle(window, 0.04)
            for page_name in page_names:
                window._show_page(page_name)
                assert_actions_visible(window, f"{page_name} at {width}x{height}")
            window._show_page("settings")
            settings_notebook = notebook_below(window.pages["settings"])
            if settings_notebook is None:
                raise RuntimeError("Settings notebook was not found during responsive UI check")
            for tab_index in range(len(settings_notebook.tabs())):
                settings_notebook.select(tab_index)
                assert_actions_visible(window, f"settings tab {tab_index} at {width}x{height}")

    def sample_qso(
        call: str,
        band: str,
        mode: str,
        freq: str,
        time_on: str,
        country: str,
        *,
        name: str = "",
        comment: str = "",
        power: str = "100",
    ) -> dict[str, str]:
        return {
            "call": call,
            "qso_date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            "time_on": time_on,
            "band": band,
            "mode": mode,
            "freq": freq,
            "rst_sent": "599" if mode == "CW" else "59",
            "rst_rcvd": "599" if mode == "CW" else "59",
            "gridsquare": "",
            "name": name,
            "qth": "",
            "country": country,
            "comment": comment,
            "notes": "Dokumentations-Demo",
            "pota_ref": "",
            "sota_ref": "",
            "wwff_ref": "",
            "tx_pwr": power,
            "operator_call": "DA6IT",
            "station_call": "DA6IT",
            "my_gridsquare": "JO31EJ",
            "my_qth": "Wachtendonk",
            "my_pota_ref": "",
            "my_sota_ref": "",
            "my_wwff_ref": "",
        }

    try:
        root = LoggerApp()
        root.geometry("1420x820+40+40")
        root.attributes("-topmost", True)
        settle(root, 0.35)

        # Pure demo configuration.  Values are deliberately obvious and are
        # stored only below demo_root.
        settings = {
            "operator_call": "DA6IT",
            "station_call": "DA6IT",
            "locator": "JO31EJ",
            "qth": "Wachtendonk",
            "default_power": "100",
            "wavelog_url": "https://wavelog.example.invalid",
            "station_profile_id": "1",
            "auto_sync_online": "1",
            "full_sync_on_start": "1",
            "full_sync_on_exit": "1",
            "udp_log_autostart": "1",
            "callbook_source": "wavelog",
            "callbook_auto_lookup": "1",
        }
        for key, value in settings.items():
            root.db.set_setting(key, value)
        root.db.set_token("wl2_documentation_demo_token")
        root._load_settings_to_ui()
        validate_responsive_pages(root)
        root.geometry("1420x820+40+40")
        settle(root)
        root.set_station_profile.set("DA6IT Portable · Profil-ID 1")

        qsos = [
            sample_qso("DL1ABC", "20m", "USB", "14.205", "143210", "Fed. Rep. of Germany", name="Anna", comment="POTA DL-0123"),
            sample_qso("ON4XYZ", "20m", "USB", "14.223", "142856", "Belgium", name="Luc"),
            sample_qso("F5RRS", "15m", "USB", "21.285", "141945", "France"),
            sample_qso("HB9JCL", "17m", "FT8", "18.100", "140432", "Switzerland", power="25"),
            sample_qso("I0VCE", "30m", "CW", "10.125", "135118", "Italy"),
            sample_qso("OK1DIX", "40m", "CW", "7.0325", "133047", "Czech Republic"),
        ]
        stored = []
        for qso in qsos:
            row = root.store.add(qso)
            root.db.ensure_local(row["local_id"], qso_hash(row))
            stored.append(row)
        root.db.set_status(
            stored[1]["local_id"], "synced", wavelog_id=1001,
            last_synced_hash=qso_hash(stored[1]), remote_hash=qso_hash(stored[1]),
        )
        root.db.set_status(
            stored[4]["local_id"], "synced", wavelog_id=1002,
            last_synced_hash=qso_hash(stored[4]), remote_hash=qso_hash(stored[4]),
        )
        root.refresh_qsos()
        root.refresh_stats()

        # Main QSO page, including a stable callbook photo placeholder.
        root.call_var.set("DL1ABC")
        root.freq_var.set("14.205")
        root.band_var.set("20m")
        root.mode_var.set("USB")
        root.form_vars["tx_pwr"].set("100")
        root.form_vars["gridsquare"].set("JO31AA")
        root.form_vars["name"].set("Anna Beispiel")
        root.form_vars["qth"].set("Düsseldorf")
        root.form_vars["pota_ref"].set("DL-0123")
        root.form_vars["comment"].set("Portable-QSO · Demo-Daten")
        root.notes_text.delete("1.0", "end")
        root.notes_text.insert("1.0", "Callbook-Daten wurden automatisch übernommen.")
        root.current_country = root.country_db.lookup("DL1ABC")
        root._update_country_summary()
        root.callbook_source_label.configure(text="WAVELOG / QRZ", bg=app_module.OK_BADGE_BG, fg=app_module.OK)
        root.callbook_name_label.configure(text="DL1ABC · Anna Beispiel")
        root.callbook_details_label.configure(text="Düsseldorf, Germany\nLocator: JO31AA\nCQ / ITU: 14 / 28")
        root.callbook_status_label.configure(text="Daten automatisch übernommen · Dokumentations-Demo", fg=app_module.OK)
        photo = tk.PhotoImage(width=330, height=150)
        photo.put("#dbeafe", to=(0, 0, 330, 150))
        photo.put("#0b65c2", to=(14, 14, 316, 17))
        photo.put("#0b65c2", to=(14, 133, 316, 136))
        photo.put("#0b65c2", to=(14, 14, 17, 136))
        photo.put("#0b65c2", to=(313, 14, 316, 136))
        root.callbook_photo = photo
        root.callbook_image_label.configure(
            image=photo, text="CALLBOOK PHOTO · DEMO", compound="center",
            fg="#0b315f", font=("Segoe UI Semibold", 11),
        )
        root.tune_button.configure(state="normal")
        root._set_wavelog_mode_ui(True)
        root.status_var.set("Bereit · Dokumentations-Demo ohne echte Online-Verbindung")
        root._show_page("log")
        capture(root, "qso-logging.png")

        # Fast Log / DXpedition.
        root._show_page("fast_log")
        root.fast_log_call_var.set("F5RRS")
        root.fast_log_band_var.set("15m")
        root.fast_log_mode_var.set("USB")
        root.fast_log_freq_var.set("21.285")
        root.fast_log_power_var.set("100")
        root.fast_log_session_ids = [row["local_id"] for row in stored[:4]]
        root.fast_log_session_started = datetime.now(timezone.utc) - timedelta(minutes=5)
        root.refresh_fast_log_page()
        root.fast_log_call_var.set("F5RRS")
        root._fast_log_call_changed()
        capture(root, "fast-log.png")

        # Contest Logging needs a little more vertical room than the other
        # pages so its header and complete session card remain visible.
        root.geometry("1420x900+40+20")
        root._show_page("contest")
        root.contest_preset_var.set("Dokumentations-Contest")
        root.contest_call_var.set("OK1DIX")
        root.contest_freq_var.set("7.0325")
        root.contest_band_var.set("40m")
        root.contest_mode_var.set("CW")
        root.contest_power_var.set("100")
        root.contest_serial_sent_var.set("027")
        root.contest_serial_rcvd_var.set("114")
        root.contest_exchange_rx_var.set("JO70")
        root.contest_operator_var.set("DA6IT")
        root.contest_session_status.configure(text="Demo-Session · 26 QSOs", fg=app_module.OK)
        root.contest_session_detail.configure(text="Station: DA6IT\nOperator: DA6IT\nStart: 13:00 UTC\nNächste Seriennummer: 027\nWavelog-Session: 17")
        root.contest_exchange_hint.configure(text="Gesendet: 027 · Exchange: JO31")
        root.contest_start_btn.configure(state="disabled")
        root.contest_stop_btn.configure(state="normal")
        root.contest_recent.delete(0, "end")
        for line in ("026  I0VCE      30m CW", "025  HB9JCL     17m FT8", "024  F5RRS      15m USB"):
            root.contest_recent.insert("end", line)
        capture(root, "contest-logging.png")
        root.geometry("1420x820+40+40")

        # xOTA with several deliberately unconfirmed references. No GPS,
        # network service or real Wavelog station is contacted.
        root._show_page("xota")
        for key, value in {
            "callsign": "DA6IT/P", "latitude": "51.408725", "longitude": "6.334693",
            "locator": "JO31EJ", "city": "Wachtendonk", "state": "Nordrhein-Westfalen",
            "country": "Germany", "dxcc": "230", "cq": "14", "itu": "28",
            "accuracy": "12", "power": "25", "note": "Portable Aktivierung · Demo",
            "POTA": "DE-0055", "WWFF": "DLFF-0012",
        }.items():
            root.xota_vars[key].set(value)
        root.xota_candidates = [
            ReferenceCandidate("POTA", "POTA", "DE-0055", "Maas-Schwalm-Nette", 51.31, 6.21, distance_m=4200, warning="Naher POTA-Marker"),
            ReferenceCandidate("POTA", "POTA", "DE-0828", "Hülser Bruch Nature Reserve", 51.39, 6.48, distance_m=9600, warning="Naher POTA-Marker"),
            ReferenceCandidate("POTA", "POTA", "NL-0281", "Groote Heide (Venlo) Park", 51.37, 6.20, distance_m=11800, warning="Großer Park möglich; Grenze prüfen"),
            ReferenceCandidate("WWFF", "WWFF", "DLFF-0012", "Naturpark Demo", 51.41, 6.33, distance_m=750, warning="Benutzerbestätigung erforderlich"),
        ]
        root.xota_candidate_tree.delete(*root.xota_candidate_tree.get_children())
        for index, item in enumerate(root.xota_candidates):
            root.xota_candidate_tree.insert(
                "", "end", iid=str(index),
                values=(item.program, item.reference, item.name, f"{item.distance_m:.0f} m", item.warning),
            )
        root.xota_candidate_tree.selection_set(("0", "3"))
        root.xota_provider_label.configure(
            text="4 mögliche Treffer · Demo-Daten. Referenzen müssen bewusst geprüft und bestätigt werden."
        )
        root.status_var.set("xOTA: mehrere mögliche Referenzen gefunden · Dokumentations-Demo")
        capture(root, "xota.png")

        root._show_page("qsos")
        capture(root, "logbook-sync.png")

        root._show_page("stats")
        capture(root, "statistics.png")

        root._show_page("cat")
        root.cat_model_search_var.set("FTX-1")
        root.cat_model_var.set("Yaesu FTX-1 · Dokumentations-Demo")
        root.cat_device_var.set("COM5")
        root.cat_baud_var.set("38400")
        root.cat_poll_var.set("500")
        root.cat_hamlib_info.configure(
            text="✓ Hamlib lokal gebündelt\n300+ Funkgerätemodelle · keine separate Installation",
            fg=app_module.OK,
        )
        root.cat_status_label.configure(
            text="CAT ist ausgeschaltet · zum Verbinden bitte CAT starten.",
            fg=app_module.MUTED,
        )
        capture(root, "cat-setup.png")

        # DX Cluster with realistic, local-only rows.
        now = datetime.now(timezone.utc)
        demo_spots = (
            DxSpot("ON5HQ", "DL1ABC", 14_205_000, "20m", "USB", "POTA DL-0123", "1432", now - timedelta(minutes=1)),
            DxSpot("F5RRS", "ON4XYZ", 14_223_000, "20m", "USB", "59 in Paris", "1431", now - timedelta(minutes=2)),
            DxSpot("HB9BOU", "HB9JCL", 18_100_000, "17m", "FT8", "CQ", "1430", now - timedelta(minutes=3)),
            DxSpot("I0KXB", "I0VCE", 10_125_000, "30m", "CW", "Calling CQ", "1428", now - timedelta(minutes=5)),
            DxSpot("G7RPH", "F6FHZ", 21_285_000, "15m", "USB", "Strong signal", "1426", now - timedelta(minutes=7)),
        )
        root.dx_cluster_spots = [(f"demo-{idx}", spot) for idx, spot in enumerate(demo_spots, 1)]
        root.dx_cluster_session_received = len(demo_spots)
        root.dx_cluster_status_label.configure(
            text="Dokumentations-Demo · Live-Empfang benötigt eine Internetverbindung.", fg=app_module.OK,
        )
        root._update_dx_cluster_worked_cache(root.store.scan())
        root._show_page("dx_cluster")
        root._refresh_dx_cluster_spots()
        capture(root, "dx-cluster.png")

        root.udp_log_autostart_var.set(True)
        root.udp_log_status_label.configure(text="Bereit auf 127.0.0.1:2237 · Dokumentations-Demo", fg=app_module.OK)
        root.udp_log_last_label.configure(text="Letztes Demo-QSO: HB9JCL · 17m · FT8")
        root._show_page("udp_log")
        capture(root, "udp-logging.png")

        root._show_page("settings")
        notebook = notebook_below(root.pages["settings"])
        if notebook is None:
            raise RuntimeError("Settings notebook not found")
        settings_files = (
            (0, "settings-general.png"),
            (1, "settings-wavelog.png"),
            (2, "settings-callbook.png"),
            (3, "settings-data-connections.png"),
        )
        for index, filename in settings_files:
            notebook.select(index)
            capture(root, filename)

        # Both automatic-sync dialog states are part of the documented flow.
        root._show_page("qsos")
        running = SyncProgressDialog(root, "startup", "Lokale und entfernte QSOs werden abgeglichen …")
        capture(running, "sync-progress-running.png")
        running.complete(True, "6 lokale QSOs geprüft\n4 neue QSOs übertragen\n2 Datensätze bereits aktuell\n0 Konflikte")
        capture(running, "sync-progress-complete.png")
        try:
            running.grab_release()
        except tk.TclError:
            pass
        running.destroy()

        # One additional capture proves both optional presentation variants:
        # English UI and dark theme.  It reuses only the isolated demo profile.
        cancel_all_after(root)
        root.shutdown()
        cancel_all_after(root)
        root.destroy()
        root = None
        preferences_file = app_data_dir() / "ui_preferences.json"
        preferences_file.parent.mkdir(parents=True, exist_ok=True)
        preferences_file.write_text(
            json.dumps({"language": "en", "theme": "dark"}, indent=2) + "\n",
            encoding="utf-8",
        )
        root = LoggerApp()
        root.geometry("1420x820+40+40")
        root.attributes("-topmost", True)
        root.call_var.set("DL1ABC")
        root.freq_var.set("14.205")
        root.band_var.set("20m")
        root.mode_var.set("USB")
        root.form_vars["tx_pwr"].set("100")
        root.form_vars["gridsquare"].set("JO31AA")
        root.form_vars["name"].set("Anna Example")
        root.form_vars["qth"].set("Düsseldorf")
        root.callbook_source_label.configure(text="WAVELOG / QRZ", bg=app_module.OK_BADGE_BG, fg=app_module.OK)
        root.callbook_name_label.configure(text="DL1ABC · Anna Example")
        root.callbook_details_label.configure(text="Düsseldorf, Germany\nGrid locator: JO31AA\nCQ / ITU: 14 / 28")
        root.callbook_status_label.configure(text="Data loaded automatically · documentation demo", fg=app_module.OK)
        root.current_country = root.country_db.lookup("DL1ABC")
        root._update_country_summary()
        root._set_wavelog_mode_ui(True)
        root.status_var.set("Ready · documentation demo without a real online connection")
        root._show_page("log")
        capture(root, "qso-logging-english-dark.png")
        root.attributes("-topmost", False)

        print(f"Created {len(created)} documentation screenshots in {output}")
        for path in created:
            print(path.name)
        return 0
    finally:
        if root is not None:
            try:
                cancel_all_after(root)
            except Exception:
                pass
            try:
                root.shutdown()
            except Exception:
                pass
            try:
                cancel_all_after(root)
            except Exception:
                pass
            try:
                root.destroy()
            except Exception:
                pass
        if args.keep_demo_data:
            print(f"Isolated demo data kept at: {demo_root}")
        else:
            shutil.rmtree(demo_root, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
