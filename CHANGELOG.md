# Changelog

Alle wesentlichen Änderungen dieses Projekts werden hier dokumentiert. Das Format orientiert sich an Keep a Changelog; Versionsnummern folgen Semantic Versioning.

## [Unreleased]

## [0.11.2-rc1] - 2026-08-13

### Added

- GitHub-taugliche Projekt-, Benutzer-, Architektur-, Sicherheits- und Beitragsdokumentation
- Reproduzierbare PowerShell-Skripte für Windows-Build und Release-Paket
- GitHub Actions für Selftests, Windows-Builds und tagbasierte Releases
- Regressionstest für den Unterschied zwischen externem ADI-Datenverlust und ausdrücklich angeforderter QSO-Löschung

### Changed

- Release Candidates verwenden einen eigenen versionsabhängigen Anwendungsordner
- Der Windows-Bootstrapper prüft den Python-Installer jetzt per SHA-256 statt MD5
- Windows schlägt bei einem DPAPI-Fehler sichtbar fehl, statt neue Tokens unbemerkt nur Base64-kodiert zu speichern

### Fixed

- Fehlt ein verknüpftes QSO außerhalb der Anwendung in der lokalen ADI-Datei, bleibt seine Sync-Zuordnung erhalten und Wavelog stellt es beim nächsten Abgleich lokal wieder her

## [0.11.1] - 2026-08-13

### Added

- Mehrprofilsystem mit getrennten Einstellungen, ADI-Dateien und Sync-Metadaten
- Contest-Logging mit profilbezogenen Presets, Seriennummern und Operatorwechsel

### Fixed

- Sichere Migration alter Sync-Hashes nach Erweiterung um Contest-Felder
- Keine falschen Massenkonflikte beim Upgrade von v0.10/v0.11.0
