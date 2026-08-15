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
        |
        +--------->  callbook.py <----> Wavelog Lookup API / QRZ XML API
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

Der Online-Modus verwendet mit `push_new_only()` bewusst einen engeren Pfad als der vollständige bidirektionale Sync: Er erstellt ausschließlich noch nie verknüpfte `LOCAL ONLY`-QSOs. Fehlerhafte, bereits verknüpfte, geänderte oder gelöschte Datensätze werden nicht blind automatisch erneut übertragen und bleiben dem sicheren Voll-Sync vorbehalten.

### `cat_control.py`

Verwaltet den gebündelten `rigctld`-Prozess, liest die Hamlib-Modellliste, erkennt Windows-COM-Ports und ordnet Funkgerätemodi den Logger-/ADIF-Modi zu. CAT-Einstellungen werden über die bestehende profilbezogene Einstellungsdatenbank gespeichert.

### `dx_cluster.py`

Implementiert eine manuell gestartete Telnet-Sitzung mit Aushandlung, profilbezogenen Serverdaten, DXSpider-Spot-Parser, Mode-Erkennung und explizitem DX-Spot-Versand. Empfangene Spots bleiben flüchtige UI-Daten; nur eine bewusste Übernahme füllt das QSO-Formular. CAT-Abstimmung läuft getrennt über `cat_control.py`, und kein Spot erzeugt automatisch ein ADI-QSO.

### `external_logging.py`

Implementiert den lokal start- und stoppbaren UDP-Empfänger, das native WSJT-X-Netzwerkprotokoll einschließlich Heartbeat-Antwort sowie ADIF-over-UDP. Empfangene Datensätze werden in normale QSO-Strukturen übersetzt; die GUI ergänzt Profil- und CTY-Daten und speichert sie über denselben `LogStore` wie manuell erfasste QSOs. Ein stabiler QSO-Schlüssel verhindert doppelte Einträge durch parallele WSJT-X-Nachrichten.

### `update_check.py`

Fragt nach dem Programmstart in einem Hintergrundthread ausschließlich die öffentliche GitHub-Release-Liste ab. Netzwerk-, HTTP- und Formatfehler liefern still kein Ergebnis. Stabile Versionen ignorieren Vorabversionen.

### `callbook.py`

Normalisiert die Wavelog- und QRZ.com-Antworten in ein gemeinsames Datenmodell. QRZ-Sitzungsschlüssel werden nur im Arbeitsspeicher gehalten und bei Ablauf einmal erneuert. Erfolgreiche Antworten werden profilspezifisch in SQLite zwischengespeichert; der Cache ersetzt niemals die ADI-QSO-Daten. Automatische Abfragen laufen in Hintergrundthreads und dürfen das lokale Logging bei Netzwerkfehlern nicht beeinflussen.

### `selftest.py`

Deckt Kernabläufe, lokale Verlustsicherheit, Profile, Migrationen, Contest-Felder, Hash-Migrationen, CAT-Zuordnungen, DX-Cluster-Parsing und lokales Telnet-Verhalten, UDP-/WSJT-X-Protokolle, Callbook-Normalisierung/Cache sowie die fehlertolerante Release-Prüfung ohne echte Wavelog-Instanz ab.

## Datenmodell

ADI ist die maßgebliche lokale QSO-Quelle. SQLite speichert keine unabhängige zweite QSO-Fassung, sondern nur Einstellungen, Identitäten, Hash-Baselines, Tombstones, Cachewerte und technische Zuordnungen.

Ein Tombstone (`pending_delete`) darf nur durch eine ausdrückliche Löschaktion in der Anwendung entstehen. Ein beim Einlesen fehlendes ADI-QSO reicht dafür nicht aus.

## Sync-Invarianten

1. Keine automatische Remote-Löschung aufgrund unvollständiger lokaler oder Clubtoken-Sicht.
2. Keine stille Auflösung echter Zwei-Seiten-Konflikte.
3. Keine Remote-Wirkung beim Löschen eines Profils.
4. Vorhandene Baselines und Legacy-Hashes werden migrationsfähig gehalten.
5. Benutzerdaten werden nicht ungefragt gelöscht.
6. Der automatische Laufzeit-Push führt keine Remote-Listenabfrage, Änderung, Löschung oder Konfliktauflösung aus.

## Token-Schutz

Unter Windows werden neue Tokens und Passwörter mit DPAPI verschlüsselt. Kann DPAPI nicht verwendet werden, wird das Speichern abgebrochen und sichtbar gemeldet. Historische `plain:`-Werte bleiben lesbar, damit bestehende Installationen kontrolliert migriert werden können. Auf anderen Plattformen werden Geheimnisse derzeit nur lokal kodiert; ein nativer Keychain-/Secret-Service-Speicher ist noch offen.

## Release-Artefakt

Der Go-Bootstrapper ist kein Python-Onefile-Bundle. Die Anwendung bleibt als eingebetteter Python-Quellcode im Launcher enthalten und wird versionsabhängig in den lokalen Anwendungsordner geschrieben. Pillow wird beim Windows-Build ohne Abhängigkeit von `pip` als offizielles, per PyPI-SHA-256 geprüftes Wheel vorbereitet. `build_pyinstaller_windows.bat` ist nur noch ein Kompatibilitätsstarter für denselben Go-Build.
