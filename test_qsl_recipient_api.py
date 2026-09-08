from __future__ import annotations

import io
import json
import unittest
from unittest.mock import patch

from qsl_client import (
    QSL_API_BASE,
    QslClient,
    QslClientError,
)


UID = "qso_" + ("a" * 64)


class FakeResponse:
    def __init__(self, payload, url):
        self.payload = payload
        self.url = url

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self, _limit=-1):
        return json.dumps(
            self.payload
        ).encode("utf-8")

    def geturl(self):
        return self.url


class FakeHttpError(Exception):
    pass


class QslRecipientApiTests(unittest.TestCase):
    def test_qrz_posts_only_qso_uid(self):
        response = FakeResponse(
            {
                "qsoUid": UID,
                "email": "",
                "cached": True,
            },
            QSL_API_BASE + "qrz",
        )

        with patch(
            "qsl_client.secure_urlopen",
            return_value=response,
        ) as mocked:
            result = QslClient(
                "secret-key"
            ).qrz_recipient(UID)

        self.assertTrue(
            result["cached"]
        )

        request = mocked.call_args.args[0]
        self.assertEqual(
            request.get_method(),
            "POST",
        )
        self.assertEqual(
            request.full_url,
            QSL_API_BASE + "qrz",
        )

        payload = json.loads(
            request.data.decode("utf-8")
        )

        self.assertEqual(
            payload,
            {"qso_uid": UID},
        )

    def test_qrz_rejects_empty_uid(self):
        with self.assertRaises(
            QslClientError
        ):
            QslClient(
                "secret-key"
            ).qrz_recipient("")

    def test_http_error_code_is_preserved(self):
        error = __import__(
            "urllib.error",
            fromlist=["HTTPError"],
        ).HTTPError(
            QSL_API_BASE + "qrz",
            404,
            "Not Found",
            {},
            io.BytesIO(
                json.dumps(
                    {
                        "code": "qrz_not_found",
                        "message": "Rufzeichen nicht gefunden",
                    }
                ).encode("utf-8")
            ),
        )

        with patch(
            "qsl_client.secure_urlopen",
            side_effect=error,
        ):
            with self.assertRaises(
                QslClientError
            ) as caught:
                QslClient(
                    "secret-key"
                ).qrz_recipient(UID)

        self.assertEqual(
            caught.exception.status_code,
            404,
        )
        self.assertEqual(
            caught.exception.error_code,
            "qrz_not_found",
        )


if __name__ == "__main__":
    unittest.main()
