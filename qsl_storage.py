from __future__ import annotations

import json
import re
from typing import Any

from logger_core import utc_now_iso


_QSO_UID_RE = re.compile(r"^qso_[0-9a-fA-F]{64}$")
_ACTION_TYPE_RE = re.compile(r"^[a-z0-9_.:-]{1,64}$")


class QslStorageError(ValueError):
    pass


def normalize_qso_uid(value: str) -> str:
    qso_uid = str(value or "").strip()

    if not _QSO_UID_RE.fullmatch(qso_uid):
        raise QslStorageError("Ungültige qsoUid")

    return "qso_" + qso_uid[4:].lower()


def _normalize_local_id(value: str) -> str:
    local_id = str(value or "").strip()

    if not local_id:
        raise QslStorageError("local_id fehlt")

    if len(local_id) > 200:
        raise QslStorageError("local_id ist zu lang")

    return local_id


def _normalize_action_type(value: str) -> str:
    action_type = str(value or "").strip().lower()

    if not _ACTION_TYPE_RE.fullmatch(action_type):
        raise QslStorageError("Ungültiger QSL-Aktionstyp")

    return action_type


def _json_dump(payload: dict[str, Any] | None) -> str:
    value = payload if payload is not None else {}

    if not isinstance(value, dict):
        raise QslStorageError("QSL-Payload muss ein Objekt sein")

    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
    except (TypeError, ValueError) as exc:
        raise QslStorageError(
            "QSL-Payload kann nicht als JSON gespeichert werden"
        ) from exc


def _json_load(value: str) -> dict[str, Any]:
    try:
        payload = json.loads(str(value or "{}"))
    except (TypeError, ValueError):
        return {}

    return payload if isinstance(payload, dict) else {}


class QslStorage:
    """Profile-local persistence for the DA6IT.de QSL Card Manager client.

    The active Logger profile owns its own MetadataDB.  Therefore all data in
    these tables is automatically isolated per profile and included in the
    existing metadata.db backup.

    The server remains authoritative for QSL history, queue state and limits.
    This storage only keeps client mappings, offline pending actions and cached
    status snapshots.
    """

    def __init__(self, db):
        self.db = db
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        with self.db.lock:
            self.db.conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS da6it_qsl_mapping (
                    qso_uid TEXT PRIMARY KEY,
                    local_id TEXT NOT NULL UNIQUE,
                    bound_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_da6it_qsl_mapping_local
                    ON da6it_qsl_mapping(local_id);

                CREATE TABLE IF NOT EXISTS da6it_qsl_pending_action (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    local_id TEXT NOT NULL,
                    qso_uid TEXT,
                    action_type TEXT NOT NULL,
                    payload TEXT NOT NULL DEFAULT '{}',
                    last_error TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_da6it_qsl_pending_local
                    ON da6it_qsl_pending_action(local_id);

                CREATE INDEX IF NOT EXISTS idx_da6it_qsl_pending_uid
                    ON da6it_qsl_pending_action(qso_uid);

                CREATE TABLE IF NOT EXISTS da6it_qsl_status_cache (
                    qso_uid TEXT PRIMARY KEY,
                    payload TEXT NOT NULL,
                    fetched_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS da6it_qsl_sync_state (
                    local_id TEXT PRIMARY KEY,
                    record_hash TEXT NOT NULL,
                    synced_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS da6it_qsl_recipient_hint (
                    local_id TEXT PRIMARY KEY,
                    email TEXT NOT NULL,
                    source TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_da6it_qsl_recipient_source
                    ON da6it_qsl_recipient_hint(source);
                """
            )
            self.db.conn.commit()

    def bind_qso_uid(
        self,
        local_id: str,
        qso_uid: str,
    ) -> dict[str, str]:
        local_id = _normalize_local_id(local_id)
        qso_uid = normalize_qso_uid(qso_uid)
        now = utc_now_iso()

        with self.db.lock:
            # One current local QSO can only point at one current qsoUid.  If a
            # user edits identity-defining QSO fields and the server returns a
            # different qsoUid, the old current mapping is dropped locally.
            self.db.conn.execute(
                """
                DELETE FROM da6it_qsl_mapping
                WHERE local_id=? AND qso_uid<>?
                """,
                (local_id, qso_uid),
            )

            # qsoUid is the stable cross-system identity.  Re-importing the
            # same QSO under a new local_id therefore re-associates the qsoUid
            # with the current local record.
            self.db.conn.execute(
                """
                INSERT INTO da6it_qsl_mapping(
                    qso_uid,local_id,bound_at,updated_at
                )
                VALUES(?,?,?,?)
                ON CONFLICT(qso_uid) DO UPDATE SET
                    local_id=excluded.local_id,
                    updated_at=excluded.updated_at
                """,
                (qso_uid, local_id, now, now),
            )

            # Offline actions may have been queued before a qsoUid existed.
            self.db.conn.execute(
                """
                UPDATE da6it_qsl_pending_action
                SET qso_uid=?,updated_at=?
                WHERE local_id=? AND qso_uid IS NULL
                """,
                (qso_uid, now, local_id),
            )

            self.db.conn.commit()

        return {
            "local_id": local_id,
            "qso_uid": qso_uid,
        }

    def qso_uid_for_local(
        self,
        local_id: str,
    ) -> str | None:
        local_id = _normalize_local_id(local_id)

        with self.db.lock:
            row = self.db.conn.execute(
                """
                SELECT qso_uid
                FROM da6it_qsl_mapping
                WHERE local_id=?
                """,
                (local_id,),
            ).fetchone()

        return str(row["qso_uid"]) if row else None

    def local_id_for_qso_uid(
        self,
        qso_uid: str,
    ) -> str | None:
        qso_uid = normalize_qso_uid(qso_uid)

        with self.db.lock:
            row = self.db.conn.execute(
                """
                SELECT local_id
                FROM da6it_qsl_mapping
                WHERE qso_uid=?
                """,
                (qso_uid,),
            ).fetchone()

        return str(row["local_id"]) if row else None

    def list_mappings(self) -> list[dict[str, Any]]:
        with self.db.lock:
            rows = self.db.conn.execute(
                """
                SELECT qso_uid,local_id,bound_at,updated_at
                FROM da6it_qsl_mapping
                ORDER BY updated_at DESC,qso_uid
                """
            ).fetchall()

        return [dict(row) for row in rows]

    def queue_action(
        self,
        local_id: str,
        action_type: str,
        payload: dict[str, Any] | None = None,
        *,
        qso_uid: str | None = None,
    ) -> int:
        local_id = _normalize_local_id(local_id)
        action_type = _normalize_action_type(action_type)
        payload_json = _json_dump(payload)
        normalized_uid = (
            normalize_qso_uid(qso_uid)
            if qso_uid
            else self.qso_uid_for_local(local_id)
        )
        now = utc_now_iso()

        with self.db.lock:
            cursor = self.db.conn.execute(
                """
                INSERT INTO da6it_qsl_pending_action(
                    local_id,qso_uid,action_type,payload,
                    last_error,created_at,updated_at
                )
                VALUES(?,?,?,?,NULL,?,?)
                """,
                (
                    local_id,
                    normalized_uid,
                    action_type,
                    payload_json,
                    now,
                    now,
                ),
            )
            self.db.conn.commit()
            return int(cursor.lastrowid)

    def list_pending_actions(
        self,
        *,
        ready_only: bool = False,
        limit: int = 500,
    ) -> list[dict[str, Any]]:
        limit = max(1, min(int(limit), 5000))
        where = "WHERE qso_uid IS NOT NULL" if ready_only else ""

        with self.db.lock:
            rows = self.db.conn.execute(
                f"""
                SELECT
                    id,local_id,qso_uid,action_type,payload,
                    last_error,created_at,updated_at
                FROM da6it_qsl_pending_action
                {where}
                ORDER BY id
                LIMIT ?
                """,  # nosec B608 - only fixed WHERE fragment above
                (limit,),
            ).fetchall()

        result = []

        for raw in rows:
            row = dict(raw)
            row["payload"] = _json_load(row.get("payload"))
            result.append(row)

        return result

    def mark_action_error(
        self,
        action_id: int,
        message: str,
    ) -> None:
        error = " ".join(str(message or "").split())[:1000]

        with self.db.lock:
            self.db.conn.execute(
                """
                UPDATE da6it_qsl_pending_action
                SET last_error=?,updated_at=?
                WHERE id=?
                """,
                (error, utc_now_iso(), int(action_id)),
            )
            self.db.conn.commit()

    def complete_action(
        self,
        action_id: int,
    ) -> None:
        with self.db.lock:
            self.db.conn.execute(
                """
                DELETE FROM da6it_qsl_pending_action
                WHERE id=?
                """,
                (int(action_id),),
            )
            self.db.conn.commit()

    def set_status_snapshot(
        self,
        qso_uid: str,
        payload: dict[str, Any],
    ) -> None:
        qso_uid = normalize_qso_uid(qso_uid)
        payload_json = _json_dump(payload)
        now = utc_now_iso()

        with self.db.lock:
            self.db.conn.execute(
                """
                INSERT INTO da6it_qsl_status_cache(
                    qso_uid,payload,fetched_at
                )
                VALUES(?,?,?)
                ON CONFLICT(qso_uid) DO UPDATE SET
                    payload=excluded.payload,
                    fetched_at=excluded.fetched_at
                """,
                (qso_uid, payload_json, now),
            )
            self.db.conn.commit()

    def get_status_snapshot(
        self,
        qso_uid: str,
    ) -> dict[str, Any] | None:
        qso_uid = normalize_qso_uid(qso_uid)

        with self.db.lock:
            row = self.db.conn.execute(
                """
                SELECT payload,fetched_at
                FROM da6it_qsl_status_cache
                WHERE qso_uid=?
                """,
                (qso_uid,),
            ).fetchone()

        if not row:
            return None

        return {
            "qso_uid": qso_uid,
            "payload": _json_load(row["payload"]),
            "fetched_at": str(row["fetched_at"]),
        }

    def list_status_snapshots_by_local(
        self,
    ) -> dict[str, dict[str, Any]]:
        with self.db.lock:
            rows = self.db.conn.execute(
                """
                SELECT
                    m.local_id,
                    m.qso_uid,
                    s.payload,
                    s.fetched_at
                FROM da6it_qsl_mapping AS m
                LEFT JOIN da6it_qsl_status_cache AS s
                    ON s.qso_uid = m.qso_uid
                """
            ).fetchall()

        result: dict[str, dict[str, Any]] = {}

        for row in rows:
            local_id = str(
                row["local_id"] or ""
            ).strip()

            if not local_id:
                continue

            payload = (
                _json_load(row["payload"])
                if row["payload"]
                else {}
            )

            result[local_id] = {
                "qso_uid": str(
                    row["qso_uid"] or ""
                ),
                "payload": payload,
                "fetched_at": str(
                    row["fetched_at"] or ""
                ),
            }

        return result

    def set_sync_fingerprint(
        self,
        local_id: str,
        record_hash: str,
    ) -> None:
        local_id = _normalize_local_id(
            local_id
        )
        record_hash = str(
            record_hash or ""
        ).strip().lower()

        if (
            len(record_hash) != 64
            or any(
                ch not in "0123456789abcdef"
                for ch in record_hash
            )
        ):
            raise QslStorageError(
                "Ungültiger QSL-Sync-Fingerprint"
            )

        with self.db.lock:
            self.db.conn.execute(
                """
                INSERT INTO da6it_qsl_sync_state(
                    local_id,record_hash,synced_at
                )
                VALUES(?,?,?)
                ON CONFLICT(local_id) DO UPDATE SET
                    record_hash=excluded.record_hash,
                    synced_at=excluded.synced_at
                """,
                (
                    local_id,
                    record_hash,
                    utc_now_iso(),
                ),
            )
            self.db.conn.commit()

    def sync_fingerprint_for_local(
        self,
        local_id: str,
    ) -> str | None:
        local_id = _normalize_local_id(
            local_id
        )

        with self.db.lock:
            row = self.db.conn.execute(
                """
                SELECT record_hash
                FROM da6it_qsl_sync_state
                WHERE local_id=?
                """,
                (local_id,),
            ).fetchone()

        if not row:
            return None

        value = str(
            row["record_hash"] or ""
        ).strip().lower()

        return value or None

    def set_recipient_hint(
        self,
        local_id: str,
        email: str,
        source: str,
    ) -> None:
        local_id = _normalize_local_id(local_id)
        email = str(email or "").strip()
        source = " ".join(str(source or "").split())[:200]

        if not email or len(email) > 320:
            raise QslStorageError("Ungültige Empfängeradresse")

        if not source:
            raise QslStorageError("Empfängerquelle fehlt")

        now = utc_now_iso()

        with self.db.lock:
            self.db.conn.execute(
                """
                INSERT INTO da6it_qsl_recipient_hint(
                    local_id,email,source,updated_at
                )
                VALUES(?,?,?,?)
                ON CONFLICT(local_id) DO UPDATE SET
                    email=excluded.email,
                    source=excluded.source,
                    updated_at=excluded.updated_at
                """,
                (local_id, email, source, now),
            )
            self.db.conn.commit()

    def get_recipient_hint(
        self,
        local_id: str,
    ) -> dict[str, str] | None:
        local_id = _normalize_local_id(local_id)

        with self.db.lock:
            row = self.db.conn.execute(
                """
                SELECT local_id,email,source,updated_at
                FROM da6it_qsl_recipient_hint
                WHERE local_id=?
                """,
                (local_id,),
            ).fetchone()

        return dict(row) if row else None

    def delete_recipient_hint(
        self,
        local_id: str,
    ) -> None:
        local_id = _normalize_local_id(local_id)

        with self.db.lock:
            self.db.conn.execute(
                """
                DELETE FROM da6it_qsl_recipient_hint
                WHERE local_id=?
                """,
                (local_id,),
            )
            self.db.conn.commit()

    def clear_status_snapshot(
        self,
        qso_uid: str,
    ) -> None:
        qso_uid = normalize_qso_uid(qso_uid)

        with self.db.lock:
            self.db.conn.execute(
                """
                DELETE FROM da6it_qsl_status_cache
                WHERE qso_uid=?
                """,
                (qso_uid,),
            )
            self.db.conn.commit()
