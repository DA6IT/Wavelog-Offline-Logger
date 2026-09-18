import threading
import unittest
import sqlite3
from email.message import Message
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import urllib.error

from logger_core import LogStore, MetadataDB, SyncEngine, WavelogClient, WavelogError


class PageClient(WavelogClient):
    def __init__(self, pages):
        super().__init__("https://example.test", "token")
        self.pages = pages
        self.calls = 0
        self.params = []

    def _request(self, method, resource, ident=None, params=None, payload=None, **kwargs):
        if kwargs.get("cancel_event") and kwargs["cancel_event"].is_set():
            raise WavelogError("Synchronisierung wurde abgebrochen")
        self.calls += 1
        self.params.append(params or {})
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

    def test_page_limit_bounds_unique_broken_pagination_and_resume_uses_checkpoint(self):
        client = PageClient([
            {"data": [{"id": 1}], "meta": {"has_more": True}},
            {"data": [{"id": 2}], "meta": {"has_more": True}},
            {"data": [{"id": 3}], "meta": {"has_more": True}},
        ])
        with self.assertRaisesRegex(WavelogError, "Seitenlimit"):
            list(client.iter_qso_pages(start_page=3, max_pages=2))
        self.assertEqual(2, client.calls)
        self.assertEqual([3, 4], [params["page"] for params in client.params])

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

    def test_control_plane_upgrade_is_idempotent_and_versions_are_journaled(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "metadata.sqlite"
            legacy = sqlite3.connect(path)
            legacy.executescript("""
                CREATE TABLE sync_meta (
                    local_id TEXT PRIMARY KEY, wavelog_id INTEGER UNIQUE,
                    status TEXT NOT NULL DEFAULT 'pending', last_synced_hash TEXT,
                    remote_hash TEXT, last_error TEXT, created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL, last_synced_at TEXT
                );
                CREATE TABLE sync_state (
                    station_id INTEGER NOT NULL, profile_key TEXT NOT NULL DEFAULT '',
                    phase TEXT NOT NULL DEFAULT 'idle', checkpoint TEXT NOT NULL DEFAULT '',
                    baseline_watermark TEXT NOT NULL DEFAULT '', qsl_watermark TEXT NOT NULL DEFAULT '',
                    updated_at TEXT NOT NULL, PRIMARY KEY(station_id, profile_key)
                );
            """)
            legacy.commit(); legacy.close()
            db = MetadataDB(path)
            db.set_sync_state(3, remote_watermark="remote:9", qsl_watermark="qsl:2")
            self.assertEqual("remote:9", db.get_sync_state(3)["remote_watermark"])
            db.ensure_local("local-1", "hash-a")
            snapshot = db.version_snapshot(["local-1"])
            self.assertEqual(1, snapshot["local-1"])
            self.assertFalse(db.unchanged_since("local-1", 2))
            self.assertEqual("create", db.pending_journal_changes()[0]["operation"])
            self.assertEqual(1, db.migration_summary()["sync_meta_rows"])
            db.close()
            reopened = MetadataDB(path)
            self.assertEqual("remote:9", reopened.get_sync_state(3)["remote_watermark"])
            meta = reopened.get_meta("local-1")
            self.assertIsNotNone(meta)
            self.assertEqual(1, (meta or {})["local_version"])

    def test_cancelled_sync_preserves_persisted_resume_state_and_journal(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            db = MetadataDB(root / "metadata.sqlite")
            db.set_sync_state(1, phase="baseline", checkpoint="page:7")
            db.journal_change("local-1", "change", version=2)
            cancelled = threading.Event()
            cancelled.set()
            engine = SyncEngine(LogStore(root / "logs"), db, PageClient([]))
            with self.assertRaisesRegex(WavelogError, "abgebrochen"):
                engine.sync(1, cancel_event=cancelled)
            self.assertEqual("page:7", db.get_sync_state(1)["checkpoint"])
            self.assertEqual(1, len(db.pending_journal_changes()))


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
