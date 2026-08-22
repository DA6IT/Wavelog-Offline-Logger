from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


PREFERENCES_FILE = "ui_preferences.json"


@dataclass(frozen=True)
class UiPreferences:
    language: str = "de"
    theme: str = "light"
    qso_notifications: bool = True

    def normalized(self) -> "UiPreferences":
        language = self.language if self.language in {"de", "en"} else "de"
        theme = self.theme if self.theme in {"light", "dark"} else "light"
        return UiPreferences(
            language=language,
            theme=theme,
            qso_notifications=bool(self.qso_notifications),
        )


PALETTES = {
    "light": {
        "BG": "#f6f8fb", "CARD": "#ffffff", "TEXT": "#172033", "MUTED": "#667085",
        "ACCENT": "#0969da", "ACCENT_DARK": "#0556b3", "BORDER": "#d8dee8",
        "OK": "#1a8f36", "WARN": "#9a6700", "ERR": "#b42318", "SIDEBAR": "#ffffff",
        "SIDEBAR_TEXT": "#253044", "ACTIVE_BG": "#eaf2ff", "SURFACE": "#f8fbff",
        "INPUT_BG": "#ffffff", "PHOTO_BG": "#f3f6fa", "NEUTRAL_BADGE_BG": "#edf2f7",
        "OK_BADGE_BG": "#e9f7ec", "WARN_BADGE_BG": "#fff4df", "NAV_HOVER": "#f1f5fb",
        "NAV_ACTIVE_HOVER": "#dceaff", "PROGRESS_BG": "#e9eef3", "DISABLED": "#9bb8cf",
    },
    "dark": {
        "BG": "#0f141c", "CARD": "#171e29", "TEXT": "#e8edf5", "MUTED": "#9aa6b5",
        "ACCENT": "#58a6ff", "ACCENT_DARK": "#79b8ff", "BORDER": "#303b4a",
        "OK": "#3fb950", "WARN": "#d29922", "ERR": "#f85149", "SIDEBAR": "#121923",
        "SIDEBAR_TEXT": "#dce6f3", "ACTIVE_BG": "#1f3552", "SURFACE": "#182231",
        "INPUT_BG": "#202938", "PHOTO_BG": "#202938", "NEUTRAL_BADGE_BG": "#273244",
        "OK_BADGE_BG": "#183b25", "WARN_BADGE_BG": "#453515", "NAV_HOVER": "#1a2635",
        "NAV_ACTIVE_HOVER": "#29476b", "PROGRESS_BG": "#273244", "DISABLED": "#526277",
    },
}


def load_ui_preferences(data_dir: Path) -> UiPreferences:
    path = Path(data_dir) / PREFERENCES_FILE
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            return UiPreferences()
        return UiPreferences(
            language=str(payload.get("language", "de")),
            theme=str(payload.get("theme", "light")),
            qso_notifications=bool(payload.get("qso_notifications", True)),
        ).normalized()
    except (OSError, ValueError, TypeError):
        return UiPreferences()


def save_ui_preferences(data_dir: Path, preferences: UiPreferences) -> None:
    data_dir = Path(data_dir)
    data_dir.mkdir(parents=True, exist_ok=True)
    path = data_dir / PREFERENCES_FILE
    temporary = path.with_suffix(path.suffix + ".tmp")
    normalized = preferences.normalized()
    temporary.write_text(
        json.dumps({
            "language": normalized.language,
            "theme": normalized.theme,
            "qso_notifications": normalized.qso_notifications,
        }, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


# Static widget texts and frequently changing status messages are translated at
# the presentation boundary. Internal values (ADIF modes, database keys and
# profile data) intentionally remain language-neutral/backwards compatible.
ENGLISH = {
    "Logbuch": "Logbook", "Logbuch & Sync": "Logbook & Sync", "Statistiken": "Statistics",
    "Einstellungen": "Settings", "QSO loggen": "Log QSO", "Gegenstation": "Contact station",
    "Frequenz (MHz)": "Frequency (MHz)", "Frequenz": "Frequency", "Leistung (W)": "Power (W)",
    "RST gesendet": "RST sent", "RST empfangen": "RST received",
    "Locator Gegenstation": "Contact grid locator", "QTH Gegenstation": "Contact QTH",
    "POTA Ref Gegenstation": "Contact POTA ref", "SOTA Ref Gegenstation": "Contact SOTA ref",
    "WWFF Ref Gegenstation": "Contact WWFF ref", "Kommentar": "Comment", "Notizen": "Notes",
    "QSO speichern": "Save QSO", "Speichern + Neu": "Save + New", "Felder leeren": "Clear fields",
    "DX-Spot senden": "Send DX spot", "Datum / Zeit": "Date / Time", "Datum": "Date", "Uhrzeit": "Time",
    "Lokal": "Local", "Callbook-Informationen": "Callbook information", "Kein Foto geladen": "No photo loaded",
    "Rufzeichen eingeben …": "Enter callsign …", "Callbook neu laden": "Reload callbook",
    "DXCC · offline": "DXCC · offline", "Land / DXCC": "Country / DXCC", "Kontinent": "Continent",
    "Bereit": "Ready", "Verwalten": "Manage", "PROFIL": "PROFILE",
    "Fast Log / DXpedition": "Fast Log / DXpedition", "Contest Logging": "Contest Logging",
    "DX Cluster": "DX Cluster", "CAT Setup": "CAT Setup", "UDP Logging": "UDP Logging",
    "Station & Wavelog": "Station & Wavelog", "Callbook & Online-Dienste": "Callbook & Online services",
    "Daten & Verbindungen": "Data & connections", "Allgemein": "General",
    "Sprache": "Language", "Darstellung": "Appearance", "Theme": "Theme",
    "Hell / Light": "Light", "Dunkel / Dark": "Dark",
    "App-weite Einstellungen": "App-wide settings", "Deutsch": "German", "English": "English",
    "Systemhinweis nach gespeichertem QSO": "System notification after a saved QSO",
    "Offline-Stationsprofil": "Offline station profile", "Operator-Rufzeichen": "Operator callsign",
    "Stationsrufzeichen": "Station callsign", "Eigener Locator": "Own grid locator", "QTH / Ort": "QTH / location",
    "Standardleistung (W)": "Default power (W)", "Aktuelle Aktivierung (optional)": "Current activation (optional)",
    "POTA-Referenz": "POTA reference", "SOTA-Referenz": "SOTA reference", "WWFF-Referenz": "WWFF reference",
    "Wavelog URL": "Wavelog URL", "API-v2 Token": "API v2 token",
    "Verbindung testen & Profile laden": "Test connection & load profiles",
    "Wavelog-Stationsprofil": "Wavelog station profile",
    "Dieses Logger-Profil synchronisiert ausschließlich QSOs des ausgewählten Wavelog-Stationsprofils.": "This logger profile synchronizes only QSOs from the selected Wavelog station profile.",
    "Werte aus Wavelog-Profil übernehmen": "Use values from Wavelog profile",
    "Rufzeichen-Lookup": "Callsign lookup", "Datenquelle": "Data source",
    "Bei vollständigem Rufzeichen automatisch abfragen": "Look up complete callsigns automatically",
    "Direkter QRZ.com-Zugang": "Direct QRZ.com access", "QRZ.com Benutzername": "QRZ.com username",
    "QRZ.com Passwort": "QRZ.com password", "Callbook-Verbindung testen": "Test callbook connection",
    "QRZ.com wird bei direkter Auswahl unabhängig von Wavelog abgefragt. Benutzername und Passwort sind dann erforderlich.": "When selected directly, QRZ.com is queried independently of Wavelog. Username and password are then required.",
    "eQSL.cc Benutzername": "eQSL.cc username", "eQSL.cc Passwort": "eQSL.cc password",
    "Lokale Logdateien": "Local log files", "DX-Spotter-Verbindung": "DX spotter connection",
    "DXSpider-Host zum Spotten": "DXSpider host for spotting", "Telnet-Port": "Telnet port",
    "Login-Rufzeichen aus Logbuch": "Login callsign from logbook",
    "Einstellungen speichern": "Save settings", "Daten & Backup": "Data & backup",
    "CAT-Einstellungen speichern": "Save CAT settings", "CAT starten": "Start CAT", "CAT stoppen": "Stop CAT",
    "Verbindung testen": "Test connection", "Funkgerät": "Radio", "Hersteller / Modell": "Manufacturer / model",
    "Geräte-Port": "Device port", "Baudrate": "Baud rate", "Datenbits": "Data bits",
    "Stoppbits": "Stop bits", "Parität": "Parity", "Handshake": "Handshake",
    "Abfrageintervall (ms)": "Polling interval (ms)", "Lokaler rigctld-Port": "Local rigctld port",
    "Telnet-Verbindung": "Telnet connection", "DX-Cluster-Host": "DX cluster host",
    "Login-Rufzeichen": "Login callsign", "Verbinden": "Connect", "Trennen": "Disconnect",
    "Spot-Filter": "Spot filters", "Zeitraum": "Time range", "Spotter-Region": "Spotter region",
    "Liste leeren": "Clear list", "Empfangene DX-Spots": "Received DX spots",
    "QSO übernehmen": "Use for QSO", "Alle": "All", "Europa": "Europe", "Nordamerika": "North America",
    "Südamerika": "South America", "Asien/Pazifik": "Asia/Pacific", "Afrika": "Africa", "Unbekannt": "Unknown",
    "15 Minuten": "15 minutes", "30 Minuten": "30 minutes", "60 Minuten": "60 minutes", "2 Stunden": "2 hours",
    "Gesamt": "All time", "Dieses Jahr": "This year", "Dieser Monat": "This month",
    "Diese Woche": "This week", "Heute (UTC)": "Today (UTC)", "Alle Operatoren": "All operators",
    "Noch keine Daten": "No data yet", "Aktivitäten": "Activities", "Offene Sync-Themen": "Open sync issues",
    "Starten": "Start", "Stoppen": "Stop", "Speichern": "Save", "Abbrechen": "Cancel", "Schließen": "Close",
    "Löschen": "Delete", "Bearbeiten": "Edit", "Aktualisieren": "Refresh", "Exportieren": "Export",
    "Importieren": "Import", "Ja": "Yes", "Nein": "No", "Deaktiviert": "Disabled",
    "Über Wavelog (empfohlen)": "Via Wavelog (recommended)", "Direkt über QRZ.com": "Directly via QRZ.com",
    "COMING SOON": "COMING SOON", "Coming soon – derzeit noch ohne Funktion.": "Coming soon – not active yet.",
    "TUNE (ATU)": "TUNE (ATU)", "TUNE läuft …": "TUNE running …", "Tuner starten": "Start tuner",
    "CAT ist nicht gestartet": "CAT is not running", "Antennentuner wird gestartet …": "Starting antenna tuner …",
    "Antennentuner gestartet": "Antenna tuner started",
    "Antennentuner konnte nicht gestartet werden": "Antenna tuner could not be started",
    "●  WAVELOG ONLINE": "●  WAVELOG ONLINE", "Verbunden · neuer QSO-Push aktiv": "Connected · new-QSO push active",
    "Verbunden · manueller Sync": "Connected · manual sync", "Wavelog nicht eingerichtet.": "Wavelog is not configured.",
    "Offline · QSOs bleiben lokal.": "Offline · QSOs remain local.",
    "Online-Modus: neue QSOs automatisch zu Wavelog pushen": "Online mode: automatically push new QSOs to Wavelog",
    "Vollständigen Sync beim App-Start ausführen": "Run a full sync when the app starts",
    "Vollständigen Sync beim Beenden ausführen": "Run a full sync when the app closes",
    "Alle Optionen gelten pro Profil und sind unabhängig wählbar. Offline werden QSOs weiter sicher lokal gespeichert.": "All options are profile-specific and can be selected independently. QSOs remain safely stored locally while offline.",
    "Wavelog-Status wird geprüft.": "Checking Wavelog status.",
    "Neue LOCAL ONLY QSOs werden zu Wavelog hochgeladen …": "Uploading new LOCAL ONLY QSOs to Wavelog …",
    "Online-Push fehlgeschlagen · QSOs bleiben lokal": "Online push failed · QSOs remain local",
    "Vollständiger Start-Sync läuft …": "Full startup sync running …",
    "Vollständiger Abschluss-Sync läuft …": "Full shutdown sync running …",
    "Beenden wartet auf die laufende Wavelog-Übertragung …": "Closing waits for the active Wavelog transfer …",
    "Wavelog-Synchronisierung": "Wavelog synchronization",
    "Wavelog wird synchronisiert": "Synchronizing Wavelog",
    "Vor der Bedienung wird das aktive Profil vollständig mit Wavelog abgeglichen.": "The active profile is fully synchronized with Wavelog before the app can be used.",
    "Vor dem Beenden wird das aktive Profil vollständig mit Wavelog abgeglichen.": "The active profile is fully synchronized with Wavelog before the app closes.",
    "Synchronisierung abgeschlossen": "Synchronization completed",
    "Synchronisierung fehlgeschlagen": "Synchronization failed",
    "Die App wird nach OK geschlossen.": "The app will close after you select OK.",
    "Nach OK kann die App verwendet werden.": "The app can be used after you select OK.",
    "Wavelog konnte nicht vollständig synchronisiert werden. Die lokalen QSOs bleiben sicher gespeichert.": "Wavelog could not be fully synchronized. The local QSOs remain safely stored.",
    "Automatische Synchronisierung läuft …": "Automatic synchronization running …",
    "Wavelog ist wieder erreichbar · Online-Modus aktiv": "Wavelog is reachable again · Online mode active",
    "Wavelog nicht erreichbar · LOCAL ONLY": "Wavelog is unavailable · LOCAL ONLY",
    "Auto-Sync fehlgeschlagen · QSOs bleiben LOCAL ONLY": "Auto-sync failed · QSOs remain LOCAL ONLY",
    "Auswertung": "Analysis", "Bänder": "Bands", "Operator:": "Operator:", "Top Calls": "Top calls",
    "Top Länder / DXCC": "Top countries / DXCC", "QSOs nach Band": "QSOs by band",
    "QSOs nach Mode": "QSOs by mode", "QSOs nach Operator": "QSOs by operator",
    "ADI-Ordner öffnen": "Open ADI folder", "Aktivieren": "Enable", "Andere Logprogramme": "Other logging programs",
    "Bind-Adresse": "Bind address", "CAT-/COM-Schnittstelle": "CAT / COM interface", "CAT-Status": "CAT status",
    "Contest-Preset": "Contest preset", "Contest-QSO loggen": "Log contest QSO", "Contest-Session": "Contest session",
    "Duplizieren": "Duplicate", "Einrichtung in WSJT-X": "Setup in WSJT-X", "Erweitert": "Advanced",
    "Exchange-Felder": "Exchange fields", "Feste QSO-Daten": "Fixed QSO data",
    "Funkgerät & Schnittstelle": "Radio & interface", "Funkgerät suchen": "Find radio",
    "Hamlib wird geprüft …": "Checking Hamlib …", "Hamlib-Funkgerät": "Hamlib radio",
    "Interne Hamlib-Steuerung": "Bundled Hamlib control", "Keine Online-Daten verfügbar.": "No online data available.",
    "Keine Session": "No session", "Letzte Contest-QSOs": "Latest contest QSOs",
    "Letztes QSO zurücknehmen": "Undo last QSO", "Lokale Version erzwingen": "Use local version",
    "Neu": "New", "Neu laden": "Reload", "Noch kein Contest-Preset angelegt": "No contest preset yet",
    "Noch kein QSO empfangen.": "No QSO received yet.", "Nur Rufzeichen + Enter": "Callsign + Enter only",
    "Pileup-Eingabe": "Pileup entry", "Profil lokal löschen": "Delete local profile",
    "QSO bearbeiten": "Edit QSO", "QSO lokal speichern": "Save QSO locally", "QSO löschen": "Delete QSO",
    "QSOs dieser Fast-Log-Sitzung": "QSOs in this Fast Log session", "Serielle Parameter": "Serial parameters",
    "Seriennummer": "Serial number", "Session beenden": "End session", "Session starten": "Start session",
    "Speicherung": "Storage", "Standardband / Mode": "Default band / mode", "Synchronisieren": "Synchronize",
    "UDP Logging beim App-Start automatisch starten": "Start UDP logging automatically when the app starts",
    "UDP starten": "Start UDP", "UDP stoppen": "Stop UDP", "UDP-Empfänger": "UDP receiver",
    "UDP-Port": "UDP port", "UDP-Status": "UDP status", "Umbenennen": "Rename",
    "Wavelog-Version übernehmen": "Use Wavelog version", "Werte aus QSO/CAT": "Values from QSO/CAT",
    "Sync-Details": "Sync details", "Keine offenen Sync-Details.": "No open sync details.",
    "QSO auswählen, um Sync-Details anzuzeigen.": "Select a QSO to display sync details.",
    "SYNC-FEHLER: ": "SYNC ERROR: ", "KONFLIKT: ": "CONFLICT: ",
    "Lokale und Wavelog-Version wurden seit dem letzten gemeinsamen Stand geändert.": "The local and Wavelog versions were both changed since the last shared state.",
    "Das QSO wurde in Wavelog gelöscht, lokal aber anschließend verändert.": "The QSO was deleted in Wavelog but was changed locally afterwards.",
    "Projekt unterstützen": "Support my work", "Buy Me a Coffee": "Buy Me a Coffee",
    "Datum UTC": "Date UTC", "Zeit": "Time", "DX-Rufzeichen": "DX callsign", "DX-Land": "DX country",
    "Spotter-Land": "Spotter country",
    "Rufzeichen": "Callsign", "Zeit UTC HHMMSS": "Time UTC HHMMSS", "Frequenz MHz": "Frequency MHz",
    "Locator": "Grid locator", "Leistung W": "Power W", "POTA Ref": "POTA ref", "SOTA Ref": "SOTA ref",
    "WWFF Ref": "WWFF ref",
    "Profil wechseln": "Switch profile", "Profil anlegen": "Create profile", "Profil umbenennen": "Rename profile",
    "Profil löschen": "Delete profile", "Profil gelöscht": "Profile deleted", "Name des neuen Profils:": "Name of the new profile:",
    "Name für das duplizierte Profil:": "Name for the duplicated profile:", "Neuer Profilname:": "New profile name:",
    "Bearbeiten fehlgeschlagen": "Editing failed", "Konflikt": "Conflict",
    "Stationsdaten sind profilspezifisch; Sprache und Theme gelten app-weit.": "Station data is profile-specific; language and theme apply app-wide.",
    "Backup und Wiederherstellung der Profile, Einstellungen und ADI-Logbücher werden hier ergänzt.": "Profile, settings and ADI logbook backup and restore will be added here.",
    "Diese Daten werden in deine ADI-Dateien geschrieben und funktionieren auch komplett ohne Internet.": "These values are written to your ADI files and work completely offline.",
    "Die Aktivierungsreferenzen werden automatisch als MY_* Felder in jedes neue QSO geschrieben.": "Activation references are written to every new QSO as MY_* fields.",
    "Name, Locator, QTH und – falls vorhanden – das Stationsfoto werden beim Tippen geladen. Ohne Internet läuft das Logging still weiter.": "Name, grid locator, QTH and, if available, the station photo are loaded while typing. Logging continues silently without internet.",
    "QRZ.com wird bei direkter Auswahl unabhängig von Wavelog abgefragt. Benutzername und Passwort sind dann erforderlich. QRZ kann ein XML-Abonnement voraussetzen.": "When selected directly, QRZ.com is queried independently of Wavelog. Username and password are then required. QRZ may require an XML subscription.",
    "Die Zugangsdaten können bereits profilspezifisch hinterlegt werden. Derzeit findet noch keine Verbindung, kein Download und kein Upload statt.": "Credentials can already be stored per profile. No connection, download or upload is active yet.",
    "ADI bleibt das primäre Logbuchformat. Die SQLite-Datei enthält nur Einstellungen, Sync-Metadaten und den Callbook-Cache.": "ADI remains the primary logbook format. SQLite contains only settings, sync metadata and the callbook cache.",
    "Doppelklick stimmt den TRX auf Frequenz und Mode ab. QSO übernehmen füllt anschließend das Formular.": "Double-click tunes the radio to frequency and mode. Use for QSO then fills the form.",
    "Überschriften sortieren · neu: hellblau · gleicher Mode gearbeitet: grün · Doppelklick stimmt TRX ab.": "Sort by headings · new: light blue · worked in the same mode: green · double-click tunes the radio.",
    "Fotoformat in dieser Laufzeit nicht verfügbar": "Photo format is not available in this runtime",
    "Hamlib ist nicht verfügbar.": "Hamlib is not available.",
    "Automatische Abfrage ist deaktiviert.": "Automatic lookup is disabled.",
    "Callbook wird abgefragt …": "Looking up callsign …", "Callbook-Abfrage ist deaktiviert.": "Callbook lookup is disabled.",
    "Spotter-Verbindung ist getrennt.": "Spotter connection is closed.",
    "Spotter-Verbindung wird erst beim Senden aufgebaut.": "The spotter connection is opened when sending.",
    "DX Cluster ist getrennt.": "DX Cluster is disconnected.",
    "DX Cluster ist getrennt · zum Empfangen bitte manuell verbinden.": "DX Cluster is disconnected · connect manually to receive spots.",
    "UDP-Logging ist ausgeschaltet.": "UDP logging is off.",
    "UDP-Logging ist ausgeschaltet · zum Empfangen bitte UDP starten.": "UDP logging is off · start UDP to receive QSOs.",
    "Mit Wavelog verbinden & synchronisieren": "Connect and synchronize with Wavelog",
    "Wavelog verbinden": "Connect Wavelog", "Aktivierung beenden": "End activation", "Beenden": "End",
    "Aktuellen Standort verwenden": "Use current location", "GPS übernehmen": "Use GPS",
    "Standortdaten online ergänzen": "Complete location online", "Standort ergänzen": "Complete location",
    "Mögliche Referenzen suchen": "Find possible references", "Referenzen suchen": "Find references",
    "Aktivierung starten": "Start activation", "Starten": "Start",
    "Ausgewählte Treffer übernehmen": "Use selected matches", "Treffer übernehmen": "Use matches",
    "POTA-Grenze prüfen": "Check POTA boundary", "POTA-Map": "POTA map",
    "Referenzdaten aktualisieren": "Update reference data", "Daten aktualisieren": "Update data",
    "Ausgewählte Aktivierung wiederholen": "Repeat selected activation",
    "Aktivierung wiederholen": "Repeat activation",
    "Mögliche Referenzen · Mehrfachauswahl mit Strg/Shift": "Possible references · multi-select with Ctrl/Shift",
    "Mögliche Referenzen · Strg/Shift": "Possible references · Ctrl/Shift",
}


PHRASES = (
    ("Schnell, lokal und unabhängig von einer Internetverbindung.", "Fast, local and independent of an internet connection."),
    ("Neues QSO erfassen und sicher lokal speichern.", "Log a new QSO and store it safely on this computer."),
    ("Pileups zügig abarbeiten: Rufzeichen und Enter.", "Work pileups quickly: callsign and Enter."),
    ("Seriennummern und Austauschdaten effizient protokollieren.", "Log serial numbers and exchanges efficiently."),
    ("Lokale QSOs prüfen und Wavelog bewusst manuell synchronisieren.", "Review local QSOs and synchronize with Wavelog manually."),
    ("Das lokale Logbuch auf einen Blick.", "Your local logbook at a glance."),
    ("Funkgerät über das eingebettete Hamlib steuern.", "Control the radio through the bundled Hamlib."),
    ("Live-Spots empfangen, filtern und an den TRX übergeben.", "Receive, filter and tune the radio to live spots."),
    ("QSOs von WSJT-X und kompatiblen Programmen empfangen.", "Receive QSOs from WSJT-X and compatible programs."),
    ("Stationsprofil, Online-Dienste und lokale Daten verwalten.", "Manage station profiles, online services and local data."),
    ("QSOs bleiben lokal, bis du\nmanuell synchronisierst.", "QSOs stay local until you\nsynchronize manually."),
    ("Online-Push:", "Online push:"), ("übertragen", "transferred"),
    ("Fehler · Voll-Sync erforderlich", "errors · full sync required"),
    ("neue QSO(s) zu Wavelog", "new QSO(s) to Wavelog"),
    ("Online-Abfrage optional · Offline-Logging bleibt immer verfügbar.", "Online lookup is optional · Offline logging always remains available."),
    ("CTY.DAT · keine Internetverbindung nötig", "CTY.DAT · no internet connection required"),
    ("Die Änderung wird nach einem Neustart der App aktiv.", "The change becomes active after restarting the app."),
    ("Einstellungen wurden gespeichert.", "Settings have been saved."),
    ("Einstellungen gespeichert", "Settings saved"),
    ("CAT ist ausgeschaltet", "CAT is off"), ("CAT ist gestoppt", "CAT is stopped"),
    ("CAT wird gestartet", "CAT is starting"), ("CAT verbunden", "CAT connected"),
    ("Frequenz:", "Frequency:"), ("Modus:", "Mode:"), ("Verbindung erfolgreich", "Connection successful"),
    ("Verbindung wird geprüft", "Testing connection"), ("Verbindung fehlgeschlagen", "Connection failed"),
    ("Keine Callbook-Daten gefunden", "No callbook data found"),
    ("keine Internetverbindung nötig", "no internet connection required"),
    ("zum Verbinden bitte CAT starten", "start CAT to connect"),
    ("wurde erfolgreich gestartet", "started successfully"),
    ("wurde gespeichert", "was saved"), ("wurde gelöscht", "was deleted"),
)


def translate_text(value: object, language: str) -> str:
    text = "" if value is None else str(value)
    if language != "en" or not text:
        return text
    translated = ENGLISH.get(text)
    if translated is not None:
        return translated
    for german, english in PHRASES:
        if german in text:
            text = text.replace(german, english)
    return text
