from __future__ import annotations


WHATS_NEW: dict[str, tuple[str, ...]] = {
    "0.18.0": (
        "WSJT-X zeigt Rufzeichen, Locator, Frequenz, Mode und Report bereits während des QSOs.",
        "Worked-Historie sowie Entfernung und Peilung stehen direkt im QSO-Formular bereit.",
        "Updates können nach Bestätigung automatisch geladen, geprüft und unter Windows installiert werden.",
        "Profile, Einstellungen und ADI-Logbücher lassen sich als ZIP sichern und wiederherstellen.",
        "Nach dem Leeren des Formulars kann das zuletzt geloggte QSO weiterhin gespottet werden.",
    ),
}

WHATS_NEW_EN: dict[str, tuple[str, ...]] = {
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
