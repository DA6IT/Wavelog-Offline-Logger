# DA6IT.de Wavelog Offline Logger v0.24.0

v0.24.0 adds the new **Live DXpeditions** page, logbook filters, a calm DX spot table and file synchronization with **WS** (formerly WSJT-X Improved).

### Highlights

- **Live DXpeditions:** shows only DXpeditions spotted within the last 30 minutes – per band and mode with frequency, spot age, country, heading and distance from your locator. Colours show whether the country is new, the band/mode is missing or already worked. The newest spot is on top and every column can be sorted; double-click tunes the radio. Data from the DA6IT.de DXpedition calendar, only while the page is open.
- **Search and filter the logbook:** callsign search (with `*`/`?`, Ctrl+F) plus filters for band, mode, period, country, QSL status and sync status; **Export filtered** writes exactly the QSOs shown as ADIF.
- **WS instead of WSJT-X:** the file sync finds `%LOCALAPPDATA%\WS` and `WS - <rig name>` automatically, uses a log path chosen in WS and warns when an old WSJT-X folder is still selected. Sync now with the **Sync WSJT-X / WS** button on **Logbook & Sync**.
- **Calm DX spot list:** fixed columns, a new "Worked" column, selection and scroll position no longer jump; Enter tunes the radio.
- **Fewer backup copies:** the WSJT-X/WS sync keeps the newest 10 backups plus one per day of the last week.
- **More accurate countries:** imported QSOs with another country spelling count as a worked country again; calls such as `K6VHF/HR9` get the right country.

Dokumentation: [Deutsch](https://github.com/DA6IT/Wavelog-Offline-Logger/blob/v0.24.0/docs/USER_GUIDE.md) · [English](https://github.com/DA6IT/Wavelog-Offline-Logger/blob/v0.24.0/docs/en/USER_GUIDE.md)
