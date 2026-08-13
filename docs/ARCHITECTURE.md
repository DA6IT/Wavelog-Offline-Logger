# Architektur

## Komponenten

```text
bootstrap_windows.go
        |
        v
      app.py  <---->  logger_core.py  <---->  ADI / SQLite / Wavelog API v2
        |
        +--------->  cat_control.py   <---->  rigctld / Funkgerät
        |
        +--------->  dx_cluster.py <---->  DXSpider-kompatibler Telnet-Cluster
        |
        +--------->  external_logging.py <---->  WSJT-X / ADIF über UDP
        |
        +--------->  update_check.py <---->  GitHub Releases API
```

### `bootstrap_windows.go`

Der Windows-GUI-Launcher enthält die Python-Anwendung, `cty.dat` und die für Windows benötigten Hamlib-Dateien per `go:embed`. Er schreibt sie in einen versionsabhängigen Anwendungsordner, richtet bei Bedarf eine private Python-3.12.10-Laufzeit ein und startet `pythonw.exe` in einem Windows-Job-Objekt.

### `app.py`

Enthält die Tkinter-Oberfläche, Dialoge, Tabellen, Profilwechsel sowie die Verbindung zwischen Benutzeraktionen und Core-Logik.

### `logger_core.py`

Enthält die fachliche Logik:

- ADIF/ADI lesen, normalisieren und schreiben
- Profile und verschlüsselte Einstellungen verwalten
- Sync-Baselines und Wavelog-Zuordnungen speichern
- Konflikte erkennen
- Wavelog API v2 ansprechen
- Statistiken und QSL-Status aufbereiten

### `cat_control.py`

Verwaltet den gebündelten `rigctld`-Prozess, liest die Hamlib-Modellliste, erkennt Windows-COM-Ports und ordnet Funkgerätemodi den Logger-/ADIF-Modi zu. CAT-Einstellungen werden über die bestehende profilbezogene Einstellungsdatenbank gespeichert.

### `dx_cluster.py`

Implementiert eine manuell gestartete Telnet-Sitzung mit Aushandlung, profilbezogenen Serverdaten, DXSpider-Spot-Parser, Mode-Erkennung und explizitem DX-Spot-Versand. Empfangene Spots bleiben flüchtige UI-Daten; nur eine bewusste Übernahme füllt das QSO-Formular. CAT-Abstimmung läuft getrennt über `cat_control.py`, und kein Spot erzeugt automatisch ein ADI-QSO.

### `external_logging.py`

Implementiert den lokal start- und stoppbaren UDP-Empfänger, das native WSJT-X-Netzwerkprotokoll einschließlich Heartbeat-Antwort sowie ADIF-over-UDP. Empfangene Datensätze werden in normale QSO-Strukturen übersetzt; die GUI ergänzt Profil- und CTY-Daten und speichert sie über denselben `LogStore` wie manuell erfasste QSOs. Ein stabiler QSO-Schlüssel verhindert doppelte Einträge durch parallele WSJT-X-Nachrichten.

### `update_check.py`

Fragt nach dem Programmstart in einem Hintergrundthread ausschließlich die öffentliche GitHub-Release-Liste ab. Netzwerk-, HTTP- und Formatfehler liefern still kein Ergebnis. Stabile Versionen ignorieren Vorabversionen.

### `selftest.py`

Deckt Kernabläufe, lokale Verlustsicherheit, Profile, Migrationen, Contest-Felder, Hash-Migrationen, CAT-Zuordnungen, DX-Cluster-Parsing und lokales Telnet-Verhalten, UDP-/WSJT-X-Protokolle und die fehlertolerante Release-Prüfung ohne echte Wavelog-Instanz ab.

## Datenmodell

ADI ist die maßgebliche lokale QSO-Quelle. SQLite speichert keine unabhängige zweite QSO-Fassung, sondern nur Einstellungen, Identitäten, Hash-Baselines, Tombstones, Cachewerte und technische Zuordnungen.

Ein Tombstone (`pending_delete`) darf nur durch eine ausdrückliche Löschaktion in der Anwendung entstehen. Ein beim Einlesen fehlendes ADI-QSO reicht dafür nicht aus.

## Sync-Invarianten

1. Keine automatische Remote-Löschung aufgrund unvollständiger lokaler oder Clubtoken-Sicht.
2. Keine stille Auflösung echter Zwei-Seiten-Konflikte.
3. Keine Remote-Wirkung beim Löschen eines Profils.
4. Vorhandene Baselines und Legacy-Hashes werden migrationsfähig gehalten.
5. Benutzerdaten werden nicht ungefragt gelöscht.

## Token-Schutz

Unter Windows werden neue Tokens mit DPAPI verschlüsselt. Kann DPAPI nicht verwendet werden, wird das Speichern abgebrochen und sichtbar gemeldet. Historische `plain:`-Werte bleiben lesbar, damit bestehende Installationen kontrolliert migriert werden können.

## Release-Artefakt

Der Go-Bootstrapper ist kein Python-Onefile-Bundle. Die Anwendung bleibt als eingebetteter Python-Quellcode im Launcher enthalten und wird versionsabhängig in den lokalen Anwendungsordner geschrieben. Der alternative PyInstaller-Batch ist nur eine historische/optionale Buildvariante.
