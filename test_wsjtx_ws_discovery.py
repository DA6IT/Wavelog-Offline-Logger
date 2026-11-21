from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

import wsjtx_sync
from logger_core import LogStore, MetadataDB, qso_to_adif_record
from wsjtx_sync import (
    WsjtxSyncSettings,
    _decode_qsettings_value,
    classify_wsjtx_dir,
    discover_wsjtx_profiles,
    format_last_result,
    format_wsjtx_result,
    load_last_result,
    read_wsjtx_ini,
    sync_wsjtx_with_local,
    ws_replacement_hint,
)


def _qso(call: str, time_on: str) -> dict:
    return {
        "call": call,
        "qso_date": "2026-11-20",
        "time_on": time_on,
        "freq": "14.074",
        "band": "20m",
        "mode": "FT8",
        "rst_sent": "-10",
        "rst_rcvd": "-12",
        "station_call": "DA6IT",
        "operator_call": "DA6IT",
    }


class ClassifyDirTests(unittest.TestCase):
    def test_ws_and_wsjtx_folder_names(self):
        self.assertEqual(classify_wsjtx_dir("WS"), ("WS", ""))
        self.assertEqual(classify_wsjtx_dir("WS - DA6IT"), ("WS", "DA6IT"))
        self.assertEqual(classify_wsjtx_dir("WS - IC-7300 Shack"), ("WS", "IC-7300 Shack"))
        self.assertEqual(classify_wsjtx_dir("ws - test"), ("WS", "test"))
        self.assertEqual(classify_wsjtx_dir("WSJT-X"), ("WSJT-X", ""))
        self.assertEqual(classify_wsjtx_dir("WSJT-X - IC7300"), ("WSJT-X", "IC7300"))

    def test_unrelated_folders_are_ignored(self):
        for name in ("WSMAP", "WSL", "Wsus", "Windows", "WS-Something", "JTDX", ""):
            self.assertIsNone(classify_wsjtx_dir(name), name)


class QSettingsIniTests(unittest.TestCase):
    def test_value_decoding(self):
        self.assertEqual(_decode_qsettings_value("C:/Users/DanielEschner/x.adi"), "C:/Users/DanielEschner/x.adi")
        self.assertEqual(_decode_qsettings_value('"C:\\\\Logs\\\\a, b.adi"'), "C:\\Logs\\a, b.adi")
        self.assertEqual(_decode_qsettings_value("M\\x00fcnchen"), "München")
        self.assertEqual(_decode_qsettings_value("@Variant(\\0\\0\\0\\x7f)"), "")

    def test_read_ini_flattens_groups(self):
        with tempfile.TemporaryDirectory() as tmp:
            ini = Path(tmp) / "WS.ini"
            ini.write_text(
                "[General]\nfoo=1\n\n[Configuration]\nMyCall=DA6IT\nMyLog=C:/Logs/ws.adi\n\n"
                "[MultiSettings]\nPortable\\Configuration\\MyLog=C:/Logs/portable.adi\n"
                "[MultiSettings%20Extra]\nkey=v\n",
                encoding="utf-8",
            )
            values = read_wsjtx_ini(ini)
        self.assertEqual(values["foo"], "1")
        self.assertEqual(values["Configuration/MyCall"], "DA6IT")
        self.assertEqual(values["Configuration/MyLog"], "C:/Logs/ws.adi")
        self.assertEqual(values["MultiSettings/Portable/Configuration/MyLog"], "C:/Logs/portable.adi")
        self.assertEqual(values["MultiSettings Extra/key"], "v")


class DiscoveryTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name) / "Local"
        self.config = Path(self._tmp.name) / "config"
        self.root.mkdir()
        self.config.mkdir()
        patches = [
            mock.patch.object(wsjtx_sync, "_wsjtx_root", return_value=self.root),
            mock.patch.object(wsjtx_sync, "_wsjtx_config_root", return_value=self.config),
        ]
        for patcher in patches:
            patcher.start()
            self.addCleanup(patcher.stop)
        self.addCleanup(self._tmp.cleanup)

    def _mkdir(self, name: str) -> Path:
        path = self.root / name
        path.mkdir()
        return path

    def test_ws_folders_are_found_first_with_default_log_name(self):
        for name in ("WSJT-X", "WS", "WS - DA6IT", "WSMAP", "WSL", "WSJT-X - IC7300"):
            self._mkdir(name)
        profiles = discover_wsjtx_profiles()
        self.assertEqual(
            [p.directory.name for p in profiles],
            ["WS", "WS - DA6IT", "WSJT-X", "WSJT-X - IC7300"],
        )
        self.assertEqual(profiles[0].name, "WS")
        self.assertEqual(profiles[1].name, "WS · DA6IT")
        self.assertEqual(profiles[1].log_path, self.root / "WS - DA6IT" / "wsjtx_log.adi")

    def test_mylog_and_mycall_from_ini_in_the_data_folder(self):
        ws = self._mkdir("WS - IC7300")
        custom = Path(self._tmp.name) / "Logbuch" / "mein log.adi"
        portable = Path(self._tmp.name) / "Logbuch" / "portabel.adi"
        (ws / "WS - IC7300.ini").write_text(
            "[Configuration]\nMyCall=da6it\nMyLog=" + custom.as_posix() + "\n"
            "[MultiSettings]\nPortabel\\Configuration\\MyLog=" + portable.as_posix() + "\n"
            "Gleich\\Configuration\\MyLog=" + custom.as_posix() + "\n",
            encoding="utf-8",
        )
        profiles = discover_wsjtx_profiles()
        self.assertEqual([p.log_path for p in profiles], [custom, portable])
        self.assertEqual(profiles[0].name, "WS · IC7300 (DA6IT)")
        self.assertEqual(profiles[1].name, "WS · IC7300 (DA6IT) – Portabel")

    def test_ini_in_config_root_is_used_outside_windows(self):
        self._mkdir("WS")
        custom = Path(self._tmp.name) / "elsewhere.adi"
        (self.config / "WS.ini").write_text(
            "[Configuration]\nMyLog=" + custom.as_posix() + "\n", encoding="utf-8"
        )
        self.assertEqual([p.log_path for p in discover_wsjtx_profiles()], [custom])

    def test_empty_mylog_falls_back_to_default(self):
        ws = self._mkdir("WS")
        (ws / "WS.ini").write_text("[Configuration]\nMyLog=\nMyCall=DA6IT\n", encoding="utf-8")
        profiles = discover_wsjtx_profiles()
        self.assertEqual(profiles[0].log_path, ws / "wsjtx_log.adi")
        self.assertEqual(profiles[0].name, "WS (DA6IT)")

    def test_ws_replacement_hint_for_old_wsjtx_selection(self):
        self._mkdir("WS")
        self._mkdir("WS - DA6IT")
        self._mkdir("WSJT-X")
        self._mkdir("WSJT-X - DA6IT")
        self._mkdir("WSJT-X - Other")
        hint = ws_replacement_hint(self.root / "WSJT-X - da6it" / "wsjtx_log.adi")
        assert hint is not None
        self.assertEqual(hint.directory.name, "WS - DA6IT")
        standard = ws_replacement_hint(self.root / "WSJT-X" / "wsjtx_log.adi")
        assert standard is not None
        self.assertEqual(standard.directory.name, "WS")
        self.assertIsNone(ws_replacement_hint(self.root / "WSJT-X - Other" / "wsjtx_log.adi"))
        self.assertIsNone(ws_replacement_hint(self.root / "WS" / "wsjtx_log.adi"))
        self.assertIsNone(ws_replacement_hint(None))


class LastResultTests(unittest.TestCase):
    def test_sync_records_last_result_and_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            db = MetadataDB(root / "metadata.db")
            try:
                db.set_setting("station_call", "DA6IT")
                store = LogStore(root / "adi", "")
                store.add(_qso("DL1AAA", "100000"))
                ws_dir = root / "WS - DA6IT"
                ws_dir.mkdir()
                log = ws_dir / "wsjtx_log.adi"
                log.write_text(qso_to_adif_record(_qso("DL2BBB", "110000")), encoding="utf-8")

                self.assertEqual(load_last_result(db), {})
                self.assertIn("Noch kein Abgleich", format_last_result(load_last_result(db)))

                result = sync_wsjtx_with_local(
                    store, db, WsjtxSyncSettings(log_path=log, sync_on_manual=True)
                )
                self.assertEqual(result.imported_to_local, 1)
                self.assertEqual(result.appended_to_wsjtx, 1)
                self.assertEqual(result.log_path, str(log))

                last = load_last_result(db)
                self.assertEqual(last["imported"], 1)
                self.assertEqual(last["appended"], 1)
                self.assertEqual(last["wsjtx"], 2)
                self.assertEqual(last["path"], str(log))
                text = format_last_result(last)
                self.assertIn("Letzter Abgleich", text)
                self.assertIn("lokal +1", text)
                self.assertIn("Last synchronization", format_last_result(last, "en"))
                self.assertIn(f"Datei: {log}", format_wsjtx_result(result))
                self.assertIn(f"File: {log}", format_wsjtx_result(result, "en"))
            finally:
                db.close()

    def test_corrupt_last_result_is_ignored(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = MetadataDB(Path(tmp) / "metadata.db")
            try:
                db.set_setting("wsjtx_sync_last_result", "{kaputt")
                self.assertEqual(load_last_result(db), {})
                db.set_setting("wsjtx_sync_last_result", "[1, 2]")
                self.assertEqual(load_last_result(db), {})
            finally:
                db.close()


if __name__ == "__main__":
    unittest.main()
