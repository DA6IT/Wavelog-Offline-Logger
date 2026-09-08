# Changelog

## [0.20.0] - 2026-09-08

### Added

- complete **DA6IT.de QSL Card Manager** integration in the Offline Logger
- per-profile QSL Client API connection key stored locally as a secret and never written to logs
- stable local mapping of synchronized QSOs through `qsoUid`; WordPress database IDs are never used as cross-system identities
- download and local caching of community motifs, personal templates and station-profile-specific field positions
- compact QSL preview in a separate window without making the main application unnecessarily large
- direct single-QSL sending from the logbook plus multi-selection through the server-side mail queue
- QSL mail status in the logbook for cards successfully handed to the configured mail transport
- server-side QRZ.com recipient resolution; QRZ credentials are never stored in the Offline Logger
- optional **private control copy** to a verified personal email address; the remote station never sees that address
- automatic QSL background synchronization on application startup, profile changes and shortly after a newly logged QSO
- automatic retries after temporary offline/server failures plus a lightweight periodic status and motif refresh
- automatic single-QSO synchronization immediately before sending when a new QSO does not yet have a `qsoUid`

### Changed

- manual QSL synchronization is no longer required during normal operation and remains available only as an explicit force refresh
- community motifs automatically use the personal field positions of the matching station profile
- new QSOs are added to the QSL system only when required; historic QSOs are not unnecessarily re-queried against QRZ
- QSL and queue status are refreshed in the background without introducing a permanent daemon or aggressive polling
- QSL integration remains modular in `feature_qsl.py` and small technical QSL modules while `app.py` stays composition-only

### Security

- final QSL mail delivery always runs through DA6IT.de/Postfix; the Offline Logger never sends QSL mail directly through SMTP
- the Logger cannot supply an arbitrary normal QSL recipient address; the remote recipient remains server-authoritative through QRZ.com
- the private control copy is server-limited to a verified personal address and is hidden from the remote station
- QSL assets are loaded only through the intended DA6IT.de endpoint and processed locally with size/image limits
- Bandit: **0 Medium / 0 High**
- `pip-audit`: **no known vulnerabilities**

### Safety / Offline-first

- local ADIF files remain the authoritative QSO data source
- missing Internet connectivity never blocks local logging; QSL work is retried later
- automatic background synchronization **never sends QSL email on its own**
- sending always remains an explicit user action
- server state `sent` still means handed to the mail transport, not delivered to or read by the recipient

[Deutsch](CHANGELOG.md) · **English**

## 0.20.0 — 2026-09-08

### Added

- optional private **QSL control copy** to an approved email address; the server sends it as BCC so the other station cannot see the copy address
- integrated **DA6IT.de QSL Card Manager**
- stable server-generated `qsoUid` mapping for local QSOs
- QRZ recipient resolution with server cache and local status cache
- community motifs, personal layouts, local preview and PNG rendering
- direct single sending plus server-side queue for multi-selection
- new **Email QSL** logbook column

### Changed
- personal web layout positions are honored per station profile
- bulk sending uses the DA6IT.de mail queue for recipient resolution, limits and duplicate protection
- QSL background assets are loaded only from `https://da6it.de` and cached locally

### Security
- Connection Keys stay in secret storage and are never logged
- QSL API is pinned to `https://da6it.de/wp-json/da6it/v1/qsl/client/v1/`
- the server remains authoritative for recipients, mail limits, duplicate protection and `qsoUid`

### Safety
- sending requires an explicit user action
- no automatic bulk sending and no retroactive mass QRZ lookup

### Final 0.20.0 state

- automatic QSL background synchronization on app startup, profile changes and after new QSOs; offline/server failures are retried later without blocking local logging
- optional private QSL control copy to a verified personal email address; the remote station never sees that address
- manual QSL sync remains available as a force refresh; QSL mail is still sent only after an explicit user action

## 0.19.4 — 2026-09-06

### Added

- Hamlib `rotctld` rotor control with profile-specific model, interface, baud rate, local port and live position polling
- compact rotor compass in the QSO form; the bearing calculated from station grids can be sent with **Turn rotor** and stopped immediately with **STOP**
- Hamlib Dummy [ID 1] as a hardware-free test path for movement, position display and STOP
- `rotctld` is shipped alongside `rigctld` in Windows, macOS and Linux packages

### Changed

- CAT Setup remains vertically scrollable on smaller windows and supports scrollbar, mouse wheel and trackpad input
- the callbook photo area uses a smaller fixed maximum size
- Hamlib update and rollback handle CAT and rotor control together
- on Az/El rotors, **Turn rotor** changes azimuth while preserving the last known elevation

### Security

- QRZ and FLRig XML responses are size-bounded and validated before parsing
- URL access is restricted to HTTP(S); HTTPS redirect downgrades are blocked and sensitive headers are removed on cross-origin redirects
- opening the local log directory no longer uses shell interpolation
- `rotctld` listens on `127.0.0.1` only

### Safety

- callsign lookup and bearing calculation never move the rotor automatically; movement begins only after an explicit click
- profile changes, Hamlib replacement and application shutdown stop the app-managed rotor runtime cleanly

## 0.19.3 — 2026-09-06

### Added

- bidirectional file-based **WSJT-X synchronization** between `wsjtx_log.adi` and the local Offline Logger, with the Offline Logger acting as the merge hub between WSJT-X and Wavelog
- dedicated **WSJT-X Sync** settings tab with profile/rig selection, manual path selection and independent startup, shutdown and manual synchronization options
- backups before changing the WSJT-X log, duplicate matching with time/band/mode tolerances and protection against importing clearly foreign `STATION_CALLSIGN` records
- architecture and regression tests for feature separation, WSJT-X synchronization and append-only QSO storage

### Changed

- split the former monolithic `app.py` into focused `feature_*.py` modules plus `dialogs.py`, `app_common.py` and `ui_theme.py`, with explicit feature dependencies
- Logbook, Fast Log/DXpedition and Statistics now reuse shared QSO caches and background workers so navigation no longer performs full ADIF/SQLite work on the Tk main thread
- normal new QSOs are appended to an existing canonical ADI log instead of rewriting the whole file for every save
- the Windows launcher automatically packages `feature_*.py` files and derives its versioned runtime directory dynamically from `appVersion`
- updated the Windows build validation for the dynamic runtime directory

### Safety

- an `.append-journal` protects fast ADI appends from partial writes and supports controlled recovery on the next scan
- editing, deletion, ADIF import and migration intentionally keep the full verified rewrite path
- WSJT-X synchronization never performs automatic deletions; missing QSOs are added to the other side only

## 0.19.2 — 2026-09-05

- fixed the automatic Windows updater by handing installation over to the Go launcher only after the desktop app exits
- replaces and restarts the exact EXE originally launched by the user regardless of filename or location
- made the PowerShell helper compatible with Windows PowerShell 5.1 path and process behavior
- added SHA-256 verification for staging and installed files plus rollback on replacement or restart failure
- logs the full update flow under `%LOCALAPPDATA%\AFU-Tools\WavelogOfflineLogger\updates\update.log`
- documented that upgrading from v0.19.1 to v0.19.2 may require one manual installation because the v0.19.1 updater itself is affected

## 0.19.1 — 2026-09-05

- unified dark-mode contrast for entries, combo boxes and their drop-down lists, tables, tabs, lists and disabled controls
- the TUNE button can start the saved CAT connection automatically when required
- the FTX-1 uses `AC003` through Hamlib's raw-command bridge because the current beta backend still maps generic `vfo_op TUNE` incorrectly to `AC002`
- manually triggered Windows Hamlib updater in CAT Setup using the official GitHub release, SHA-256 verification and a runtime test before activation
- the previously used Hamlib version is retained for rollback; Linux and macOS continue to receive Hamlib through the verified application packages

## 0.19.0 — 2026-09-04

- FLRig can be used from CAT Setup through a freely editable `IP/hostname:port` endpoint
- optional FLRig discovery on the local computer and bounded private IPv4 networks with positive XML-RPC identification
- ClubLog status in the existing logbook and statistics QSL displays
- Wavelog 3.2.0 confirmation requests are restricted to the permitted station locations
- structured Wavelog API error codes and details are retained in the visible failure reason
- existing `qsl_meta` tables gain the `clublog` column automatically without changing stored status values

## 0.18.4 — 2026-08-30

- automatic Windows updates now replace and restart the exact launched EXE regardless of its location or custom filename
- the downloaded package and rollback copy are managed outside the user's program folder after replacement
- the most recently saved QSO remains reliably available as a DX-spot candidate after the form is cleared

## 0.18.3 — 2026-08-30

- refined and unified German and English documentation screenshots
- regenerated every documentation image for a clean, consistent presentation

## 0.18.2 — 2026-08-29

- completed English localization for all main pages, dialogs, confirmations, errors and runtime status messages
- added a complete English user and maintainer documentation set
- added full English screenshots for every main page and Settings tab
- release packages now contain both language variants; language is selected under Settings → General

## 0.18.1

- added verified Windows `VERSIONINFO` metadata, complete uninstall instructions and SignPath-readiness documentation
- documented CPython and project roles; Windows release intentionally remained unsigned

## 0.18.0

- added WSJT-X live QSO preview, worked history, distance and bearing in the QSO form
- added verified in-app downloads and automatic Windows replacement updates
- added first-start “What's new?”, backup/restore and last-QSO DX spotting after clearing the form

## 0.17.x

- introduced one continuous ADI file per profile with safe migration, ADIF import/export and xOTA
- added POTA catalogue/radius candidates, boundary verification and multiple references
- added Wavelog contest-session synchronization and broad responsive-layout fixes
- improved profile-specific UDP autostart and external-QSO callbook enrichment

## 0.16.x

- introduced the modern responsive UI, English UI option and Light/Dark themes
- added QRZ/Wavelog callbook information, photos, automatic online push and startup/shutdown full sync
- added Windows, macOS and Linux release pipelines and detailed illustrated documentation

## 0.15.x and earlier

- established offline-first ADI logging, profiles, Wavelog API v2 synchronization and conflict safety
- added Fast Log, contest logging, statistics, CAT/Hamlib, DX Cluster, UDP/WSJT-X and QSL status
- added Windows bootstrap packaging and cross-platform build foundations

The detailed German historical changelog remains available in [CHANGELOG.md](CHANGELOG.md).
