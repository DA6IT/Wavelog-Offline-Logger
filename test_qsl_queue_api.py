from __future__ import annotations

import json
import unittest
from unittest.mock import patch

from qsl_client import QSL_API_BASE, QslClient


UID_A = "qso_" + ("a" * 64)
UID_B = "qso_" + ("b" * 64)


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


class QslQueueApiTests(unittest.TestCase):
    def test_mail_queue_posts_qso_uids(self):
        response = FakeResponse(
            {
                "jobId": "job123",
                "queued": 2,
            },
            QSL_API_BASE + "mail/queue",
        )

        with patch(
            "qsl_client.secure_urlopen",
            return_value=response,
        ) as mocked:
            result = QslClient("secret-key").mail_queue(
                [UID_A, UID_B]
            )

        self.assertEqual(result["jobId"], "job123")
        request = mocked.call_args.args[0]
        self.assertEqual(request.get_method(), "POST")
        self.assertEqual(
            json.loads(request.data.decode("utf-8")),
            {"qso_uids": [UID_A, UID_B]},
        )

    def test_queue_status_uses_job_filter(self):
        response = FakeResponse(
            {
                "jobId": "job123",
                "summary": {
                    "queued": 1,
                    "sent": 1,
                    "failed": 0,
                    "cancelled": 0,
                    "skipped": 0,
                },
                "items": [],
            },
            QSL_API_BASE + "mail/queue?limit=100&job_id=job123",
        )

        with patch(
            "qsl_client.secure_urlopen",
            return_value=response,
        ) as mocked:
            result = QslClient("secret-key").queue_status(
                job_id="job123",
                limit=100,
            )

        self.assertEqual(result["jobId"], "job123")
        request = mocked.call_args.args[0]
        self.assertEqual(request.get_method(), "GET")
        self.assertEqual(
            request.full_url,
            QSL_API_BASE + "mail/queue?limit=100&job_id=job123",
        )


if __name__ == "__main__":
    unittest.main()
