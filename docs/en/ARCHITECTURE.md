# Wavelog Offline Logger — architecture and developer notes

> Version: 0.19.3
> Goal: keep large functional areas independently maintainable without growing `app.py` back into a monolith.

## Overview

Since 0.19.3 the desktop logger is composed from focused feature modules.

```text
app.py
│
├── feature_ui_shell.py
├── feature_update.py
├── feature_wavelog_online.py
├── feature_profiles.py
├── feature_lifecycle.py
├── feature_logbook.py
├── feature_fastlog.py
├── feature_contest.py
├── feature_xota.py
├── feature_qso_sync.py
├── feature_stats.py
├── feature_cat.py
├── feature_dxcluster.py
├── feature_udp.py
├── feature_backup.py
└── feature_settings.py

app_common.py
ui_theme.py
dialogs.py

logger_core.py
cat_control.py
dx_cluster.py
external_logging.py
callbook.py
xota.py
wsjtx_sync.py
...
```

`app.py` should contain composition, shared application context, feature initialization, page construction, startup scheduling and `main()`. New substantial UI or domain behavior belongs in the appropriate feature or service module.

## Feature responsibilities

| File | Responsibility |
|---|---|
| `feature_ui_shell.py` | main window, navigation, styles and responsive UI |
| `feature_update.py` | release checks, update flow and What's New |
| `feature_wavelog_online.py` | Wavelog reachability, online mode and auto-push |
| `feature_profiles.py` | Logger profiles and profile-specific storage |
| `feature_lifecycle.py` | shutdown and cleanup |
| `feature_logbook.py` | normal QSO logging and callbook UI |
| `feature_fastlog.py` | Fast Log / DXpedition |
| `feature_contest.py` | contest logging |
| `feature_xota.py` | xOTA UI and orchestration |
| `feature_qso_sync.py` | QSO view, Wavelog sync and WSJT-X sync orchestration |
| `feature_stats.py` | statistics |
| `feature_cat.py` | CAT, Hamlib, FLRig and TUNE |
| `feature_dxcluster.py` | DX Cluster and spotting |
| `feature_udp.py` | UDP and WSJT-X live logging |
| `feature_backup.py` | backup and restore |
| `feature_settings.py` | settings pages |
| `app_common.py` | small shared UI-independent helpers |
| `ui_theme.py` | mutable shared theme palette |
| `dialogs.py` | larger dialogs |

Reusable technical logic remains outside the feature mixins, for example in `logger_core.py`, `cat_control.py`, `dx_cluster.py`, `external_logging.py`, `callbook.py`, `xota.py` and `wsjtx_sync.py`.

## Explicit dependencies

The transitional `bind_app_globals()` / `globals().update(...)` mechanism has been removed. Every feature imports its dependencies explicitly.

Do not introduce namespace injection into new feature modules. Prefer normal imports and neutral shared service modules.

## Feature-owned runtime state

A feature should initialize its own runtime state in `_init_<feature>_feature()` whenever practical. `LoggerApp._initialize_features()` invokes these initializers centrally. Profile initialization runs last because it opens the active `MetadataDB`, `LogStore` and profile-scoped services.

## Shared UI state

`ui_theme.py` exposes the mutable `theme` object. UI modules should use `theme.CARD`, `theme.TEXT`, and similar attributes rather than copying palette constants.

`app_common.py` contains small shared helpers such as responsive scaling, common dimensions, callbook labels, startup logging and time conversion. It should not become a second `logger_core.py`.

## Adding a new feature

A substantial new UI area should normally be implemented as `feature_<name>.py` with a clearly named mixin and, when needed, `_init_<name>_feature()`.

The mixin must still be imported and added to `LoggerApp`; the filename alone does not activate it.

## Windows packaging

The Windows executable is a Go launcher. `bootstrap_windows.go` embeds all `feature_*.py` files through `embed.FS`, writes them to the versioned runtime directory and verifies their presence and contents.

Non-feature modules such as `app_common.py`, `ui_theme.py`, `dialogs.py` and `wsjtx_sync.py` must be embedded explicitly.

The runtime directory is derived from `appVersion`. For example, `0.19.3` becomes `app-v0193`, so a new release does not require a second hard-coded runtime-path update.

Linux and macOS use PyInstaller with `app.py`; normal Python imports are discovered automatically, but real platform builds still need release smoke testing.

## Versioning

At minimum these values must match:

```python
# logger_core.py
VERSION = "0.19.3"
```

```go
// bootstrap_windows.go
appVersion = "0.19.3"
```

The Windows build script verifies this relationship. `whats_new.py`, changelogs, user guides and release notes should be updated for every published version.

## Architecture tests

`test_architecture.py` protects the refactor by checking, among other things:

- no `bind_app_globals`
- no `globals().update(namespace)` feature injection
- no duplicate method names across feature mixins
- `_vars` remains instance state
- root Python sources parse successfully

Run:

```powershell
python -m compileall -q .
python -m unittest test_architecture.py
```

For WSJT-X changes also run:

```powershell
python -m unittest test_wsjtx_sync.py
```

For LogStore append changes:

```powershell
python -m unittest test_logstore_append.py
```

## Navigation and QSO cache rules

Data-heavy pages must not synchronously scan the whole ADI log on normal navigation.

`QsoSyncFeatureMixin` owns the shared QSO snapshot. Logbook & Sync, Fast Log/DXpedition, Statistics and worked/DX-cluster helpers reuse that snapshot. Expensive ADIF, SQLite and aggregation work runs in worker threads; Treeview population is chunked through Tk idle callbacks.

When a feature changes QSO data, it should invalidate/refresh the shared cache rather than introduce another independent full scan on the Tk main thread.

## Append-only QSO storage

Normal new QSOs use append-only writes when the canonical ADI file already exists. A small `.append-journal` records the original file size and complete record before modification. The new tail is flushed with `fsync()` and verified.

On the next scan an interrupted append is recovered when the on-disk state matches a safe recoverable case. Contradictory state aborts rather than silently overwriting data.

New/empty log files, editing, deletion, ADIF import and migration retain the full verified rewrite path. Legacy ISO-8859-1 logs are normalized to UTF-8 once before their first append.

## Synchronization model

The Offline Logger remains the local merge hub:

```text
Wavelog  → Offline Logger ← WSJT-X
Wavelog  ← Offline Logger → WSJT-X
```

Core rules:

- ADI is the authoritative local QSO source
- SQLite stores settings, synchronization metadata, mappings and caches
- no automatic remote deletion because a record is absent locally
- no silent resolution of genuine two-sided conflicts
- Logger-profile deletion has no Wavelog side effect
- Wavelog downloads remain station-profile scoped
- WSJT-X synchronization adds missing contacts and protects station-profile boundaries
- `wsjtx_log.adi` is backed up before the logger modifies it

## Release smoke test

Before release, cover at least:

- application startup and shutdown
- profile switching
- normal QSO logging
- Fast Log/DXpedition
- contest logging
- xOTA
- Logbook & Sync
- manual/startup/shutdown Wavelog sync
- WSJT-X file sync
- statistics
- CAT start/stop
- DX Cluster
- UDP logging
- settings persistence
- backup/restore
- Windows executable
- Linux package
- macOS application
