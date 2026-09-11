# Changelog

**Deutsch** · [English](CHANGELOG.en.md)

## [0.21.0] - 2026-09-11

### Added

- direkter **QRZ.com öffnen**-Button für den ausgewählten DX-Cluster-Spot
- direkter QRZ.com-Aufruf für das aktuell eingegebene Rufzeichen im Reiter **QSO loggen**
- lokale QSL-Empfehlungen auf Basis der eQSL-Mitgliederliste
- 6-Monats-Aktivitätsregel für eQSL-Empfehlungen: nicht gefundene Rufzeichen sowie Accounts ohne aktuellen Log-Upload können als E-Mail-QSL-Kandidaten erscheinen
- pseudonyme Nutzungsstatistik mit zufälliger Installations-ID, App-Version und Betriebssystemfamilie
- sichtbare Installations-ID in den Einstellungen sowie Funktionen zum Kopieren und Löschen der zugehörigen Statistikdaten

### Changed

- der QSL Card Manager wurde deutlich kompakter gestaltet, damit die QSL-Empfehlungsliste wesentlich mehr Platz erhält
- die eQSL-Mitgliederliste wird lokal gecacht und nach Ablauf des Cache-Zeitraums im Hintergrund aktualisiert
- bereits versendete sowie laufende/queued QSL-Mails werden aus den Empfehlungen ausgeschlossen
- die stabile Installationskennung der Nutzungsstatistik wird korrekt als pseudonym statt anonym beschrieben
- README, Benutzerhandbuch, Architektur- und Datenschutztexte wurden an die neuen Funktionen angepasst

### Privacy / Safety

- die Nutzungsstatistik überträgt keine Rufzeichen, QSOs, Locator, E-Mail-Adressen, Wavelog-URLs, Zugangsdaten, Profilnamen oder detaillierte Funktionsnutzung
- vor Bestätigung des Erststart-Hinweises wird kein Statistik-Heartbeat gesendet; die Funktion kann später abgeschaltet werden
- DA6IT.de speichert in den Statistiktabellen nur den SHA-256-Hash der zufälligen Installations-ID; normale Webserver-/Security-Logs können unabhängig davon Verbindungsmetadaten verarbeiten
- die eQSL-Auswertung erfolgt lokal; für die Empfehlung werden keine lokalen QSOs oder Rufzeichenlisten an eQSL übertragen
- QSL-Empfehlungen lösen niemals selbstständig einen Versand aus; jede QSL-Mail bleibt eine ausdrückliche Benutzeraktion

### Security / Reliability

- der eQSL-Download ist größenbegrenzt und auf den vorgesehenen HTTPS-Host beschränkt
- ein neuer eQSL-Cache wird erst nach erfolgreichem Parsen und Plausibilitätsprüfung aktiviert
- Fehler beim eQSL-Refresh überschreiben keinen bereits nutzbaren Cache
- die neuen eQSL- und Nutzungsstatistik-Tests laufen zusätzlich in der GitHub-CI

## [0.20.2] - 2026-09-11

### Added

- profilspezifisch konfigurierbare Verzögerung für den automatischen Wavelog-Upload mit Auswahl von 1 bis 60 Minuten; Standard sind 5 Minuten
- Mehrfachauswahl beim Löschen von QSOs mit zusammengefasster Sicherheitsabfrage und sichtbarer Anzahl bereits mit Wavelog verknüpfter QSOs
- gemeinsame Dublettenerkennung für WSJT-X-Sync, ADIF-Import und UDP-Logging

### Changed

- der Auto-Sync arbeitet batchweise: das erste neue QSO startet den Timer, weitere QSOs verlängern das Zeitfenster nicht erneut
- Mehrfachlöschungen lesen und schreiben das lokale ADIF-Log nur einmal und bleiben dadurch auch bei großen Logbüchern schnell
- nach einer Löschung bleibt die Ansicht am nächsten sinnvollen QSO statt an den Anfang des Logbuchs zu springen
- FT8/FT4 und weitere WSJT-Familienmodi erkennen zeitlich nahe Wiederholungen desselben QSOs toleranter; andere Betriebsarten bleiben streng abgeglichen
- Dubletten, die bereits innerhalb derselben importierten WSJT-X-ADIF-Datei vorhanden sind, werden während desselben Imports erkannt

### Safety / Sync

- Remote-Löschungen bleiben ausdrücklich dem vollständigen Sync vorbehalten; der normale verzögerte Auto-Push löscht keine QSOs in Wavelog
- beim Löschen bereits synchronisierter QSOs weist ein deutlicher Warnhinweis auf die spätere Löschung in Wavelog hin
- lokales ADIF bleibt weiterhin die maßgebliche QSO-Datenquelle

### Danke

- Vielen Dank an **DO1DX** für das hilfreiche Feedback und die Praxishinweise zu diesen Verbesserungen.

## [0.20.1] - 2026-09-09

### Fixed

- QSL-Vorschau und Versand verwenden jetzt denselben Renderpfad; dadurch entspricht die Vorschau zuverlässiger der tatsächlich versendeten PNG-Karte
- horizontale Ausrichtung von QSL-Feldern mit `center` und `right` bleibt beim Rendern korrekt erhalten
- QSL-Hintergrundbilder werden bei einer neuen Vorlagenrevision zuverlässig neu geladen, auch wenn die Bild-URL unverändert bleibt

### Changed

- der QSL-Abgleich überträgt zusätzliche für den Card Manager relevante QSO-/ADIF-Felder, sofern sie im lokalen QSO vorhanden sind
- bereits zugeordnete QSOs werden erneut abgeglichen, wenn sich ihr QSL-relevanter Inhalt geändert hat; bestehende Zuordnungen aus älteren Versionen werden einmalig nachgezogen
- der regelmäßige QSL-Statusabgleich ist für große Logbücher begrenzt und priorisiert fehlende sowie aktive Zustände
- stabile QSL-Zustände werden deutlich seltener erneut abgefragt, um unnötige Serverlast zu vermeiden
- die Texte unter **Was ist neu?** sind bewusst anwenderfreundlich formuliert; technische Details bleiben im Changelog und in den Release Notes

### Security / Reliability

- Wiederherstellung von Backups prüft ZIP-Pfade jetzt plattformübergreifend strenger und blockiert Traversal-, Windows-Pfad-, Symlink- und Pfadkollisionsfälle
- Manifest, Profilregister, Profil-IDs und referenzierte ADI-Dateien eines Backups werden vor der Wiederherstellung gegengeprüft
- die GitHub-CI enthält jetzt eigene Security-Checks mit Bandit, `pip-audit` und `detect-secrets`
- Bandit: **0 Medium / 0 High**
- `pip-audit`: **keine bekannten Vulnerabilities**

## [0.20.0] - 2026-09-08

### Added

- vollständige Integration des **DA6IT.de QSL Card Managers** in den Offline Logger
- profilspezifischer Verbindungsschlüssel für die QSL Client API; der Schlüssel wird lokal als Secret gespeichert und niemals in Logs ausgegeben
- stabile lokale Zuordnung jedes synchronisierten QSOs über `qsoUid`; WordPress-Datenbank-IDs werden nicht als systemübergreifende Identität verwendet
- Abruf und lokaler Cache von Community-Motiven, persönlichen Vorlagen und profilspezifischen Feldpositionen
- kompakte QSL-Vorschau in einem separaten Fenster, ohne die Hauptoberfläche unnötig zu vergrößern
- direkter Versand einer einzelnen QSL aus dem Logbuch sowie Mehrfachauswahl mit serverseitiger Mail-Queue
- QSL-Mailstatus direkt im Logbuch; erfolgreich an den Mailtransport übergebene QSLs werden mit einem Status angezeigt
- serverseitige QRZ.com-Empfängerermittlung; QRZ-Zugangsdaten werden nicht im Offline Logger gespeichert
- optional aktivierbare **private Kontrollkopie** an eine bestätigte eigene E-Mail-Adresse; die Gegenstation sieht diese Adresse nicht
- automatischer QSL-Hintergrundabgleich beim Programmstart, nach Profilwechseln und kurz nach neu gespeicherten QSOs
- automatischer Retry nach vorübergehenden Offline-/Serverfehlern sowie regelmäßiger leichter Status- und Motivabgleich
- automatischer Einzel-QSO-Sync direkt vor einem Versand, falls ein neues QSO noch keine `qsoUid` besitzt

### Changed

- der bisher manuell notwendige QSL-Sync ist im Normalbetrieb nicht mehr erforderlich und bleibt nur als bewusster Force-Refresh erhalten
- Community-Motive verwenden automatisch die persönlichen Feldpositionen des passenden Stationsprofils
- neue QSOs werden im Hintergrund nur bei Bedarf zum QSL-System ergänzt; bestehende alte QSOs werden nicht unnötig erneut gegen QRZ geprüft
- QSL-Status und Queue-Ergebnisse werden im Hintergrund nachgezogen, ohne einen permanenten Daemon oder aggressives Polling einzuführen
- die QSL-Integration bleibt modular in `feature_qsl.py` und kleinen technischen QSL-Modulen; `app.py` bleibt reine Komposition

### Security

- der endgültige QSL-Mailversand erfolgt ausschließlich über DA6IT.de/Postfix; der Offline Logger versendet niemals direkt per SMTP
- der Logger übergibt keine frei wählbare Empfängeradresse für normale QSL-Mails; die Gegenstationsadresse bleibt serverseitig über QRZ.com autoritativ
- die private Kontrollkopie wird serverseitig auf eine bestätigte eigene Adresse begrenzt und ist für die Gegenstation nicht sichtbar
- QSL-Assets werden nur über den vorgesehenen DA6IT.de-Endpunkt geladen und lokal mit Größen-/Bildgrenzen verarbeitet
- Bandit: **0 Medium / 0 High**
- `pip-audit`: **keine bekannten Vulnerabilities**

### Safety / Offline-First

- lokale ADIF-Dateien bleiben die maßgebliche QSO-Datenquelle
- fehlende Internetverbindung blockiert das lokale Logging nicht; QSL-Aktionen werden später erneut versucht
- der automatische Hintergrundabgleich **versendet niemals selbstständig QSL-Mails**
- Mailversand bleibt immer eine ausdrückliche Benutzeraktion
- ein Serverstatus `sent` bedeutet weiterhin Übergabe an den Mailtransport, nicht Zustellung oder Lesen beim Empfänger

## [0.19.4] - 2026-09-06

### Added

- Rotorsteuerung über Hamlib `rotctld` mit profilspezifischem Modell, Schnittstelle, Baudrate, lokalem Port und Live-Positionsabfrage
- kompakter Rotor-Kompass im QSO-Log; die aus den Locators berechnete Peilung kann mit **Rotor drehen** bewusst angefahren und mit **STOP** jederzeit angehalten werden
- Hamlib Dummy [ID 1] als hardwarefreier Testpfad für Bewegung, Positionsanzeige und STOP
- `rotctld` wird gemeinsam mit `rigctld` in Windows-, macOS- und Linux-Paketen bereitgestellt

### Changed

- CAT Setup bleibt auf kleineren Fenstern vertikal scrollbar und unterstützt Scrollbar, Mausrad und Trackpad
- der Callbook-Fotobereich verwendet eine kompaktere feste Maximalgröße
- Hamlib-Update und Rollback berücksichtigen CAT und Rotorsteuerung gemeinsam
- bei Az/El-Rotoren ändert **Rotor drehen** nur den Azimut und behält die zuletzt gelesene Elevation bei

### Security

- QRZ- und FLRig-XML-Antworten werden größenbegrenzt gelesen und vor dem Parsen gegen problematische DTD-/Entity-Deklarationen geprüft
- URL-Zugriffe sind auf HTTP(S) beschränkt; HTTPS-Downgrades per Redirect werden blockiert und sensible Header bei Cross-Origin-Redirects entfernt
- das Öffnen des lokalen Logordners verwendet keine Shell-Interpolation mehr
- `rotctld` wird ausschließlich an `127.0.0.1` gebunden

### Safety

- Callbook-Lookup und Peilungsberechnung bewegen den Rotor niemals automatisch; eine Bewegung beginnt nur nach einem ausdrücklichen Klick
- Profilwechsel, Hamlib-Wechsel und Programmende stoppen die von der App gestartete Rotorsteuerung kontrolliert

## [0.19.3] - 2026-09-06

### Added

- bidirektionaler dateibasierter **WSJT-X-Sync** zwischen `wsjtx_log.adi` und dem lokalen Offline Logger; der Offline Logger bleibt dabei der zentrale Merge-Hub zwischen WSJT-X und Wavelog
- eigener Einstellungs-Tab **WSJT-X Sync** mit Profil-/Rig-Auswahl, manuellem Pfad und getrennten Optionen für Start-, Beenden- und manuellen Abgleich
- sichere WSJT-X-Dateisicherung vor Änderungen, Dublettenerkennung mit Zeit-/Band-/Mode-Toleranzen sowie Schutz vor dem Import eindeutig profilfremder `STATION_CALLSIGN`-Datensätze
- Architektur- und Regressionstests für Feature-Trennung, WSJT-X-Synchronisierung und append-only QSO-Speicherung

### Changed

- `app.py` in klar getrennte `feature_*.py`-Module, `dialogs.py`, `app_common.py` und `ui_theme.py` aufgeteilt; neue Features deklarieren ihre Abhängigkeiten explizit
- Logbuch, Fast Log/DXpedition und Statistiken verwenden gemeinsame QSO-Caches und Hintergrundarbeit, damit Seitenwechsel den Tk-Hauptthread nicht mehr durch vollständige ADIF-/SQLite-Auswertungen blockieren
- normale neue QSOs werden in bestehende kanonische ADI-Dateien append-only geschrieben statt die komplette Datei bei jedem Speichern neu aufzubauen
- Windows-Bootstrap nimmt `feature_*.py` automatisch auf und leitet sein versionsabhängiges Runtime-Verzeichnis dynamisch aus `appVersion` ab
- Windows-Buildprüfung an den dynamisch erzeugten Runtime-Pfad angepasst

### Safety

- ein `.append-journal` schützt den schnellen ADI-Append vor partiellen Schreibvorgängen; beim nächsten Scan wird ein abgebrochener Append kontrolliert abgeschlossen oder bei widersprüchlichem Zustand sichtbar abgebrochen
- Editieren, Löschen, ADIF-Import und Migration bleiben bewusst beim vollständigen, verifizierten Rewrite
- der WSJT-X-Sync führt keine automatischen Löschungen durch; fehlende QSOs werden nur auf der jeweils anderen Seite ergänzt

## [0.19.2] - 2026-09-05

- automatischen Windows-Updater repariert: Update-Übergabe erfolgt erst nach dem Ende der Desktop-App über den Go-Launcher
- exakt die ursprünglich gestartete EXE wird unabhängig von Dateiname und Speicherort ersetzt und neu gestartet
- PowerShell-Helper auf Windows PowerShell 5.1 kompatible Pfad- und Prozessoperationen umgestellt
- zusätzliche SHA-256-Prüfung beim Staging und nach dem Austausch sowie Rollback bei Fehlern
- Update-Ablauf wird ausführlich unter `%LOCALAPPDATA%\AFU-Tools\WavelogOfflineLogger\updates\update.log` protokolliert
- Hinweis ergänzt, dass der Sprung von v0.19.1 auf v0.19.2 wegen des defekten v0.19.1-Updaters einmalig manuell erfolgen kann

## [0.19.1] - 2026-09-05

- Dark-Mode-Kontraste für Eingaben, Comboboxen samt Auswahlliste, Tabellen, Register, Listen und deaktivierte Bedienelemente vereinheitlicht
- der TUNE-Knopf kann die gespeicherte CAT-Verbindung bei Bedarf selbst starten
- FTX-1 verwendet über Hamlibs Raw-Command-Brücke `AC003`, da das aktuelle Beta-Backend den allgemeinen `vfo_op TUNE` noch fälschlich auf `AC002` abbildet
- manuell auslösbarer Hamlib-Updater im CAT Setup für Windows mit offizieller GitHub-Quelle, SHA-256-Prüfung und Funktionstest vor der Aktivierung
- die zuvor verwendete Hamlib-Version wird gesichert und kann im CAT Setup wiederhergestellt werden; Linux und macOS bleiben an die geprüften App-Pakete gekoppelt

## [0.19.0] - 2026-09-04

### Added

- FLRig kann im CAT Setup mit einer frei editierbaren `IP/Hostname:Port`-Adresse genutzt werden
- optionale FLRig-Suche auf dem eigenen Rechner und in begrenzten privaten IPv4-Netzen mit eindeutiger XML-RPC-Erkennung
- ClubLog-Status in der vorhandenen QSL-Anzeige des Logbuchs und der Statistik

### Changed

- Confirmation-Abfragen verwenden den finalen Wavelog-3.2.0-Vertrag und sind auf die erlaubten Station Locations begrenzt
- Wavelog-API-Fehler enthalten in der sichtbaren Ursache zusätzlich Fehlercode und strukturierte Details
- deutsche und englische CAT-, Sync- und Fehlerhilfe dokumentieren FLRig und ClubLog

### Migration

- vorhandene `qsl_meta`-Tabellen werden automatisch und verlustfrei um die Spalte `clublog` erweitert

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
