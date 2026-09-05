# DA6IT.de Wavelog Offline Logger v0.19.2

Version 0.19.2 fixes the automatic Windows updater while preserving the existing offline-first workflow and Wavelog synchronization.

Highlights:

- the desktop app now hands the update over to the Windows launcher only after the Python process exits
- the updater is no longer terminated by the launcher's internal Windows Job Object
- the exact EXE originally launched by the user is replaced and restarted, regardless of filename or location
- the PowerShell helper is compatible with Windows PowerShell 5.1
- staged and installed executables are verified again with SHA-256
- failed replacements or restarts roll back to the previous launcher
- the update process is logged under `%LOCALAPPDATA%\AFU-Tools\WavelogOfflineLogger\updates\update.log`

Important: because the updater itself is broken in v0.19.1, upgrading from v0.19.1 to v0.19.2 may require one manual download and replacement of the existing EXE. From v0.19.2 onward, the repaired update flow is included.

Profiles, settings, ADI logbooks and Wavelog synchronization data are not changed by this update. The Windows package remains intentionally unsigned while SignPath onboarding is pending.
