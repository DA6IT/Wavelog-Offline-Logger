from __future__ import annotations

import json
import unittest
from unittest.mock import patch

from qsl_client import QSL_API_BASE, QslClient


class FakeResponse:
    def __init__(self, payload, url):
        self.payload = payload
        self.url = url

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self, _limit=-1):
        return json.dumps(self.payload).encode("utf-8")

    def geturl(self):
        return self.url


class QslControlCopyApiTests(unittest.TestCase):
    def test_get_control_copy_uses_fixed_endpoint(self):
        response = FakeResponse(
            {
                "enabled": False,
                "email": "",
                "verified": False,
                "pending": False,
                "mode": "bcc",
            },
            QSL_API_BASE + "mail/copy",
        )

        with patch(
            "qsl_client.secure_urlopen",
            return_value=response,
        ) as mocked:
            result = QslClient("secret-key").control_copy()

        self.assertFalse(result["enabled"])
        request = mocked.call_args.args[0]
        self.assertEqual(request.get_method(), "GET")
        self.assertEqual(request.full_url, QSL_API_BASE + "mail/copy")

    def test_set_control_copy_posts_only_setting(self):
        response = FakeResponse(
            {
                "enabled": True,
                "email": "operator@example.org",
                "verified": True,
                "pending": False,
                "mode": "bcc",
            },
            QSL_API_BASE + "mail/copy",
        )

        with patch(
            "qsl_client.secure_urlopen",
            return_value=response,
        ) as mocked:
            result = QslClient("secret-key").set_control_copy(
                True,
                "operator@example.org",
            )

        self.assertTrue(result["enabled"])
        request = mocked.call_args.args[0]
        self.assertEqual(request.get_method(), "POST")
        payload = json.loads(request.data.decode("utf-8"))
        self.assertEqual(
            payload,
            {
                "enabled": True,
                "email": "operator@example.org",
            },
        )
        self.assertNotIn(b"secret-key", request.data)


if __name__ == "__main__":
    unittest.main()
