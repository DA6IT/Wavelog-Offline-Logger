# DA6IT.de Wavelog Offline Logger v0.23.0

## Deutsch

v0.23.0 ersetzt WaveLogGate durch eine eingebaute Wavelog-Verbindung für Funkgerät und Rotor und sorgt dafür, dass beim Bearbeiten, Importieren und Abgleichen alle Angaben eines QSOs erhalten bleiben.

### Highlights

- **Wavelog-Verbindung für Funkgerät:** Frequenz, Modus und Sendeleistung erscheinen in Wavelog; ein Klick auf einen DX-Spot oder in die Bandmap stellt das Funkgerät ein; „Live - WebSocket“ zeigt den Funkgerätestatus direkt an; der Rotor kann der Peilung aus Wavelog folgen. Einschalten unter **CAT → Wavelog-Verbindung für Funkgerät** – WaveLogGate vorher beenden. Das API-Token braucht die Berechtigung `radio:write`.
- **Alle QSO-Angaben bleiben erhalten:** Auch Felder wie DOK, IOTA, Satellit, SIG, Bundesland/County oder QSL-Hinweise, die der Logger nicht selbst anzeigt, bleiben beim Bearbeiten, Löschen, Importieren und Abgleichen erhalten.
- **Abgleich ergänzt statt ersetzt:** Sendeleistung, QSO-Ende und eigene Angaben wie Portabel-Locator oder POTA-Referenz bleiben erhalten. Früher verlorene Angaben wie DOK oder IOTA holt der erste vollständige Abgleich aus Wavelog zurück.
- **Mehr übertragene Daten:** Satelliten-QSOs, DOK, IOTA, SIG, Bundesland/County und das QSO-Ende werden mit Wavelog ausgetauscht; lokal geleerte Felder werden auch in Wavelog geleert.
- **Sichereres Löschen:** Ein QSO wird lokal erst entfernt, wenn Wavelog die Löschung einzeln bestätigt; fehlen ungewöhnlich viele QSOs, fragt der Logger vorher nach.
- **Zuverlässigere Zuordnung:** QSOs rund um Mitternacht UTC werden wiedererkannt statt doppelt angelegt; die Verbindung funktioniert auch mit Servern, die „Missing API token“ meldeten.

Tipp: Vor dem ersten vollständigen Abgleich nach dem Update ein Backup anlegen (**Einstellungen → Allgemein → Daten & Backup**).

Dokumentation: [Deutsch](https://github.com/DA6IT/Wavelog-Offline-Logger/blob/v0.23.0/docs/USER_GUIDE.md) · [English](https://github.com/DA6IT/Wavelog-Offline-Logger/blob/v0.23.0/docs/en/USER_GUIDE.md)

---

## English

v0.23.0 replaces WaveLogGate with a built-in Wavelog connection for radio and rotator and keeps every detail of a QSO when editing, importing and synchronizing.

### Highlights

- **Wavelog radio connection:** frequency, mode and TX power appear in Wavelog; a click on a DX spot or the bandmap tunes the radio; “Live - WebSocket” shows the radio status directly; the rotator can follow the bearing from Wavelog. Enable it under **CAT → Wavelog radio connection** – close WaveLogGate first. The API token needs the `radio:write` permission.
- **Every QSO detail is kept:** fields such as DOK, IOTA, satellite, SIG, state/county or QSL hints that the Logger does not display itself are kept when editing, deleting, importing and synchronizing.
- **Synchronization adds instead of replacing:** TX power, QSO end time and your own data such as a portable locator or POTA reference are kept. Details lost earlier, such as DOK or IOTA, are restored from Wavelog by the first complete synchronization.
- **More data exchanged:** satellite QSOs, DOK, IOTA, SIG, state/county and the QSO end time are exchanged with Wavelog; fields cleared locally are cleared in Wavelog as well.
- **Safer deletion:** a QSO is only removed locally once Wavelog confirms the deletion individually; if unusually many QSOs are missing, the Logger asks first.
- **More reliable matching:** QSOs around midnight UTC are recognised instead of being duplicated; the connection also works with servers that reported “Missing API token”.

Tip: create a backup (**Settings → General → Data & backup**) before the first complete synchronization after the update.

Dokumentation: [Deutsch](https://github.com/DA6IT/Wavelog-Offline-Logger/blob/v0.23.0/docs/USER_GUIDE.md) · [English](https://github.com/DA6IT/Wavelog-Offline-Logger/blob/v0.23.0/docs/en/USER_GUIDE.md)
