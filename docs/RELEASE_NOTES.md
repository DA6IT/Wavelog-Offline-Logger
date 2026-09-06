# DA6IT.de Wavelog Offline Logger v0.19.3

## Deutsch

v0.19.3 bringt einen bidirektionalen WSJT-X-Dateisync, eine große interne Modularisierung und deutliche Performance-Verbesserungen bei großen lokalen Logbüchern.

### Highlights

- **WSJT-X ↔ Offline Logger ↔ Wavelog:** `wsjtx_log.adi` kann bidirektional mit dem lokalen Logger abgeglichen werden. Bei konfiguriertem Wavelog lässt sich der Dateiabgleich mit dem vorhandenen Vollsync kombinieren.
- **Eigener WSJT-X-Sync-Tab:** Standardprofil, `--rig-name`-Profile oder ein manueller Pfad können pro Logger-Profil gewählt werden. Start-, Beenden- und manueller Sync sind getrennt schaltbar.
- **Sicherer Merge:** Vor Änderungen an der WSJT-X-Datei entsteht ein Backup. Dubletten werden tolerant erkannt, eindeutig profilfremde Stationsrufzeichen werden nicht in das aktive Profil übernommen und es gibt keine automatischen Löschungen.
- **Schnellere Oberfläche:** Logbuch & Sync, Fast Log/DXpedition und Statistiken verwenden gemeinsame QSO-Caches und Hintergrundverarbeitung statt bei jedem Seitenwechsel das komplette ADI-Logbuch synchron neu einzulesen.
- **Schnelleres Speichern:** Neue QSOs werden in bestehende ADI-Logbücher append-only geschrieben. Ein Recovery-Journal schützt vor einem abgebrochenen oder partiellen Append.
- **Modulare Architektur:** Die frühere große `app.py` wurde in fachliche `feature_*.py`-Module, `dialogs.py`, `app_common.py` und `ui_theme.py` aufgeteilt. Abhängigkeiten werden explizit importiert und Architekturtests schützen die Trennung.
- **Windows-Build:** Feature-Module werden automatisch eingebettet; der Runtime-Ordner wird aus der Programmversion erzeugt und die Build-Prüfung berücksichtigt diesen dynamischen Pfad.

### Daten- und Sync-Sicherheit

ADI bleibt die maßgebliche lokale QSO-Quelle. SQLite speichert weiterhin Einstellungen, Sync-Metadaten, Zuordnungen und Caches. Editieren, Löschen, ADIF-Import und Migration verwenden weiterhin den vollständigen verifizierten Rewrite. Weder Wavelog- noch WSJT-X-Sync leiten aus einem fehlenden lokalen Datensatz automatisch eine Remote-Löschung ab.

Profile, vorhandene ADI-Logbücher und Wavelog-Daten werden durch das Update nicht automatisch gelöscht oder zurückgesetzt.

Dokumentation: [Deutsch](https://github.com/DA6IT/Wavelog-Offline-Logger/blob/v0.19.3/docs/USER_GUIDE.md) · [English](https://github.com/DA6IT/Wavelog-Offline-Logger/blob/v0.19.3/docs/en/USER_GUIDE.md)

---

## English

v0.19.3 adds bidirectional WSJT-X file synchronization, a major internal modularization and substantial performance improvements for large local logbooks.

### Highlights

- **WSJT-X ↔ Offline Logger ↔ Wavelog:** `wsjtx_log.adi` can be merged bidirectionally with the local logger and combined with the existing Wavelog full synchronization.
- **Dedicated WSJT-X Sync tab:** select the standard profile, a `--rig-name` profile or a manual path per Logger profile, with independent startup, shutdown and manual synchronization.
- **Safe merge behavior:** the WSJT-X file is backed up before changes, duplicates are matched tolerantly, clearly foreign station callsigns are not imported into the active profile, and no automatic deletions are performed.
- **Responsive UI:** Logbook & Sync, Fast Log/DXpedition and Statistics reuse shared QSO caches and background processing instead of synchronously rescanning the full ADI log during navigation.
- **Faster saves:** normal new QSOs use append-only writes to existing ADI logs with a recovery journal for interrupted or partial appends.
- **Modular architecture:** the former large `app.py` is split into focused `feature_*.py` modules plus `dialogs.py`, `app_common.py` and `ui_theme.py`, protected by architecture tests.
- **Windows build:** feature modules are packaged automatically and the versioned runtime directory is derived dynamically from the application version.

### Data and synchronization safety

ADI remains the authoritative local QSO source. SQLite continues to hold settings, synchronization metadata, mappings and caches. Editing, deletion, ADIF import and migration retain the full verified rewrite path. Neither Wavelog nor WSJT-X synchronization interprets a missing local record as an automatic remote deletion.

Profiles, existing ADI logbooks and Wavelog data are not automatically deleted or reset by this update.

Documentation: [Deutsch](https://github.com/DA6IT/Wavelog-Offline-Logger/blob/v0.19.3/docs/USER_GUIDE.md) · [English](https://github.com/DA6IT/Wavelog-Offline-Logger/blob/v0.19.3/docs/en/USER_GUIDE.md)
