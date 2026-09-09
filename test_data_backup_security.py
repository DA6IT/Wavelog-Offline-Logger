from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
import zipfile
from pathlib import Path

from data_backup import (
    BackupError,
    create_backup,
    inspect_backup,
    restore_backup,
)


PROFILE_ID = "a" * 32


def _manifest(
    *,
    profile_id: str = PROFILE_ID,
    log_files=None,
):
    return {
        "format": 1,
        "application": (
            "DA6IT.de Wavelog Offline Logger"
        ),
        "app_version": "0.20.1",
        "created_utc": (
            "2026-09-09T18:00:00+00:00"
        ),
        "active_profile_id": profile_id,
        "profiles": [
            {
                "id": profile_id,
                "name": "Test",
                "original_log_dir": "",
                "log_files": list(
                    log_files or []
                ),
            }
        ],
    }


def _registry(
    *,
    profile_id: str = PROFILE_ID,
):
    return {
        "version": 1,
        "active_id": profile_id,
        "profiles": [
            {
                "id": profile_id,
                "name": "Test",
                "created_at": (
                    "2026-09-09T18:00:00+00:00"
                ),
            }
        ],
    }


def _write_minimal_backup(
    path: Path,
    *,
    manifest=None,
    registry=None,
    extra_entries=None,
):
    manifest = (
        _manifest()
        if manifest is None
        else manifest
    )
    registry = (
        _registry()
        if registry is None
        else registry
    )

    profile_id = str(
        manifest["profiles"][0]["id"]
    )

    with zipfile.ZipFile(
        path,
        "w",
        compression=zipfile.ZIP_DEFLATED,
    ) as archive:
        archive.writestr(
            "manifest.json",
            json.dumps(manifest),
        )
        archive.writestr(
            "data/profiles.json",
            json.dumps(registry),
        )
        archive.writestr(
            (
                "data/profiles/"
                + profile_id
                + "/metadata.db"
            ),
            b"placeholder",
        )

        for name, payload in (
            extra_entries or []
        ):
            archive.writestr(
                name,
                payload,
            )


class BackupSecurityTests(
    unittest.TestCase
):
    def test_valid_minimal_backup_is_accepted(
        self,
    ):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "valid.zip"
            _write_minimal_backup(path)

            manifest = inspect_backup(path)

            self.assertEqual(
                manifest["profiles"][0]["id"],
                PROFILE_ID,
            )

    def test_posix_parent_traversal_is_rejected(
        self,
    ):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "posix.zip"
            _write_minimal_backup(
                path,
                extra_entries=[
                    (
                        "../escape.txt",
                        b"x",
                    )
                ],
            )

            with self.assertRaises(
                BackupError
            ):
                inspect_backup(path)

    def test_backslash_traversal_is_rejected(
        self,
    ):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "backslash.zip"
            _write_minimal_backup(
                path,
                extra_entries=[
                    (
                        "data\\..\\escape.txt",
                        b"x",
                    )
                ],
            )

            with self.assertRaises(
                BackupError
            ):
                inspect_backup(path)

    def test_windows_drive_path_is_rejected(
        self,
    ):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "drive.zip"
            _write_minimal_backup(
                path,
                extra_entries=[
                    (
                        "C:/escape.txt",
                        b"x",
                    )
                ],
            )

            with self.assertRaises(
                BackupError
            ):
                inspect_backup(path)

    def test_manifest_log_traversal_is_rejected(
        self,
    ):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "log.zip"
            manifest = _manifest(
                log_files=[
                    "..\\escape.adi"
                ]
            )
            _write_minimal_backup(
                path,
                manifest=manifest,
            )

            with self.assertRaises(
                BackupError
            ):
                inspect_backup(path)

    def test_invalid_profile_id_is_rejected(
        self,
    ):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "profile.zip"
            bad_id = "g" * 32

            _write_minimal_backup(
                path,
                manifest=_manifest(
                    profile_id=bad_id
                ),
                registry=_registry(
                    profile_id=bad_id
                ),
            )

            with self.assertRaises(
                BackupError
            ):
                inspect_backup(path)

    def test_registry_and_manifest_must_match(
        self,
    ):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "mismatch.zip"

            _write_minimal_backup(
                path,
                registry=_registry(
                    profile_id="b" * 32
                ),
            )

            with self.assertRaises(
                BackupError
            ):
                inspect_backup(path)

    def test_case_colliding_members_are_rejected(
        self,
    ):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "collision.zip"

            _write_minimal_backup(
                path,
                extra_entries=[
                    (
                        "MANIFEST.JSON",
                        b"{}",
                    )
                ],
            )

            with self.assertRaises(
                BackupError
            ):
                inspect_backup(path)

    def test_backup_restore_roundtrip_stays_in_owned_paths(
        self,
    ):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            data_dir = (
                root / "source-data"
            )
            profile_dir = (
                data_dir
                / "profiles"
                / PROFILE_ID
            )
            profile_dir.mkdir(
                parents=True
            )

            log_dir = (
                root / "source-logs"
            )
            log_dir.mkdir()
            (
                log_dir
                / "DA6IT.2026-09-09.adi"
            ).write_text(
                "<CALL:5>DL1AA<EOR>\n",
                encoding="utf-8",
            )

            db_path = (
                profile_dir
                / "metadata.db"
            )
            connection = sqlite3.connect(
                db_path
            )

            try:
                connection.execute(
                    (
                        "CREATE TABLE settings("
                        "key TEXT PRIMARY KEY,"
                        "value TEXT NOT NULL)"
                    )
                )
                connection.execute(
                    (
                        "INSERT INTO settings("
                        "key,value) VALUES(?,?)"
                    ),
                    (
                        "log_dir",
                        str(log_dir),
                    ),
                )
                connection.commit()
            finally:
                connection.close()

            (
                data_dir
                / "profiles.json"
            ).write_text(
                json.dumps(
                    _registry()
                ),
                encoding="utf-8",
            )

            backup_path = (
                root / "backup.zip"
            )

            created = create_backup(
                data_dir,
                backup_path,
                app_version="0.20.1",
            )

            self.assertEqual(
                created["profiles"],
                1,
            )
            self.assertEqual(
                created["adi_files"],
                1,
            )

            restored_data = (
                root / "restored-data"
            )
            restored_logs = (
                root / "restored-logs"
            )

            result = restore_backup(
                backup_path,
                restored_data,
                log_root=restored_logs,
            )

            self.assertEqual(
                result["profiles"],
                1,
            )

            restored_db = (
                restored_data
                / "profiles"
                / PROFILE_ID
                / "metadata.db"
            )

            self.assertTrue(
                restored_db.is_file()
            )

            restored_adi = list(
                restored_logs.rglob(
                    "*.adi"
                )
            )

            self.assertEqual(
                len(restored_adi),
                1,
            )

            restored_root = (
                restored_logs.resolve()
            )
            restored_file = (
                restored_adi[0].resolve()
            )

            restored_file.relative_to(
                restored_root
            )


if __name__ == "__main__":
    unittest.main()
