from __future__ import annotations

import threading
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from app_common import CALLBOOK_SOURCE_LABELS, callbook_source_labels, callbook_source_name
from callbook import (
    CALLBOOK_SOURCE_DISABLED, CALLBOOK_SOURCE_QRZ, CALLBOOK_SOURCE_WAVELOG, CallbookError, QrzClient, lookup_candidate, normalize_wavelog_result,
)
from dx_cluster import DEFAULT_SPOTTER_HOST, DEFAULT_SPOTTER_PORT, DxClusterConfig, DxSpotterConfig
from logger_core import WavelogClient
from qsl_client import QSL_API_BASE, QslClient
from ui_preferences import UiPreferences, save_ui_preferences
from wsjtx_sync import WsjtxSyncSettingsPanel
from xota import ActivationReferenceService, ReverseGeocodeService
from ui_theme import theme


class SettingsFeatureMixin:
    def _init_settings_feature(self) -> None:
        self.station_rows: list[dict] = []
        self.station_by_label: dict[str, dict] = {}

    def _build_settings_page(self):
        p = self._new_page("settings")
        p.columnconfigure(0, weight=1)
        p.rowconfigure(0, weight=1)

        notebook = ttk.Notebook(p, style="Settings.TNotebook")
        notebook.grid(row=0, column=0, sticky="nsew")
        self.settings_notebook = notebook
        general_tab = ttk.Frame(notebook, padding=(2, 12))
        station_tab = ttk.Frame(notebook, padding=(2, 12))
        online_tab = ttk.Frame(notebook, padding=(2, 12))
        qsl_tab = ttk.Frame(notebook, padding=(2, 12))
        data_tab = ttk.Frame(notebook, padding=(2, 12))
        wsjtx_tab = ttk.Frame(notebook, padding=(2, 12))
        self.settings_wsjtx_tab = wsjtx_tab
        notebook.add(general_tab, text="Allgemein")
        notebook.add(station_tab, text="Station & Wavelog")
        notebook.add(online_tab, text="Callbook & Online-Dienste")
        notebook.add(qsl_tab, text="QSL Card Manager")
        notebook.add(data_tab, text="Daten & Verbindungen")
        notebook.add(wsjtx_tab, text="WSJT-X Sync")
        for tab in (general_tab, station_tab, online_tab, qsl_tab, data_tab, wsjtx_tab):
            tab.columnconfigure(0, weight=1)
            tab.columnconfigure(1, weight=1)
            tab.rowconfigure(0, weight=1)

        general_left = self._card(general_tab, row=0, column=0, sticky="nsew", padx=(0, 8))
        general_left.columnconfigure(1, weight=1)
        ttk.Label(general_left, text="App-weite Einstellungen", style="CardTitle.TLabel").grid(
            row=0, column=0, columnspan=2, sticky="w",
        )
        ttk.Label(
            general_left,
            text="Sprache und Darstellung gelten für alle Stationsprofile. Die Änderung wird nach einem Neustart der App aktiv.",
            style="Muted.Card.TLabel", wraplength=470,
        ).grid(row=1, column=0, columnspan=2, sticky="w", pady=(3, 14))
        self.set_ui_language = tk.StringVar(value="English" if self.language == "en" else "Deutsch")
        self.set_ui_theme = tk.StringVar(value="Dunkel / Dark" if self.ui_preferences.theme == "dark" else "Hell / Light")
        self.set_qso_notifications = tk.BooleanVar(value=self.ui_preferences.qso_notifications)
        ttk.Label(general_left, text="Sprache", style="Card.TLabel").grid(row=2, column=0, sticky="w", padx=(0, 12), pady=7)
        ttk.Combobox(
            general_left, textvariable=self.set_ui_language, values=("Deutsch", "English"), state="readonly",
        ).grid(row=2, column=1, sticky="ew", pady=7)
        ttk.Label(general_left, text="Theme", style="Card.TLabel").grid(row=3, column=0, sticky="w", padx=(0, 12), pady=7)
        ttk.Combobox(
            general_left, textvariable=self.set_ui_theme, values=("Hell / Light", "Dunkel / Dark"), state="readonly",
        ).grid(row=3, column=1, sticky="ew", pady=7)
        ttk.Checkbutton(
            general_left,
            text="Systemhinweis nach gespeichertem QSO",
            variable=self.set_qso_notifications,
        ).grid(row=4, column=0, columnspan=2, sticky="w", pady=(10, 0))
        ttk.Button(
            general_left, text="Was ist neu?", command=lambda: self._show_whats_new(mark_seen=False),
        ).grid(row=5, column=0, columnspan=2, sticky="w", pady=(14, 0))

        general_right = self._card(general_tab, row=0, column=1, sticky="nsew", padx=(8, 0))
        ttk.Label(general_right, text="Daten & Backup", style="CardTitle.TLabel").pack(anchor="w")
        ttk.Label(
            general_right,
            text=(
                "Ein ZIP sichert alle Logger-Profile, Einstellungen, Sync-Metadaten und ADI-Logbücher. "
                "Gespeicherte Zugangsdaten sind ebenfalls enthalten – das Backup bitte geschützt aufbewahren."
            ),
            style="Muted.Card.TLabel", wraplength=450,
        ).pack(anchor="w", pady=(4, 16))
        backup_actions = ttk.Frame(general_right, style="Card.TFrame")
        backup_actions.pack(anchor="w", fill="x")
        ttk.Button(
            backup_actions, text="Backup erstellen", style="Primary.TButton", command=self.create_data_backup,
        ).pack(side="left")
        ttk.Button(
            backup_actions, text="Backup wiederherstellen", command=self.restore_data_backup,
        ).pack(side="left", padx=(8, 0))
        self.backup_status_label = ttk.Label(general_right, text="Noch kein Backup in dieser Sitzung erstellt.", style="Muted.Card.TLabel")
        self.backup_status_label.pack(anchor="w", pady=(14, 0))

        left = self._card(station_tab, row=0, column=0, sticky="nsew", padx=(0, 8))
        left.columnconfigure(1, weight=1)
        ttk.Label(left, text="Offline-Stationsprofil", style="CardTitle.TLabel").grid(row=0, column=0, columnspan=2, sticky="w")
        ttk.Label(left, text="Diese Daten werden in deine ADI-Dateien geschrieben und funktionieren auch komplett ohne Internet.", style="Muted.Card.TLabel", wraplength=450).grid(row=1, column=0, columnspan=2, sticky="w", pady=(3, 12))
        self.set_operator = tk.StringVar()
        self.set_station = tk.StringVar()
        self.set_locator = tk.StringVar()
        self.set_qth = tk.StringVar()
        self.set_power = tk.StringVar()
        self.set_pota = tk.StringVar()
        self.set_sota = tk.StringVar()
        self.set_wwff = tk.StringVar()
        self._settings_row(left, "Operator-Rufzeichen", self.set_operator, 2)
        self._settings_row(left, "Stationsrufzeichen", self.set_station, 3)
        self._settings_row(left, "Eigener Locator", self.set_locator, 4)
        self._settings_row(left, "QTH / Ort", self.set_qth, 5)
        self._settings_row(left, "Standardleistung (W)", self.set_power, 6)
        ttk.Separator(left).grid(row=7, column=0, columnspan=2, sticky="ew", pady=14)
        ttk.Label(left, text="Aktuelle Aktivierung (optional)", style="CardTitle.TLabel").grid(row=8, column=0, columnspan=2, sticky="w", pady=(0,4))
        self._settings_row(left, "POTA-Referenz", self.set_pota, 9)
        self._settings_row(left, "SOTA-Referenz", self.set_sota, 10)
        self._settings_row(left, "WWFF-Referenz", self.set_wwff, 11)
        hint = tk.Label(left, text="Die Aktivierungsreferenzen werden automatisch als MY_* Felder in jedes neue QSO geschrieben.", bg=theme.CARD, fg=theme.MUTED, font=("Segoe UI", 9), justify="left", wraplength=430)
        hint.grid(row=12, column=0, columnspan=2, sticky="w", pady=(12,0))

        right = self._card(station_tab, row=0, column=1, sticky="nsew", padx=(8, 0))
        right.columnconfigure(0, weight=1)
        ttk.Label(right, text="Wavelog Sync", style="CardTitle.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(right, text="API v2 (wl2_… Token). Manueller Sync bleibt immer möglich; optional wechselt die App automatisch in den Online-Modus. Für Callbook-Daten wird zusätzlich lookup:read benötigt.", style="Muted.Card.TLabel", wraplength=450).grid(row=1, column=0, sticky="w", pady=(3, 10))
        self.set_url = tk.StringVar()
        self.set_token = tk.StringVar()
        self.set_station_profile = tk.StringVar()
        self.set_auto_sync_online = tk.BooleanVar(value=False)
        self.set_auto_sync_delay = tk.StringVar(value="5 min")
        self.set_full_sync_on_start = tk.BooleanVar(value=False)
        self.set_full_sync_on_exit = tk.BooleanVar(value=False)
        ttk.Label(right, text="Wavelog URL", style="Card.TLabel").grid(row=2, column=0, sticky="w", pady=(5,3))
        ttk.Entry(right, textvariable=self.set_url).grid(row=3, column=0, sticky="ew")
        ttk.Label(right, text="API-v2 Token", style="Card.TLabel").grid(row=4, column=0, sticky="w", pady=(8, 3))
        ttk.Entry(right, textvariable=self.set_token, show="●").grid(row=5, column=0, sticky="ew")
        ttk.Button(right, text="Verbindung testen & Profile laden", style="Secondary.TButton", command=self.test_wavelog).grid(row=6, column=0, sticky="w", pady=(10, 8))
        self.connection_label = tk.Label(right, text="", bg=theme.CARD, fg=theme.MUTED, font=("Segoe UI", 9), justify="left", anchor="w", wraplength=450)
        self.connection_label.grid(row=7, column=0, sticky="ew")
        ttk.Label(right, text="Wavelog-Stationsprofil", style="Card.TLabel").grid(row=8, column=0, sticky="w", pady=(12, 3))
        self.station_combo = ttk.Combobox(right, textvariable=self.set_station_profile, state="readonly")
        self.station_combo.grid(row=9, column=0, sticky="ew")
        self.station_combo.bind("<<ComboboxSelected>>", lambda e: self._station_selection_changed())
        ttk.Label(
            right,
            text="Dieses Logger-Profil synchronisiert ausschließlich QSOs des ausgewählten Wavelog-Stationsprofils.",
            style="Muted.Card.TLabel", wraplength=450,
        ).grid(row=10, column=0, sticky="w", pady=(4, 6))
        ttk.Button(right, text="Werte aus Wavelog-Profil übernehmen", style="Secondary.TButton", command=self.copy_station_values).grid(row=11, column=0, sticky="w", pady=(4, 12))
        ttk.Separator(right).grid(row=12, column=0, sticky="ew", pady=(2, 10))
        ttk.Checkbutton(
            right,
            text="Online-Modus: neue QSOs automatisch zu Wavelog pushen",
            variable=self.set_auto_sync_online,
        ).grid(row=13, column=0, sticky="w")
        auto_sync_delay_row = ttk.Frame(right, style="Card.TFrame")
        auto_sync_delay_row.grid(row=14, column=0, sticky="ew", pady=(7, 0))
        ttk.Label(
            auto_sync_delay_row,
            text="Auto-Sync Verzögerung",
            style="Card.TLabel",
        ).pack(side="left")
        ttk.Combobox(
            auto_sync_delay_row,
            textvariable=self.set_auto_sync_delay,
            values=("1 min", "2 min", "5 min", "10 min", "15 min", "30 min", "60 min"),
            state="readonly",
            width=9,
        ).pack(side="left", padx=(10, 0))
        ttk.Checkbutton(
            right,
            text="Vollständigen Sync beim App-Start ausführen",
            variable=self.set_full_sync_on_start,
        ).grid(row=15, column=0, sticky="w", pady=(6, 0))
        ttk.Checkbutton(
            right,
            text="Vollständigen Sync beim Beenden ausführen",
            variable=self.set_full_sync_on_exit,
        ).grid(row=16, column=0, sticky="w", pady=(6, 0))
        ttk.Label(
            right,
            text="Die Auto-Sync-Verzögerung startet mit dem ersten neuen QSO eines Batches und wird durch weitere QSOs nicht verlängert.",
            style="Muted.Card.TLabel", wraplength=450,
        ).grid(row=17, column=0, sticky="w", pady=(5, 0))

        callbook_card = self._card(online_tab, row=0, column=0, sticky="nsew", padx=(0, 8))
        callbook_card.columnconfigure(0, weight=1)
        callbook_card.columnconfigure(1, weight=1)
        ttk.Label(callbook_card, text="Rufzeichen-Lookup", style="CardTitle.TLabel").grid(row=0, column=0, columnspan=2, sticky="w")
        ttk.Label(
            callbook_card,
            text="Name, Locator, QTH und – falls vorhanden – das Stationsfoto werden beim Tippen geladen. Ohne Internet läuft das Logging still weiter.",
            style="Muted.Card.TLabel", wraplength=480,
        ).grid(row=1, column=0, columnspan=2, sticky="w", pady=(3, 12))
        self.set_callbook_source = tk.StringVar(value=callbook_source_name(CALLBOOK_SOURCE_WAVELOG, self.language))
        self.set_callbook_auto = tk.BooleanVar(value=True)
        ttk.Label(callbook_card, text="Datenquelle", style="Card.TLabel").grid(row=2, column=0, columnspan=2, sticky="w", pady=(3, 3))
        ttk.Combobox(
            callbook_card, textvariable=self.set_callbook_source,
            values=tuple(callbook_source_labels(self.language)), state="readonly",
        ).grid(row=3, column=0, columnspan=2, sticky="ew")
        ttk.Checkbutton(
            callbook_card, text="Bei vollständigem Rufzeichen automatisch abfragen",
            variable=self.set_callbook_auto,
        ).grid(row=4, column=0, columnspan=2, sticky="w", pady=(10, 10))
        ttk.Separator(callbook_card).grid(row=5, column=0, columnspan=2, sticky="ew", pady=(2, 10))
        ttk.Label(callbook_card, text="Direkter QRZ.com-Zugang", style="CardTitle.TLabel").grid(row=6, column=0, columnspan=2, sticky="w")
        ttk.Label(
            callbook_card,
            text="QRZ.com wird bei direkter Auswahl unabhängig von Wavelog abgefragt. Benutzername und Passwort sind dann erforderlich. QRZ kann ein XML-Abonnement voraussetzen.",
            style="Muted.Card.TLabel", wraplength=480,
        ).grid(row=7, column=0, columnspan=2, sticky="w", pady=(3, 8))
        self.set_qrz_username = tk.StringVar()
        self.set_qrz_password = tk.StringVar()
        ttk.Label(callbook_card, text="QRZ.com Benutzername", style="Card.TLabel").grid(row=8, column=0, sticky="w", padx=(0, 6), pady=(3, 3))
        ttk.Label(callbook_card, text="QRZ.com Passwort", style="Card.TLabel").grid(row=8, column=1, sticky="w", padx=(6, 0), pady=(3, 3))
        ttk.Entry(callbook_card, textvariable=self.set_qrz_username).grid(row=9, column=0, sticky="ew", padx=(0, 6))
        ttk.Entry(callbook_card, textvariable=self.set_qrz_password, show="●").grid(row=9, column=1, sticky="ew", padx=(6, 0))
        ttk.Button(callbook_card, text="Callbook-Verbindung testen", style="Secondary.TButton", command=self.test_callbook).grid(row=10, column=0, columnspan=2, sticky="w", pady=(12, 7))
        self.callbook_test_label = tk.Label(callbook_card, text="", bg=theme.CARD, fg=theme.MUTED, font=("Segoe UI", 9), justify="left", anchor="w", wraplength=470)
        self.callbook_test_label.grid(row=11, column=0, columnspan=2, sticky="ew")

        eqsl_card = self._card(online_tab, row=0, column=1, sticky="nsew", padx=(8, 0))
        eqsl_card.columnconfigure(0, weight=1)
        ttk.Label(eqsl_card, text="eQSL.cc", style="CardTitle.TLabel").grid(row=0, column=0, sticky="w")
        coming = tk.Label(eqsl_card, text="COMING SOON", bg=theme.WARN_BADGE_BG, fg=theme.WARN, font=("Segoe UI Semibold", 8), padx=8, pady=3)
        coming.grid(row=0, column=1, sticky="e")
        ttk.Label(
            eqsl_card,
            text="Die Zugangsdaten können bereits profilspezifisch hinterlegt werden. Derzeit findet noch keine Verbindung, kein Download und kein Upload statt.",
            style="Muted.Card.TLabel", wraplength=450,
        ).grid(row=1, column=0, columnspan=2, sticky="w", pady=(5, 14))
        self.set_eqsl_username = tk.StringVar()
        self.set_eqsl_password = tk.StringVar()
        ttk.Label(eqsl_card, text="eQSL.cc Benutzername", style="Card.TLabel").grid(row=2, column=0, columnspan=2, sticky="w", pady=(4, 3))
        ttk.Entry(eqsl_card, textvariable=self.set_eqsl_username).grid(row=3, column=0, columnspan=2, sticky="ew")
        ttk.Label(eqsl_card, text="eQSL.cc Passwort", style="Card.TLabel").grid(row=4, column=0, columnspan=2, sticky="w", pady=(10, 3))
        ttk.Entry(eqsl_card, textvariable=self.set_eqsl_password, show="●").grid(row=5, column=0, columnspan=2, sticky="ew")
        tk.Label(
            eqsl_card, text="Coming soon – derzeit noch ohne Funktion.",
            bg=theme.WARN_BADGE_BG, fg=theme.WARN, font=("Segoe UI Semibold", 10),
            padx=12, pady=10, anchor="w",
        ).grid(row=6, column=0, columnspan=2, sticky="ew", pady=(16, 0))

        qsl_connection_card = self._card(qsl_tab, row=0, column=0, sticky="nsew", padx=(0, 8))
        qsl_connection_card.columnconfigure(0, weight=1)
        ttk.Label(
            qsl_connection_card,
            text="DA6IT.de QSL Card Manager",
            style="CardTitle.TLabel",
        ).grid(row=0, column=0, sticky="w")
        ttk.Label(
            qsl_connection_card,
            text=(
                "Der QSL Card Manager ist fester Bestandteil des Loggers. "
                "Die Verbindung erfolgt ausschließlich zur DA6IT.de QSL API. "
                "Es kann keine eigene oder fremde API-URL eingetragen werden."
            ),
            style="Muted.Card.TLabel",
            wraplength=470,
        ).grid(row=1, column=0, sticky="w", pady=(3, 14))

        ttk.Label(
            qsl_connection_card,
            text="API-Endpunkt",
            style="Card.TLabel",
        ).grid(row=2, column=0, sticky="w", pady=(3, 3))

        self.qsl_api_label = tk.Label(
            qsl_connection_card,
            text=QSL_API_BASE,
            bg=theme.CARD,
            fg=theme.MUTED,
            font=("Segoe UI", 9),
            justify="left",
            anchor="w",
            wraplength=470,
        )
        self.qsl_api_label.grid(row=3, column=0, sticky="ew")

        self.set_qsl_connection_key = tk.StringVar()
        ttk.Label(
            qsl_connection_card,
            text="Connection Key",
            style="Card.TLabel",
        ).grid(row=4, column=0, sticky="w", pady=(14, 3))
        ttk.Entry(
            qsl_connection_card,
            textvariable=self.set_qsl_connection_key,
            show="●",
        ).grid(row=5, column=0, sticky="ew")

        ttk.Label(
            qsl_connection_card,
            text=(
                "Den Connection Key erzeugst du im QSL Card Manager auf DA6IT.de. "
                "Es wird kein WordPress-Passwort im Logger benötigt."
            ),
            style="Muted.Card.TLabel",
            wraplength=470,
        ).grid(row=6, column=0, sticky="w", pady=(5, 12))

        ttk.Button(
            qsl_connection_card,
            text="QSL-Verbindung testen",
            style="Secondary.TButton",
            command=self.test_qsl_connection,
        ).grid(row=7, column=0, sticky="w")

        self.qsl_connection_label = tk.Label(
            qsl_connection_card,
            text="Noch nicht geprüft.",
            bg=theme.CARD,
            fg=theme.MUTED,
            font=("Segoe UI", 9),
            justify="left",
            anchor="w",
            wraplength=470,
        )
        self.qsl_connection_label.grid(row=8, column=0, sticky="ew", pady=(10, 0))

        qsl_info_card = self._card(qsl_tab, row=0, column=1, sticky="nsew", padx=(8, 0))
        qsl_info_card.columnconfigure(0, weight=1)
        ttk.Label(
            qsl_info_card,
            text="Servergesteuerte Funktionen",
            style="CardTitle.TLabel",
        ).grid(row=0, column=0, sticky="w")
        ttk.Label(
            qsl_info_card,
            text=(
                "Vorlagen, Versandlimits, Queue-Status und verfügbare Funktionen "
                "werden vom DA6IT.de QSL Card Manager vorgegeben. Der Logger "
                "übernimmt diese Werte über den Bootstrap-Endpunkt und hardcodiert "
                "keine Versandlimits."
            ),
            style="Muted.Card.TLabel",
            wraplength=470,
        ).grid(row=1, column=0, sticky="w", pady=(3, 14))

        self.qsl_server_info_label = tk.Label(
            qsl_info_card,
            text=(
                "Nach erfolgreichem Verbindungstest werden hier API-Version, "
                "Core-Version und die aktuellen Mail-Limits angezeigt."
            ),
            bg=theme.CARD,
            fg=theme.MUTED,
            font=("Segoe UI", 9),
            justify="left",
            anchor="nw",
            wraplength=470,
        )
        self.qsl_server_info_label.grid(row=2, column=0, sticky="nsew")

        ttk.Separator(
            qsl_info_card,
            orient="horizontal",
        ).grid(row=3, column=0, sticky="ew", pady=(18, 14))

        ttk.Label(
            qsl_info_card,
            text="Private Kontrollkopie",
            style="CardTitle.TLabel",
        ).grid(row=4, column=0, sticky="w")

        self.set_qsl_control_copy_enabled = tk.BooleanVar()
        self.set_qsl_control_copy_email = tk.StringVar()

        ttk.Checkbutton(
            qsl_info_card,
            text="Kontrollkopie an mich senden",
            variable=self.set_qsl_control_copy_enabled,
        ).grid(row=5, column=0, sticky="w", pady=(8, 6))

        ttk.Label(
            qsl_info_card,
            text="E-Mail-Adresse für Kontrollkopie",
            style="Card.TLabel",
        ).grid(row=6, column=0, sticky="w", pady=(4, 3))

        ttk.Entry(
            qsl_info_card,
            textvariable=self.set_qsl_control_copy_email,
        ).grid(row=7, column=0, sticky="ew")

        ttk.Label(
            qsl_info_card,
            text=(
                "Die Kontrollkopie wird privat per BCC mit derselben QSL-Karte "
                "verschickt. Die Gegenstation sieht diese Adresse nicht. "
                "Bei einer neuen, vom QSL-Account abweichenden Adresse muss "
                "die Änderung einmal über die Account-E-Mail freigegeben werden."
            ),
            style="Muted.Card.TLabel",
            wraplength=470,
        ).grid(row=8, column=0, sticky="w", pady=(6, 10))

        ttk.Button(
            qsl_info_card,
            text="Kontrollkopie speichern",
            style="Secondary.TButton",
            command=self.save_qsl_control_copy,
        ).grid(row=9, column=0, sticky="w")

        self.qsl_control_copy_status_label = tk.Label(
            qsl_info_card,
            text="Noch nicht mit dem Server abgeglichen.",
            bg=theme.CARD,
            fg=theme.MUTED,
            font=("Segoe UI", 9),
            justify="left",
            anchor="w",
            wraplength=470,
        )
        self.qsl_control_copy_status_label.grid(
            row=10,
            column=0,
            sticky="ew",
            pady=(8, 0),
        )

        data_left = self._card(data_tab, row=0, column=0, sticky="nsew", padx=(0, 8))
        data_left.columnconfigure(0, weight=1)
        ttk.Label(data_left, text="Lokale Logdateien", style="CardTitle.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(
            data_left,
            text="ADI bleibt das primäre Logbuchformat. Die SQLite-Datei enthält nur Einstellungen, Sync-Metadaten und den Callbook-Cache.",
            style="Muted.Card.TLabel", wraplength=450,
        ).grid(row=1, column=0, sticky="w", pady=(3, 12))
        self.set_log_dir = tk.StringVar()
        logrow = ttk.Frame(data_left, style="Card.TFrame")
        logrow.grid(row=2, column=0, sticky="ew", pady=(6, 0))
        logrow.columnconfigure(0, weight=1)
        ttk.Entry(logrow, textvariable=self.set_log_dir).grid(row=0, column=0, sticky="ew")
        ttk.Button(logrow, text="…", width=4, command=self.choose_log_dir).grid(row=0, column=1, padx=(6, 0))
        ttk.Separator(data_left).grid(row=3, column=0, sticky="ew", pady=14)
        ttk.Label(data_left, text="xOTA-Datenquellen", style="CardTitle.TLabel").grid(row=4, column=0, sticky="w")
        ttk.Label(
            data_left,
            text="POTA, SOTA und WWFF verwenden die eingebauten Quellen. Für IOTA und COTA/WCA kann optional eine eigene CSV-URL hinterlegt werden; ohne Quelle bleibt die manuelle Eingabe verfügbar.",
            style="Muted.Card.TLabel", wraplength=450,
        ).grid(row=5, column=0, sticky="w", pady=(3, 8))
        self.set_xota_iota_url = tk.StringVar()
        self.set_xota_cota_url = tk.StringVar()
        self.set_xota_geocode_url = tk.StringVar()
        for row, label, variable in (
            (6, "IOTA CSV-URL (optional)", self.set_xota_iota_url),
            (8, "COTA/WCA CSV-URL (optional)", self.set_xota_cota_url),
            (10, "Reverse-Geocoding-URL", self.set_xota_geocode_url),
        ):
            ttk.Label(data_left, text=label, style="Card.TLabel").grid(row=row, column=0, sticky="w", pady=(5, 2))
            ttk.Entry(data_left, textvariable=variable).grid(row=row+1, column=0, sticky="ew")

        spotter = self._card(data_tab, row=0, column=1, sticky="nsew", padx=(8, 0))
        spotter.columnconfigure(0, weight=2)
        spotter.columnconfigure(1, weight=1)
        spotter.columnconfigure(2, weight=2)
        ttk.Label(spotter, text="DX-Spotter-Verbindung", style="CardTitle.TLabel").grid(
            row=0, column=0, columnspan=3, sticky="w",
        )
        ttk.Label(
            spotter,
            text=(
                "Getrennt vom reinen Empfangs-Cluster. Beim öffentlichen Spotten wird diese "
                "DXSpider-Verbindung automatisch aufgebaut. Sie benötigt Internet; ohne Verbindung "
                "wird nichts gesendet. Das Login-Rufzeichen kommt immer aus dem aktiven Stationsprofil."
            ),
            style="Muted.Card.TLabel", wraplength=1050,
        ).grid(row=1, column=0, columnspan=3, sticky="w", pady=(3, 8))
        self.dx_spotter_host_var = tk.StringVar(value=DEFAULT_SPOTTER_HOST)
        self.dx_spotter_port_var = tk.StringVar(value=str(DEFAULT_SPOTTER_PORT))
        self.dx_spotter_call_var = tk.StringVar()
        for column, (label, variable) in enumerate((
            ("DXSpider-Host zum Spotten", self.dx_spotter_host_var),
            ("Telnet-Port", self.dx_spotter_port_var),
            ("Login-Rufzeichen aus Logbuch", self.dx_spotter_call_var),
        )):
            ttk.Label(spotter, text=label, style="Card.TLabel").grid(
                row=2, column=column, sticky="w", padx=(0, 10), pady=(2, 3),
            )
            state = "readonly" if variable is self.dx_spotter_call_var else "normal"
            ttk.Entry(spotter, textvariable=variable, state=state).grid(
                row=3, column=column, sticky="ew", padx=(0, 10),
            )
        self.dx_spotter_status_label = tk.Label(
            spotter, text="Spotter-Verbindung wird erst beim Senden aufgebaut.",
            bg=theme.CARD, fg=theme.MUTED, font=("Segoe UI", 9), anchor="w",
        )
        self.dx_spotter_status_label.grid(row=4, column=0, columnspan=3, sticky="ew", pady=(10, 0))

        # Descriptive copy remains visible at normal size.  In compact
        # windows it yields space to the actual fields and buttons instead of
        # pushing them beyond the lower edge of the page.
        self._settings_optional_help.clear()
        def collect_optional_help(widget):
            for child in widget.winfo_children():
                collect_optional_help(child)
                if isinstance(child, ttk.Label):
                    try:
                        if child.cget("style") == "Muted.Card.TLabel":
                            self._settings_optional_help.append(child)
                    except tk.TclError:
                        pass
        collect_optional_help(notebook)
        self._settings_optional_help.append(hint)

        self.wsjtx_settings_panel = WsjtxSyncSettingsPanel(
            wsjtx_tab,
            self.db,
            language=self.language,
            sync_callback=self.sync_wsjtx_now,
        )
        self.wsjtx_settings_panel.grid(
            row=0,
            column=0,
            columnspan=2,
            sticky="nsew",
        )

        savebar = ttk.Frame(p)
        savebar.grid(row=1, column=0, sticky="ew", pady=(10, 0))
        ttk.Label(savebar, text="Stationsdaten sind profilspezifisch; Sprache und Theme gelten app-weit.", foreground=theme.MUTED).pack(side="left")
        ttk.Button(savebar, text="Einstellungen speichern", style="Primary.TButton", command=self.save_settings).pack(side="right")

    def _settings_row(self, parent, label, var, row):
        ttk.Label(parent, text=label, style="Card.TLabel").grid(row=row, column=0, sticky="w", padx=(0,12), pady=4)
        ttk.Entry(parent, textvariable=var).grid(row=row, column=1, sticky="ew", pady=4)

    def _load_settings_to_ui(self):
        self.set_ui_language.set("English" if self.ui_preferences.language == "en" else "Deutsch")
        self.set_ui_theme.set("Dunkel / Dark" if self.ui_preferences.theme == "dark" else "Hell / Light")
        self.set_qso_notifications.set(self.ui_preferences.qso_notifications)
        self.set_operator.set(self.db.get_setting("operator_call", ""))
        self.set_station.set(self.db.get_setting("station_call", ""))
        self.set_locator.set(self.db.get_setting("locator", ""))
        self.set_qth.set(self.db.get_setting("qth", ""))
        self.set_power.set(self.db.get_setting("default_power", ""))
        self.set_pota.set(self.db.get_setting("my_pota_ref", ""))
        self.set_sota.set(self.db.get_setting("my_sota_ref", ""))
        self.set_wwff.set(self.db.get_setting("my_wwff_ref", ""))
        self.set_url.set(self.db.get_setting("wavelog_url", ""))
        self.set_token.set(self.db.get_token())
        self.set_auto_sync_online.set(self.db.get_setting("auto_sync_online", "0") == "1")
        try:
            auto_sync_delay_seconds = int(self.db.get_setting("auto_sync_delay_seconds", "300") or "300")
        except ValueError:
            auto_sync_delay_seconds = 300
        auto_sync_delay_seconds = min(3600, max(60, auto_sync_delay_seconds))
        self.set_auto_sync_delay.set(f"{auto_sync_delay_seconds // 60} min")
        self.set_full_sync_on_start.set(self.db.get_setting("full_sync_on_start", "0") == "1")
        self.set_full_sync_on_exit.set(self.db.get_setting("full_sync_on_exit", "0") == "1")
        source = self.db.get_setting("callbook_source", CALLBOOK_SOURCE_WAVELOG).strip().lower()
        self.set_callbook_source.set(callbook_source_name(source, self.language))
        self.set_callbook_auto.set(self.db.get_setting("callbook_auto_lookup", "1") == "1")
        self.set_qrz_username.set(self.db.get_setting("qrz_username", ""))
        self.set_qrz_password.set(self.db.get_secret("qrz_password"))
        self.set_eqsl_username.set(self.db.get_setting("eqsl_username", ""))
        self.set_eqsl_password.set(self.db.get_secret("eqsl_password"))
        self.set_qsl_connection_key.set(self.db.get_secret("qsl_connection_key"))
        self.set_qsl_control_copy_enabled.set(self.db.get_setting("qsl_control_copy_enabled", "0") == "1")
        self.set_qsl_control_copy_email.set(self.db.get_setting("qsl_control_copy_email", ""))
        self.set_log_dir.set(self.db.get_setting("log_dir", str(self.store.log_dir)))
        self.set_xota_iota_url.set(self.db.get_setting("xota_iota_data_url", ""))
        self.set_xota_cota_url.set(self.db.get_setting("xota_cota_wca_data_url", ""))
        self.set_xota_geocode_url.set(self.db.get_setting("xota_reverse_geocode_url", "https://nominatim.openstreetmap.org/reverse"))
        self.time_mode_var.set(self.db.get_setting("time_mode", "UTC") or "UTC")
        self.form_vars["tx_pwr"].set(self.db.get_setting("default_power", ""))
        self._update_profile_summary()
        self._set_current_qso_time()
        self._load_cat_settings_to_ui()
        self._load_rotor_settings_to_ui()
        self._load_dx_cluster_settings_to_ui()
        self._load_dx_spotter_settings_to_ui()
        self._load_udp_log_settings_to_ui()
        if hasattr(self, "wsjtx_settings_panel"):
            self.wsjtx_settings_panel.reload(
                self.db,
                language=self.language,
            )
        self._update_callbook_distance()

        # If Wavelog was configured before, profile labels are loaded only on explicit test.
        sid = self.db.get_setting("station_profile_id", "")
        if sid:
            logbook_id = self.db.get_setting("station_logbook_id", "")
            suffix = f" · Logbuch-ID {logbook_id}" if logbook_id else ""
            self.set_station_profile.set(f"Profil-ID {sid}{suffix}")

    def save_settings(self):
        try:
            if self.set_power.get().strip():
                float(self.set_power.get().replace(",", "."))
            old_station_call = self._active_station_callsign()
            proposed_station_call = (
                self.set_station.get().strip().upper()
                or self.set_operator.get().strip().upper()
            )
            try:
                spotter_port = int(self.dx_spotter_port_var.get().strip())
            except ValueError as exc:
                raise ValueError("Der DX-Spotter-Port muss eine ganze Zahl sein.") from exc
            spotter_config = DxSpotterConfig(
                self.dx_spotter_host_var.get().strip(),
                spotter_port,
                proposed_station_call,
            )
            if proposed_station_call:
                spotter_config.validate()
            else:
                DxClusterConfig(spotter_config.host, spotter_config.port, "N0CALL").validate()
            self.db.set_setting("operator_call", self.set_operator.get().strip().upper())
            self.db.set_setting("station_call", self.set_station.get().strip().upper())
            self.db.set_setting("locator", self.set_locator.get().strip().upper())
            self.db.set_setting("qth", self.set_qth.get().strip())
            self.db.set_setting("default_power", self.set_power.get().strip().replace(",", "."))
            self.db.set_setting("my_pota_ref", self.set_pota.get().strip().upper())
            self.db.set_setting("my_sota_ref", self.set_sota.get().strip().upper())
            self.db.set_setting("my_wwff_ref", self.set_wwff.get().strip().upper())
            self.db.set_setting("wavelog_url", self.set_url.get().strip())
            self.db.set_token(self.set_token.get().strip())
            self.db.set_setting("auto_sync_online", "1" if self.set_auto_sync_online.get() else "0")
            try:
                auto_sync_delay_minutes = int(self.set_auto_sync_delay.get().split()[0])
            except (ValueError, IndexError) as exc:
                raise ValueError("Die Auto-Sync-Verzögerung ist ungültig.") from exc
            if auto_sync_delay_minutes not in (1, 2, 5, 10, 15, 30, 60):
                raise ValueError("Die Auto-Sync-Verzögerung ist ungültig.")
            self.db.set_setting("auto_sync_delay_seconds", auto_sync_delay_minutes * 60)
            self.db.set_setting("full_sync_on_start", "1" if self.set_full_sync_on_start.get() else "0")
            self.db.set_setting("full_sync_on_exit", "1" if self.set_full_sync_on_exit.get() else "0")
            source = CALLBOOK_SOURCE_LABELS.get(self.set_callbook_source.get(), CALLBOOK_SOURCE_WAVELOG)
            self.db.set_setting("callbook_source", source)
            self.db.set_setting("callbook_auto_lookup", "1" if self.set_callbook_auto.get() else "0")
            self.db.set_setting("qrz_username", self.set_qrz_username.get().strip())
            self.db.set_secret("qrz_password", self.set_qrz_password.get())
            self.db.set_setting("eqsl_username", self.set_eqsl_username.get().strip())
            self.db.set_secret("eqsl_password", self.set_eqsl_password.get())
            self.db.set_secret("qsl_connection_key", self.set_qsl_connection_key.get().strip())
            self._schedule_qsl_background_sync(
                500,
                reason="settings",
            )
            self.db.set_setting("qsl_control_copy_enabled", "1" if self.set_qsl_control_copy_enabled.get() else "0")
            self.db.set_setting("qsl_control_copy_email", self.set_qsl_control_copy_email.get().strip())
            self.db.set_setting("log_dir", self.set_log_dir.get().strip())
            self.db.set_setting("xota_iota_data_url", self.set_xota_iota_url.get().strip())
            self.db.set_setting("xota_cota_wca_data_url", self.set_xota_cota_url.get().strip())
            self.db.set_setting("xota_reverse_geocode_url", self.set_xota_geocode_url.get().strip())
            if hasattr(self, "wsjtx_settings_panel"):
                self.wsjtx_settings_panel.save_to_db(self.db)
            new_ui_preferences = UiPreferences(
                language="en" if self.set_ui_language.get() == "English" else "de",
                theme="dark" if self.set_ui_theme.get() == "Dunkel / Dark" else "light",
                qso_notifications=self.set_qso_notifications.get(),
                last_whats_new_version=self.ui_preferences.last_whats_new_version,
            )
            restart_required = (
                new_ui_preferences.language != self.ui_preferences.language
                or new_ui_preferences.theme != self.ui_preferences.theme
            )
            save_ui_preferences(self.data_dir, new_ui_preferences)
            # Notification changes take effect immediately. Language and theme
            # still use the existing controlled restart path.
            self.ui_preferences = new_ui_preferences
            self._store_dx_spotter_config(spotter_config)
            selected = self.station_by_label.get(self.set_station_profile.get())
            if selected:
                self.db.set_setting("station_profile_id", selected.get("id"))
                logbook_id, logbook_name = self._station_logbook_details(selected)
                self.db.set_setting("station_logbook_id", logbook_id)
                self.db.set_setting("station_logbook_name", logbook_name)
            # Keep an existing numeric profile id if the list wasn't loaded in this session.
            self.store.set_dir(Path(self.set_log_dir.get().strip() or self._profile_default_log_dir()))
            self.xota_references = ActivationReferenceService(self.xota_repository, self.db.get_setting)
            self.xota_geocoder = ReverseGeocodeService(self.xota_repository, self.db.get_setting("xota_reverse_geocode_url", ""))
            self.form_vars["tx_pwr"].set(self.db.get_setting("default_power", ""))
            self._update_profile_summary()
            self._update_callbook_distance()
            self._update_logfile_preview()
            self.dx_cluster_call_var.set(self._active_station_callsign())
            self.dx_spotter_call_var.set(self._active_station_callsign())
            if self._active_station_callsign() != old_station_call:
                self._stop_dx_cluster_runtime(update_ui=True)
                self._stop_dx_spotter_runtime(update_ui=True)
            elif self.dx_spotter_active_config != spotter_config:
                self._stop_dx_spotter_runtime(update_ui=True)
            self.refresh_fast_log_page()
            self.qrz_client = None
            self.qrz_client_credentials = None
            if self.call_var.get().strip():
                self._schedule_callbook_lookup(self.call_var.get().strip().upper(), force=True)
            self._reset_wavelog_monitor(delay_ms=300)
            self.status_var.set("Einstellungen gespeichert")
            message = "Einstellungen wurden gespeichert."
            if restart_required:
                message += "\n\nSprache oder Theme werden nach dem nächsten Programmstart aktiv."
            messagebox.showinfo("Einstellungen", message, parent=self)
        except Exception as e:
            messagebox.showerror("Einstellungen", str(e), parent=self)

    def choose_log_dir(self):
        p = filedialog.askdirectory(initialdir=self.set_log_dir.get() or str(self._profile_default_log_dir()), parent=self)
        if p:
            self.set_log_dir.set(p)

    def test_callbook(self):
        call = (self.set_station.get().strip() or self.set_operator.get().strip()).upper()
        if not lookup_candidate(call):
            self.callbook_test_label.configure(text="Bitte zuerst ein gültiges Operator- oder Stationsrufzeichen eintragen.", fg=theme.WARN)
            return
        selected = CALLBOOK_SOURCE_LABELS.get(self.set_callbook_source.get(), CALLBOOK_SOURCE_WAVELOG)
        qrz_user = self.set_qrz_username.get().strip()
        qrz_password = self.set_qrz_password.get()
        source = selected
        if source == CALLBOOK_SOURCE_DISABLED:
            self.callbook_test_label.configure(text="Callbook-Abfrage ist deaktiviert.", fg=theme.MUTED)
            return
        self.callbook_test_label.configure(text="Verbindung wird geprüft …", fg=theme.MUTED)
        url = self.set_url.get().strip()
        token = self.set_token.get().strip()

        def worker():
            try:
                if source == CALLBOOK_SOURCE_QRZ:
                    result = QrzClient(qrz_user, qrz_password, timeout=8).lookup(call)
                else:
                    payload = WavelogClient(url, token, timeout=8).lookup_callsign(call, include_callbook=True)
                    result = normalize_wavelog_result(payload, call)
                if not any((result.name, result.qth, result.grid, result.country, result.image_url)):
                    raise CallbookError("Keine Callbook-Daten gefunden")
                summary = " · ".join(part for part in (result.callsign, result.name, result.grid, result.qth) if part)
                if not self.closing:
                    self.after(0, lambda text=summary: self.callbook_test_label.configure(text="✓ " + text, fg=theme.OK))
            except Exception as exc:
                if not self.closing:
                    error_message = str(exc)
                    self.after(0, lambda message=error_message: self.callbook_test_label.configure(text="✕ " + message, fg=theme.ERR))

        threading.Thread(target=worker, name="callbook-test", daemon=True).start()

    def _apply_qsl_control_copy_state(self, payload: dict) -> None:
        if not isinstance(payload, dict):
            return
        enabled = bool(payload.get("enabled"))
        verified = bool(payload.get("verified"))
        pending = bool(payload.get("pending"))
        email = str(payload.get("email") or "").strip()
        pending_email = str(payload.get("pendingEmail") or "").strip()

        if email:
            self.set_qsl_control_copy_email.set(email)
        self.set_qsl_control_copy_enabled.set(enabled)
        self.db.set_setting("qsl_control_copy_enabled", "1" if enabled else "0")
        if email:
            self.db.set_setting("qsl_control_copy_email", email)

        if pending:
            self.qsl_control_copy_status_label.configure(
                text=(
                    "Freigabe ausstehend für "
                    + (pending_email or "die neue Adresse")
                    + ". Bitte die Bestätigungsmail am QSL-Account öffnen."
                ),
                fg=theme.WARN,
            )
        elif enabled and verified:
            self.qsl_control_copy_status_label.configure(
                text="✓ Private Kontrollkopie aktiv" + ((" · " + email) if email else ""),
                fg=theme.OK,
            )
        elif verified and email:
            self.qsl_control_copy_status_label.configure(
                text="Kontrolladresse bestätigt, Kontrollkopie ist deaktiviert · " + email,
                fg=theme.MUTED,
            )
        else:
            self.qsl_control_copy_status_label.configure(
                text="Kontrollkopie ist deaktiviert.",
                fg=theme.MUTED,
            )

    def save_qsl_control_copy(self):
        connection_key = self.set_qsl_connection_key.get().strip()
        enabled = bool(self.set_qsl_control_copy_enabled.get())
        email = self.set_qsl_control_copy_email.get().strip()

        if not connection_key:
            self.qsl_control_copy_status_label.configure(
                text="Bitte zuerst einen Connection Key eintragen.",
                fg=theme.WARN,
            )
            return
        if enabled and (not email or "@" not in email):
            self.qsl_control_copy_status_label.configure(
                text="Bitte eine gültige E-Mail-Adresse eintragen.",
                fg=theme.WARN,
            )
            return

        self.db.set_setting("qsl_control_copy_enabled", "1" if enabled else "0")
        self.db.set_setting("qsl_control_copy_email", email)
        self.qsl_control_copy_status_label.configure(
            text="Kontrollkopie wird mit DA6IT.de abgeglichen …",
            fg=theme.MUTED,
        )

        def worker():
            try:
                payload = QslClient(connection_key, timeout=10).set_control_copy(enabled, email)
                if not self.closing:
                    self.after(0, lambda data=payload: self._apply_qsl_control_copy_state(data))
            except Exception as exc:
                error = str(exc)
                if not self.closing:
                    self.after(
                        0,
                        lambda message=error: self.qsl_control_copy_status_label.configure(
                            text="✗ " + message,
                            fg=theme.ERR,
                        ),
                    )

        threading.Thread(
            target=worker,
            name="qsl-control-copy-save",
            daemon=True,
        ).start()

    def test_qsl_connection(self):
        connection_key = self.set_qsl_connection_key.get().strip()

        if not connection_key:
            self.qsl_connection_label.configure(
                text="Bitte zuerst einen Connection Key eintragen.",
                fg=theme.WARN,
            )
            return

        self.qsl_connection_label.configure(
            text="Verbindung wird geprüft …",
            fg=theme.MUTED,
        )
        self.qsl_server_info_label.configure(
            text="Bootstrap wird von DA6IT.de geladen …",
            fg=theme.MUTED,
        )

        def worker():
            try:
                payload = QslClient(
                    connection_key,
                    timeout=8,
                ).bootstrap()

                if not self.closing:
                    self.after(
                        0,
                        lambda data=payload: self._qsl_test_ok(data),
                    )

            except Exception as exc:
                if not self.closing:
                    error_message = str(exc)
                    self.after(
                        0,
                        lambda message=error_message: self._qsl_test_fail(message),
                    )

        threading.Thread(
            target=worker,
            name="qsl-api-test",
            daemon=True,
        ).start()

    def _qsl_test_ok(self, payload: dict):
        core_version = str(payload.get("coreVersion") or "—")
        api_version = str(payload.get("apiVersion") or "—")
        mail_usage = payload.get("mailUsage")
        mail_usage = mail_usage if isinstance(mail_usage, dict) else {}

        hour_limit = mail_usage.get("hourLimit")
        hour_remaining = mail_usage.get("hourRemaining")
        day_limit = mail_usage.get("dayLimit")
        day_remaining = mail_usage.get("dayRemaining")
        queued = mail_usage.get("queued")
        mail_enabled = mail_usage.get("mailEnabled")
        control_copy = payload.get("controlCopy")
        control_copy = control_copy if isinstance(control_copy, dict) else {}

        self.qsl_connection_label.configure(
            text="✓ QSL Card Manager verbunden",
            fg=theme.OK,
        )

        lines = [
            f"Core: {core_version} · API: {api_version}",
        ]

        if hour_limit is not None:
            lines.append(
                f"Stunde: {hour_remaining if hour_remaining is not None else '—'} "
                f"von {hour_limit} verfügbar"
            )

        if day_limit is not None:
            lines.append(
                f"Tag: {day_remaining if day_remaining is not None else '—'} "
                f"von {day_limit} verfügbar"
            )

        if queued is not None:
            lines.append(f"Queue: {queued}")

        if mail_enabled is not None:
            lines.append(
                "Mailversand: "
                + ("aktiv" if bool(mail_enabled) else "deaktiviert")
            )

        self.qsl_server_info_label.configure(
            text="\n".join(lines),
            fg=theme.OK,
        )

        if control_copy:
            self._apply_qsl_control_copy_state(control_copy)

    def _qsl_test_fail(self, message: str):
        self.qsl_connection_label.configure(
            text="✗ " + message,
            fg=theme.ERR,
        )
        self.qsl_server_info_label.configure(
            text="Keine gültigen Serverdaten geladen.",
            fg=theme.ERR,
        )
    def test_wavelog(self):
        url = self.set_url.get().strip()
        token = self.set_token.get().strip()
        self.connection_label.configure(text="Verbindung wird geprüft …", fg=theme.MUTED)

        def worker():
            try:
                c = WavelogClient(url, token)
                info = c.token_info()
                stations = c.stations()
                if not self.closing:
                    self.after(0, lambda: self._wavelog_test_ok(info, stations))
            except Exception as e:
                if not self.closing:
                    error_message = str(e)
                    self.after(0, lambda message=error_message: self._wavelog_test_fail(message))
        threading.Thread(target=worker, name="wavelog-test", daemon=True).start()

    @staticmethod
    def _station_logbook_details(station: dict) -> tuple[str, str]:
        nested = station.get("logbook")
        nested = nested if isinstance(nested, dict) else {}
        logbook_id = next((
            station.get(key) for key in ("station_logbook_id", "logbook_id")
            if station.get(key) not in (None, "")
        ), nested.get("id", ""))
        logbook_name = next((
            station.get(key) for key in ("station_logbook_name", "logbook_name")
            if station.get(key) not in (None, "")
        ), nested.get("name", ""))
        return str(logbook_id or ""), str(logbook_name or "")

    def _wavelog_test_ok(self, info: dict, stations: list[dict]):
        owner = str(info.get("owner") or "")
        scopes = ", ".join(info.get("scopes") or [])
        scope_list = info.get("scopes") or []
        qsl_hint = "" if "confirmation:read" in scope_list else "\n⚠ confirmation:read fehlt – Bestätigungen (✓) sind nicht verfügbar."
        lookup_hint = "" if "lookup:read" in scope_list else "\n⚠ lookup:read fehlt – Rufzeichen-/Callbook-Daten über Wavelog sind nicht verfügbar."
        club_hint = ""
        station_call = self.set_station.get().strip().upper()
        if station_call and owner.upper() == station_call and "club:read" not in scope_list:
            club_hint = "\nℹ Clubstation: Für sicheren clubweiten Operator-Abgleich einen Officer-Token mit club:read verwenden."
        warn = bool(qsl_hint or lookup_hint)
        self.connection_label.configure(text=f"✓ Token gültig · Owner: {owner or '—'}\nScopes: {scopes or '—'}{qsl_hint}{lookup_hint}{club_hint}", fg=theme.WARN if warn else theme.OK)
        if not self.set_operator.get().strip() and owner:
            self.set_operator.set(owner.upper())
        self.station_rows = stations
        self.station_by_label.clear()
        labels = []
        chosen = None
        saved_id = self.db.get_setting("station_profile_id", "")
        for s in stations:
            logbook_id, logbook_name = self._station_logbook_details(s)
            logbook = ""
            if logbook_name or logbook_id:
                logbook = f" · Logbuch {logbook_name or logbook_id}"
                if logbook_name and logbook_id:
                    logbook += f" [ID {logbook_id}]"
            label = f"{s.get('name') or 'Station'} · {s.get('callsign') or '?'} · {s.get('gridsquare') or '—'}{logbook} [Profil-ID {s.get('id')}]"
            labels.append(label)
            self.station_by_label[label] = s
            if str(s.get("id")) == saved_id or (not saved_id and s.get("active")):
                chosen = label
        self.station_combo.configure(values=labels)
        if chosen:
            self.set_station_profile.set(chosen)
        elif labels:
            self.set_station_profile.set(labels[0])
        self._station_selection_changed()

    def _wavelog_test_fail(self, msg: str):
        self.connection_label.configure(text="✗ " + msg, fg=theme.ERR)

    def _station_selection_changed(self):
        s = self.station_by_label.get(self.set_station_profile.get())
        if s:
            self.connection_label.configure(text=(self.connection_label.cget("text") + f"\nAusgewählt: {s.get('callsign','')} / {s.get('gridsquare','')}").strip())

    def copy_station_values(self):
        s = self.station_by_label.get(self.set_station_profile.get())
        if not s:
            messagebox.showinfo("Wavelog-Profil", "Bitte zuerst die Verbindung testen und ein Stationsprofil auswählen.", parent=self)
            return
        self.set_station.set(str(s.get("callsign") or "").upper())
        self.set_locator.set(str(s.get("gridsquare") or "").upper())
        self.set_qth.set(str(s.get("city") or ""))
        self.set_power.set(str(s.get("power") or ""))
        self.set_pota.set(str(s.get("pota") or "").upper())
        self.set_sota.set(str(s.get("sota") or "").upper())
        self.set_wwff.set(str(s.get("wwff") or "").upper())
        self.status_var.set("Stationswerte aus Wavelog übernommen · noch nicht gespeichert")
