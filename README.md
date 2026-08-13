# DA6IT.de Wavelog Offline Logger

Offlinefähiger Desktop-Logger für Funkamateure. QSOs werden zuerst lokal gespeichert und erst auf Wunsch mit Wavelog synchronisiert.

**Download:** [Aktuelle Version für Windows und macOS](https://github.com/DA6IT/Wavelog-Offline-Logger/releases/latest)

## Funktionen

- Normales QSO-Logging vollständig ohne Internet
- **Fast Log / DXpedition:** Rufzeichen eingeben, Enter drücken, nächstes QSO
- Tägliche ADI-Dateien als primäres lokales Logbuch
- Mehrere getrennte Stations- und Operatorprofile
- Bidirektionaler Abgleich mit Wavelog API v2
- Sichtbare Konflikte statt stiller Überschreibungen
- Offline-Länder-, DXCC-, Zonen- und Kontinenterkennung
- POTA-, SOTA-, WWFF- und Contest-Felder
- CAT-Steuerung über das mitgelieferte Hamlib
- Telnet-DX-Cluster mit Filtern, CAT-Abstimmung und Spotversand
- WSJT-X- und ADIF-Empfang über einen frei wählbaren UDP-Port
- QRZ-, LoTW-, eQSL- und DCL-Status sowie lokale Statistiken
- Automatischer Hinweis auf neue Releases, ohne Fehlermeldung bei fehlendem Internet

## Windows installieren

1. Im [GitHub-Release](https://github.com/DA6IT/Wavelog-Offline-Logger/releases) die Datei `DA6IT.de-Wavelog-Offline-Logger-v<VERSION>-windows-x64.exe` herunterladen.
2. Optional die Prüfsumme aus `SHA256SUMS.txt` vergleichen.
3. EXE starten.

Beim ersten Start richtet der Bootstrapper eine private Python-3.12.10-Laufzeit ein. Dafür wird einmalig Internet benötigt; Python muss nicht systemweit installiert sein. Download und Prüfsumme werden vor der Einrichtung geprüft.

Hamlib ist vollständig im Windows-Build enthalten. Für CAT wird nur der passende Windows-Treiber des Funkgeräts benötigt.

Anwendungsdaten liegen unter:

```text
%LOCALAPPDATA%\AFU-Tools\WavelogOfflineLogger\
```

## macOS installieren

GitHub erzeugt getrennte Pakete für Apple Silicon (`macos-arm64`) und Intel-Macs (`macos-x64`). Das passende ZIP herunterladen, entpacken und `DA6IT.de Wavelog Offline Logger.app` nach **Programme** verschieben. Python und Hamlib sind im App-Bundle enthalten.

Die kostenlose macOS-Fassung ist derzeit nur technisch ad-hoc signiert und nicht von Apple notarisiert. Beim ersten Start deshalb im Finder mit Rechtsklick **Öffnen** wählen und die Rückfrage bestätigen. Es werden keine Systemeinstellungen oder Sicherheitsmechanismen automatisch verändert.

Die Anwendungsdaten liegen kompatibel zu bestehenden Installationen unter:

```text
~/Library/Application Support/AFU-Tools/WavelogOfflineLogger/
```

Offizielle Releases werden für **Windows x64**, **macOS Apple Silicon** und **macOS Intel** gebaut.

## Schnelleinstieg

1. Logger-Profil anlegen oder bearbeiten.
2. Stationsrufzeichen, Operator und lokalen ADI-Ordner festlegen.
3. Optional Wavelog-URL, API-v2-Token und Stationsprofil eintragen.
4. QSO lokal speichern.
5. Erst bei vorhandener Verbindung **Synchronisieren** auswählen.

Der Logger ersetzt Wavelog nicht. Er ergänzt Wavelog für portable Einsätze, Pileups, Fielddays und andere Situationen ohne zuverlässiges Internet.

## Fast Log / DXpedition

Band, Mode, Frequenz, Rapporte und Leistung werden einmal festgelegt. Danach genügt für jedes QSO:

```text
Rufzeichen + Enter
```

Datum und UTC-Zeit werden automatisch gesetzt. Jedes QSO landet sofort als `LOCAL ONLY` in der lokalen ADI-Datei. Wavelog wird erst beim manuellen Sync angesprochen. Das letzte noch nicht synchronisierte Fast-Log-QSO kann kontrolliert zurückgenommen werden.

## CAT mit Hamlib

Unter **CAT Setup** stehen mehr als 300 Hamlib-Funkgerätemodelle zur Verfügung. Frequenz, Band und Mode können automatisch in normales Logging, Fast Log und Contest-Logging übernommen werden.

CAT startet nach jedem Programmstart bewusst ausgeschaltet. **CAT stoppen** und das Beenden des Loggers beenden auch den von der Anwendung gestarteten `rigctld`-Prozess.

## DX Cluster

Für den Empfang ist standardmäßig `dxcluster.afu-tools.de:7300` eingetragen. Spots erscheinen live und können nach Band, Mode, Zeitraum und Spotter-Region gefiltert sowie über jede Tabellenspalte sortiert werden.

- Doppelklick stimmt bei aktivem CAT den TRX auf Frequenz und erkannten Mode ab.
- **QSO übernehmen** füllt anschließend das normale QSO-Formular.
- Neue Spots werden kurz hellblau markiert.
- Bereits gearbeitete Rufzeichen und Länder werden nur für dasselbe **Band und denselben Mode** grün markiert.
- Fehlende Modes werden aus Kommentar, typischen FT8-Frequenzen und eindeutigen Bereichen des IARU-Region-1-Bandplans abgeleitet; mehrdeutige Bereiche verwenden weiterhin LSB oder USB.

Zum eigenen Spotten dient getrennt die DXSpider-Verbindung `dxcluster.afu-tools.de:7301`. Beide Server und Ports sind profilbezogen änderbar; das Login-Rufzeichen kommt automatisch aus dem aktiven Stationsprofil. Ein Spot wird nur nach ausdrücklicher Bestätigung gesendet.

Empfang und Versand von DX-Spots benötigen Internet. Alle lokalen Logfunktionen bleiben offline nutzbar.

## WSJT-X und ADIF über UDP

Unter **UDP Logging** kann ein freier Port gewählt werden. Unterstützt werden:

- native geloggte QSOs von WSJT-X
- vollständige ADIF-Datensätze mit `<EOR>` anderer Programme
- Duplikatschutz bei mehrfach übertragenen QSOs

Der Empfänger startet bewusst manuell. Eingehende QSOs werden lokal gespeichert und später über den normalen Wavelog-Sync abgeglichen.

## Daten und Sync-Sicherheit

- ADI bleibt das primäre lokale QSO-Logbuch.
- SQLite speichert nur Einstellungen, Zuordnungen und Sync-Metadaten.
- Gleichzeitige lokale und entfernte Änderungen erzeugen einen sichtbaren Konflikt.
- Ein außerhalb der App fehlendes lokales QSO wird nicht ungefragt aus Wavelog gelöscht.
- Profil-Löschung wirkt ausschließlich lokal und löscht keine Wavelog-Daten.
- Es erfolgen keine heimlichen Online-Callbook-Abfragen.

Regelmäßige Sicherungen der ADI-Ordner und des Anwendungsordners werden empfohlen.

## Dokumentation

- [Benutzerhandbuch](docs/USER_GUIDE.md)
- [Fehlerhilfe](docs/TROUBLESHOOTING.md)
- [Architektur](docs/ARCHITECTURE.md)
- [Mitwirken](CONTRIBUTING.md)
- [Sicherheit](SECURITY.md)

## Aus dem Quellcode starten

Benötigt wird Python 3.12 mit Tk-Unterstützung; externe Python-Pakete sind nicht erforderlich.

```powershell
python app.py
python selftest.py
```

Der reproduzierbare Windows-Build verwendet zusätzlich Go 1.23.2:

```powershell
.\scripts\package-release.ps1
```

Die macOS-App wird auf einem echten Mac beziehungsweise durch die beiden GitHub-macOS-Runner gebaut:

```bash
./scripts/build-macos.sh dist
```

## Lizenz

Dieses Projekt steht unter der [MIT-Lizenz](LICENSE). Es ist ein unabhängiges Community-Projekt und kein Bestandteil des Wavelog-Projekts.
