from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from callbook import (
    CallbookResult,
    normalize_wavelog_result,
    parse_qrz_xml,
)
from logger_core import MetadataDB
from qsl_storage import QslStorage


class QslRecipientHintTests(unittest.TestCase):
    def test_callbook_json_roundtrip_keeps_email(self):
        original = CallbookResult(
            callsign="DL1ABC",
            email="dl1abc@example.org",
            source="QRZ.com",
        )
        loaded = CallbookResult.from_json(original.to_json())
        self.assertEqual(loaded.email, "dl1abc@example.org")
        self.assertEqual(loaded.source, "QRZ.com")

    def test_old_callbook_cache_without_email_stays_compatible(self):
        loaded = CallbookResult.from_json(
            '{"callsign":"DL1ABC","source":"QRZ.com"}'
        )
        self.assertEqual(loaded.email, "")

    def test_qrz_xml_email_is_extracted(self):
        xml = b"""<?xml version="1.0"?>
<QRZDatabase>
  <Callsign>
    <call>DL1ABC</call>
    <email>dl1abc@example.org</email>
    <grid>JO31AA</grid>
  </Callsign>
  <Session>
    <Key>dummy</Key>
  </Session>
</QRZDatabase>
"""
        result, _session = parse_qrz_xml(xml, "DL1ABC")
        self.assertIsNotNone(result)
        self.assertEqual(result.email, "dl1abc@example.org")
        self.assertEqual(result.source, "QRZ.com")

    def test_wavelog_email_is_extracted(self):
        payload = {
            "data": {
                "callsign": "DL1ABC",
                "callbook": {
                    "email": "dl1abc@example.org",
                    "source": "QRZ",
                },
            }
        }
        result = normalize_wavelog_result(payload, "DL1ABC")
        self.assertEqual(result.email, "dl1abc@example.org")
        self.assertEqual(result.source, "Wavelog / QRZ")

    def test_recipient_hint_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = MetadataDB(Path(tmp) / "metadata.db")
            try:
                storage = QslStorage(db)
                storage.set_recipient_hint(
                    "local-1",
                    "dl1abc@example.org",
                    "Wavelog / QRZ",
                )
                hint = storage.get_recipient_hint("local-1")
                self.assertIsNotNone(hint)
                self.assertEqual(hint["email"], "dl1abc@example.org")
                self.assertEqual(hint["source"], "Wavelog / QRZ")
            finally:
                db.close()

    def test_recipient_hint_survives_database_reopen(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "metadata.db"
            db = MetadataDB(path)
            storage = QslStorage(db)
            storage.set_recipient_hint(
                "local-1",
                "dl1abc@example.org",
                "QRZ.com",
            )
            db.close()

            reopened = MetadataDB(path)
            try:
                storage = QslStorage(reopened)
                hint = storage.get_recipient_hint("local-1")
                self.assertIsNotNone(hint)
                self.assertEqual(hint["source"], "QRZ.com")
            finally:
                reopened.close()


if __name__ == "__main__":
    unittest.main()
