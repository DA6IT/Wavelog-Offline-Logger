# DA6IT.de Wavelog Offline Logger

Offlinefähiger Desktop-Logger für Funkamateure mit sicherer Synchronisation zu Wavelog.

> Aktueller Entwicklungsstand: **v0.12.0-rc2 (Release Candidate)**. Die neue CAT-Steuerung wurde mit einem Yaesu FTX-1 praktisch getestet.

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
5. Optional unter **CAT Setup** Funkgerät, COM-Port und serielle Parameter wählen, Verbindung testen und CAT aktivieren.
6. Ein QSO erfassen und speichern.
7. Bei vorhandener Internetverbindung die Synchronisation starten.

CAT-Einstellungen sind profilbezogen. Bei aktiver Verbindung aktualisiert der Logger Frequenz, Band und Mode fortlaufend. Hamlib-Modi wie `FMN` werden für das ADIF-Log korrekt als `FM` übernommen.

CAT startet nach jedem Programmstart bewusst ausgeschaltet. Einstellungen speichern, CAT starten und CAT stoppen sind getrennte Aktionen; das Funkgerät wird erst nach einem ausdrücklichen Start verbunden.

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
