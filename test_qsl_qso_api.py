from __future__ import annotations

import json
import unittest
from unittest.mock import patch

from qsl_client import (
    MAX_QSO_BATCH,
    QSL_API_BASE,
    QslClient,
    QslClientError,
)


class FakeResponse:
    def __init__(
        self,
        payload: dict,
        *,
        url: str,
    ):
        self._raw = json.dumps(payload).encode("utf-8")
        self._url = url

    def read(self, size: int = -1) -> bytes:
        if size < 0:
            return self._raw
        return self._raw[:size]

    def geturl(self) -> str:
        return self._url

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class QslQsoApiTests(unittest.TestCase):
    def test_upsert_posts_documented_records_envelope(self):
        response = FakeResponse(
            {"ok": True},
            url=QSL_API_BASE + "qsos/upsert",
        )

        with patch(
            "qsl_client.secure_urlopen",
            return_value=response,
        ) as mocked:
            result = QslClient(
                "secret-key"
            ).upsert_qsos([
                {
                    "CALL": "DL1ABC",
                    "QSO_DATE": "20260908",
                    "TIME_ON": "184200",
                    "BAND": "20m",
                    "MODE": "FT8",
                    "STATION_CALLSIGN": "DA6IT",
                }
            ])

        self.assertTrue(result["ok"])

        request = mocked.call_args.args[0]
        self.assertEqual(request.get_method(), "POST")
        self.assertEqual(
            request.full_url,
            QSL_API_BASE + "qsos/upsert",
        )

        payload = json.loads(
            request.data.decode("utf-8")
        )

        self.assertEqual(
            list(payload),
            ["records"],
        )
        self.assertEqual(
            payload["records"][0]["MODE"],
            "FT8",
        )

    def test_status_posts_documented_qso_uids_envelope(self):
        uid = "qso_" + ("a" * 64)

        response = FakeResponse(
            {"states": {}},
            url=QSL_API_BASE + "qsos/status",
        )

        with patch(
            "qsl_client.secure_urlopen",
            return_value=response,
        ) as mocked:
            QslClient(
                "secret-key"
            ).qso_status([uid])

        request = mocked.call_args.args[0]
        payload = json.loads(
            request.data.decode("utf-8")
        )

        self.assertEqual(
            payload,
            {"qso_uids": [uid]},
        )

    def test_upsert_rejects_more_than_server_batch_limit(self):
        records = [{} for _ in range(MAX_QSO_BATCH + 1)]

        with self.assertRaisesRegex(
            QslClientError,
            "maximal 1000",
        ):
            QslClient(
                "secret-key"
            ).upsert_qsos(records)

    def test_status_rejects_more_than_server_batch_limit(self):
        values = [
            f"qso_{index:064x}"
            for index in range(MAX_QSO_BATCH + 1)
        ]

        with self.assertRaisesRegex(
            QslClientError,
            "maximal 1000",
        ):
            QslClient(
                "secret-key"
            ).qso_status(values)

    def test_list_qsos_uses_supported_filters(self):
        response = FakeResponse(
            {"rows": []},
            url=(
                QSL_API_BASE
                + "qsos?page=2&per_page=500&search=DL1ABC"
                + "&band=20m&mode=FT8&date_from=20260901"
                + "&date_to=20260908&recent=1"
            ),
        )

        with patch(
            "qsl_client.secure_urlopen",
            return_value=response,
        ) as mocked:
            QslClient(
                "secret-key"
            ).list_qsos(
                page=2,
                per_page=999,
                search="DL1ABC",
                band="20m",
                mode="FT8",
                date_from="20260901",
                date_to="20260908",
                recent=1,
            )

        request = mocked.call_args.args[0]
        self.assertEqual(request.get_method(), "GET")

        self.assertIn(
            "page=2",
            request.full_url,
        )
        self.assertIn(
            "per_page=500",
            request.full_url,
        )
        self.assertIn(
            "search=DL1ABC",
            request.full_url,
        )


if __name__ == "__main__":
    unittest.main()
