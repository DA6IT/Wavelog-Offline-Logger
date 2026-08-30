from __future__ import annotations


WHATS_NEW: dict[str, tuple[str, ...]] = {
    "0.18.3": (
        "Dokumentations-Screenshots werden jetzt garantiert ohne Windows-Taskleiste aufgenommen.",
        "Die vollständige deutsche und englische Dokumentation aus v0.18.2 ist enthalten.",
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
    "0.18.3": (
        "Documentation screenshots are now guaranteed to exclude the Windows taskbar.",
        "The complete German and English documentation from v0.18.2 is included.",
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
