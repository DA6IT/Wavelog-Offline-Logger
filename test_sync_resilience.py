import threading
import unittest
from email.message import Message
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import urllib.error

from logger_core import MetadataDB, WavelogClient, WavelogError


class PageClient(WavelogClient):
    def __init__(self, pages):
        super().__init__("https://example.test", "token")
        self.pages = pages
        self.calls = 0

    def _request(self, method, resource, ident=None, params=None, payload=None, **kwargs):
        if kwargs.get("cancel_event") and kwargs["cancel_event"].is_set():
            raise WavelogError("Synchronisierung wurde abgebrochen")
        self.calls += 1
        return self.pages[min(self.calls - 1, len(self.pages) - 1)]


class SyncResilienceTests(unittest.TestCase):
    def test_pages_are_bounded_and_streamed(self):
        client = PageClient([
            {"data": [{"id": 1}], "meta": {"has_more": True}},
            {"data": [{"id": 2}], "meta": {"has_more": False}},
        ])
        pages = list(client.iter_qso_pages(station_ids={1}))
        self.assertEqual([[1], [2]], [[row["id"] for row in page] for page in pages])
        self.assertEqual(500, client.MAX_PAGE_SIZE)

    def test_repeated_or_empty_more_page_is_rejected(self):
        for data in ([], [{"id": 1}]):
            client = PageClient([
                {"data": [{"id": 1}], "meta": {"has_more": True}},
                {"data": data, "meta": {"has_more": True}},
            ])
            with self.assertRaises(WavelogError):
                list(client.iter_qso_pages())

    def test_cancel_before_page(self):
        event = threading.Event()
        event.set()
        client = WavelogClient("https://example.test", "token")
        with self.assertRaises(WavelogError):
            list(client.iter_qso_pages(cancel_event=event))

    def test_retry_wait_honours_cancel_without_exposing_request_details(self):
        client = WavelogClient("https://example.test", "token")
        event = threading.Event()
        event.set()
        with self.assertRaisesRegex(WavelogError, "abgebrochen"):
            client._wait_for_retry(30, event, None)

    def test_rate_limit_retry_uses_retry_after(self):
        client = WavelogClient("https://example.test", "token")
        headers = Message()
        headers["Retry-After"] = "0"
        limited = urllib.error.HTTPError(
            "https://example.test/index.php/api/v2/qso", 429, "Too many requests",
            headers, None,
        )
        with patch("logger_core.secure_urlopen", side_effect=[limited, _JsonResponse({"data": []})]) as request:
            self.assertEqual({"data": []}, client._request("GET", "qso"))
        self.assertEqual(2, request.call_count)

    def test_metadata_control_plane_migration_does_not_require_qsos(self):
        with TemporaryDirectory() as directory:
            db = MetadataDB(Path(directory) / "metadata.sqlite")
            db.set_sync_state(7, phase="baseline", checkpoint="page:2")
            self.assertEqual("page:2", db.get_sync_state(7)["checkpoint"])
            db.journal_change("local-1", "update")
            pending = db.pending_journal_changes()
            self.assertEqual("local-1", pending[0]["local_id"])
            db.consume_journal_changes([pending[0]["id"]])
            self.assertEqual([], db.pending_journal_changes())


class _JsonResponse:
    def __init__(self, payload):
        self.headers = {"Content-Length": "12"}
        self.payload = b'{"data": []}'

    def __enter__(self):
        return self

    def __exit__(self, *unused):
        return False

    def read(self, size=-1):
        return self.payload


if __name__ == "__main__":
    unittest.main()
