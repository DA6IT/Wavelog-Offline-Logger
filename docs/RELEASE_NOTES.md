# DA6IT.de Wavelog Offline Logger v0.24.0

## Deutsch

v0.24.0 bringt die neue Seite **Live DXpeditionen**, Filter im Logbuch, eine ruhige DX-Spot-Tabelle und den Datei-Abgleich mit **WS** (früher WSJT-X Improved).

### Highlights

- **Live DXpeditionen:** zeigt nur DXpeditionen, die in den letzten 30 Minuten gespottet wurden – je Band und Mode mit Frequenz, Alter des Spots, Land, Richtung und Entfernung vom eigenen Locator. Farbig markiert, ob das Land neu ist, das Band/der Mode fehlt oder schon gearbeitet wurde. Der aktuellste Spot steht oben, jede Spalte ist sortierbar; Doppelklick stimmt den TRX ab. Daten vom DA6IT.de DXpedition-Kalender, nur solange die Seite offen ist.
- **Logbuch durchsuchen und filtern:** Rufzeichensuche (mit `*`/`?`, Strg+F) plus Filter nach Band, Mode, Zeitraum, Land, QSL-Status und Sync-Status; **Gefilterte exportieren** schreibt genau die angezeigten QSOs als ADIF.
- **WS statt WSJT-X:** Der Datei-Abgleich findet `%LOCALAPPDATA%\WS` und `WS - <Rig-Name>` automatisch, übernimmt einen in WS gewählten Logpfad und weist auf einen noch gewählten alten WSJT-X-Ordner hin. Abgleichen geht jetzt mit dem Knopf **WSJT-X / WS abgleichen** unter **Logbuch & Sync**.
- **Ruhige DX-Spot-Liste:** feste Spalten, neue Spalte „Gearbeitet“, Auswahl und Scrollposition springen nicht mehr; Enter stimmt den TRX ab.
- **Weniger Sicherungskopien:** Beim WSJT-X/WS-Abgleich bleiben die letzten 10 Backups und je eines pro Tag der letzten Woche erhalten.
- **Genauere Länder:** Importierte QSOs mit anderer Länder-Schreibweise zählen wieder als gearbeitetes Land; Rufzeichen wie `K6VHF/HR9` werden dem richtigen Land zugeordnet.

Dokumentation: [Deutsch](https://github.com/DA6IT/Wavelog-Offline-Logger/blob/v0.24.0/docs/USER_GUIDE.md) · [English](https://github.com/DA6IT/Wavelog-Offline-Logger/blob/v0.24.0/docs/en/USER_GUIDE.md)

---

## English

v0.24.0 adds the new **Live DXpeditions** page, logbook filters, a calm DX spot table and file synchronization with **WS** (formerly WSJT-X Improved).

### Highlights

- **Live DXpeditions:** shows only DXpeditions spotted within the last 30 minutes – per band and mode with frequency, spot age, country, heading and distance from your locator. Colours show whether the country is new, the band/mode is missing or already worked. The newest spot is on top and every column can be sorted; double-click tunes the radio. Data from the DA6IT.de DXpedition calendar, only while the page is open.
- **Search and filter the logbook:** callsign search (with `*`/`?`, Ctrl+F) plus filters for band, mode, period, country, QSL status and sync status; **Export filtered** writes exactly the QSOs shown as ADIF.
- **WS instead of WSJT-X:** the file sync finds `%LOCALAPPDATA%\WS` and `WS - <rig name>` automatically, uses a log path chosen in WS and warns when an old WSJT-X folder is still selected. Sync now with the **Sync WSJT-X / WS** button on **Logbook & Sync**.
- **Calm DX spot list:** fixed columns, a new "Worked" column, selection and scroll position no longer jump; Enter tunes the radio.
- **Fewer backup copies:** the WSJT-X/WS sync keeps the newest 10 backups plus one per day of the last week.
- **More accurate countries:** imported QSOs with another country spelling count as a worked country again; calls such as `K6VHF/HR9` get the right country.

Dokumentation: [Deutsch](https://github.com/DA6IT/Wavelog-Offline-Logger/blob/v0.24.0/docs/USER_GUIDE.md) · [English](https://github.com/DA6IT/Wavelog-Offline-Logger/blob/v0.24.0/docs/en/USER_GUIDE.md)
