from __future__ import annotations

import io
import json
import unittest
import urllib.error
from unittest.mock import patch

from qsl_client import (
    QSL_API_BASE,
    QSL_CONTRACT,
    QslClient,
    QslClientError,
)


class FakeResponse:
    def __init__(
        self,
        payload: dict,
        *,
        url: str | None = None,
    ):
        self._raw = json.dumps(payload).encode("utf-8")
        self._url = url or QSL_API_BASE + "bootstrap"

    def read(self, size: int = -1) -> bytes:
        if size < 0:
            return self._raw
        return self._raw[:size]

    def geturl(self) -> str:
        return self._url

    def __enter__(self):
        return self

    def __exit__(
        self,
        exc_type,
        exc,
        tb,
    ):
        return False


class QslClientTests(unittest.TestCase):
    def bootstrap_payload(self) -> dict:
        return {
            "contract": QSL_CONTRACT,
            "coreVersion": "1.31.0",
            "apiVersion": "1.0",
            "mailUsage": {
                "hourLimit": 30,
                "hourRemaining": 30,
                "dayLimit": 120,
                "dayRemaining": 120,
                "queued": 0,
                "mailEnabled": True,
            },
        }

    def test_bootstrap_uses_fixed_prod_url_and_bearer(self):
        response = FakeResponse(self.bootstrap_payload())

        with patch(
            "qsl_client.secure_urlopen",
            return_value=response,
        ) as mocked:
            payload = QslClient(
                "secret-key",
                timeout=8,
            ).bootstrap()

        self.assertEqual(payload["contract"], QSL_CONTRACT)

        request = mocked.call_args.args[0]
        headers = {
            key.lower(): value
            for key, value in request.header_items()
        }

        self.assertEqual(
            request.full_url,
            QSL_API_BASE + "bootstrap",
        )
        self.assertEqual(
            headers.get("authorization"),
            "Bearer secret-key",
        )
        self.assertNotIn("x-da6it-qsl-token", headers)

    def test_bootstrap_retries_with_fallback_header_after_auth_error(self):
        error = urllib.error.HTTPError(
            QSL_API_BASE + "bootstrap",
            401,
            "Unauthorized",
            hdrs=None,
            fp=io.BytesIO(
                b'{"message":"Authorization header missing"}'
            ),
        )

        response = FakeResponse(self.bootstrap_payload())

        with patch(
            "qsl_client.secure_urlopen",
            side_effect=[error, response],
        ) as mocked:
            payload = QslClient("secret-key").bootstrap()

        self.assertEqual(payload["contract"], QSL_CONTRACT)
        self.assertEqual(mocked.call_count, 2)

        second_request = mocked.call_args_list[1].args[0]
        headers = {
            key.lower(): value
            for key, value in second_request.header_items()
        }

        self.assertEqual(
            headers.get("x-da6it-qsl-token"),
            "secret-key",
        )
        self.assertNotIn("authorization", headers)

    def test_bootstrap_rejects_wrong_contract(self):
        response = FakeResponse({
            "contract": "something-else",
        })

        with patch(
            "qsl_client.secure_urlopen",
            return_value=response,
        ):
            with self.assertRaisesRegex(
                QslClientError,
                "Contract stimmt nicht",
            ):
                QslClient("secret-key").bootstrap()

    def test_redirected_response_must_stay_on_pinned_api(self):
        response = FakeResponse(
            self.bootstrap_payload(),
            url=(
                "https://example.net/"
                "wp-json/da6it/v1/qsl/client/v1/bootstrap"
            ),
        )

        with patch(
            "qsl_client.secure_urlopen",
            return_value=response,
        ):
            with self.assertRaisesRegex(
                QslClientError,
                "unerwartetes Ziel",
            ):
                QslClient("secret-key").bootstrap()


if __name__ == "__main__":
    unittest.main()
