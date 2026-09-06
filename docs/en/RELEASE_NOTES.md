# DA6IT.de Wavelog Offline Logger v0.19.3

Version 0.19.3 adds bidirectional WSJT-X file synchronization, a major internal modularization and substantial performance improvements for large local ADI logbooks.

## Highlights

- **WSJT-X ↔ Offline Logger ↔ Wavelog:** `wsjtx_log.adi` can be merged bidirectionally with the local logger and combined with the normal Wavelog full synchronization.
- **Dedicated WSJT-X Sync settings:** select the standard WSJT-X profile, a `--rig-name` profile or a manual log path, with independent startup, shutdown and manual synchronization.
- **Safe file merge:** timestamped backup before changing the WSJT-X log, tolerant duplicate matching, station-profile protection and no automatic deletions.
- **Responsive navigation:** Logbook & Sync, Fast Log/DXpedition and Statistics reuse shared QSO caches and perform expensive work outside the Tk main thread.
- **Append-only QSO saves:** new contacts no longer require a full rewrite of an existing canonical ADI file; a small recovery journal protects interrupted writes.
- **Modular application structure:** `app.py` is now primarily composition and startup, while functional areas live in focused `feature_*.py` modules with explicit dependencies.
- **Improved Windows packaging:** `feature_*.py` files are embedded automatically and the versioned runtime directory is derived dynamically from `appVersion`.

## Safety and compatibility

ADI remains the authoritative local QSO source. Editing, deletion, ADIF import and migration continue to use the full verified rewrite path. WSJT-X synchronization only adds missing contacts and never derives deletion intent from absence.

Existing Logger profiles, ADI files and Wavelog data are not automatically removed or reset by this update.
