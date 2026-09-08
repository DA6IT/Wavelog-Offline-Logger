from __future__ import annotations

import json
import unittest
from unittest.mock import patch

from qsl_client import (
    QSL_API_BASE,
    QslClient,
)


UID = "qso_" + ("e" * 64)


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


class QslDeliveryApiTests(unittest.TestCase):
    def test_upload_card_uses_multipart_without_secret_in_body(self):
        response = FakeResponse(
            {
                "qsoUid": UID,
                "status": "generated",
            },
            QSL_API_BASE + "cards",
        )

        png = (
            b"\x89PNG\r\n\x1a\n"
            + b"test-png-payload"
        )

        with patch(
            "qsl_client.secure_urlopen",
            return_value=response,
        ) as mocked:
            result = QslClient(
                "very-secret-key"
            ).upload_card(
                UID,
                10,
                png,
            )

        self.assertEqual(
            result["status"],
            "generated",
        )

        request = mocked.call_args.args[0]

        self.assertEqual(
            request.get_method(),
            "POST",
        )
        self.assertEqual(
            request.full_url,
            QSL_API_BASE + "cards",
        )

        content_type = request.get_header(
            "Content-type"
        ) or ""

        self.assertIn(
            "multipart/form-data",
            content_type,
        )
        self.assertIn(
            b'name="qso_uid"',
            request.data,
        )
        self.assertIn(
            UID.encode("ascii"),
            request.data,
        )
        self.assertIn(
            b'name="template_id"',
            request.data,
        )
        self.assertIn(
            b'name="file"; filename="qsl.png"',
            request.data,
        )
        self.assertIn(
            png,
            request.data,
        )
        self.assertNotIn(
            b"very-secret-key",
            request.data,
        )

    def test_mail_send_posts_only_qso_uid(self):
        response = FakeResponse(
            {
                "qsoUid": UID,
                "sent": True,
                "recipient": "ham@example.org",
            },
            QSL_API_BASE + "mail/send",
        )

        with patch(
            "qsl_client.secure_urlopen",
            return_value=response,
        ) as mocked:
            result = QslClient(
                "secret-key"
            ).mail_send(
                UID
            )

        self.assertTrue(
            result["sent"]
        )

        request = mocked.call_args.args[0]

        self.assertEqual(
            request.get_method(),
            "POST",
        )

        payload = json.loads(
            request.data.decode(
                "utf-8"
            )
        )

        self.assertEqual(
            payload,
            {
                "qso_uid": UID,
            },
        )


if __name__ == "__main__":
    unittest.main()
