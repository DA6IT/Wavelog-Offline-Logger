# Changelog

Alle wesentlichen Änderungen dieses Projekts werden hier dokumentiert. Das Format orientiert sich an Keep a Changelog; Versionsnummern folgen Semantic Versioning.

## [Unreleased]

## [0.15.0] - 2026-08-14

### Added

- Reproduzierbare GitHub-Actions-Builds für eigenständige macOS-App-Bundles auf Apple Silicon und Intel
- Plattformgerecht kompiliertes und im macOS-App-Bundle eingebettetes Hamlib 4.7.2 einschließlich Prüfsummen- und Portabilitätskontrolle

### Changed

- CAT findet die eingebettete Hamlib-Laufzeit jetzt auch in einem eingefrorenen PyInstaller-App-Bundle

## [0.14.0] - 2026-08-13

### Added

- Neuer Fast-Log-/DXpedition-Modus für schnelle lokale Pileup-Erfassung mit festem Band, Mode, Frequenz, Rapport und Leistung
- Sitzungsübersicht, QSO-Rate, Dupe-Hinweis nach Band und Mode sowie kontrolliertes Zurücknehmen des letzten ausschließlich lokalen Fast-Log-QSOs
- Getrennte profilbezogene DXSpider-Verbindung für den öffentlichen Spotversand; Standard ist `dxcluster.afu-tools.de:7301`
- Erweiterte lokale Mode-Erkennung aus Spot-Kommentaren, üblichen FT8-Frequenzen und eindeutigen Bereichen des IARU-Region-1-Bandplans

### Changed

- DX-Cluster- und Spotter-Login verwenden automatisch das Stationsrufzeichen beziehungsweise den Operator des aktiven Profils
- Worked-Markierungen für DX-Rufzeichen und Länder vergleichen jetzt Band und Mode
- Beim öffentlichen Spotversand wird der gewählte Mode als DXSpider-Kommentarhinweis mitgesendet
- Ein erneuter GitHub-Release-Lauf für einen vorhandenen Tag ersetzt die Assets, statt wegen eines bereits vorhandenen Releases abzubrechen

### Fixed

- Schreibweisen wie `FT-8`, `JS8Call`, `FMN`, `D-STAR` und weitere gebräuchliche Mode-Hinweise werden beim Spot-Empfang zuverlässig erkannt

## [0.13.0-rc1] - 2026-08-13

### Added

- Profilbezogenes UDP Logging für das native WSJT-X-Protokoll und vollständige ADIF-Datensätze anderer Programme
- Frei wählbare Bind-Adresse und UDP-Portnummer mit verständlicher Meldung bei bereits belegtem Port
- Automatische WSJT-X-Heartbeat-Antwort und Duplikatschutz für mehrfach gesendete QSOs
- Profilbezogener Telnet-DX-Cluster mit frei wählbarem Host, Port und Login-Rufzeichen; vorbelegt mit dxcluster.afu-tools.de:7300
- Nach Band, Mode und Zeitraum filterbare Spotliste; Standardansicht sind die letzten 30 Minuten
- Profilbezogener Filter für die Region des Spotters: Europa, Nordamerika, Südamerika, Asien/Pazifik, Afrika oder Unbekannt
- DX- und Spotter-Land aus der Offline-Länderdatenbank sowie zellgenaue Worked-Markierung aus dem lokalen ADI-Logbuch
- Hellblaue Hervorhebung neuer Spots für zwei Minuten
- Sofortige Anzeige fortlaufend empfangener Live-Spots mit Sitzungszähler und Zeit des letzten Empfangs
- Sortierung über alle Tabellenüberschriften einschließlich DX-Land und Spotter-Land; jüngster Spot steht standardmäßig oben
- Getrennte Bedienung: Doppelklick stimmt den TRX auf Frequenz und Mode ab, **QSO übernehmen** füllt das Formular
- Bewusst bestätigter öffentlicher DX-Spot-Versand aus dem normalen QSO-Formular

### Changed

- Über UDP empfangene QSOs durchlaufen denselben ADI- und LOCAL-ONLY-Speicherpfad wie manuell erfasste QSOs
- Der UDP-Empfänger startet bewusst manuell und wird bei Profilwechsel oder Programmende sicher gestoppt
- Auch die DX-Cluster-Verbindung startet nur manuell und wird bei Profilwechsel oder Programmende beendet; ohne Internet bleibt der Offline-Betrieb unverändert
- Generisches SSB und Spots ohne Mode-Angabe werden bandabhängig als LSB oder USB behandelt
- Worked-Markierungen vergleichen zusätzlich den Mode, damit beispielsweise ein FT8-QSO keinen USB-Spot als gearbeitet markiert

## [0.12.0-rc2] - 2026-08-13

### Fixed

- Ein während des Beendens noch startender `rigctld`-Prozess wird zuverlässig erkannt und sofort beendet
- CAT-Einstellungen lassen sich getrennt speichern; **CAT starten** und **CAT stoppen** steuern die Verbindung eindeutig

### Changed

- Der Windows-Launcher tritt vor dem Start der Python-Anwendung einem Kill-on-close-Job bei, sodass auch verbleibende CAT-Kindprozesse beim Beenden entfernt werden
- CAT startet nach jedem Programmstart grundsätzlich ausgeschaltet und muss bewusst manuell gestartet werden

## [0.12.0-rc1] - 2026-08-13

### Added

- Neues profilbezogenes CAT Setup für Funkgerät, COM-Port und serielle Parameter
- Gebündeltes Hamlib 4.7.2 mit dynamischer Auswahl aus mehr als 300 Funkgerätemodellen; keine separate Hamlib-Installation erforderlich
- Automatische CAT-Übernahme von Frequenz, Band und Mode in QSO- und Contest-Logging
- Hintergrundprüfung auf neuere GitHub-Releases mit stiller Fehlerbehandlung bei fehlender Internetverbindung
- Lizenzhinweise und Original-Lizenzdateien für die eingebetteten Hamlib-Komponenten

### Fixed

- Der vom Yaesu FTX-1 gemeldete Hamlib-Modus `FMN` wird beim Loggen korrekt als `FM` übernommen

### Changed

- Der Windows-Build lädt und prüft das offizielle Hamlib-x64-Paket reproduzierbar während des Builds und bettet die benötigten Dateien in die EXE ein

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
