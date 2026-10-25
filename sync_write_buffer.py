"""Batched local writes for the full Wavelog sync.

The full sync used to rewrite the complete ADIF and commit SQLite once per
changed QSO.  With large logbooks that made remote edits, restores, links and
the first download quadratic in the logbook size.  This buffer collects the
per-QSO results of a sync phase and applies them in bounded batches:

* ADIF: one ``LogStore.upsert_many()`` / ``delete_many()`` per batch
* SQLite: one transaction per batch via ``MetadataDB.bulk()``

Crash safety: before an ADIF batch is written, the intended link/baselines
are staged in ``sync_pending_apply`` (one transaction).  If the process dies
between the ADIF write and the status commit, the next
``MetadataDB.reconcile_index()`` finds the staged rows and applies them when
the ADIF contains exactly the staged record, or discards them when the write
never happened.  An interruption therefore neither re-uploads pulled QSOs as
LOCAL ONLY nor turns remote updates into false conflicts.

Local edits or deletions made while a batch was pending are detected with the
same version snapshot check as before: pending writes become conflicts and
deferred baseline refreshes are skipped instead of overwriting the change.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

DEFAULT_BATCH_SIZE = 500
_NO_SNAPSHOT = object()


@dataclass
class _PendingUpsert:
    local_id: str
    record: dict[str, Any]
    wavelog_id: int
    remote_hash: str
    counter: str
    snapshot: int | None = None
    check_snapshot: bool = False
    after: Callable[[], None] | None = None


@dataclass
class _PendingDelete:
    local_id: str
    wavelog_id: int
    snapshot: int | None


@dataclass
class SyncWriteBuffer:
    store: Any
    db: Any
    qso_hash: Callable[[dict[str, Any]], str]
    summary: Any
    # Phase 1 handled per-QSO failures as an ``error`` status; phase 2 let
    # failures abort the sync.  Both behaviours are preserved.
    raise_errors: bool = False
    batch_size: int = DEFAULT_BATCH_SIZE
    upserts: list[_PendingUpsert] = field(default_factory=list)
    deletes: list[_PendingDelete] = field(default_factory=list)
    statuses: list[tuple[str, Any, dict[str, Any]]] = field(default_factory=list)

    def pending(self) -> int:
        return len(self.upserts) + len(self.deletes) + len(self.statuses)

    def _maybe_flush(self) -> None:
        if self.pending() >= self.batch_size:
            self.flush()

    def defer_status(self, local_id: str, status: str, *, snapshot: Any = _NO_SNAPSHOT, **kwargs: Any) -> None:
        """Pure metadata update without dependency on later loop iterations.

        With ``snapshot`` the update is skipped at flush time when the QSO was
        edited/deleted locally in the meantime (the next sync handles it).
        """
        self.statuses.append((local_id, snapshot, {"status": status, **kwargs}))
        self._maybe_flush()

    def upsert(self, local_id: str, record: dict[str, Any], *, wavelog_id: int, remote_hash: str,
               counter: str, snapshot: int | None = None, check_snapshot: bool = False,
               after: Callable[[], None] | None = None) -> None:
        row = dict(record)
        row["local_id"] = local_id
        self.upserts.append(_PendingUpsert(
            local_id, row, int(wavelog_id), remote_hash, counter, snapshot, check_snapshot, after,
        ))
        self._maybe_flush()

    def delete(self, local_id: str, *, wavelog_id: int, snapshot: int | None) -> None:
        self.deletes.append(_PendingDelete(local_id, int(wavelog_id), snapshot))
        self._maybe_flush()

    def _changed_during_sync(self, local_id: str, wavelog_id: int, snapshot: int | None) -> bool:
        if self.db.unchanged_since(local_id, snapshot):
            return False
        self.db.set_status(local_id, "conflict", wavelog_id=wavelog_id, error="local_changed_during_sync")
        self.summary.conflicts += 1
        return True

    def _mark_errors(self, items: list[Any], exc: Exception) -> None:
        with self.db.bulk():
            for item in items:
                self.db.set_status(item.local_id, "error", wavelog_id=item.wavelog_id, error=str(exc))
        self.summary.errors += len(items)

    def flush(self) -> None:
        deletes, self.deletes = self.deletes, []
        upserts, self.upserts = self.upserts, []
        statuses, self.statuses = self.statuses, []

        deletes = [d for d in deletes if not self._changed_during_sync(d.local_id, d.wavelog_id, d.snapshot)]
        if deletes:
            try:
                self.store.delete_many([d.local_id for d in deletes])
            except Exception as exc:
                if self.raise_errors:
                    raise
                self._mark_errors(deletes, exc)
            else:
                with self.db.bulk():
                    for d in deletes:
                        self.db.delete_meta(d.local_id)
                self.summary.remote_deleted += len(deletes)

        upserts = [
            u for u in upserts
            if not (u.check_snapshot and self._changed_during_sync(u.local_id, u.wavelog_id, u.snapshot))
        ]
        if upserts:
            hashes = [self.qso_hash(u.record) for u in upserts]
            stage = getattr(self.db, "stage_pending_apply", None)
            if stage is not None:
                stage([(u.local_id, u.wavelog_id, h, u.remote_hash) for u, h in zip(upserts, hashes)])
            try:
                self.store.upsert_many([u.record for u in upserts])
            except Exception as exc:
                self._clear_staged(upserts)
                if self.raise_errors:
                    raise
                self._mark_errors(upserts, exc)
            else:
                with self.db.bulk():
                    for u, local_hash in zip(upserts, hashes):
                        self.db.set_status(
                            u.local_id, "synced", wavelog_id=u.wavelog_id,
                            last_synced_hash=local_hash, remote_hash=u.remote_hash,
                        )
                        setattr(self.summary, u.counter, getattr(self.summary, u.counter) + 1)
                        if u.after is not None:
                            u.after()
                    self._clear_staged(upserts)

        if statuses:
            with self.db.bulk():
                for local_id, snapshot, values in statuses:
                    if snapshot is not _NO_SNAPSHOT and snapshot is not None \
                            and not self.db.unchanged_since(local_id, snapshot):
                        continue
                    values = dict(values)
                    self.db.set_status(local_id, values.pop("status"), **values)

    def _clear_staged(self, upserts: list[_PendingUpsert]) -> None:
        clear = getattr(self.db, "clear_pending_apply", None)
        if clear is not None:
            clear([u.local_id for u in upserts])
