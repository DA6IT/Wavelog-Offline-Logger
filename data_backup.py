from __future__ import annotations

import json
import os
import shutil
import sqlite3
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any


BACKUP_FORMAT = 1
MAX_BACKUP_FILES = 20_000
MAX_UNCOMPRESSED_BYTES = 4 * 1024 * 1024 * 1024


class BackupError(RuntimeError):
    pass


def _utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")


def _safe_profile_name(value: str) -> str:
    import re
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "-", str(value or "Profil").strip()).strip("-._")
    return cleaned or "Profil"


def _default_log_dir(profile: dict[str, Any], *, log_root: Path | None = None) -> Path:
    if log_root is None:
        documents = Path.home() / "Documents"
        if not documents.exists():
            documents = Path.home()
        base = documents / "DA6IT.de Wavelog Logger" / "Profiles"
    else:
        base = Path(log_root)
    folder = f"{_safe_profile_name(str(profile.get('name') or 'Profil'))}-{str(profile.get('id') or '')[:6]}"
    return base / folder / "Logs"


def _read_registry(data_dir: Path) -> dict[str, Any]:
    path = Path(data_dir) / "profiles.json"
    try:
        registry = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise BackupError(f"Profilregister kann nicht gelesen werden: {exc}") from exc
    profiles = registry.get("profiles") if isinstance(registry, dict) else None
    if not isinstance(profiles, list) or not profiles:
        raise BackupError("Das Profilregister enthält keine Profile.")
    return registry


def _sqlite_snapshot(source: Path, destination: Path) -> None:
    if not source.is_file():
        raise BackupError(f"Profildatenbank fehlt: {source}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    source_db = sqlite3.connect(f"file:{source.as_posix()}?mode=ro", uri=True, timeout=10)
    destination_db = sqlite3.connect(destination)
    try:
        source_db.backup(destination_db)
    finally:
        destination_db.close()
        source_db.close()


def _setting_from_db(path: Path, key: str, default: str = "") -> str:
    try:
        connection = sqlite3.connect(path)
        try:
            row = connection.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
            return str(row[0]) if row and row[0] is not None else default
        finally:
            connection.close()
    except sqlite3.Error:
        return default


def _set_setting(path: Path, key: str, value: str) -> None:
    connection = sqlite3.connect(path)
    try:
        connection.execute("CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT NOT NULL)")
        connection.execute(
            "INSERT INTO settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, value),
        )
        connection.commit()
    finally:
        connection.close()


def create_backup(data_dir: Path, destination: Path, *, app_version: str) -> dict[str, Any]:
    """Create a portable, consistent ZIP of profiles, settings and ADI logs."""
    data_dir = Path(data_dir).resolve()
    destination = Path(destination).resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    registry = _read_registry(data_dir)
    profiles = [dict(row) for row in registry["profiles"] if isinstance(row, dict)]

    with tempfile.TemporaryDirectory(prefix="wavelog-backup-") as temporary:
        staging = Path(temporary)
        data_stage = staging / "data"
        logs_stage = staging / "logs"
        data_stage.mkdir(parents=True)
        logs_stage.mkdir(parents=True)
        shutil.copy2(data_dir / "profiles.json", data_stage / "profiles.json")
        preferences = data_dir / "ui_preferences.json"
        if preferences.is_file():
            shutil.copy2(preferences, data_stage / "ui_preferences.json")

        manifest_profiles: list[dict[str, Any]] = []
        qso_files = 0
        for profile in profiles:
            profile_id = str(profile.get("id") or "").strip()
            if not profile_id or any(ch not in "0123456789abcdefABCDEF" for ch in profile_id):
                raise BackupError("Das Profilregister enthält eine ungültige Profil-ID.")
            source_db = data_dir / "profiles" / profile_id / "metadata.db"
            staged_db = data_stage / "profiles" / profile_id / "metadata.db"
            _sqlite_snapshot(source_db, staged_db)
            configured_log_dir = Path(
                _setting_from_db(source_db, "log_dir", str(_default_log_dir(profile)))
            ).expanduser()
            log_entries: list[str] = []
            if configured_log_dir.is_dir():
                for source in sorted(configured_log_dir.rglob("*.adi")):
                    if not source.is_file():
                        continue
                    relative = source.relative_to(configured_log_dir)
                    target = logs_stage / profile_id / relative
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(source, target)
                    log_entries.append(relative.as_posix())
                    qso_files += 1
            manifest_profiles.append({
                "id": profile_id,
                "name": str(profile.get("name") or "Profil"),
                "original_log_dir": str(configured_log_dir),
                "log_files": log_entries,
            })

        manifest = {
            "format": BACKUP_FORMAT,
            "application": "DA6IT.de Wavelog Offline Logger",
            "app_version": str(app_version),
            "created_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "active_profile_id": str(registry.get("active_id") or ""),
            "profiles": manifest_profiles,
        }
        (staging / "manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8",
        )
        temporary_zip = destination.with_name(destination.name + ".tmp")
        try:
            with zipfile.ZipFile(temporary_zip, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
                for source in sorted(path for path in staging.rglob("*") if path.is_file()):
                    archive.write(source, source.relative_to(staging).as_posix())
            os.replace(temporary_zip, destination)
        finally:
            temporary_zip.unlink(missing_ok=True)
    return {"path": str(destination), "profiles": len(profiles), "adi_files": qso_files}


def _validated_members(archive: zipfile.ZipFile) -> list[zipfile.ZipInfo]:
    members = archive.infolist()
    if not members or len(members) > MAX_BACKUP_FILES:
        raise BackupError("Das ZIP enthält keine oder zu viele Dateien.")
    total = 0
    for member in members:
        path = PurePosixPath(member.filename)
        if path.is_absolute() or ".." in path.parts or not path.parts:
            raise BackupError("Das ZIP enthält einen unsicheren Dateipfad.")
        total += int(member.file_size)
        if total > MAX_UNCOMPRESSED_BYTES:
            raise BackupError("Das entpackte Backup wäre größer als 4 GiB.")
    return members


def inspect_backup(path: Path) -> dict[str, Any]:
    path = Path(path)
    try:
        with zipfile.ZipFile(path, "r") as archive:
            names = {member.filename for member in _validated_members(archive)}
            if "manifest.json" not in names or "data/profiles.json" not in names:
                raise BackupError("Dies ist kein vollständiges Logger-Backup.")
            manifest = json.loads(archive.read("manifest.json").decode("utf-8"))
            if not isinstance(manifest, dict) or manifest.get("format") != BACKUP_FORMAT:
                raise BackupError("Die Backup-Version wird nicht unterstützt.")
            profiles = manifest.get("profiles")
            if not isinstance(profiles, list) or not profiles:
                raise BackupError("Das Backup enthält keine Profile.")
            for profile in profiles:
                profile_id = str(profile.get("id") or "")
                if f"data/profiles/{profile_id}/metadata.db" not in names:
                    raise BackupError(f"Profildatenbank fehlt im Backup: {profile_id}")
            return manifest
    except BackupError:
        raise
    except Exception as exc:
        raise BackupError(f"Backup kann nicht gelesen werden: {exc}") from exc


def restore_backup(path: Path, data_dir: Path, *, log_root: Path | None = None) -> dict[str, Any]:
    """Restore a validated backup into safe application-owned profile paths."""
    path = Path(path).resolve()
    data_dir = Path(data_dir).resolve()
    manifest = inspect_backup(path)
    with tempfile.TemporaryDirectory(prefix="wavelog-restore-") as temporary:
        staging = Path(temporary)
        with zipfile.ZipFile(path, "r") as archive:
            for member in _validated_members(archive):
                if member.is_dir():
                    continue
                target = staging.joinpath(*PurePosixPath(member.filename).parts)
                target.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(member, "r") as source, target.open("wb") as destination:
                    shutil.copyfileobj(source, destination)

        restored_profiles = staging / "data" / "profiles"
        registry_source = staging / "data" / "profiles.json"
        registry = json.loads(registry_source.read_text(encoding="utf-8"))
        profiles_by_id = {
            str(row.get("id") or ""): dict(row)
            for row in registry.get("profiles", []) if isinstance(row, dict)
        }
        restore_stamp = _utc_stamp()
        log_swaps: list[tuple[Path, Path, Path]] = []
        for profile in manifest["profiles"]:
            profile_id = str(profile["id"])
            row = profiles_by_id.get(profile_id, {"id": profile_id, "name": profile.get("name") or "Profil"})
            safe_log_dir = _default_log_dir(row, log_root=log_root).resolve()
            prepared_log_dir = safe_log_dir.with_name(safe_log_dir.name + f".restore-{restore_stamp}")
            old_log_dir = safe_log_dir.with_name(safe_log_dir.name + f".pre-restore-{restore_stamp}")
            if prepared_log_dir.exists() or old_log_dir.exists():
                raise BackupError("Ein temporäres Wiederherstellungsverzeichnis existiert bereits.")
            prepared_log_dir.mkdir(parents=True, exist_ok=False)
            for relative_text in profile.get("log_files") or []:
                relative = PurePosixPath(str(relative_text))
                if relative.is_absolute() or ".." in relative.parts:
                    raise BackupError("Das Backup enthält einen unsicheren ADI-Pfad.")
                source = staging / "logs" / profile_id / Path(*relative.parts)
                if source.is_file():
                    destination = prepared_log_dir / Path(*relative.parts)
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(source, destination)
            _set_setting(restored_profiles / profile_id / "metadata.db", "log_dir", str(safe_log_dir))
            log_swaps.append((safe_log_dir, prepared_log_dir, old_log_dir))

        data_dir.mkdir(parents=True, exist_ok=True)
        new_profiles = data_dir / f"profiles.restore-{_utc_stamp()}"
        shutil.copytree(restored_profiles, new_profiles)
        current_profiles = data_dir / "profiles"
        old_profiles = data_dir / f"profiles.pre-restore-{_utc_stamp()}"
        swapped_logs: list[tuple[Path, Path]] = []
        try:
            if current_profiles.exists():
                current_profiles.replace(old_profiles)
            new_profiles.replace(current_profiles)
            for safe_log_dir, prepared_log_dir, old_log_dir in log_swaps:
                moved_old = False
                try:
                    if safe_log_dir.exists():
                        safe_log_dir.replace(old_log_dir)
                        moved_old = True
                    prepared_log_dir.replace(safe_log_dir)
                except Exception:
                    if moved_old and not safe_log_dir.exists() and old_log_dir.exists():
                        old_log_dir.replace(safe_log_dir)
                    raise
                swapped_logs.append((safe_log_dir, old_log_dir))
        except Exception:
            for safe_log_dir, old_log_dir in reversed(swapped_logs):
                shutil.rmtree(safe_log_dir, ignore_errors=True)
                if old_log_dir.exists():
                    old_log_dir.replace(safe_log_dir)
            if old_profiles.exists():
                shutil.rmtree(current_profiles, ignore_errors=True)
                old_profiles.replace(current_profiles)
            raise
        else:
            shutil.rmtree(old_profiles, ignore_errors=True)
            for _safe_log_dir, old_log_dir in swapped_logs:
                shutil.rmtree(old_log_dir, ignore_errors=True)

        registry_tmp = data_dir / "profiles.json.restore"
        shutil.copy2(registry_source, registry_tmp)
        os.replace(registry_tmp, data_dir / "profiles.json")
        preferences_source = staging / "data" / "ui_preferences.json"
        if preferences_source.is_file():
            preferences_tmp = data_dir / "ui_preferences.json.restore"
            shutil.copy2(preferences_source, preferences_tmp)
            os.replace(preferences_tmp, data_dir / "ui_preferences.json")

    return {
        "profiles": len(manifest["profiles"]),
        "created_utc": str(manifest.get("created_utc") or ""),
        "app_version": str(manifest.get("app_version") or ""),
    }
