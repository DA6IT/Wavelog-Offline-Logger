# DA6IT.de Wavelog Offline Logger

Offlinefähiger Desktop-Logger für Funkamateure mit sicherer Synchronisation zu Wavelog.

> Aktuelle Vorabversion: **v0.13.0-rc1**. Sie ergänzt die praktisch getestete CAT-Steuerung um UDP-Logging für WSJT-X und andere Programme sowie einen integrierten Telnet-DX-Cluster.

## Zweck

Der Logger ermöglicht das Erfassen und Bearbeiten von QSOs ohne dauerhafte Internetverbindung. Sobald Wavelog erreichbar ist, können lokale und entfernte Änderungen abgeglichen werden.

Das Programm ersetzt Wavelog nicht. Wavelog bleibt das zentrale Online-Logbuch; lokal sind die ADI-Dateien das primäre Logbuchformat. SQLite enthält ausschließlich Einstellungen, Zuordnungen sowie Sync- und Cache-Metadaten.

## Funktionen

- Offline-QSO-Erfassung in täglichen ADI-Dateien
- Mehrere vollständig getrennte Logger-Profile
- Wavelog API v2 für Upload, Download und bidirektionalen Abgleich
- Sichtbare Konflikte statt stiller Überschreibungen
- Offline-DXCC- und Ländererkennung über `cty.dat`
- POTA-, SOTA- und WWFF-Felder
- Contest-Presets, Seriennummern und Operatorwechsel
- Profilbezogenes CAT Setup mit gebündeltem Hamlib 4.7.2 und mehr als 300 unterstützten Funkgerätemodellen
- Automatische Übernahme von Frequenz, Band und Mode in normales und Contest-Logging
- Profilbezogener Telnet-DX-Cluster mit Spot-Filtern, QSO-Übernahme, optionaler CAT-Abstimmung und bewusst bestätigtem Spotversand
- Profilbezogener UDP-Empfänger für native WSJT-X-QSOs und ADIF-Broadcasts anderer Logprogramme
- QRZ-, LoTW-, eQSL- und DCL-Status im Logbuch
- Statistiken und Operatorauswertung
- Schutz des Wavelog-Tokens über Windows DPAPI
- Unaufdringlicher Hinweis beim Programmstart, wenn ein neueres GitHub-Release verfügbar ist

## Sicherheitsmodell für Logdaten

Der Sync arbeitet bewusst konservativ:

- Ein außerhalb der Anwendung aus einer ADI-Datei verschwundenes QSO wird nicht automatisch in Wavelog gelöscht. Wenn es dort noch existiert, wird es lokal wiederhergestellt.
- Nur eine ausdrücklich in der Anwendung ausgelöste QSO-Löschung erzeugt eine Remote-Löschanforderung.
- Wurden lokale und entfernte Daten gleichzeitig verändert, entsteht ein sichtbarer Konflikt.
- Das Löschen eines Logger-Profils wirkt ausschließlich lokal und löscht niemals Wavelog-QSOs oder Wavelog-Stationsprofile.

Trotzdem sollten Logordner und Anwendungsdaten regelmäßig gesichert werden.

## Windows installieren

1. Im GitHub-Release die Datei `DA6IT.de-Wavelog-Offline-Logger-v<VERSION>-windows-x64.exe` herunterladen.
2. Optional die SHA-256-Prüfsumme mit der beigefügten `SHA256SUMS.txt` vergleichen.
3. Die EXE starten.

Beim ersten Start lädt der Bootstrapper den von der Python Software Foundation signierten Python-3.12.10-Installer über HTTPS. Vor der unbeaufsichtigten Einrichtung einer privaten Laufzeit wird dessen SHA-256-Prüfsumme geprüft. Eine systemweite Python-Installation ist nicht erforderlich.

Hamlib ist im Windows-Build bereits enthalten. Für CAT muss deshalb keine zusätzliche CAT- oder Hamlib-Software installiert werden; benötigt wird lediglich die passende Windows-Treiberunterstützung für die Schnittstelle des Funkgeräts.

Anwendungsdaten liegen standardmäßig unter:

```text
%LOCALAPPDATA%\AFU-Tools\WavelogOfflineLogger\
```

Release Candidates verwenden einen eigenen versionsabhängigen Programmordner und überschreiben keinen stabilen Programmstand.

## Plattformstatus

- **Windows x64:** automatisierter Build und Release-Paket vorhanden
- **macOS:** im aktuellen Repository noch kein vollständig reproduzierbarer Buildquelltext enthalten
- **Linux:** derzeit kein offizielles Release-Artefakt; ein Start aus dem Python-Quellcode kann je nach Tk-Installation möglich sein

## Erste Schritte

1. Ein Logger-Profil anlegen oder das Standardprofil bearbeiten.
2. Wavelog-URL und API-v2-Token eintragen.
3. Verbindung testen und ein Wavelog-Stationsprofil auswählen.
4. Stationsrufzeichen, Operator und optional Locator/QTH ergänzen.
5. Optional unter **CAT Setup** Funkgerät, COM-Port und serielle Parameter wählen, Einstellungen speichern und CAT starten.
6. Optional unter **DX Cluster** den vorbelegten Telnet-Server oder einen eigenen Server konfigurieren und manuell verbinden.
7. Optional unter **UDP Logging** eine freie Portnummer wählen und den Empfänger starten.
8. Ein QSO erfassen und speichern.
9. Bei vorhandener Internetverbindung die Synchronisation starten.

## CAT-Steuerung mit Hamlib

Der Windows-Build enthält Hamlib 4.7.2 und unterstützt damit mehr als 300 Funkgerätemodelle, ohne dass Hamlib oder eine zusätzliche CAT-Anwendung installiert werden muss. Benötigt wird lediglich der passende Windows-Treiber für die USB- beziehungsweise serielle Schnittstelle des Funkgeräts.

### CAT einrichten

1. **CAT Setup** öffnen.
2. Hersteller oder Modell suchen und das passende Hamlib-Funkgerät auswählen.
3. COM-Port, Baudrate, Datenbits, Stoppbits, Parität und gegebenenfalls Handshake/DTR/RTS entsprechend der Funkgerätekonfiguration einstellen.
4. **Einstellungen speichern** auswählen.
5. Optional mit **Verbindung testen** Frequenz und Mode probeweise auslesen.
6. Mit **CAT starten** die laufende Verbindung herstellen.

### Verhalten

- CAT-Einstellungen werden getrennt für jedes Logger-Profil gespeichert.
- Frequenz, Band und Mode werden fortlaufend in das normale QSO- und Contest-Logging übernommen.
- Hamlib-Modi wie `FMN` werden für das ADIF-Log korrekt als `FM` zugeordnet.
- Ein ausdrücklich gewählter Digitalmodus wie FT8 bleibt bei passenden USB-/LSB-Datenmodi erhalten.
- CAT startet nach jedem Programmstart bewusst ausgeschaltet und verbindet sich erst nach **CAT starten** mit dem Funkgerät.
- **CAT stoppen** oder das Beenden des Loggers beendet auch den von der Anwendung gestarteten `rigctld`-Prozess.

Weitere Einzelheiten stehen im Abschnitt CAT des [Benutzerhandbuchs](docs/USER_GUIDE.md#5-cat-einrichten). Die Lizenzhinweise zu den eingebetteten Hamlib-Dateien enthält [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

## DX Cluster über Telnet

Unter **DX Cluster** steht eine direkte Telnet-Anbindung zur Verfügung. Standardmäßig sind `dxcluster.afu-tools.de` und Port `7300` eingetragen; Host, Port und Login-Rufzeichen können für jedes Logger-Profil frei geändert werden.

1. Login-Rufzeichen prüfen und **Verbinden** auswählen.
2. Spots nach Band, Mode, Zeitraum und Spotter-Region filtern; voreingestellt sind die letzten 30 Minuten. Für die Region stehen Europa, Nordamerika, Südamerika, Asien/Pazifik, Afrika und Unbekannt zur Auswahl. Neu empfangene Telnet-Spots erscheinen ohne manuelles Neuladen sofort in der Liste.
3. Einen Spot doppelt anklicken, um den TRX bei laufendem CAT auf Frequenz und den erkannten Mode abzustimmen. Die Cluster-Seite bleibt dabei geöffnet.
4. **QSO übernehmen** auswählen, um Rufzeichen, Frequenz, Band und Mode in das normale QSO-Formular zu laden.

Die Übernahme speichert niemals automatisch ein QSO. Ein generisches `SSB` im Spot-Kommentar wird auf 160, 80 und 40 Metern als `LSB`, auf den übrigen Bändern als `USB` behandelt. Fehlt die Mode-Angabe vollständig, verwendet der Logger dieselbe bandabhängige SSB-Vorgabe. Eindeutige Modes wie FT8, CW oder FM haben Vorrang und bleiben erhalten.

DX-Rufzeichen, DX-Land und das Land des Spotters werden mit der lokalen `cty.dat` bestimmt. Ein Klick auf eine beliebige Tabellenüberschrift sortiert die Liste nach dieser Spalte – einschließlich DX-Land und Spotter-Land; ein zweiter Klick kehrt die Reihenfolge um. Standardmäßig steht der jüngste Spot oben. Neue Spots besitzen zwei Minuten lang einen hellblauen Zeilenhintergrund. Die grüne Worked-Markierung gilt immer nur für denselben Mode: Ein in FT8 gearbeitetes Land wird bei einem USB-Spot daher nicht grün. Wurde das Land im Spot-Mode bereits gearbeitet, erscheint nur der Ländertext grün; wurde auch das konkrete Rufzeichen in diesem Mode gearbeitet, erscheinen Rufzeichen und Land grün.

Über **DX-Spot senden** im QSO-Formular können Rufzeichen und Frequenz an den verbundenen Cluster gemeldet werden. Vor dem öffentlichen Versand werden ein optionaler Kommentar und eine ausdrückliche Bestätigung abgefragt. Es werden weder beim Start noch automatisch beim Loggen Spots gesendet.

Der DX Cluster benötigt Internet, die übrigen Offline-Funktionen jedoch nicht. Die Telnet-Verbindung startet stets manuell und wird bei Profilwechsel oder Programmende beendet.

## WSJT-X und ADIF über UDP

Unter **UDP Logging** kann das aktive Profil geloggte QSOs direkt von WSJT-X empfangen. Der Empfänger erkennt sowohl das native WSJT-X-Netzwerkprotokoll als auch vollständige ADIF-Datensätze mit `<EOR>`, die andere Programme per UDP senden.

1. Als Bind-Adresse für Programme auf demselben PC `127.0.0.1` beibehalten.
2. Einen freien UDP-Port wählen, beispielsweise `2237`, und die Einstellungen speichern.
3. In WSJT-X unter **File > Settings > Reporting** dieselbe Adresse und Portnummer als UDP Server eintragen.
4. Im Offline Logger **UDP starten** auswählen.

Ist der primäre WSJT-X-Port bereits von JTAlert, GridTracker oder einer anderen Anwendung belegt, kann der zusätzliche „logged contact ADIF broadcast“ von WSJT-X auf einen separaten freien Port zeigen, beispielsweise `2333`. Ein belegter Port wird beim Start verständlich gemeldet. Nach einer Portänderung genügt **UDP stoppen** und erneutes **UDP starten**; ein Programmneustart ist nicht nötig.

Empfangene QSOs werden direkt in der ADI-Datei des aktiven Profils gespeichert, im Logbuch als `LOCAL ONLY` angezeigt und später mit dem normalen Wavelog-Abgleich synchronisiert. Identische Mehrfachübertragungen werden nicht doppelt gespeichert. Der UDP-Empfänger bleibt nach einem Programmstart ausgeschaltet, bis er ausdrücklich gestartet wird.

## Updates

Beim Start prüft die Anwendung im Hintergrund die öffentliche Release-Liste dieses GitHub-Projekts. Gibt es eine neuere passende Version, kann deren Downloadseite direkt geöffnet werden. Ohne Internet oder bei einem nicht erreichbaren GitHub bleibt die Prüfung still und beeinträchtigt das Offline-Logging nicht. Stabile Versionen bieten keine Vorabversionen an; Release Candidates können auf neuere Release Candidates hinweisen.

Eine ausführlichere Anleitung steht im [Benutzerhandbuch](docs/USER_GUIDE.md). Häufige Start- und Sync-Probleme behandelt die [Fehlerhilfe](docs/TROUBLESHOOTING.md).

## Aus dem Quellcode starten

Voraussetzungen:

- Python 3.12 mit Tk-Unterstützung
- keine externen Python-Pakete

```powershell
python app.py
```

Die Tests laufen ohne Wavelog-Zugang:

```powershell
python selftest.py
```

## Windows-Build

Voraussetzungen:

- Python 3.12.10
- Go 1.23.2

```powershell
.\scripts\build-windows.ps1
```

Ein vollständiges lokales Release-Paket entsteht mit:

```powershell
.\scripts\package-release.ps1
```

Die Ausgabe liegt in `dist\`. Details zum Tag- und Releaseablauf enthält [RELEASING.md](docs/RELEASING.md).

Die empfohlenen GitHub-Einstellungen für Maintainer beschreibt [GITHUB_SETUP.md](docs/GITHUB_SETUP.md).

## Projektstruktur

| Pfad | Aufgabe |
| --- | --- |
| `app.py` | Tkinter-Oberfläche und Benutzerinteraktion |
| `logger_core.py` | ADI-, Profil-, Metadaten-, Sync- und Statistiklogik |
| `cat_control.py` | Hamlib-Modellliste, `rigctld`-Prozess, CAT-Abfragen und Mode-Zuordnung |
| `dx_cluster.py` | Telnet-Verbindung, DX-Spot-Parser, Login und expliziter Spotversand |
| `external_logging.py` | WSJT-X- und ADIF-Empfang über UDP |
| `update_check.py` | Fehlertolerante Prüfung auf neuere GitHub-Releases |
| `bootstrap_windows.go` | Kleiner Windows-Launcher mit eingebetteter Anwendung |
| `cty.dat` | Offline-Länder- und DXCC-Daten |
| `selftest.py` | Regressions- und Migrations-Selftests |
| `scripts/` | Reproduzierbare Build- und Paket-Skripte |
| `.github/workflows/` | Automatische Tests, Windows-Builds und Tag-Releases |
| `docs/` | Benutzer-, Architektur-, Fehler- und Release-Dokumentation |

Technische Hintergründe stehen in [ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Mitwirken und Sicherheit

Beiträge sind willkommen. Bitte zuerst [CONTRIBUTING.md](CONTRIBUTING.md) lesen. Sicherheitsprobleme bitte nicht öffentlich als normales Issue melden; der vorgesehene Meldeweg steht in [SECURITY.md](SECURITY.md).

## Lizenz

Dieses Projekt steht unter der [MIT-Lizenz](LICENSE).

## Hinweis zu Wavelog

Dieses Projekt ist ein unabhängiges Community-Projekt und nicht Bestandteil des Wavelog-Projekts. Für die Nutzung werden eine erreichbare Wavelog-Instanz und passende API-Berechtigungen benötigt.
