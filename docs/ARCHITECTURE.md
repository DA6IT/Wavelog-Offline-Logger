# Wavelog Offline Logger – Architektur & Entwicklerhinweise

> Stand: 0.19.4
> Ziel: große Funktionsbereiche getrennt entwickeln, ohne die zentrale `app.py` wieder wachsen zu lassen.

## Überblick

Seit 0.19.3 ist der Desktop-Logger modular aufgebaut.

`app.py` enthält nur noch:

- Zusammensetzung der Feature-Mixins,
- gemeinsamen Anwendungskontext,
- Aufruf der Feature-Initialisierung,
- Aufbau der Seiten,
- Start-Timer,
- `main()`.

Die eigentliche Funktionalität liegt in separaten Modulen.

```text
app.py
│
├── feature_ui_shell.py
├── feature_update.py
├── feature_wavelog_online.py
├── feature_profiles.py
├── feature_lifecycle.py
│
├── feature_logbook.py
├── feature_fastlog.py
├── feature_contest.py
├── feature_xota.py
├── feature_qso_sync.py
├── feature_stats.py
├── feature_cat.py
├── feature_rotor.py
├── feature_dxcluster.py
├── feature_udp.py
├── feature_backup.py
└── feature_settings.py

app_common.py
ui_theme.py
dialogs.py

logger_core.py
cat_control.py
rotor_control.py
dx_cluster.py
external_logging.py
callbook.py
xota.py
wsjtx_sync.py
...
```

`app.py` soll keine neue umfangreiche Fach- oder UI-Logik mehr aufnehmen.

---

# Zuständigkeiten

| Datei | Aufgabe |
|---|---|
| `app.py` | Komposition, gemeinsamer Kontext, Start |
| `feature_ui_shell.py` | Hauptfenster, Navigation, Styles, Responsive UI |
| `feature_update.py` | Updateprüfung, Download, „Was ist neu?“ |
| `feature_wavelog_online.py` | Erreichbarkeit, Online-Modus, Auto-Push |
| `feature_profiles.py` | Profile und profilspezifischer Storage |
| `feature_lifecycle.py` | Shutdown und sauberes Beenden |
| `feature_logbook.py` | normales QSO-Logging und Callbook-UI |
| `feature_fastlog.py` | Fast Log / DXpedition |
| `feature_contest.py` | Contest Logging |
| `feature_xota.py` | xOTA-Oberfläche und Orchestrierung |
| `feature_qso_sync.py` | QSO-Liste, Wavelog- und WSJT-X-Sync-Orchestrierung |
| `feature_stats.py` | Statistiken |
| `feature_cat.py` | CAT/Hamlib/FLRig/TUNE-UI |
| `feature_rotor.py` | Rotor-UI, `rotctld`-Lifecycle, Live-Position und QSO-Peilungssteuerung |
| `feature_dxcluster.py` | DX-Cluster und Spots |
| `feature_udp.py` | UDP-/WSJT-X-Live-Logging |
| `feature_backup.py` | Backup/Restore |
| `feature_settings.py` | Einstellungsseiten |
| `app_common.py` | kleine, UI-unabhängige gemeinsame Helfer |
| `ui_theme.py` | zentraler, dynamischer Zugriff auf die aktive Farbpalette |
| `dialogs.py` | größere Dialogfenster |

Technische oder wiederverwendbare Logik bleibt außerhalb der Feature-Mixins, z. B.:

```text
logger_core.py
cat_control.py
dx_cluster.py
external_logging.py
callbook.py
xota.py
wsjtx_sync.py
```

---

# Feature-Mixins

Die UI-Funktionsbereiche werden als Mixins eingebunden.

Beispiel:

```python
class ContestFeatureMixin:
    def _build_contest_page(self):
        ...
```

`LoggerApp` setzt sie zusammen:

```python
class LoggerApp(
    UiShellFeatureMixin,
    UpdateFeatureMixin,
    WavelogOnlineFeatureMixin,
    ProfilesFeatureMixin,
    LifecycleFeatureMixin,
    LogbookFeatureMixin,
    FastLogFeatureMixin,
    ContestFeatureMixin,
    ...
    tk.Tk,
):
    ...
```

Dadurch bleiben vorhandene Aufrufe über `self` erhalten, die Implementierung liegt aber in der fachlich passenden Datei.

---

# Explizite Abhängigkeiten

Frühere Zwischenstände des Refactors verwendeten:

```python
bind_app_globals(...)
globals().update(...)
```

Dieser Mechanismus ist entfernt.

Jedes Feature importiert seine Abhängigkeiten jetzt explizit:

```python
from logger_core import BANDS, MODES, qso_hash
from tkinter import messagebox, ttk
from ui_theme import theme
```

Das ist wichtig, weil dadurch direkt in der Datei sichtbar ist, was ein Feature benötigt.

## Regel

Neue Feature-Module dürfen **kein** allgemeines Runtime-Namespace-Injection-Muster einführen.

Also nicht:

```python
globals().update(...)
```

sondern normale, gezielte Imports verwenden.

---

# Feature-eigener State

Auch der Runtime-State wurde aus `LoggerApp.__init__()` herausgezogen.

Beispiel:

```python
class CatFeatureMixin:
    def _init_cat_feature(self) -> None:
        self.cat_manager = HamlibManager()
        self.cat_models = []
        self.cat_generation = 0
        ...
```

`app.py` ruft die Initialisierer zentral auf:

```python
def _initialize_features(self):
    self._init_ui_shell_feature()
    self._init_lifecycle_feature()
    self._init_qso_sync_feature()
    ...
```

Dadurch liegen UI, Methoden und State eines Funktionsbereichs möglichst in derselben Datei.

## Reihenfolge

Profilinitialisierung läuft zuletzt, weil dabei unter anderem erzeugt werden:

- `MetadataDB`
- `LogStore`
- xOTA-Repository und Dienste

Andere Features dürfen ihren lokalen State vorher initialisieren, sollen aber noch nicht auf eine geöffnete Profildatenbank angewiesen sein.

---

# Gemeinsamer UI-State

## `ui_theme.py`

Farben werden nicht als kopierte Konstanten in jedes Modul importiert.

Stattdessen verwenden UI-Module:

```python
from ui_theme import theme

label = tk.Label(
    parent,
    bg=theme.CARD,
    fg=theme.TEXT,
)
```

`theme` ist ein veränderliches Objekt. Beim Start setzt `app.py` genau einmal die gespeicherte Palette:

```python
set_theme(self.ui_preferences.theme)
```

Damit sehen alle Module automatisch dieselben aktuellen Farbwerte.

## `app_common.py`

Kleine gemeinsame Helfer liegen hier, zum Beispiel:

- Responsive-Skalierung,
- UI-Größenkonstanten,
- Callbook-Quellennamen,
- `write_startup_log()`,
- UTC-Konvertierung für das Formular,
- `display_now()`.

`app_common.py` soll kein zweites `logger_core.py` werden. Größere Fachlogik gehört weiterhin in passende Service-/Core-Module.

---

# Neue Features anlegen

Ein neuer größerer UI-Bereich sollte so aussehen:

```text
feature_awards.py
```

Beispiel:

```python
from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from ui_theme import theme


class AwardsFeatureMixin:
    def _init_awards_feature(self) -> None:
        self.awards_busy = False

    def _build_awards_page(self) -> None:
        ...
```

Dann in `app.py`:

```python
from feature_awards import AwardsFeatureMixin
```

und in `LoggerApp`:

```python
class LoggerApp(
    ...
    AwardsFeatureMixin,
    tk.Tk,
):
```

Falls das Feature eigenen State besitzt, zusätzlich in `_initialize_features()`:

```python
self._init_awards_feature()
```

## Wichtig

Eine `feature_xyz.py` wird durch ihren Dateinamen zwar automatisch in den Windows-Build aufgenommen, aber dadurch **nicht automatisch in der Python-Anwendung aktiviert**.

Das Mixin muss weiterhin bewusst in `app.py` eingebunden werden.

---

# Windows-Build

Windows verwendet einen Go-Launcher.

Der Launcher bettet die Python-Anwendung ein und schreibt sie beim Start in das private Anwendungsverzeichnis.

## Automatische Feature-Dateien

In `bootstrap_windows.go`:

```go
//go:embed feature_*.py
var featureFS embed.FS
```

Alle Dateien mit diesem Muster werden automatisch:

1. in die EXE eingebettet,
2. in das Runtime-Verzeichnis geschrieben,
3. durch `appFilesComplete()` geprüft,
4. durch `embeddedAppFilesMatch()` auf identischen Inhalt geprüft.

Für eine neue `feature_xyz.py` muss der Bootstrap deshalb nicht manuell erweitert werden.

## Nicht-Feature-Module

Module ohne `feature_`-Prefix müssen explizit eingebettet sein.

Aktuell gehören dazu unter anderem:

```text
app.py
app_common.py
ui_theme.py
dialogs.py
wsjtx_sync.py
logger_core.py
cat_control.py
dx_cluster.py
...
```

Wird ein neues eigenständiges Nicht-Feature-Modul eingeführt, muss geprüft werden, ob `bootstrap_windows.go` ergänzt werden muss.

---

# Windows-Runtime-Verzeichnis

Der Verzeichnisname wird aus `appVersion` erzeugt.

Beispiel:

```go
appVersion = "0.19.4"
```

ergibt:

```text
app-v0193
```

Damit muss der Runtime-Pfad beim nächsten Release nicht mehr separat von Hand geändert werden.

---

# Linux- und macOS-Build

Linux und macOS verwenden PyInstaller direkt mit:

```text
app.py
```

PyInstaller verfolgt die regulären Python-Imports automatisch.

Deshalb müssen neue importierte Feature-Module dort normalerweise nicht separat in einer Dateiliste gepflegt werden.

Trotzdem gilt vor einem Release:

- echten Linux-Build laufen lassen,
- echten macOS-Build laufen lassen,
- gebaute Pakete kurz starten.

---

# Versionierung

Mindestens diese beiden Werte müssen übereinstimmen:

`logger_core.py`:

```python
VERSION = "0.19.4"
```

`bootstrap_windows.go`:

```go
appVersion = "0.19.4"
```

Das Windows-Buildscript prüft diesen Zustand absichtlich und bricht bei einem Konflikt ab.

`whats_new.py` sollte für jedes veröffentlichte Release ebenfalls aktualisiert werden.

---

# Architekturtests

`test_architecture.py` schützt zentrale Regeln des Refactors.

Geprüft wird unter anderem:

- kein `bind_app_globals`,
- kein `globals().update(namespace)` in Feature-Modulen,
- keine versehentlich doppelten Methodennamen zwischen Mixins,
- `_vars` ist Instanz-State statt Klassen-State,
- alle Python-Quellen sind syntaktisch parsebar.

Ausführen:

```powershell
python -m unittest test_architecture.py
```

Zusätzlich:

```powershell
python -m compileall -q .
```

und vorhandene fachliche Tests, z. B.:

```powershell
python -m unittest test_wsjtx_sync.py
```

---

# Empfohlener Entwicklungsablauf

Nach einer Änderung:

```powershell
python -m compileall -q .
python -m unittest test_architecture.py
python app.py
```

Bei WSJT-X-Änderungen zusätzlich:

```powershell
python -m unittest test_wsjtx_sync.py
```

Danach plattformspezifische Builds testen.

---

# Release-Smoke-Test

Mindestens prüfen:

- Start der Anwendung,
- Profilwechsel,
- normales QSO Logging,
- Callbook,
- Fast Log,
- Contest Logging,
- xOTA,
- QSO-Liste,
- Wavelog manueller Sync,
- Wavelog Start-/Shutdown-Sync,
- WSJT-X-Sync,
- Statistik,
- CAT Start/Stop,
- DX-Cluster,
- UDP Logging,
- Einstellungen speichern,
- Backup/Restore,
- sauberer Shutdown,
- Windows-EXE,
- Linux-Paket,
- macOS-App.

---

# Architekturregeln

## 1. `app.py` klein halten

`app.py` ist Komposition, nicht Feature-Ablage.

## 2. State gehört zum Feature

Wenn ein Feature zehn Runtime-Variablen benötigt, sollen sie in seinem `_init_*_feature()` initialisiert werden.

## 3. Explizite Imports

Ein Feature soll seine Abhängigkeiten selbst deklarieren.

## 4. Fachlogik aus der UI halten

Wiederverwendbare, testbare Logik bevorzugt in Service-/Core-Modulen implementieren.

## 5. Keine zyklischen Feature-Imports

Gemeinsame Logik besser in ein neutrales Modul verschieben.

## 6. Methodennamen eindeutig halten

Doppelte Methodennamen zwischen Mixins sind gefährlich, weil die Python-MRO entscheidet, welche Implementierung verwendet wird.

`test_architecture.py` schützt davor.

---

# Synchronisationsprinzip

Der Offline Logger bleibt der lokale Merge-Hub:

```text
Wavelog  ───────→  Offline Logger
WSJT-X   ───────→  Offline Logger

Offline Logger ─→  Wavelog
Offline Logger ─→  WSJT-X
```

Grundregeln:

- keine automatischen Remote-Löschungen, nur weil lokal etwas fehlt,
- Dubletten erkennen,
- Stations-/Profilzuordnung beachten,
- WSJT-X-Datei vor Änderungen sichern,
- ADIF bleibt maßgebliche lokale QSO-Datenquelle,
- SQLite speichert Einstellungen, Sync-Metadaten und Zuordnungen.

---

# Kurzfassung

Für neue Arbeit gilt:

> Große UI-Funktion → `feature_xyz.py`

> Feature-State → `_init_xyz_feature()`

> Abhängigkeiten → explizite Imports

> Farben → `ui_theme.theme`

> wiederverwendbare Logik → Service-/Core-Modul

> Windows packt `feature_*.py` automatisch ein

> Nicht-Feature-Modul → Bootstrap prüfen


## Logbuch-Performance

Die Seite **Logbuch & Sync** darf beim Navigieren nicht synchron das komplette
ADI-Logbuch neu aufbauen.

Seit der Performance-Überarbeitung gelten deshalb folgende Regeln:

- ADIF-Scan und Sync-Metadatenabgleich laufen in einem Worker-Thread.
- Die zuletzt gelesenen QSOs werden im `QsoSyncFeatureMixin` gecacht.
- Ein normaler Seitenwechsel zu `Logbuch & Sync` verwendet den Cache, solange
  keine QSO-Daten geändert wurden.
- Änderungen markieren die Ansicht als `dirty`; mehrere schnelle Änderungen
  werden zu möglichst wenigen Refreshes zusammengefasst.
- Die `ttk.Treeview` wird in kleinen Batches über `after_idle()` gefüllt.
  Dadurch bekommt Tk zwischen den Batches Zeit für Navigation, Repaint und
  Benutzereingaben.
- Bereits geparste QSO-Daten werden außerdem für Worked-/DX-Cluster-Caches und
  das zuletzt spottbare QSO wiederverwendet, statt die ADI-Datei erneut zu lesen.

Wichtig für neue Features:

> Wenn ein Feature QSO-Daten verändert und bisher `refresh_qsos()` aufruft,
> soll dieser Aufruf erhalten bleiben. Er blockiert nicht mehr, sondern
> invalidiert den Cache und stößt einen asynchronen Refresh an.

Für reine Navigation wird dagegen verwendet:

```python
self.refresh_qsos(force=False, immediate=True)
```

So wird nur dann neu gelesen, wenn der Cache tatsächlich veraltet ist.



### Fast Log und Statistiken

Fast Log und Statistiken dürfen ebenfalls keinen eigenen synchronen
`LogStore.scan()` beim Seitenwechsel ausführen.

- Fast Log verwendet den gemeinsamen QSO-Cache für Worked-/Dupe-Erkennung und
  die Session-Anzeige.
- Neu gespeicherte Fast-Log-QSOs werden zusätzlich kurz im Session-State
  gehalten, damit sie sofort sichtbar sind, während der globale Cache im
  Hintergrund aktualisiert wird.
- Statistiken verwenden QSO-, Sync-Meta- und QSL-Snapshots aus dem gemeinsamen
  Cache.
- Die Aggregation der Statistiken (Zeitraum, Operator, Länder, Bänder, Modes,
  Sync/QSL) läuft in einem Worker-Thread.
- Ein erneuter Seitenwechsel mit unverändertem QSO-Cache und denselben Filtern
  rendert die Statistik nicht erneut.

Damit gilt für datenintensive Seiten grundsätzlich:

> Navigation hebt zuerst die Seite an. Teure ADIF-/SQLite-/Aggregationsarbeit
> darf den Tk-Hauptthread nicht blockieren.


### Append-only QSO-Speicherung

Normales Speichern eines neuen QSOs darf bei großen Logbüchern nicht die
komplette kanonische ADIF-Datei erneut lesen und schreiben.

`LogStore.add()` arbeitet deshalb bei einer bereits vorhandenen Logdatei
append-only:

- nur der neue ADIF-Datensatz wird angehängt,
- der Schreibvorgang wird mit `fsync()` auf den Datenträger gespült,
- ein kleines `.append-journal` hält vor dem Append die alte Dateigröße und den
  vollständigen neuen Datensatz fest,
- nach dem Schreiben wird ausschließlich der neu angehängte Tail verifiziert,
- bleibt der Prozess während des Appends stehen, wird ein vollständiger oder
  partieller Append beim nächsten Start/Scan anhand des Journals abgeschlossen,
- widersprechen sich Journal und vorhandener Dateitail, wird abgebrochen statt
  still Daten zu überschreiben.

Neue oder leere Logdateien werden weiterhin atomar als vollständige Datei
geschrieben. Ebenso bleiben **Editieren, Löschen, ADIF-Import und Migration**
bewusst beim vollständigen Rewrite mit Verifikation.

Ältere ISO-8859-1-Logdateien werden vor ihrem ersten Append einmalig nach UTF-8
normalisiert. Danach greift ebenfalls der schnelle Append-Pfad.

Damit wächst der Aufwand eines normalen neuen QSOs nicht mehr mit der Größe des
gesamten Logbuchs.
