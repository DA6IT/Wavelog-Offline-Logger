# Benutzerhandbuch

Dieses Handbuch beschreibt den DA6IT.de Wavelog Offline Logger ab Version 0.18.1. Die Screenshots wurden automatisch mit isolierten Demo-Daten erzeugt. Sie enthalten keine privaten ADI-Dateien, API-Tokens oder echten Zugangsdaten.

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

### Deinstallation

Vor der Deinstallation die App schließen. Ein ZIP-Backup unter **Einstellungen → Daten & Verbindungen** bewahrt Profile, Einstellungen, Metadaten und ADI-Logbücher gemeinsam auf.

- **Windows:** Die heruntergeladene EXE beziehungsweise den entpackten Programmordner und eigene Verknüpfungen löschen. `%LOCALAPPDATA%\AFU-Tools\WavelogOfflineLogger\` bleibt zunächst erhalten, damit Profile und Einstellungen nicht versehentlich verloren gehen. Wer wirklich alle App-Daten entfernen möchte, kann diesen Ordner anschließend bewusst löschen.
- **macOS:** Die `.app` aus **Programme** löschen. Die optional zu entfernenden App-Daten liegen unter `~/Library/Application Support/AFU-Tools/WavelogOfflineLogger/`.
- **Debian/Ubuntu:** `sudo apt remove wavelog-offline-logger` ausführen.
- **Arch Linux:** `sudo pacman -R wavelog-offline-logger` ausführen.
- **AppImage:** Die AppImage-Datei löschen.
- **Linux-Benutzerdaten:** Bei vollständiger Entfernung zusätzlich `~/.local/share/AFU-Tools/WavelogOfflineLogger/` löschen.

Die eigentlichen ADI-Dateien liegen standardmäßig unter `~/Documents/DA6IT.de Wavelog Logger/Profiles/<Profil-ID>/Logs/` beziehungsweise unter Windows im entsprechenden Dokumente-Ordner. Falls kein Dokumente-Ordner vorhanden war oder ein eigener Speicherort gewählt wurde, kann der Pfad abweichen. Paket-Deinstallation und Löschen des App-Datenordners entfernen diese Logbücher nicht automatisch; sie dürfen nur nach eigener Prüfung bewusst gelöscht werden.

## 3. Oberfläche und Navigation

Die linke Navigation öffnet:

- **Logbuch** – vollständiges QSO-Formular
- **Fast Log / DXpedition** – Rufzeichen und Enter für schnelle Serien
- **Contest Logging** – Seriennummern, Exchanges und Contest-Sitzung
- **xOTA** – portable POTA-, SOTA-, WWFF-, IOTA-, COTA- und WCA-Aktivierungen vorbereiten
- **Logbuch & Sync** – lokale QSOs, Sync- und QSL-Status
- **Statistiken** – lokale Auswertungen
- **DX Cluster** – Spots empfangen, filtern und übernehmen
- **CAT Setup** – Funkgerät über Hamlib verbinden
- **UDP Logging** – QSOs von WSJT-X oder anderen Programmen empfangen
- **Einstellungen** – App, Station, Online-Dienste und Speicherorte

Das DA6IT.de-Logo oben links ist anklickbar und öffnet `https://da6it.de/`. Der Status unten und links zeigt `LOCAL ONLY` oder `WAVELOG ONLINE`.

Die Oberfläche passt Schrift, Karten, Tabellenzeilen, Abstände und Aktionsleisten gemeinsam an die Fenstergröße an. Bei geringer Höhe werden in den Einstellungen ausschließlich zusätzliche Erklärungstexte ausgeblendet; Eingabefelder und Schaltflächen bleiben erreichbar. Unterstützt werden Fenster ab 900 × 580 Pixel. Der Release-Prozess kontrolliert alle Hauptseiten und Einstellungs-Tabs automatisch in mehreren Größen.

## 4. Profile und Einstellungen

Einstellungen mit Zugangsdaten, Speicherort und Stationsrufzeichen gelten pro Logger-Profil. Sprache und Theme gelten für die gesamte App.

### 4.1 Allgemein

![Allgemeine Einstellungen](screenshots/settings-general.png)

- **Sprache:** Deutsch oder Englisch
- **Theme:** Hell oder Dunkel
- Änderungen an Sprache und Theme werden nach einem Neustart vollständig aktiv.
- **Was ist neu?** öffnet die Versionshinweise erneut. Nach dem ersten Start einer neuen Version erscheinen sie einmal automatisch.
- Unter **Daten & Backup** lassen sich alle Profile, Einstellungen, Sync-Metadaten und ADI-Logbücher in einem ZIP sichern und wiederherstellen.

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

Die drei Sync-Optionen sind unabhängig voneinander und gelten nur für das aktive Profil. Jedes lokale Logger-Profil ist fest mit dem dort ausgewählten Wavelog-Stationsprofil verknüpft. Beim Download werden nur dessen QSOs übernommen; das aktive Logbuch muss dazu in der Wavelog-Weboberfläche nicht umgestellt werden.

### 4.3 Callbook & Online-Dienste

![Callbook- und Online-Einstellungen](screenshots/settings-callbook.png)

Als Rufzeichenquelle stehen zur Verfügung:

- **Wavelog:** Abfrage über die konfigurierte Wavelog-API
- **QRZ.com direkt:** eigene QRZ-XML-Zugangsdaten; je nach Konto kann ein XML-Abonnement nötig sein
- **Deaktiviert:** keine automatische Online-Abfrage

Der direkte QRZ-Modus arbeitet unabhängig von einer Wavelog-Konfiguration. Fehlen QRZ-Benutzername oder Passwort, zeigt der Verbindungstest dies als QRZ-Fehler an; es wird nicht unbemerkt auf Wavelog umgeschaltet. Erfolgreiche Ergebnisse werden lokal zwischengespeichert. Name, Locator und QTH werden nur in leere oder zuvor automatisch ausgefüllte Felder geschrieben; eigene Eingaben werden nicht überschrieben.

Die eQSL.cc-Felder sind vorbereitet und klar als **Coming soon** markiert. Version 0.16.0 stellt noch keine eQSL-Verbindung her und führt weder Upload noch Download aus.

### 4.4 Daten & Verbindungen

![Daten und Verbindungen](screenshots/settings-data-connections.png)

- Der lokale ADI-Ordner bestimmt, wo das primäre Logbuch liegt.
- Die getrennte DXSpider-Verbindung wird nur zum **eigenen Spotversand** verwendet.
- Standard: `dxcluster.afu-tools.de`, Port `7301`.
- Das Login-Rufzeichen wird automatisch aus dem aktiven Stationsprofil übernommen.

## 5. Normales QSO loggen

Beim Eingeben eines Rufzeichens prüft der Logger ausschließlich das lokale Logbuch des aktiven Profils. Wurde das Rufzeichen bereits auf demselben Band und im selben Mode gearbeitet, wird das Rufzeichenfeld grün und zeigt Anzahl, Band und Mode an. Existieren nur QSOs auf einem anderen Band oder in einem anderen Mode, erscheint stattdessen ein gelber Hinweis. Unterhalb des Formulars erscheinen zusätzlich die fünf neuesten QSOs mit diesem Rufzeichen einschließlich Datum, UTC-Zeit, Band und Mode; weitere Treffer werden als Anzahl zusammengefasst. CAT-, Frequenz-, Band- und Modeänderungen aktualisieren die Anzeige sofort. Die Markierung und Historie sind nur Hinweise und verhindern das Speichern eines weiteren QSOs nicht.

![Vollständiges QSO-Formular](screenshots/qso-logging.png)

Pflicht für ein übliches QSO sind mindestens Rufzeichen, Band und Mode. Datum und Zeit laufen standardmäßig live in UTC, können aber auf lokale Zeit oder manuelle Eingabe umgestellt werden.

Typischer Ablauf:

1. Rufzeichen eingeben.
2. Frequenz, Band und Mode prüfen; bei aktivem CAT werden diese Werte übernommen.
3. Rapporte, Leistung und optionale Aktivierungsreferenzen ergänzen.
4. **QSO speichern** wählen. Nach erfolgreichem Speichern wird das Formular automatisch für das nächste QSO zurückgesetzt.

Unter **Einstellungen → Allgemein** lässt sich die plattformübliche Desktop-Benachrichtigung nach einem erfolgreich lokal gespeicherten QSO ein- oder ausschalten. Ein fehlender Benachrichtigungsdienst beeinflusst die Speicherung nicht.

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

- Name und ADIF Contest-ID aus dem lokal gespeicherten Wavelog-Katalog
- Start und Ende der Contest-Session in UTC
- Start-Seriennummer
- gesendeten Text-Exchange
- Standardfrequenz und Standard-RST

Mit **Mit Wavelog abgleichen** lädt der Logger die für das gewählte Stationsprofil vorhandenen Contest-Sessions und legt ein nur lokal erstelltes Preset bei Wavelog an, sofern die Wavelog-Instanz bereits `/api/v2/contest` anbietet. Die numerische Session-ID vergibt Wavelog; sie darf nicht als ADIF-Name eingetragen werden. Das lokale Profil kann gewechselt werden, ohne in der Wavelog-Weboberfläche ein aktives Logbuch oder Stationsprofil umzustellen.

Nach dem Start einer Sitzung werden Seriennummern und Exchanges in die entsprechenden ADIF-Felder geschrieben. Bereits zur exakten Session gehörende QSOs bestimmen automatisch die nächste freie gesendete Seriennummer. QSOs bleiben Teil des normalen lokalen ADI-Logbuchs: Ein Online-Push überträgt zunächst das QSO und ordnet es danach der passenden Wavelog-Contest-Session zu. Der vollständige Sync lädt Session, Einstellungen und QSO-Zuordnungen wieder zurück.

Für diesen Abgleich benötigt der API-v2-Token `contest:read` und `contest:write` zusätzlich zu den QSO- und Stationsrechten. Bei einer Clubstation darf jedes Mitglied eigene QSOs einer Session zuordnen; das Anlegen oder Ändern der Session verlangt in Wavelog Club-Officer-Rechte. Unterstützt die verwendete Wavelog-Version die Contest-API noch nicht, bleiben Logging und normaler QSO-Sync vollständig nutzbar: `CONTEST_ID`, STX/SRX und Exchanges werden weiterhin übertragen. Bereits synchronisierte QSOs werden anhand von ADIF-Contest-Name und Jahr als lokale Contest-Auswahl rekonstruiert. Nur der Eintrag im Wavelog-Bereich **Contest Management** kann dann noch nicht automatisch erzeugt oder verknüpft werden.

## 8. xOTA-Aktivierungen

![xOTA-Aktivierung](screenshots/xota.png)

Der xOTA-Bereich fasst mehrere portable Programme in einer Aktivierung zusammen. Eine Aktivierung kann gleichzeitig mehrere bestätigte Referenzen enthalten, etwa einen POTA-Park und ein WWFF-Gebiet oder mehrere überlappende POTA-Parks.

1. Rufzeichen und optional Leistung eintragen.
2. Den aktuellen Standort per GPS übernehmen oder Breiten- und Längengrad manuell eintragen. Der Locator wird lokal berechnet.
3. Optional Standortdaten online ergänzen.
4. **Mögliche Referenzen suchen** wählen.
5. Einen oder mehrere Treffer mit `Strg` beziehungsweise `Shift` markieren, bewusst prüfen und übernehmen.
6. Aktivierung starten. Danach gespeicherte QSOs werden der aktiven Aktivierung zugeordnet und bleiben zuerst lokal.

Für POTA lädt der Logger den offiziellen Gesamtkatalog in einen lokalen Cache. Kandidaten bis 10 km gelten als nahe Katalogmarker; Treffer bis 25 km werden zusätzlich angezeigt, weil der Mittelpunkt eines großen Parks deutlich vom eigenen Standort entfernt liegen kann. Die Koordinate beweist keine Zugehörigkeit zur Parkfläche. Mit **POTA-Grenze prüfen** öffnet der Logger deshalb den ausgewählten Park auf `pota-map.info`; die endgültige Bestätigung bleibt immer beim Benutzer.

GPS, Internet und Referenzdienste sind optional. Fällt GPS aus oder wird die Standortfreigabe verweigert, können alle Werte manuell erfasst werden. Eine fertige Aktivierung lässt sich später wiederholen oder einer vorhandenen Wavelog Station Location zuordnen. Eine neue Wavelog Location wird nur nach ausdrücklicher Bestätigung angelegt.

## 9. Logbuch und Synchronisierung

![Logbuch und Sync](screenshots/logbook-sync.png)

Die Tabelle zeigt lokale QSOs und deren Zustand:

- `LOCAL ONLY` – nur lokal vorhanden
- `WAVELOG ✓` – erfolgreich verknüpft
- `GEÄNDERT` – lokal nach dem letzten Sync geändert
- `KONFLIKT` – lokal und in Wavelog unterschiedlich geändert
- `SYNC-FEHLER` – Übertragung nicht eindeutig erfolgreich

Ein QSO kann lokal bearbeitet oder gelöscht werden. Bei einem Konflikt entscheidet der Benutzer ausdrücklich zwischen lokaler und Wavelog-Version. Ein außerhalb der App fehlendes lokales ADI-QSO ist kein automatischer Auftrag, es aus Wavelog zu löschen.

Bei `SYNC-FEHLER` zeigt die Detailzeile unter der Tabelle die gespeicherte technische Ursache des ausgewählten QSOs. Eine Stationsprofil-Abweichung wird dort ausdrücklich genannt. Sie wird nicht automatisch repariert oder gelöscht.

Die Spalten QRZ, LoTW, eQSL und DCL zeigen den von Wavelog gelieferten Bestätigungsstatus, sofern die API ihn bereitstellt.

### 9.1 Online-Modus

Die App prüft regelmäßig die konfigurierte Wavelog-API:

- erreichbar: `WAVELOG ONLINE`
- nicht erreichbar oder nicht konfiguriert: `LOCAL ONLY`

Bei aktivierter Option werden im laufenden Betrieb ausschließlich neue, noch nie verknüpfte `LOCAL ONLY`-QSOs gepusht. Ein fehlgeschlagener oder mehrdeutiger Upload wird nicht blind wiederholt. Änderungen, Downloads, Löschungen und Konflikte sind Aufgabe des vollständigen Syncs.

### 9.2 Vollständiger Sync beim Start oder Beenden

![Laufender automatischer Sync](screenshots/sync-progress-running.png)

Während eines automatischen Voll-Syncs sperrt ein Statusfenster die Bedienung. Beim Beenden werden CAT, DX-Cluster und UDP zuerst gestoppt, damit kein weiteres externes QSO eingeht.

![Abgeschlossener automatischer Sync](screenshots/sync-progress-complete.png)

Nach Abschluss zeigt das Fenster die Zusammenfassung. Erst **OK** gibt die App frei beziehungsweise beendet sie. Scheitert der Sync, bleiben die lokalen ADI-Daten erhalten und die Fehlermeldung wird im Fenster angezeigt.

### ADIF importieren und exportieren

Unter **Logbuch & Sync** kann ein ADIF-Log importiert oder das aktuelle Profil-Log exportiert werden. Vor einem Import legt die App eine Sicherung an, prüft Pflichtfelder, überspringt natürliche Dubletten und verifiziert die neu geschriebene Datei durch erneutes Einlesen.

Ab Version 0.17.0 verwendet jedes Profil genau eine fortlaufende ADI-Datei. Beim ersten Öffnen eines älteren Profils werden vorhandene Tagesdateien zuerst als ZIP gesichert, anschließend zusammengeführt und byte-semantisch geprüft. Erst nach erfolgreicher Prüfung verschiebt die App die alten Quelldateien in das Wiederherstellungsverzeichnis `.migration-backups`.

## 10. Statistiken

![Lokale Statistiken](screenshots/statistics.png)

Statistiken werden ausschließlich aus dem lokalen Logbuch berechnet. Filterbar sind Zeitraum und Operator. Angezeigt werden unter anderem QSO-Anzahl, DXCC-Entities, Bänder, Modes, Länder, häufige Rufzeichen sowie Sync- und QSL-Status.

## 11. CAT und Hamlib

![CAT Setup](screenshots/cat-setup.png)

1. Funkgerätemodell auswählen.
2. Serielle Schnittstelle beziehungsweise Netzwerkziel und Baudrate eintragen.
3. Einstellungen speichern.
4. **CAT starten** oder zuerst **Verbindung testen**.

CAT startet nach jedem App-Start bewusst ausgeschaltet. Der Logger übernimmt Frequenz und Mode in normales Logging, Fast Log und Contest Logging. Ein Doppelklick auf einen DX-Spot stimmt den TRX ebenfalls ab.

Beim Stoppen von CAT, Profilwechsel und Programmende wird der von der App gestartete `rigctld`-Prozess beendet.

### TUNE / ATU

Der TUNE-Knopf im QSO-Fenster sendet nach einer Sicherheitsabfrage den Hamlib-Tunerbefehl. Während der Vorgang läuft, ist der Knopf rot und deaktiviert; danach wird er wieder neutral. Die App schaltet PTT nicht selbst ein. Ob und wie der Befehl arbeitet, hängt von Funkgerät, Firmware und Hamlib-Unterstützung ab.

## 12. DX Cluster

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
- **DX-Spot senden:** aktuellen QSO-Kandidaten über die getrennte DXSpider-Verbindung melden. Nach dem Speichern und Leeren des Formulars bleibt das letzte QSO als eigener Spot-Kandidat erhalten.

## 13. UDP Logging / WSJT-X

![UDP Logging](screenshots/udp-logging.png)

Unterstützt werden:

- das native WSJT-X-Protokoll für geloggte Kontakte
- vollständige ADIF-Datensätze mit `<EOR>` per UDP
- Duplikatschutz bei mehrfach gesendeten identischen QSOs

Empfohlene lokale Bind-Adresse ist `127.0.0.1`. Der Port ist frei wählbar und muss im sendenden Programm identisch sein. Ist der primäre WSJT-X-Port bereits belegt, kann der sekundäre „logged contact ADIF broadcast“ auf einen anderen freien Port zeigen.

**UDP Logging beim App-Start und Profilwechsel automatisch starten** ist profilbezogen. Beim Profilwechsel beendet der Logger zuerst den Listener des bisherigen Profils und startet anschließend den Listener des neuen Profils mit dessen eigener Bind-Adresse und Portnummer, sofern die Option dort aktiviert ist. Eingehende QSOs werden sofort lokal gespeichert und erscheinen als `LOCAL ONLY`; der normale Online-Modus beziehungsweise Sync übernimmt die spätere Übertragung.

Beim nativen WSJT-X-Protokoll verarbeitet der Logger zusätzlich die laufenden Statuspakete. Dafür muss der **primäre UDP-Server** von WSJT-X auf dieselbe Adresse und denselben Port wie der Logger zeigen; der sekundäre ADIF-Broadcast überträgt nur abgeschlossene QSOs und enthält keine Live-Statuspakete. Sobald in WSJT-X ein DX-Rufzeichen gewählt ist, werden Rufzeichen, Locator, Frequenz, Band, Mode und der aktuelle Report in das normale QSO-Formular gespiegelt. Dadurch stehen auch Callbook-Foto, Name, QTH und lokale Worked-Historie bereits während des QSOs zur Verfügung. Liegen sowohl der eigene Profil-Locator als auch der Locator der Gegenstation vor, zeigt der Callbook-Bereich zusätzlich die offline berechnete ungefähre Entfernung und Peilung an. Ein Statuspaket speichert ausdrücklich noch nichts: Erst die Bestätigung in WSJT-X und das danach gesendete `QSO Logged`-Paket erzeugen den lokalen ADI-Eintrag. Anschließend wird das Formular automatisch geleert. Eine gleichzeitig vorhandene manuelle Formulareingabe für ein anderes Rufzeichen wird nicht überschrieben.

Fehlen bei einem über WSJT-X oder den ADIF/UDP-Broadcast empfangenen QSO Name, Locator oder QTH, ergänzt der Logger diese Angaben im Hintergrund über die unter **Callbook & Online-Dienste** gewählte Quelle. Bereits vom sendenden Programm gelieferte Werte werden niemals überschrieben. Das QSO wird aus Sicherheitsgründen vor der Abfrage lokal gespeichert; ohne Internet oder bei einem Lookup-Fehler bleibt es unverändert erhalten. Die automatische Ergänzung folgt der Einstellung **Bei vollständigem Rufzeichen automatisch abfragen**. Ein Batch-ADIF-Import löst bewusst keine massenhaften Online-Abfragen aus.

## 14. Lokale Daten sichern und wiederherstellen

Unter **Einstellungen → Allgemein → Daten & Backup** erstellt **Backup erstellen** ein portables ZIP. Enthalten sind alle Logger-Profile, app-weiten Einstellungen, profilbezogenen Datenbanken und auch ADI-Dateien aus extern gewählten Logverzeichnissen. Weil gespeicherte Tokens und Passwörter enthalten sein können, muss das ZIP wie ein Zugangsschlüssel geschützt aufbewahrt werden.

**Backup wiederherstellen** prüft Inhalt, Format, Pfade und Größenlimits, zeigt Herkunft und Profilzahl an und verlangt eine ausdrückliche Bestätigung. Vor jeder Wiederherstellung erzeugt die App automatisch ein zweites Sicherheitsbackup des aktuellen Zustands. Die wiederhergestellten ADI-Dateien landen anschließend in sicheren profilbezogenen Logverzeichnissen. Nach erfolgreicher Wiederherstellung schließt sich die App und muss neu gestartet werden.

Eine einzelne ADI-Datei darf bei geschlossener App ersetzt oder aus einer Sicherung zurückkopiert werden. Niemals nur die SQLite-Datei als QSO-Sicherung behandeln – ADI ist das primäre Logbuch.

## 15. Updates

Beim Start prüft die App im Hintergrund, ob ein neueres GitHub-Release vorhanden ist. Ohne Internet erscheint keine Fehlermeldung. Nach Zustimmung lädt die App ausschließlich das zum System passende HTTPS-Paket und verifiziert es gegen die im Release veröffentlichte SHA-256-Prüfsumme. Unter Windows ersetzt ein Helfer nach dem sauberen Beenden die bisherige Programmdatei, behält eine Rückfallkopie und startet die neue Version. Auf macOS und Linux wird das geprüfte Paket gespeichert und anschließend mit dem üblichen Systemweg installiert.

Beim ersten Start einer neuen Version erscheint einmalig **Was ist neu?**. Die Hinweise können später unter **Einstellungen → Allgemein** erneut geöffnet werden.

## 16. Datenschutz und Netzwerkzugriffe

Offline verfügbar sind QSO-Erfassung, ADI-Speicherung, Profile, Statistiken, CTY.DAT-Ländererkennung und die lokale Logbuchansicht.

Netzwerk benötigen nur ausdrücklich konfigurierte oder gestartete Funktionen:

- Wavelog-Erreichbarkeitsprüfung und Sync
- Wavelog- oder QRZ-Callbook
- DX-Cluster-Empfang und Spotversand
- Release-Prüfung
- einmalige Windows-Runtime-Einrichtung

Zugangsdaten und Benutzerdaten gehören nicht in Git, Screenshots oder Fehlermeldungen. Das Dokumentations-Screenshot-Skript verwendet deshalb immer ein temporäres Demo-Profil.

## 17. Fehlerhilfe

Typische Ursachen und Diagnosepfade stehen in [TROUBLESHOOTING.md](TROUBLESHOOTING.md). Hilfreich sind Betriebssystem, App-Version, Funkgerät, Verbindungsart und der genaue Meldungstext. API-Tokens und Passwörter vor dem Teilen immer entfernen.

Die vollständige Bildübersicht steht in der [Screenshot-Galerie](SCREENSHOTS.md).
