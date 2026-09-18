# DA6IT.de Wavelog Offline Logger v0.21.1

v0.21.1 makes automatic Wavelog synchronization at startup and shutdown faster. These operations upload only new local QSOs; complete synchronization with integrity checking remains an intentional manual action.

### Highlights

- **Faster startup and shutdown:** Optional automatic synchronization uses a delta upload of new local QSOs instead of a full reconciliation.
- **Complete synchronization remains available:** Downloads, edits, deletions, integrity checking and conflict handling remain available through manual full synchronization.
- **Safe transition:** Existing automatic startup/shutdown settings are migrated to their matching delta-sync options without overwriting an explicitly selected new option.
- **Visible control:** Delta synchronization shows progress and a result. A cancelled full synchronization retains its persisted checkpoint and journal for later resume.
- **Protected state:** Synchronization snapshots protect local changes and conflicts, while QSL status processing remains separate from QSO synchronization.

Documentation: [Deutsch](https://github.com/DA6IT/Wavelog-Offline-Logger/blob/v0.21.1/docs/USER_GUIDE.md) · [English](https://github.com/DA6IT/Wavelog-Offline-Logger/blob/v0.21.1/docs/en/USER_GUIDE.md)
