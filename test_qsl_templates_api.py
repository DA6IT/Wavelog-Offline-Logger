from __future__ import annotations

import json
import unittest
from unittest.mock import patch

from qsl_client import (
    QSL_API_BASE,
    QslClient,
    QslClientError,
)


class FakeResponse:
    def __init__(
        self,
        payload,
        url,
    ):
        self.payload = payload
        self.url = url

    def __enter__(self):
        return self

    def __exit__(
        self,
        exc_type,
        exc,
        tb,
    ):
        return False

    def read(
        self,
        _limit=-1,
    ):
        return json.dumps(
            self.payload
        ).encode("utf-8")

    def geturl(self):
        return self.url


class QslTemplateApiTests(unittest.TestCase):
    def test_templates_uses_fixed_endpoint_and_profile_query(self):
        response = FakeResponse(
            {
                "apiVersion": "1.0",
                "stationProfile": "DA6IT",
                "templates": [],
            },
            (
                QSL_API_BASE
                + "templates?station_profile=DA6IT"
            ),
        )

        with patch(
            "qsl_client.secure_urlopen",
            return_value=response,
        ) as mocked:
            result = QslClient(
                "secret-key"
            ).templates(
                "da6it"
            )

        self.assertEqual(
            result["stationProfile"],
            "DA6IT",
        )

        request = mocked.call_args.args[0]

        self.assertEqual(
            request.get_method(),
            "GET",
        )
        self.assertEqual(
            request.full_url,
            QSL_API_BASE
            + "templates?station_profile=DA6IT",
        )

    def test_templates_requires_station_profile(self):
        with self.assertRaises(
            QslClientError
        ):
            QslClient(
                "secret-key"
            ).templates("")


if __name__ == "__main__":
    unittest.main()
