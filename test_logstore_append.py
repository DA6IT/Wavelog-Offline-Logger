from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase, main
from unittest.mock import patch

from logger_core import LogStore, adif_header, qso_to_adif_record


def sample(call: str, *, name: str = "Test", local_id: str = "") -> dict:
    return {
        "local_id": local_id,
        "call": call,
        "qso_date": "2026-09-06",
        "time_on": "120000",
        "band": "20m",
        "mode": "SSB",
        "freq": "14.205",
        "rst_sent": "59",
        "rst_rcvd": "59",
        "gridsquare": "JO31EJ",
        "name": name,
        "qth": "Wachtendonk",
        "comment": "",
        "notes": "",
        "pota_ref": "",
        "sota_ref": "",
        "wwff_ref": "",
        "tx_pwr": "100",
        "operator_call": "DA6IT",
        "station_call": "DA6IT",
    }


class LogStoreAppendTests(TestCase):
    def test_second_add_is_append_only(self):
        with TemporaryDirectory() as temp:
            store = LogStore(Path(temp), profile_key="append")
            first = store.add(sample("DL1AAA"))
            self.assertTrue(first["local_id"])

            with patch.object(
                store,
                "_read_file",
                side_effect=AssertionError("append path must not scan the whole ADIF"),
            ), patch.object(
                store,
                "_write_file",
                side_effect=AssertionError("existing ADIF must not be fully rewritten"),
            ):
                second = store.add(sample("PA3BBB", name="Jörg"))

            self.assertTrue(second["local_id"])
            reopened = LogStore(Path(temp), profile_key="append")
            rows = reopened.scan()
            self.assertEqual({row["call"] for row in rows}, {"DL1AAA", "PA3BBB"})
            self.assertEqual(
                next(row for row in rows if row["call"] == "PA3BBB")["name"],
                "Jörg",
            )

    def test_partial_append_journal_is_recovered(self):
        with TemporaryDirectory() as temp:
            store = LogStore(Path(temp), profile_key="recovery")
            store.add(sample("DL1AAA"))
            path = store.canonical_path

            pending = sample(
                "ON4CCC",
                local_id="11111111-2222-3333-4444-555555555555",
            )
            payload = qso_to_adif_record(pending).encode("utf-8")
            original_size = path.stat().st_size
            store._write_append_journal(path, original_size, payload)

            # Simulate a hard crash after only part of the record reached disk.
            with path.open("ab", buffering=0) as handle:
                handle.write(payload[: max(1, len(payload) // 3)])

            reopened = LogStore(Path(temp), profile_key="recovery")
            rows = reopened.scan()
            self.assertEqual({row["call"] for row in rows}, {"DL1AAA", "ON4CCC"})
            self.assertFalse(reopened._append_journal_path(path).exists())

    def test_legacy_latin1_is_converted_once_before_append(self):
        with TemporaryDirectory() as temp:
            store = LogStore(Path(temp), profile_key="latin1")
            path = store.canonical_path

            old = sample(
                "DL1AAA",
                name="Jörg",
                local_id="aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
            )
            legacy = adif_header() + qso_to_adif_record(old)
            path.write_bytes(legacy.encode("iso-8859-1"))

            store = LogStore(Path(temp), profile_key="latin1")
            store.add(sample("PA3BBB"))

            # After the first append the complete canonical log is UTF-8.
            path.read_bytes().decode("utf-8")
            rows = store.scan()
            self.assertEqual({row["call"] for row in rows}, {"DL1AAA", "PA3BBB"})
            self.assertEqual(
                next(row for row in rows if row["call"] == "DL1AAA")["name"],
                "Jörg",
            )


if __name__ == "__main__":
    main()
