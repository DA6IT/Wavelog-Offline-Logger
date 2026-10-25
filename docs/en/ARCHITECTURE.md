# Wavelog Offline Logger — architecture and developer notes

> Version: 0.22.0
> Goal: keep large functional areas independently maintainable without growing `app.py` back into a monolith.

## Overview

Since 0.19.3 the desktop logger is composed from focused feature modules.

```text
app.py
│
├── feature_ui_shell.py
├── feature_update.py
├── feature_usage.py
├── feature_wavelog_online.py
├── feature_profiles.py
├── feature_lifecycle.py
├── feature_logbook.py
├── feature_fastlog.py
├── feature_contest.py
├── feature_xota.py
├── feature_qso_sync.py
├── feature_qsl.py
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
qsl_eqsl.py
usage_stats.py
...
```

`app.py` should contain composition, shared application context, feature initialization, page construction, startup scheduling and `main()`. New substantial UI or domain behavior belongs in the appropriate feature or service module.

## Feature responsibilities

| File | Responsibility |
|---|---|
| `feature_ui_shell.py` | main window, navigation, styles and responsive UI |
| `feature_update.py` | release checks, update flow and What's New |
| `feature_usage.py` | first-start notice, settings and asynchronous usage-statistics heartbeat |
| `feature_wavelog_online.py` | Wavelog reachability, online mode and auto-push |
| `feature_profiles.py` | Logger profiles and profile-specific storage |
| `feature_lifecycle.py` | shutdown and cleanup |
| `feature_logbook.py` | normal QSO logging and callbook UI |
| `feature_fastlog.py` | Fast Log / DXpedition |
| `feature_contest.py` | contest logging |
| `feature_xota.py` | xOTA UI and orchestration |
| `feature_qso_sync.py` | QSO view, Wavelog sync and WSJT-X sync orchestration |
| `feature_qsl.py` | QSL Card Manager UI, templates, local eQSL recommendations and delivery orchestration |
| `feature_stats.py` | statistics |
| `feature_cat.py` | CAT, Hamlib, FLRig and TUNE |
| `feature_rotor.py` | rotor UI, `rotctld` lifecycle, live position and QSO bearing control |
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

Non-feature modules such as `app_common.py`, `ui_theme.py`, `dialogs.py`, `wsjtx_sync.py`, `qsl_eqsl.py` and `usage_stats.py` must be embedded explicitly.

The runtime directory is derived from `appVersion`. For example, `0.22.0` becomes `app-v0220`, so a new release does not require a second hard-coded runtime-path update.

Linux and macOS use PyInstaller with `app.py`; normal Python imports are discovered automatically, but real platform builds still need release smoke testing.

## Versioning

At minimum these values must match:

```python
# logger_core.py
VERSION = "0.22.0"
```

```go
// bootstrap_windows.go
appVersion = "0.22.0"
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

For parser, LogStore cache, metadata or sync performance changes:

```powershell
python -m unittest test_performance_paths.py
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
- DX Cluster including the QRZ.com action
- QSL recommendations and eQSL cache
- first-start usage notice plus enable/disable/delete statistics controls
- UDP logging
- settings persistence
- backup/restore
- Windows executable
- Linux package
- macOS application

## Parser, LogStore cache and batched sync (v0.22.0)

Runtime must not grow quadratically with the number of QSOs:

- `parse_adif()` searches with start/end positions instead of copying the remaining text per record.
- `LogStore` keeps the parsed records of the canonical ADI file in memory, validated on every access against size, `mtime_ns`, inode and `ctime_ns`. Own writes invalidate the cache, appends extend it incrementally, callers always receive copies.
- `find()` uses an index, `update()` reads and writes exactly once, `add_many()` appends several QSOs in one journaled append and `upsert_many()` replaces/adds several QSOs with at most one verified rewrite (never for an unreadable file). Full rewrites are fsynced before `os.replace()`.
- `MetadataDB.bulk()` groups many small metadata writes in one transaction; `reconcile_index()` uses one query and one commit.
- `SyncEngine.sync()` collects local results per phase in `sync_write_buffer.py` and applies them in batches (ADIF first, then the `synced` status). Unlinked local QSOs are bucketed by call/date/band. Local edits during an open batch still become conflicts.
- Batch crash safety: before each ADIF batch the intended links/baselines are staged in `sync_pending_apply`. If the process dies between the ADIF write and the status commit, the next `reconcile_index()` applies staged rows whose record is present in the ADIF and discards the rest, so neither duplicate delta uploads nor false conflicts occur. Deferred baseline updates are skipped when the QSO was edited/deleted locally meanwhile.
- Without uploads or patches in the same run, the QSL status refresh reuses the downloaded QSO list and ADIF export.
- `CountryDB.lookup()` uses a longest-prefix index; the DX Cluster table rebuild is coalesced and worked-before caches are computed in the logbook worker.

Regression tests: `test_performance_paths.py`. `sync_write_buffer.py` is a non-feature module and is embedded explicitly in the Windows bootstrap.

## UI responsiveness (v0.22.0)

Measured with a probe (real app under Xvfb, 20,000 QSOs, 5 ms heartbeat on the Tk thread):

- **Incremental logbook Treeview:** `qso_tree_view.plan_row_diff()` compares the shown rows with the new cache. When the relative order is unchanged (add, edit, delete, status change) only changed rows are inserted/updated/removed; otherwise (reordering, duplicate ids, more than 2000 changes) the previous chunked rebuild runs. Inserts/updates use direct Tcl calls.
- **Delete and edit** write the ADI file in a worker (`_run_qso_write`). Deleted rows disappear immediately (and stay hidden until a refresh without them arrives); delete/edit are locked until the write completes, and closing/profile switching wait for it (non-daemon thread, `_wait_qso_write` before `db.close()`). The order "ADI first, then `mark_pending_delete_many`" is unchanged.
- **Profile index at startup/profile switch:** `reconcile_index()` runs in a worker, at startup only after the window has been shown and its first layout has settled; a failed background reconcile is repeated by the waiting worker. `reconcile_index(scan_started=…)` keeps metadata rows created after the scan began. Logbook refresh, delta upload and full sync wait for `_profile_index_ready` in their workers, so the index is still reconciled before any automatic upload.
- **CTY.DAT** is loaded in the background; `CountryDB.lookup()` waits for completion.
- **Shared fonts:** one scalable font per font specification instead of one per widget.
- **Refresh worker:** worked-before history is built per call on demand (`dx_cluster.LazyWorkedHistory`), country/mode normalization is memoized per run, `list_meta()` avoids `sqlite3.Row` conversion.
- **Statistics** no longer copy the shared cache lists on the Tk thread.
- `sys.setswitchinterval(0.001)` lets the Tk thread regain the GIL sooner while workers run.

Regression tests: `test_ui_performance.py`. `qso_tree_view.py` is embedded in the Windows bootstrap.
