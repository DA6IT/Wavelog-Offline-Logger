# Benutzerhandbuch

Dieses Handbuch beschreibt den DA6IT.de Wavelog Offline Logger ab Version 0.16.0. Die Screenshots wurden automatisch mit isolierten Demo-Daten erzeugt. Sie enthalten keine privaten ADI-Dateien, API-Tokens oder echten Zugangsdaten.

## 1. Grundprinzip

Der Logger arbeitet **Offline-first**:

1. Jedes neue QSO wird zuerst als ADI auf dem eigenen Rechner gespeichert.
2. Ohne Internet oder ohne erreichbares Wavelog bleibt es als `LOCAL ONLY` erhalten.
3. Bei erreichbarem Wavelog kann die App neue QSOs automatisch pushen.
4. Ein vollständiger bidirektionaler Sync bleibt jederzeit manuell möglich und kann zusätzlich beim Start und/oder Beenden laufen.

Damit ist das Logbuch nicht von einer dauerhaften Internetverbindung abhängig. Wavelog-Daten werden bei einer lokalen Profil-Löschung niemals automatisch gelöscht.

## 2. Installation

### Windows x64

1. Auf der [Release-Seite](https://github.com/DA6IT/Wavelog-Offline-Logger/releases) `DA6IT.de-Wavelog-Offline-Logger-v<VERSION>-windows-x64.exe` herunterladen.
2. Optional die Datei gegen `SHA256SUMS.txt` prüfen.
3. Die EXE starten.

Beim ersten Start wird einmalig eine geprüfte private Python-3.12-Laufzeit eingerichtet. Eine systemweite Python-Installation ist nicht nötig. Hamlib wird mitgeliefert; für den Funkgeräteanschluss kann der passende Hersteller- oder USB-Seriell-Treiber erforderlich sein.

Anwendungsdaten: `%LOCALAPPDATA%\AFU-Tools\WavelogOfflineLogger\`

### macOS

Das passende ZIP für Apple Silicon (`macos-arm64`) oder Intel (`macos-x64`) entpacken und die `.app` nach **Programme** verschieben. Die kostenlose App ist derzeit technisch signiert, aber nicht von Apple notarisiert. Beim ersten Start im Finder Rechtsklick auf die App und **Öffnen** wählen.

Anwendungsdaten: `~/Library/Application Support/AFU-Tools/WavelogOfflineLogger/`

### Debian und Ubuntu

```bash
sudo apt install ./DA6IT.de-Wavelog-Offline-Logger-*-linux-*.deb
```

Alternativ steht ein AppImage bereit. Dieses mit `chmod +x DATEI.AppImage` ausführbar machen und starten.

### Arch Linux

```bash
sudo pacman -U DA6IT.de-Wavelog-Offline-Logger-*.pkg.tar.zst
```

Anwendungsdaten unter Linux: `~/.local/share/AFU-Tools/WavelogOfflineLogger/`

## 3. Oberfläche und Navigation

Die linke Navigation öffnet:

- **Logbuch** – vollständiges QSO-Formular
- **Fast Log / DXpedition** – Rufzeichen und Enter für schnelle Serien
- **Contest Logging** – Seriennummern, Exchanges und Contest-Sitzung
- **Logbuch & Sync** – lokale QSOs, Sync- und QSL-Status
- **Statistiken** – lokale Auswertungen
- **DX Cluster** – Spots empfangen, filtern und übernehmen
- **CAT Setup** – Funkgerät über Hamlib verbinden
- **UDP Logging** – QSOs von WSJT-X oder anderen Programmen empfangen
- **Einstellungen** – App, Station, Online-Dienste und Speicherorte

Das DA6IT.de-Logo oben links ist anklickbar und öffnet `https://da6it.de/`. Der Status unten und links zeigt `LOCAL ONLY` oder `WAVELOG ONLINE`.

## 4. Profile und Einstellungen

Einstellungen mit Zugangsdaten, Speicherort und Stationsrufzeichen gelten pro Logger-Profil. Sprache und Theme gelten für die gesamte App.

### 4.1 Allgemein

![Allgemeine Einstellungen](screenshots/settings-general.png)

- **Sprache:** Deutsch oder Englisch
- **Theme:** Hell oder Dunkel
- Änderungen an Sprache und Theme werden nach einem Neustart vollständig aktiv.
- Der Bereich Daten & Backup weist auf die lokale Datensicherung hin; eine automatische ZIP-Wiederherstellung ist in 0.16.0 noch nicht enthalten.

![Englische Oberfläche im Dark-Theme](screenshots/qso-logging-english-dark.png)

### 4.2 Station & Wavelog

![Station und Wavelog](screenshots/settings-wavelog.png)

Linke Seite:

- Operator- und Stationsrufzeichen
- eigener Locator und QTH
- Standardleistung
- optionale eigene POTA-, SOTA- und WWFF-Referenzen

Rechte Seite:

- Wavelog-URL, zum Beispiel `https://log.example.org`
- API-v2-Token im Format `wl2_…`
- Wavelog-Stationsprofil
- automatischer Push neuer QSOs im Online-Modus
- vollständiger Sync beim App-Start
- vollständiger Sync beim Beenden

Für den Sync werden passende QSO- und Stationsrechte benötigt. Für Callbook-Abfragen über Wavelog wird zusätzlich `lookup:read` benötigt.

Die drei Sync-Optionen sind unabhängig voneinander und gelten nur für das aktive Profil.

### 4.3 Callbook & Online-Dienste

![Callbook- und Online-Einstellungen](screenshots/settings-callbook.png)

Als Rufzeichenquelle stehen zur Verfügung:

- **Wavelog:** Abfrage über die konfigurierte Wavelog-API
- **QRZ.com direkt:** eigene QRZ-XML-Zugangsdaten; je nach Konto kann ein XML-Abonnement nötig sein
- **Deaktiviert:** keine automatische Online-Abfrage

Sind beim direkten QRZ-Modus Benutzername oder Passwort leer, hat Wavelog automatisch Vorrang. Erfolgreiche Ergebnisse werden lokal zwischengespeichert. Name, Locator und QTH werden nur in leere oder zuvor automatisch ausgefüllte Felder geschrieben; eigene Eingaben werden nicht überschrieben.

Die eQSL.cc-Felder sind vorbereitet und klar als **Coming soon** markiert. Version 0.16.0 stellt noch keine eQSL-Verbindung her und führt weder Upload noch Download aus.

### 4.4 Daten & Verbindungen

![Daten und Verbindungen](screenshots/settings-data-connections.png)

- Der lokale ADI-Ordner bestimmt, wo das primäre Logbuch liegt.
- Die getrennte DXSpider-Verbindung wird nur zum **eigenen Spotversand** verwendet.
- Standard: `dxcluster.afu-tools.de`, Port `7301`.
- Das Login-Rufzeichen wird automatisch aus dem aktiven Stationsprofil übernommen.

## 5. Normales QSO loggen

![Vollständiges QSO-Formular](screenshots/qso-logging.png)

Pflicht für ein übliches QSO sind mindestens Rufzeichen, Band und Mode. Datum und Zeit laufen standardmäßig live in UTC, können aber auf lokale Zeit oder manuelle Eingabe umgestellt werden.

Typischer Ablauf:

1. Rufzeichen eingeben.
2. Frequenz, Band und Mode prüfen; bei aktivem CAT werden diese Werte übernommen.
3. Rapporte, Leistung und optionale Aktivierungsreferenzen ergänzen.
4. **QSO speichern** oder **Speichern + Neu** wählen.

Rechts erscheinen, soweit verfügbar:

- Stationsfoto
- Name, QTH und Land
- Locator sowie CQ-/ITU-Zonen
- Offline-DXCC-Daten aus `CTY.DAT`

Kein Foto oder keine Internetverbindung vergrößert die Seitenleiste nicht. Der Logger bleibt vollständig benutzbar. **DX-Spot senden** verwendet die getrennte Spotter-Verbindung. **TUNE (ATU)** ist nur bei aktiver CAT-Verbindung verfügbar.

## 6. Fast Log / DXpedition

![Fast Log](screenshots/fast-log.png)

Fast Log ist für Pileups und Expeditionen gedacht:

1. Band, Mode, Frequenz, Rapporte und Leistung einmal festlegen.
2. Rufzeichen eingeben.
3. Enter drücken.
4. Das Feld ist sofort für das nächste Rufzeichen bereit.

Datum und UTC-Zeit werden automatisch gesetzt. Angezeigt werden Sitzungsanzahl, QSO-Rate, letzter Eintrag und die jüngsten QSOs. Die Dupe-Prüfung vergleicht Rufzeichen, Band und Mode. Das letzte ausschließlich lokale QSO der Sitzung kann kontrolliert zurückgenommen werden.

Auch im Online-Modus wird jedes Fast-Log-QSO zuerst lokal gespeichert. Nur der neue Datensatz wird danach automatisch zu Wavelog gepusht.

## 7. Contest Logging

![Contest Logging](screenshots/contest-logging.png)

Ein Contest-Preset enthält unter anderem:

- Name und ADIF Contest-ID
- Start-Seriennummer
- gesendeten Text-Exchange
- Standardfrequenz und Standard-RST

Nach dem Start einer Sitzung werden Seriennummern und Exchanges in die entsprechenden ADIF-Felder geschrieben. QSOs bleiben Teil des normalen lokalen ADI-Logbuchs und werden über denselben Wavelog-Sync verarbeitet.

## 8. Logbuch und Synchronisierung

![Logbuch und Sync](screenshots/logbook-sync.png)

Die Tabelle zeigt lokale QSOs und deren Zustand:

- `LOCAL ONLY` – nur lokal vorhanden
- `WAVELOG ✓` – erfolgreich verknüpft
- `GEÄNDERT` – lokal nach dem letzten Sync geändert
- `KONFLIKT` – lokal und in Wavelog unterschiedlich geändert
- `SYNC-FEHLER` – Übertragung nicht eindeutig erfolgreich

Ein QSO kann lokal bearbeitet oder gelöscht werden. Bei einem Konflikt entscheidet der Benutzer ausdrücklich zwischen lokaler und Wavelog-Version. Ein außerhalb der App fehlendes lokales ADI-QSO ist kein automatischer Auftrag, es aus Wavelog zu löschen.

Die Spalten QRZ, LoTW, eQSL und DCL zeigen den von Wavelog gelieferten Bestätigungsstatus, sofern die API ihn bereitstellt.

### 8.1 Online-Modus

Die App prüft regelmäßig die konfigurierte Wavelog-API:

- erreichbar: `WAVELOG ONLINE`
- nicht erreichbar oder nicht konfiguriert: `LOCAL ONLY`

Bei aktivierter Option werden im laufenden Betrieb ausschließlich neue, noch nie verknüpfte `LOCAL ONLY`-QSOs gepusht. Ein fehlgeschlagener oder mehrdeutiger Upload wird nicht blind wiederholt. Änderungen, Downloads, Löschungen und Konflikte sind Aufgabe des vollständigen Syncs.

### 8.2 Vollständiger Sync beim Start oder Beenden

![Laufender automatischer Sync](screenshots/sync-progress-running.png)

Während eines automatischen Voll-Syncs sperrt ein Statusfenster die Bedienung. Beim Beenden werden CAT, DX-Cluster und UDP zuerst gestoppt, damit kein weiteres externes QSO eingeht.

![Abgeschlossener automatischer Sync](screenshots/sync-progress-complete.png)

Nach Abschluss zeigt das Fenster die Zusammenfassung. Erst **OK** gibt die App frei beziehungsweise beendet sie. Scheitert der Sync, bleiben die lokalen ADI-Daten erhalten und die Fehlermeldung wird im Fenster angezeigt.

## 9. Statistiken

![Lokale Statistiken](screenshots/statistics.png)

Statistiken werden ausschließlich aus dem lokalen Logbuch berechnet. Filterbar sind Zeitraum und Operator. Angezeigt werden unter anderem QSO-Anzahl, DXCC-Entities, Bänder, Modes, Länder, häufige Rufzeichen sowie Sync- und QSL-Status.

## 10. CAT und Hamlib

![CAT Setup](screenshots/cat-setup.png)

1. Funkgerätemodell auswählen.
2. Serielle Schnittstelle beziehungsweise Netzwerkziel und Baudrate eintragen.
3. Einstellungen speichern.
4. **CAT starten** oder zuerst **Verbindung testen**.

CAT startet nach jedem App-Start bewusst ausgeschaltet. Der Logger übernimmt Frequenz und Mode in normales Logging, Fast Log und Contest Logging. Ein Doppelklick auf einen DX-Spot stimmt den TRX ebenfalls ab.

Beim Stoppen von CAT, Profilwechsel und Programmende wird der von der App gestartete `rigctld`-Prozess beendet.

### TUNE / ATU

Der TUNE-Knopf im QSO-Fenster sendet nach einer Sicherheitsabfrage den Hamlib-Tunerbefehl. Während der Vorgang läuft, ist der Knopf rot und deaktiviert; danach wird er wieder neutral. Die App schaltet PTT nicht selbst ein. Ob und wie der Befehl arbeitet, hängt von Funkgerät, Firmware und Hamlib-Unterstützung ab.

## 11. DX Cluster

![DX Cluster](screenshots/dx-cluster.png)

Der Empfangsserver ist standardmäßig `dxcluster.afu-tools.de:7300`. Die Verbindung wird nach jedem App-Start manuell hergestellt und benötigt Internet.

Funktionen:

- Live-Spots ohne manuelles Neuladen
- Zeitraum standardmäßig 30 Minuten
- Filter nach Band, Mode und Spotter-Region
- Sortierung über jede Tabellenüberschrift
- Offline-Ländererkennung für DX und Spotter
- hellblaue Markierung neuer Spots
- grüne Schrift für bereits gearbeitetes Rufzeichen oder Land

Worked-Markierungen vergleichen immer **Band und Mode**. Ein 20-m-FT8-QSO markiert daher keinen 20-m-USB-Spot und kein QSO auf 15 m.

Fehlt der Mode, wertet die App Kommentar, typische FT8-Frequenzen und eindeutige IARU-Region-1-Bandplanbereiche aus. Mehrdeutiges SSB wird bandabhängig als LSB oder USB behandelt.

- **Doppelklick:** TRX auf Frequenz und Mode abstimmen; kein Seitenwechsel
- **QSO übernehmen:** ausgewählten Spot in das QSO-Formular übertragen
- **DX-Spot senden:** aktuellen QSO-Kandidaten über die getrennte DXSpider-Verbindung melden

## 12. UDP Logging / WSJT-X

![UDP Logging](screenshots/udp-logging.png)

Unterstützt werden:

- das native WSJT-X-Protokoll für geloggte Kontakte
- vollständige ADIF-Datensätze mit `<EOR>` per UDP
- Duplikatschutz bei mehrfach gesendeten identischen QSOs

Empfohlene lokale Bind-Adresse ist `127.0.0.1`. Der Port ist frei wählbar und muss im sendenden Programm identisch sein. Ist der primäre WSJT-X-Port bereits belegt, kann der sekundäre „logged contact ADIF broadcast“ auf einen anderen freien Port zeigen.

**UDP Logging beim App-Start automatisch starten** ist profilbezogen. Eingehende QSOs werden sofort lokal gespeichert und erscheinen als `LOCAL ONLY`; der normale Online-Modus beziehungsweise Sync übernimmt die spätere Übertragung.

## 13. Lokale Daten sichern und wiederherstellen

Version 0.16.0 enthält noch keinen automatischen ZIP-Backup-/Restore-Knopf. Für eine vollständige manuelle Sicherung die App beenden und den gesamten Anwendungsordner kopieren. Damit werden Profile, Einstellungen, Sync-Metadaten, Callbook-Cache und standardmäßig auch die verwalteten ADI-Ordner erfasst.

Wurde für ein Profil ein ADI-Ordner außerhalb des Anwendungsordners gewählt, muss dieser zusätzlich gesichert werden.

Zur Wiederherstellung:

1. App vollständig beenden.
2. Den vorhandenen Anwendungsordner vorsichtshalber umbenennen.
3. Die Sicherung an den ursprünglichen Pfad kopieren.
4. App starten und Profile sowie ADI-Pfade kontrollieren.

Eine einzelne ADI-Datei darf bei geschlossener App ersetzt oder aus einer Sicherung zurückkopiert werden. Niemals nur die SQLite-Datei als QSO-Sicherung behandeln – ADI ist das primäre Logbuch.

## 14. Updates

Beim Start prüft die App im Hintergrund, ob ein neueres GitHub-Release vorhanden ist. Ohne Internet erscheint keine Fehlermeldung. Ein Update wird nicht automatisch installiert; der Benutzer entscheidet selbst über Download und Start der neuen Version.

## 15. Datenschutz und Netzwerkzugriffe

Offline verfügbar sind QSO-Erfassung, ADI-Speicherung, Profile, Statistiken, CTY.DAT-Ländererkennung und die lokale Logbuchansicht.

Netzwerk benötigen nur ausdrücklich konfigurierte oder gestartete Funktionen:

- Wavelog-Erreichbarkeitsprüfung und Sync
- Wavelog- oder QRZ-Callbook
- DX-Cluster-Empfang und Spotversand
- Release-Prüfung
- einmalige Windows-Runtime-Einrichtung

Zugangsdaten und Benutzerdaten gehören nicht in Git, Screenshots oder Fehlermeldungen. Das Dokumentations-Screenshot-Skript verwendet deshalb immer ein temporäres Demo-Profil.

## 16. Fehlerhilfe

Typische Ursachen und Diagnosepfade stehen in [TROUBLESHOOTING.md](TROUBLESHOOTING.md). Hilfreich sind Betriebssystem, App-Version, Funkgerät, Verbindungsart und der genaue Meldungstext. API-Tokens und Passwörter vor dem Teilen immer entfernen.

Die vollständige Bildübersicht steht in der [Screenshot-Galerie](SCREENSHOTS.md).
