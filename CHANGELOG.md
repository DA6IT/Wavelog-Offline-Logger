# Changelog

**Deutsch** · [English](CHANGELOG.en.md)

## [0.18.4] - 2026-08-30

- automatische Windows-Updates ersetzen und starten die tatsächlich gestartete EXE unabhängig von ihrem Speicherort oder individuellen Dateinamen
- Downloadpaket und Rückfallkopie werden nach dem Austausch außerhalb des Benutzerordners verwaltet
- das zuletzt gespeicherte QSO bleibt nach dem Leeren des Formulars zuverlässig als DX-Spot-Kandidat erhalten

## [0.18.3] - 2026-08-30

- Screenshots und Darstellung der deutschen und englischen Dokumentation wurden vereinheitlicht
- sämtliche Dokumentationsabbildungen wurden neu erzeugt

## [0.18.2] - 2026-08-30

### Added

- vollständige englische Übersetzung aller Hauptseiten, Dialoge, Sicherheitsabfragen, Fehler- und Statusmeldungen
- vollständige englische Benutzer- und Maintainer-Dokumentation
- eigener englischer Screenshot-Satz für jede Hauptseite und jedes Einstellungsregister
- zweisprachige README, Release-Hinweise, Beitragsanleitung und Changelog

### Changed

- Release-Pakete und Prüfskripte verlangen und enthalten jetzt beide Sprachfassungen
- Sprachwahl unter Einstellungen → Allgemein gilt dokumentiert appweit für alle Stationsprofile

Alle wesentlichen Änderungen dieses Projekts werden hier dokumentiert. Das Format orientiert sich an Keep a Changelog; Versionsnummern folgen Semantic Versioning.

## [Unreleased]

## [0.18.1] - 2026-08-29

### Added

- Windows-`VERSIONINFO` mit einheitlichem Produktnamen, Produkt-/Dateiversion, Beschreibung und ursprünglichem Dateinamen; der Windows-Build bricht bei jeder Abweichung ab
- Vollständige Deinstallationsanweisungen für Windows, macOS, Debian/Ubuntu, Arch Linux und AppImage mit klarer Trennung von Programm-, Profil- und ADI-Daten
- CPython 3.12.10 und die Python Software Foundation License in den Drittanbieterhinweisen

### Changed

- Code-Signing-Rollen verwenden ausdrücklich die SignPath-Bezeichnungen Authors/Committers, Reviewers und Approvers
- SignPath-Unterlagen nennen v0.18.1 als noch unsigniertes Referenzrelease in exakt dem später zu signierenden Buildformat

## [0.18.0] - 2026-08-29

### Added

- Vollständiges ZIP-Backup und Restore aller Logger-Profile, Einstellungen, ADI-Dateien, Metadatenbanken und lokaler Zusatzdaten; vor jeder Wiederherstellung wird automatisch eine zusätzliche Sicherung angelegt
- Bestätigter In-App-Updater mit passender Plattformdatei, HTTPS-Download und verpflichtender SHA-256-Prüfung; unter Windows ersetzt ein separater Helfer die bisherige EXE nach dem Beenden
- Einmalige deutsch- oder englischsprachige „Was ist neu?“-Übersicht beim ersten Start einer neuen Version
- Das zuletzt erfolgreich geloggte QSO bleibt nach dem automatischen Leeren des Formulars als bewusster DX-Spot-Kandidat verfügbar
- Öffentliche Datenschutz-, Sicherheits- und Code-Signing-Richtlinien zur Vorbereitung der SignPath-Bewerbung

### Changed

- Der Update-Dialog führt bestätigte Aktualisierungen direkt aus, statt den Benutzer nur zur Downloadseite weiterzuleiten
- macOS- und Linux-Updates bevorzugen die zum gewählten Paket gehörende Prüfsummendatei; Windows verwendet weiterhin die vollständige `SHA256SUMS.txt`

### Security

- Restore-Archive werden vor Änderungen auf Format, Pfade, Dateianzahl und entpackte Gesamtgröße geprüft; bei Fehlern wird nicht übernommen und ein begonnener Austausch kann zurückgerollt werden
- Heruntergeladene Updatepakete werden erst nach erfolgreichem SHA-256-Abgleich aus der temporären Datei freigegeben

## [0.17.2] - 2026-08-28

### Added

- Worked-Anzeige im normalen QSO-Formular: Bereits auf demselben Band und Mode gearbeitete Rufzeichen werden grün markiert; frühere QSOs auf anderen Bändern oder Modes erscheinen als gelber Hinweis. Eine kompakte Historie zeigt zusätzlich die fünf neuesten lokalen QSOs mit Datum, UTC-Zeit, Band und Mode
- Extern über WSJT-X oder ADIF/UDP empfangene QSOs werden im Hintergrund über die konfigurierte Wavelog- oder QRZ.com-Callbook-Quelle ergänzt; vorhandene Senderdaten bleiben unverändert und Offline-Fehler blockieren das lokale Speichern nicht
- WSJT-X-Live-Vorschau: Statuspakete füllen während eines laufenden QSOs das normale Formular mit Rufzeichen, Locator, Frequenz, Band, Mode und Report; der vorhandene Callbook-Lookup zeigt schon vor dem Loggen Name, QTH, Foto und Worked-Historie. Gespeichert wird ausschließlich beim echten `QSO Logged`-Paket
- Offline berechnete Entfernung und Peilung zur Gegenstation im Callbook-Bereich, sobald eigener und fremder Maidenhead-Locator vorliegen

### Changed

- Nach jedem erfolgreichen manuellen oder externen QSO-Log wird das normale Formular zurückgesetzt; die bisher redundante Schaltfläche `Speichern + Neu` entfällt

### Fixed

- Beim Profilwechsel wird der UDP-Listener des vorherigen Profils beendet und für das neue Profil mit dessen eigener Host-/Port-Konfiguration automatisch neu gestartet, sofern dort UDP-Autostart aktiviert ist

## [0.17.1] - 2026-08-22

### Added

- Bidirektionaler Wavelog-Abgleich von Contest-Sessions, Einstellungen und QSO-Zuordnungen
- Automatische Übernahme der von Wavelog vergebenen Contest-Session-ID und der nächsten freien Seriennummer
- Automatischer Layout-Check aller Hauptseiten, Einstellungs-Tabs und unterstützten Fenstergrößen vor einem Release

### Changed

- Contest-Presets verwenden den Wavelog-Contest-Katalog; neue Contest-QSOs werden nach dem Online-Push der passenden Session zugeordnet
- Falls Wavelog die Contest-Session-API noch nicht anbietet, werden vorhandene Contest-QSOs anhand von `CONTEST_ID` und Jahr als lokale Presets rekonstruiert
- Modale Formulare verwenden kompakte, größenveränderbare Layouts statt starrer Fensterabmessungen
- Schrift, Karten, Widget-Abstände und Aktionsleisten reagieren nun gemeinsam auf die Fenstergröße; nicht notwendige Erklärungstexte weichen in der Kompaktansicht den Eingabefeldern

### Fixed

- Einstellungen und Aktionsschaltflächen werden bei kleineren Fenstern nicht mehr unterhalb oder seitlich außerhalb des sichtbaren Bereichs abgeschnitten
- Eine fehlende Wavelog-Catalog-API beendet den Contest-Abgleich nicht mehr vor der eigentlichen Funktionsprüfung
- Numerische Wavelog-IDs können nicht mehr versehentlich als ADIF Contest-ID gespeichert oder weitergeloggt werden

## [0.17.0] - 2026-08-22

### Added

- Integrierter xOTA-Bereich für kombinierte POTA-, SOTA-, WWFF-, IOTA-, COTA- und WCA-Aktivierungen
- Offline-GPS, lokale Maidenhead-Berechnung, editierbare Standortdaten, bestätigungspflichtige Referenzvorschläge und lokaler Referenzcache
- Dauerhafte Aktivierungs-/QSO-Zuordnung sowie sichere Auswahl oder bestätigte Erstellung einer passenden Wavelog Station Location
- ADIF-Import und -Export mit Prüfung, Dublettenschutz und Backup
- Vollständiger offizieller POTA-Parkkatalog als lokaler Offline-Cache, nahe 10-km-Marker plus markierte 25-km-Kandidaten für große Parks und direkte Grenzprüfung auf pota-map.info
- Mehrfachauswahl und gemeinsame Übernahme mehrerer gleichzeitiger xOTA-Referenzen
- DA6IT.de-Funkmastlogo als Fenster-, Taskleisten- und Windows-Dateiicon

### Changed

- Ein einziges ADIF-Logbuch pro Profil; bisherige Tagesdateien werden gesichert, zusammengeführt, verifiziert und anschließend archiviert
- Die Kopfzeilenuhr verwendet eine feste Breite und monospaced Ziffern, damit das Layout beim Sekundenwechsel nicht springt
- Der xOTA-Bereich passt Beschriftungen, Aktionsleisten und Tabellenspalten dynamisch an die verfügbare Fensterbreite an

### Fixed

- Windows-GPS verwendet die aktuelle WinRT-Geoposition-API und fällt bei fehlender Freigabe kontrolliert auf manuelle Koordinaten zurück
- Mehrere gleichzeitig markierte xOTA-Referenzen werden gemeinsam und ohne Dubletten in die Aktivierung übernommen
- Große POTA-Parks werden nicht mehr allein wegen eines mehr als 10 km entfernten Katalogmittelpunkts ausgeblendet

## [0.16.2] - 2026-08-20

### Added

- Optionale plattformgerechte Desktop-Benachrichtigung nach jedem erfolgreich lokal gespeicherten QSO
- Dezente Support-Links zu Buy Me a Coffee und PayPal in der App und in der README
- Native Zertifikatsspeicher-Unterstützung mit geprüftem CA-Bundle als Fallback für die eingebetteten Laufzeiten

### Changed

- Der vollständige Wavelog-Download wird clientseitig strikt auf das im aktiven Logger-Profil gewählte Wavelog-Stationsprofil begrenzt
- Direkte QRZ.com-Abfragen funktionieren unabhängig davon, ob Wavelog eingerichtet oder erreichbar ist
- Profilfremde oder nicht sicher zuordenbare Wavelog-QSOs werden nicht übernommen und bestehende unpassende Verknüpfungen werden als nachvollziehbarer Sync-Fehler angezeigt

### Fixed

- Wavelog- und QRZ-Verbindungen verwenden unter Windows, macOS und Linux den nativen System-Zertifikatsspeicher; typische `CERTIFICATE_VERIFY_FAILED`-Fehler durch fehlende Zwischenzertifikate werden vermieden
- Der Logger zeigt beim Profilwechsel nur das zum gewählten Wavelog-Stationsprofil gehörende Remote-Logbuch, ohne dass in Wavelog das aktive Logbuch umgestellt werden muss
- Ein QRZ.com-Lookup wird nicht mehr durch eine fehlende Wavelog-Konfiguration blockiert

## [0.16.1] - 2026-08-16

### Changed

- Das Hauptfenster skaliert Schrift, Felder, Buttons, Tabellen, Abstände, Navigation, Logo und Callbook-Fotos jetzt proportional mit der Fenstergröße
- Die unterstützte Mindestgröße wurde auf 900 × 580 Pixel reduziert; auf großen Fenstern wächst die Oberfläche kontrolliert mit

### Fixed

- Beim Verkleinern des Hauptfensters werden Inhalte nicht mehr einfach am Fensterrand abgeschnitten
- Das vollständig aufgebaute Hauptfenster wird beim App-Start sichtbar in den Vordergrund geholt und das Rufzeichenfeld erhält den Eingabefokus
- Der Windows-Publish-Ablauf behandelt leere native Ausgaben und JSON-Arrays unter Windows PowerShell 5.1 zuverlässig und wählt genau einen Release-Workflow aus

## [0.16.0] - 2026-08-15

### Added

- Neu gestaltete Oberfläche mit schmaler Navigation, DA6IT.de-Logo, deutschem und englischem UI sowie hellem und dunklem Theme
- Optionaler Callbook-Lookup über die Wavelog-API oder direkt über QRZ.com einschließlich Name, Locator, QTH, Zonen und optionalem Stationsfoto
- Profilbezogener Online-Modus, der ausschließlich neue `LOCAL ONLY`-QSOs direkt zu Wavelog pusht
- Unabhängige Optionen für einen vollständigen bidirektionalen Sync beim App-Start und beim Beenden
- Modales Statusfenster für automatische Start- und Abschluss-Syncs mit Ergebniszusammenfassung und bewusster OK-Freigabe
- TUNE-/ATU-Befehl im normalen QSO-Fenster über die vorhandene Hamlib-CAT-Verbindung
- Profilbezogener Autostart des UDP-Empfängers
- Automatisierte Linux-Pakete für x64 und ARM64 als DEB, AppImage und Arch-Paket
- Ausführliches Benutzerhandbuch mit echten, anonymitätsbewusst ausgewählten App-Screenshots

### Changed

- Einstellungen sind in **Allgemein**, **Station & Wavelog**, **Callbook & Online-Dienste** und **Daten & Verbindungen** gegliedert
- Online-Erreichbarkeit wird direkt an der konfigurierten Wavelog-API geprüft; ohne Verbindung bleibt die App still im Modus `LOCAL ONLY`
- Beim Abschluss-Sync werden CAT, DX-Cluster und UDP-Empfang zuerst gestoppt, damit während des letzten Abgleichs kein neues externes QSO eingeht
- Callbook-Seitenleiste besitzt eine feste Größe und springt beim Wechsel zwischen Rufzeichen mit und ohne Foto nicht mehr
- Das DA6IT.de-Logo öffnet die Projektwebsite im Standardbrowser

### Fixed

- Linux-Verbindungstests behalten Fehlermeldungen aus asynchronen Tkinter-Callbacks korrekt bei
- Callbook-Anzeige wird nach einem vorher geladenen Foto vollständig und ohne übergroße Leerfläche zurückgesetzt
- Automatische Laufzeit-Uploads wiederholen mehrdeutige fehlgeschlagene Erstübertragungen nicht blind und vermeiden damit mögliche Duplikate
- Der lokale Windows-Release-Build benötigt kein `pip` mehr; das freigegebene Pillow-Wheel wird direkt geladen und gegen seine fest hinterlegte PyPI-SHA-256-Prüfsumme geprüft

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
