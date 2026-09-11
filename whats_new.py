from __future__ import annotations


# User-facing release copy only: describe what improves for the user.
# Avoid internal implementation terms, module names, APIs and developer jargon.

WHATS_NEW: dict[str, tuple[str, ...]] = {
    "0.21.0": (
    "Im DX-Cluster und beim QSO-Log lÃ¤sst sich das aktuelle Rufzeichen jetzt direkt auf QRZ.com Ã¶ffnen.",
    "Der QSL Card Manager zeigt E-Mail-QSL-Empfehlungen, wenn eine Gegenstation bei eQSL nicht gefunden wird oder dort seit mehr als sechs Monaten kein aktueller Log-Upload erkennbar ist und eine E-Mail-Adresse verfÃ¼gbar ist.",
    "Die eQSL-Mitgliederliste wird lokal gecacht und ausgewertet; QSL-Empfehlungen lÃ¶sen niemals automatisch einen Versand aus.",
    "Der QSL-Bereich wurde deutlich kompakter gestaltet, damit die Empfehlungsliste wesentlich mehr Platz erhÃ¤lt.",
    "Eine datensparsame pseudonyme Nutzungsstatistik kann hÃ¶chstens einmal tÃ¤glich Installations-ID, Version und Betriebssystem melden. Sie lÃ¤sst sich abschalten und die gespeicherten Statistikdaten kÃ¶nnen direkt aus der App gelÃ¶scht werden.",
),    "0.20.2": (
        "Der automatische Wavelog-Abgleich lässt sich jetzt verzögert ausführen; standardmäßig werden neue QSOs nach fünf Minuten gesammelt übertragen.",
        "Mehrere QSOs können gemeinsam ausgewählt und deutlich schneller gelöscht werden. Bei bereits synchronisierten QSOs warnt der Logger klar vor der späteren Löschung in Wavelog.",
        "Der Dublettenschutz für WSJT-X und externe digitale Logs wurde erweitert, damit wiederholte Abschlussmeldungen nicht unnötig doppelte oder dreifache QSOs erzeugen.",
        "Auch bereits doppelte Einträge in einer WSJT-X-Logdatei werden beim Import zuverlässiger erkannt und übersprungen.",
        "Vielen Dank an DO1DX für das hilfreiche Feedback und die Praxishinweise zu diesen Verbesserungen.",
    ),
    "0.20.1": (
        "Die Vorschau von QSL-Karten wurde verbessert, damit sie noch zuverlässiger der später versendeten Karte entspricht.",
        "Änderungen an bereits bekannten QSOs werden jetzt zuverlässiger mit dem QSL Card Manager abgeglichen.",
        "Die automatische Aktualisierung von QSL-Informationen wurde für große Logbücher optimiert.",
        "Sicherung und Wiederherstellung deiner Logger-Daten wurden sicherer und zuverlässiger gemacht.",
        "Zusätzlich wurden verschiedene kleinere Fehler behoben und die Stabilität verbessert.",
    ),
    "0.20.0": (
        "Neu: Der DA6IT.de QSL Card Manager ist direkt in den Offline Logger integriert – inklusive Motiven, persönlichem Layout, Vorschau und Versand aus dem Logbuch.",
        "Neue QSOs, QSL-Status und Motive werden nach der einmaligen Einrichtung automatisch im Hintergrund abgeglichen; Offline-Logging bleibt dabei jederzeit nutzbar.",
        "Einzelne QSLs können direkt versendet werden, mehrere ausgewählte QSOs laufen über die serverseitige Queue. Fehlende qsoUid-Zuordnungen werden vor dem Versand automatisch ergänzt.",
        "Optional kann eine private Kontrollkopie jeder versendeten QSL an eine bestätigte eigene E-Mail-Adresse geschickt werden, ohne diese der Gegenstation anzuzeigen.",
        "Der Logger versendet niemals selbstständig oder direkt per SMTP: QSL-Mail bleibt immer eine bewusste Benutzeraktion und läuft ausschließlich über DA6IT.de.",
    ),
    "0.19.4": (
        "Neu: Rotorsteuerung über Hamlib rotctld mit Live-Position, kompaktem Kompass und bewusster Peilungsübernahme aus dem QSO-Log.",
        "Hamlib Dummy ermöglicht einen vollständigen Test ohne echte Rotorhardware; STOP ist direkt im QSO-Log erreichbar.",
        "Netzwerk- und XML-Verarbeitung wurden weiter gehärtet, während CAT Setup und Callbook-Seitenleiste auf kleineren Fenstern kompakter bedienbar bleiben.",
    ),
    "0.19.3": (
        "Der neue WSJT-X Sync gleicht wsjtx_log.adi bidirektional mit dem lokalen Logbuch ab und kann gemeinsam mit Wavelog als sicherer Drei-Wege-Abgleich genutzt werden.",
        "Logbuch, Fast Log und Statistiken reagieren bei großen ADI-Logbüchern deutlich schneller; neue QSOs werden append-only mit Recovery-Journal gespeichert.",
        "Die Anwendung ist intern in klar getrennte Feature-Module aufgeteilt, wodurch neue Funktionen gezielter entwickelt und getestet werden können.",
    ),    "0.19.2": (
        "Der automatische Windows-Updater ersetzt und startet jetzt zuverlässig genau die ursprünglich gestartete EXE – unabhängig von Dateiname und Speicherort.",
        "Die Update-Übergabe erfolgt erst nach dem Beenden der Desktop-App über den Windows-Launcher, sodass der Update-Prozess nicht mehr vom internen Job Object beendet wird.",
        "Der Update-Helper ist vollständig mit Windows PowerShell 5.1 kompatibel und protokolliert den Ablauf inklusive Integritätsprüfung und Rollback.",
    ),
    "0.19.1": (
        "Der Dark Mode stellt Eingabefelder, Auswahllisten, Tabellen, Register und deaktivierte Bedienelemente kontrastreich dar.",
        "TUNE startet eine konfigurierte CAT-Verbindung bei Bedarf automatisch und verwendet beim FTX-1 den korrekten Tuner-Startbefehl.",
        "Hamlib kann unter Windows im CAT Setup sicher aktualisiert und auf die vorherige Version zurückgesetzt werden.",
    ),
    "0.19.0": (
        "FLRig lässt sich per IP/Hostname und Port verbinden und auf Wunsch automatisch im lokalen Netzwerk finden.",
        "Der Wavelog-3.2.0-Abgleich unterstützt ClubLog-Status und fragt Bestätigungen gezielt für das gewählte Stationsprofil ab.",
        "Wavelog-API-Fehler zeigen jetzt zusätzlich den maschinenlesbaren Fehlercode und vorhandene Details.",
    ),
    "0.18.4": (
        "Automatische Windows-Updates ersetzen und starten jetzt zuverlässig die tatsächlich gestartete Programmdatei – unabhängig von Speicherort und Dateiname.",
        "Das zuletzt gespeicherte QSO bleibt nach dem Leeren des Formulars zuverlässig für einen DX-Spot verfügbar.",
    ),
    "0.18.3": (
        "Screenshots und Darstellung der Dokumentation wurden angepasst.",
        "Die vollständige deutsche und englische Dokumentation ist enthalten.",
    ),
    "0.18.2": (
        "Die gesamte Oberfläche ist jetzt durchgängig auf Deutsch und Englisch verfügbar.",
        "Handbuch, Fehlerhilfe, Release-Dokumentation und Screenshot-Galerie liegen vollständig in beiden Sprachen bei.",
        "Die Sprache wird unter Einstellungen → Allgemein gewählt und gilt für alle Stationsprofile.",
    ),
    "0.18.0": (
        "WSJT-X zeigt Rufzeichen, Locator, Frequenz, Mode und Report bereits während des QSOs.",
        "Worked-Historie sowie Entfernung und Peilung stehen direkt im QSO-Formular bereit.",
        "Updates können nach Bestätigung automatisch geladen, geprüft und unter Windows installiert werden.",
        "Profile, Einstellungen und ADI-Logbücher lassen sich als ZIP sichern und wiederherstellen.",
        "Nach dem Leeren des Formulars kann das zuletzt geloggte QSO weiterhin gespottet werden.",
    ),
}

WHATS_NEW_EN: dict[str, tuple[str, ...]] = {
    "0.21.0": (
    "The DX Cluster and Log QSO pages can now open QRZ.com directly for the selected or currently entered callsign.",
    "The QSL Card Manager can recommend email QSLs when a station is missing from eQSL or has no recent log upload for more than six months and a usable email address is available.",
    "The eQSL member list is cached and evaluated locally, and QSL recommendations never trigger delivery automatically.",
    "The QSL area is substantially more compact so the recommendation list receives much more space.",
    "Privacy-conscious pseudonymous usage statistics can report the installation ID, version and operating system at most once per day. They can be disabled and the stored statistics can be deleted directly from the app.",
),    "0.20.2": (
        "Automatic Wavelog synchronization can now be delayed; by default, new QSOs are collected and uploaded after five minutes.",
        "Multiple QSOs can be selected and deleted together much faster. The Logger clearly warns when synchronized QSOs will also be removed from Wavelog during a later full sync.",
        "Duplicate protection for WSJT-X and external digital logs has been improved so repeated final exchanges do not create unnecessary duplicate or triplicate QSOs.",
        "Duplicates that already exist inside a WSJT-X log file are also detected and skipped more reliably during import.",
        "Many thanks to DO1DX for the helpful feedback and practical input behind these improvements.",
    ),
    "0.20.1": (
        "QSL card preview has been improved so it more reliably matches the card that is later sent.",
        "Changes to existing QSOs are now kept in sync with the QSL Card Manager more reliably.",
        "Automatic QSL updates have been optimized for large logbooks.",
        "Backup and restore of your Logger data are now safer and more reliable.",
        "Several smaller issues have also been fixed to improve overall stability.",
    ),
    "0.20.0": (
        "New: the DA6IT.de QSL Card Manager is integrated directly into the Offline Logger, including motifs, personal layouts, preview and sending from the logbook.",
        "New QSOs, QSL status and motifs synchronize automatically in the background after the one-time setup while offline logging always remains available.",
        "Single QSLs can be sent directly while multiple selected QSOs use the server-side queue. Missing qsoUid mappings are created automatically before sending.",
        "An optional private control copy of each sent QSL can be delivered to a verified personal email address without exposing that address to the remote station.",
        "The Logger never sends mail automatically or directly through SMTP: QSL delivery always remains an explicit user action and runs exclusively through DA6IT.de.",
    ),
    "0.19.4": (
        "New Hamlib rotctld rotor control with live position, compact compass and explicit bearing control from the QSO form.",
        "Hamlib Dummy provides a complete hardware-free test path, with STOP available directly in the QSO form.",
        "Network and XML handling have been hardened further while CAT Setup and the callbook sidebar remain compact and usable on smaller windows.",
    ),
    "0.19.3": (
        "The new WSJT-X Sync merges wsjtx_log.adi bidirectionally with the local logbook and can participate in a safe three-way workflow with Wavelog.",
        "Logbook, Fast Log and Statistics remain responsive with large ADI logs, while new QSOs use append-only storage with recovery journaling.",
        "The application is now split into focused feature modules so future changes can be developed and tested more independently.",
    ),    "0.19.2": (
        "The automatic Windows updater now reliably replaces and restarts the exact EXE that was originally launched, regardless of its filename or location.",
        "The update hand-off now happens through the Windows launcher after the desktop app exits, preventing the updater process from being terminated by the internal Job Object.",
        "The update helper is fully compatible with Windows PowerShell 5.1 and logs the process including integrity verification and rollback.",
    ),
    "0.19.1": (
        "Dark mode now renders inputs, selection lists, tables, tabs and disabled controls with consistent contrast.",
        "TUNE starts a configured CAT connection when required and uses the correct tuner-start command on the FTX-1.",
        "On Windows, Hamlib can be securely updated and rolled back from CAT Setup.",
    ),
    "0.19.0": (
        "FLRig can be connected by IP/hostname and port and optionally discovered on the local network.",
        "Wavelog 3.2.0 synchronization supports ClubLog status and requests confirmations for the selected station profile.",
        "Wavelog API errors now include the machine-readable error code and available details.",
    ),
    "0.18.4": (
        "Automatic Windows updates now reliably replace and restart the exact launched program file, regardless of its location or filename.",
        "The most recently saved QSO remains reliably available for a DX spot after the form is cleared.",
    ),
    "0.18.3": (
        "Documentation screenshots and presentation have been refined.",
        "The complete German and English documentation is included.",
    ),
    "0.18.2": (
        "The complete user interface is now consistently available in German and English.",
        "The user guide, troubleshooting, release documentation and screenshot gallery are included in both languages.",
        "Choose the language under Settings → General; it applies to all station profiles.",
    ),
    "0.18.0": (
        "WSJT-X displays callsign, grid locator, frequency, mode and report while the QSO is in progress.",
        "Worked history, distance and bearing are available directly in the QSO form.",
        "After confirmation, updates can be downloaded, verified and installed automatically on Windows.",
        "Profiles, settings and ADI logbooks can be backed up to and restored from a ZIP file.",
        "After clearing the form, the most recently logged QSO can still be sent as a DX spot.",
    ),
}


def notes_for_version(version: str, language: str = "de") -> tuple[str, ...]:
    table = WHATS_NEW_EN if language == "en" else WHATS_NEW
    return table.get(str(version or "").strip(), ())
