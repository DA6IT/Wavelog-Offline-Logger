from __future__ import annotations

import unittest

from qsl_qso import (
    QslQsoError,
    prepare_upsert_batches,
    qso_to_upsert_record,
    upsert_payload,
)


def qso(index: int = 1) -> dict:
    return {
        "local_id": f"local-{index}",
        "call": "dl1abc",
        "qso_date": "2026-09-08",
        "time_on": "18:42:00",
        "band": "20m",
        "freq": "14,074",
        "mode": "ft8",
        "station_call": "da6it",
        "rst_sent": "-08",
        "rst_rcvd": "-12",
    }


class QslQsoTests(unittest.TestCase):
    def test_qso_is_converted_to_documented_adif_names(self):
        prepared = qso_to_upsert_record(qso())

        self.assertEqual(
            prepared.local_id,
            "local-1",
        )

        self.assertEqual(
            prepared.record,
            {
                "CALL": "DL1ABC",
                "QSO_DATE": "20260908",
                "TIME_ON": "184200",
                "BAND": "20m",
                "MODE": "FT8",
                "STATION_CALLSIGN": "DA6IT",
                "FREQ": "14.074",
                "RST_SENT": "-08",
                "RST_RCVD": "-12",
            },
        )

    def test_qsl_designer_and_activity_fields_are_forwarded(self):
        row = qso()
        row.update(
            {
                "gridsquare": "jo30ab",
                "qth": "Köln",
                "name": "Thomas",
                "operator_call": "da6it",
                "my_gridsquare": "jo31ej",
                "my_qth": "Wachtendonk",
                "pota_ref": "de-0123",
                "my_pota_ref": "de-0456",
                "sota_ref": "dm/nw-001",
                "my_sota_ref": "dm/nw-002",
                "wwff_ref": "dlff-0123",
                "my_wwff_ref": "dlff-0456",
                "contest_id": "arrl-field-day",
                "comment": "QSL via DA6IT.de",
                "notes": "Portable test",
                "tx_pwr": "50",
                "stx": "12",
                "srx": "34",
                "stx_string": "001 A",
                "srx_string": "002 B",
            }
        )

        prepared = qso_to_upsert_record(
            row
        )

        expected = {
            "GRIDSQUARE": "JO30AB",
            "QTH": "Köln",
            "NAME": "Thomas",
            "OPERATOR": "DA6IT",
            "MY_GRIDSQUARE": "JO31EJ",
            "MY_CITY": "Wachtendonk",
            "POTA_REF": "DE-0123",
            "MY_POTA_REF": "DE-0456",
            "SOTA_REF": "DM/NW-001",
            "MY_SOTA_REF": "DM/NW-002",
            "WWFF_REF": "DLFF-0123",
            "MY_WWFF_REF": "DLFF-0456",
            "CONTEST_ID": "ARRL-FIELD-DAY",
            "COMMENT": "QSL via DA6IT.de",
            "NOTES": "Portable test",
            "TX_PWR": "50",
            "STX": "12",
            "SRX": "34",
            "STX_STRING": "001 A",
            "SRX_STRING": "002 B",
        }

        for field, value in expected.items():
            self.assertEqual(
                prepared.record[field],
                value,
            )

    def test_empty_optional_qsl_fields_are_omitted(self):
        row = qso()
        row.update(
            {
                "gridsquare": " ",
                "my_gridsquare": "",
                "my_qth": None,
                "comment": "",
                "notes": "   ",
                "tx_pwr": None,
            }
        )

        prepared = qso_to_upsert_record(
            row
        )

        for field in (
            "GRIDSQUARE",
            "MY_GRIDSQUARE",
            "MY_CITY",
            "COMMENT",
            "NOTES",
            "TX_PWR",
        ):
            self.assertNotIn(
                field,
                prepared.record,
            )

    def test_ft8_is_not_rewritten_to_mfsk(self):
        prepared = qso_to_upsert_record(qso())
        self.assertEqual(prepared.record["MODE"], "FT8")
        self.assertNotIn("SUBMODE", prepared.record)

    def test_four_digit_time_gets_seconds(self):
        row = qso()
        row["time_on"] = "1842"

        prepared = qso_to_upsert_record(row)
        self.assertEqual(
            prepared.record["TIME_ON"],
            "184200",
        )

    def test_missing_station_callsign_is_rejected(self):
        row = qso()
        row["station_call"] = ""

        with self.assertRaisesRegex(
            QslQsoError,
            "STATION_CALLSIGN",
        ):
            qso_to_upsert_record(row)

    def test_invalid_date_is_rejected(self):
        row = qso()
        row["qso_date"] = "2026-02-31"

        with self.assertRaisesRegex(
            QslQsoError,
            "QSO_DATE",
        ):
            qso_to_upsert_record(row)

    def test_1001_qsos_are_split_into_two_batches(self):
        batches = prepare_upsert_batches(
            qso(index)
            for index in range(1001)
        )

        self.assertEqual(
            [len(batch) for batch in batches],
            [1000, 1],
        )

    def test_payload_contains_only_server_records(self):
        batch = prepare_upsert_batches(
            [qso()],
        )[0]

        payload = upsert_payload(batch)

        self.assertEqual(
            list(payload),
            ["records"],
        )
        self.assertNotIn(
            "local_id",
            payload["records"][0],
        )


if __name__ == "__main__":
    unittest.main()
