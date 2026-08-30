# Architecture

[Deutsch](../ARCHITECTURE.md) · **English**

ADI is the authoritative QSO logbook. SQLite stores settings, caches, local/Wavelog IDs, hashes and synchronization state only. `APP_AFUTOOLS_ID` is the stable local UUID and must not be removed without migration.

`app.py` contains the Tkinter presentation layer; `logger_core.py` contains profiles, ADIF, metadata, Wavelog client and synchronization; dedicated modules handle CAT, callbook, external UDP logging, DX Cluster, notifications, backup, updates and xOTA. User-visible translation is applied at the presentation boundary by `ui_preferences.py`; data values and ADIF remain language-neutral.

Each profile has independent identity, paths, Wavelog credentials/station profile, CAT, cluster, UDP and synchronization metadata. Profile deletion is strictly local. Sync uses shared hashes: local-only changes are uploaded, remote-only changes are applied locally, both-sided changes become explicit conflicts, and ambiguous/missing visibility is handled conservatively.

Windows uses a Go bootstrapper and private verified CPython runtime. macOS builds an app bundle; Linux builds Debian, AppImage and Arch packages. Official releases are built on GitHub-hosted runners and checked by `selftest.py` plus packaging validation.
