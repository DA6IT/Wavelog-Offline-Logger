# Changelog

[Deutsch](CHANGELOG.md) · **English**

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
