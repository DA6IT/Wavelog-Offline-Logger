"""Regression tests for the v0.22.0 performance paths.

They pin the observable behaviour of the optimized code (ADIF parser, LogStore
cache, bulk metadata writes, batched full sync, CountryDB index) and guard
against the former quadratic patterns returning.
"""
from __future__ import annotations

import os
import re
import sqlite3
import time
import uuid
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase, main
from unittest.mock import patch

import logger_core
from logger_core import (
    CountryDB, LogStore, MetadataDB, SyncEngine, adif_header, parse_adif, qso_hash, qso_to_adif_record,
)
from sync_write_buffer import SyncWriteBuffer

ROOT = Path(__file__).resolve().parent


def reference_parse_adif(text: str) -> list[dict[str, str]]:
    """The pre-0.22 implementation (slicing), kept as behavioural oracle."""
    pos = 0
    eoh = re.search(r"<EOH\s*>", text, re.IGNORECASE)
    if eoh:
        pos = eoh.end()
    out = []
    while True:
        eor = re.search(r"<EOR\s*>", text[pos:], re.IGNORECASE)
        if not eor:
            break
        end = pos + eor.start()
        chunk = text[pos:end]
        fields = {}
        p = 0
        while True:
            m = logger_core.FIELD_RE.search(chunk, p)
            if not m:
                break
            start = m.end()
            length = int(m.group(2))
            fields[m.group(1).upper().strip()] = chunk[start:start + length]
            p = start + length
        if fields:
            out.append(fields)
        pos = pos + eor.end()
    return out


def sample(call: str, minute: int = 0, **extra) -> dict:
    row = {
        "call": call, "band": "20m", "mode": "SSB", "freq": "14.250",
        "qso_date": "2026-10-01", "time_on": f"12{minute:02d}00",
        "rst_sent": "59", "rst_rcvd": "59", "station_call": "DA6IT",
    }
    row.update(extra)
    return row


def write_log(store: LogStore, rows: list[dict]) -> None:
    store.canonical_path.write_text(
        adif_header() + "".join(qso_to_adif_record({"local_id": str(uuid.uuid4()), **r}) for r in rows),
        encoding="utf-8",
    )


class ParserTests(TestCase):
    CASES = [
        "",
        "no header no records",
        "<EOH>",
        "<CALL:4>DL1A<EOR>",
        "hdr<eoh>\n<call:4>DL1A<band:3>20m<eor>\n<CALL:5>PA3BB<EOR >",
        # Declared length runs past the record's EOR: value is cut at EOR.
        "<EOH><CALL:20>DL1A<EOR><CALL:4>G4CC<EOR>",
        "<EOH><CALL:4:S>DL1A<NAME:4>Jörg<EOR><EOR><EOR>",
        "<EOH><CALL:4>DL1A<COMMENT:9>a <b> c d<EOR>trailing <CALL:4>XXXX",
        "<EOH>  <Call:4>dl1a  <Eor>  <CALL:0><EOR>",
    ]

    def test_parser_matches_reference_on_edge_cases(self):
        for text in self.CASES:
            with self.subTest(text=text):
                self.assertEqual(parse_adif(text), reference_parse_adif(text))

    def test_parser_matches_reference_on_generated_log(self):
        rows = [sample(f"DL{i}ABC", i % 60, name="Jörg ÄÖÜ", comment="<b>x</b>") for i in range(800)]
        text = adif_header() + "".join(qso_to_adif_record({"local_id": str(i), **r}) for i, r in enumerate(rows))
        self.assertEqual(parse_adif(text), reference_parse_adif(text))

    def test_parser_is_not_quadratic(self):
        record = qso_to_adif_record({"local_id": "x", **sample("DL1ABC")})
        small = adif_header() + record * 2000
        large = adif_header() + record * 8000

        def best_of_three(text):
            timings = []
            for _ in range(3):
                started = time.perf_counter()
                parse_adif(text)
                timings.append(time.perf_counter() - started)
            return min(timings)

        t_small = best_of_three(small)
        t_large = best_of_three(large)
        # 4x data: linear ~4x; the former implementation was ~16x and more.
        self.assertLess(t_large, max(t_small, 0.005) * 10)


class LogStoreCacheTests(TestCase):
    def test_scan_returns_independent_copies(self):
        with TemporaryDirectory() as temp:
            store = LogStore(Path(temp), "cache")
            store.add(sample("DL1AAA"))
            first = store.scan()
            first[0]["call"] = "MUTATED"
            self.assertEqual(store.scan()[0]["call"], "DL1AAA")
            found = store.find(first[0]["local_id"])
            found["call"] = "MUTATED"
            self.assertEqual(store.find(first[0]["local_id"])["call"], "DL1AAA")

    def test_cached_reads_do_not_reparse(self):
        with TemporaryDirectory() as temp:
            store = LogStore(Path(temp), "cache")
            write_log(store, [sample(f"DL{i}AA", i) for i in range(20)])
            rows = store.scan()
            with patch.object(store, "_read_file_strict", side_effect=AssertionError("re-parsed")):
                self.assertEqual(len(store.scan()), 20)
                self.assertIsNotNone(store.find(rows[5]["local_id"]))
                added = store.add(sample("PA3NEW", 59))
                self.assertEqual(len(store.scan()), 21)
                self.assertEqual(store.find(added["local_id"])["call"], "PA3NEW")

    def test_incremental_cache_equals_fresh_parse(self):
        with TemporaryDirectory() as temp:
            store = LogStore(Path(temp), "cache")
            write_log(store, [sample(f"DL{i}AA", i % 3) for i in range(10)])
            store.scan()
            store.add_many([sample("PA3AAA", 1, name="Jörg"), sample("PA3BBB", 1)])
            store.add(sample("G4CCC", 2))
            cached = store.scan()
            fresh = LogStore(Path(temp), "cache").scan()
            self.assertEqual(cached, fresh)

    def test_external_change_is_detected(self):
        with TemporaryDirectory() as temp:
            store = LogStore(Path(temp), "cache")
            write_log(store, [sample("DL1AAA")])
            self.assertEqual([q["call"] for q in store.scan()], ["DL1AAA"])
            # Replacement (restore/other tool) and an in-place rewrite.
            tmp = Path(temp) / "replacement.adi.tmp"
            tmp.write_text(adif_header() + qso_to_adif_record({"local_id": "r1", **sample("G4XYZ")}), encoding="utf-8")
            os.replace(tmp, store.canonical_path)
            self.assertEqual([q["call"] for q in store.scan()], ["G4XYZ"])
            text = store.canonical_path.read_text(encoding="utf-8")
            store.canonical_path.write_text(text + qso_to_adif_record({"local_id": "r2", **sample("F5ABC", 5)}),
                                            encoding="utf-8")
            self.assertEqual(sorted(q["call"] for q in store.scan()), ["F5ABC", "G4XYZ"])

    def test_update_reads_and_writes_once_and_moves_record_to_end(self):
        with TemporaryDirectory() as temp:
            store = LogStore(Path(temp), "cache")
            write_log(store, [sample("DL1AAA", 1), sample("DL2BBB", 2), sample("DL3CCC", 3)])
            target = next(q for q in store.scan() if q["call"] == "DL1AAA")
            original_write = store._write_file
            with patch.object(store, "_write_file", wraps=original_write) as writer:
                store.update(target["local_id"], {**target, "comment": "edited"})
            self.assertEqual(writer.call_count, 1)
            order = [f["CALL"] for f in parse_adif(store.canonical_path.read_text(encoding="utf-8"))]
            self.assertEqual(order, ["DL2BBB", "DL3CCC", "DL1AAA"])
            self.assertEqual(store.find(target["local_id"])["comment"], "edited")
            with self.assertRaises(KeyError):
                store.update("missing", sample("X"))

    def test_upsert_many_matches_sequential_update_and_add(self):
        with TemporaryDirectory() as temp:
            a = LogStore(Path(temp) / "a", "x")
            b = LogStore(Path(temp) / "b", "x")
            base = [{"local_id": f"id{i}", **sample(f"DL{i}AA", i)} for i in range(6)]
            for store in (a, b):
                store.add_many(base)
            changes = [
                {"local_id": "id4", **sample("DL4AA", 4, comment="remote")},
                {"local_id": "new1", **sample("G4NEW", 30)},
                {"local_id": "id1", **sample("DL1AA", 1, comment="remote")},
            ]
            for row in changes:
                if a.find(row["local_id"]):
                    a.update(row["local_id"], row)
                else:
                    a.add(row)
            b.upsert_many(changes)
            self.assertEqual(a.canonical_path.read_bytes().split(b"<EOH>", 1)[1],
                             b.canonical_path.read_bytes().split(b"<EOH>", 1)[1])

    def test_upsert_many_refuses_to_rewrite_unreadable_log(self):
        with TemporaryDirectory() as temp:
            store = LogStore(Path(temp), "x")
            store.add(sample("DL1AAA"))
            store.canonical_path.write_text("<EOH> damaged <EOR>", encoding="utf-8")
            with self.assertRaises(ValueError):
                store.upsert_many([{"local_id": "a", **sample("G4AAA")}])
            self.assertIn("damaged", store.canonical_path.read_text(encoding="utf-8"))

    def test_full_rewrite_is_fsynced_before_replace(self):
        with TemporaryDirectory() as temp:
            store = LogStore(Path(temp), "x")
            write_log(store, [sample("DL1AAA"), sample("DL2BBB", 2)])
            qso = store.scan()[0]
            calls = []
            real_fsync = os.fsync
            real_replace = os.replace

            def fsync(fd):
                calls.append("fsync")
                return real_fsync(fd)

            def replace(src, dst):
                calls.append("replace")
                return real_replace(src, dst)

            with patch.object(logger_core.os, "fsync", side_effect=fsync), \
                    patch.object(logger_core.os, "replace", side_effect=replace):
                store.update(qso["local_id"], {**qso, "comment": "x"})
            self.assertEqual(calls[:2], ["fsync", "replace"])


class MetadataBulkTests(TestCase):
    @staticmethod
    def _tables(db: MetadataDB):
        meta = sorted(
            (r["local_id"], r["status"], r["wavelog_id"], r["local_version"], r["last_synced_hash"])
            for r in db.conn.execute("SELECT * FROM sync_meta")
        )
        journal = sorted(
            (r["local_id"], r["operation"], r["version"]) for r in db.conn.execute("SELECT * FROM sync_change_journal")
        )
        return meta, journal

    def _reference_reconcile(self, db: MetadataDB, qsos: list[dict]) -> None:
        ids = {q["local_id"] for q in qsos}
        for q in qsos:
            db.ensure_local(q["local_id"], qso_hash(q))
        for row in db.list_meta():
            if row["local_id"] not in ids and row["status"] != "pending_delete" and row["wavelog_id"] is None:
                db.delete_meta(row["local_id"])

    def test_bulk_reconcile_equals_per_qso_reconcile(self):
        with TemporaryDirectory() as temp:
            qsos = [{"local_id": f"q{i}", **sample(f"DL{i}AA", i)} for i in range(12)]
            dbs = [MetadataDB(Path(temp) / "a.sqlite"), MetadataDB(Path(temp) / "b.sqlite")]
            for db in dbs:
                for lid, wid in (("q1", 101), ("q2", 102), ("gone-linked", 103)):
                    db.set_status(lid, "synced", wavelog_id=wid, last_synced_hash="old", remote_hash="r")
                db.set_status("q3", "synced", wavelog_id=104, last_synced_hash=qso_hash(qsos[3]), remote_hash="r")
                db.set_status("gone-local", "local_only")
                db.set_status("gone-pending", "pending_delete", wavelog_id=105)
            self._reference_reconcile(dbs[0], qsos)
            dbs[1].reconcile_index(qsos)
            self.assertEqual(self._tables(dbs[0]), self._tables(dbs[1]))
            for db in dbs:
                db.close()

    def test_reconcile_commits_once(self):
        with TemporaryDirectory() as temp:
            db = MetadataDB(Path(temp) / "m.sqlite")
            qsos = [{"local_id": f"q{i}", **sample(f"DL{i}AA", i)} for i in range(50)]
            commits = []
            real_conn = db.conn

            class Conn:
                def __getattr__(self, name):
                    return getattr(real_conn, name)

                def commit(self):
                    commits.append(1)
                    real_conn.commit()

            db.conn = Conn()
            db.reconcile_index(qsos)
            db.conn = real_conn
            self.assertEqual(len(commits), 1)
            self.assertEqual(len(db.list_meta()), 50)
            db.close()

    def test_bulk_keeps_completed_writes_on_error(self):
        with TemporaryDirectory() as temp:
            path = Path(temp) / "m.sqlite"
            db = MetadataDB(path)
            with self.assertRaises(RuntimeError):
                with db.bulk():
                    db.set_status("a", "local_only")
                    raise RuntimeError("boom")
            db.close()
            check = sqlite3.connect(path)
            self.assertEqual(check.execute("SELECT count(*) FROM sync_meta").fetchone()[0], 1)
            check.close()

    def test_qsl_status_map(self):
        with TemporaryDirectory() as temp:
            db = MetadataDB(Path(temp) / "m.sqlite")
            db.set_qsl_status(7, {"lotw": "confirmed"})
            mapping = db.qsl_status_map()
            self.assertEqual(mapping[7], db.get_qsl_status(7))
            db.close()


class CountryIndexTests(TestCase):
    def test_lookup_matches_linear_prefix_scan(self):
        db = CountryDB(ROOT / "cty.dat")
        self.assertTrue(db.loaded)

        def linear(call):
            call = re.sub(r"[^A-Z0-9/]", "", (call or "").strip().upper())
            if not call:
                return None
            if call in db.exact:
                return db.exact[call]
            for prefix, info in db.prefixes:
                if call.startswith(prefix):
                    return info
            return None

        calls = ["", "dl1abc", "DA6IT", "VP8/G4ABC", "3D2AG/P", "ZZ9ZZZ", "KH6XYZ", "R1FJ", "9A1A"]
        calls += [prefix + "1XYZ" for prefix, _ in db.prefixes[::7]]
        calls += list(db.exact)[::25]
        for call in calls:
            with self.subTest(call=call):
                self.assertIs(db.lookup(call), linear(call))


class FakeClient:
    def __init__(self, remote, *, adif=None):
        self.remote = remote
        self.adif = adif or []
        self.calls: dict[str, int] = {}
        self.next_id = 900000

    def _count(self, name):
        self.calls[name] = self.calls.get(name, 0) + 1

    def token_info(self):
        self._count("token")
        return {"scopes": []}

    def list_qsos(self, **_kwargs):
        self._count("list_qsos")
        return [dict(r) for r in self.remote]

    def export_qsos_adif(self, **_kwargs):
        self._count("export_adif")
        return [dict(r) for r in self.adif]

    def list_confirmations(self, **_kwargs):
        self._count("confirmations")
        return []

    def create_qso(self, payload):
        self._count("create")
        self.next_id += 1
        return {"id": self.next_id, **payload}


def remote_row(wid: int, call: str, minute: int, **extra) -> dict:
    row = {
        "id": wid, "call": call, "band": "20m", "mode": "SSB", "freq": 14250000,
        "qso_date": f"2026-10-01 12:{minute:02d}:00", "station_id": 1, "rst_sent": "59", "rst_rcvd": "59",
    }
    row.update(extra)
    return row


class SyncBatchTests(TestCase):
    def _tempdir(self) -> str:
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        return directory.name

    def _engine(self, temp, remote, **kwargs):
        store = LogStore(Path(temp) / "logs")
        db = MetadataDB(Path(temp) / "meta.sqlite")
        client = FakeClient(remote, **kwargs)
        # Windows cannot delete the temp dir while SQLite holds the file.
        self.addCleanup(db.close)
        return store, db, client, SyncEngine(store, db, client)

    def test_initial_import_links_and_pulls_without_quadratic_queries(self):
        temp = self._tempdir()
        remote = [remote_row(i + 1, f"DL{i}ABC", i % 60) for i in range(300)]
        store, db, client, engine = self._engine(temp, remote)
        # Two QSOs were already logged offline (one 30 s apart).
        store.add(sample("DL5ABC", 5))
        store.add({**sample("DL7ABC", 7), "time_on": "120730"})
        with patch.object(db, "get_meta", wraps=db.get_meta) as get_meta:
            summary = engine.sync(1, {1: {"callsign": "DA6IT"}})
        self.assertEqual(summary.linked, 2)
        self.assertEqual(summary.pulled, 298)
        self.assertEqual(summary.errors, 0)
        self.assertLess(get_meta.call_count, 50)
        rows = store.scan()
        self.assertEqual(len(rows), 300)
        linked = {m["wavelog_id"] for m in db.list_meta() if m["status"] == "synced"}
        self.assertEqual(linked, set(range(1, 301)))
        # Downloads are reused for the QSL refresh when nothing was pushed.
        self.assertEqual(client.calls.get("list_qsos"), 1)
        self.assertEqual(client.calls.get("export_adif"), 1)

        again = engine.sync(1, {1: {"callsign": "DA6IT"}})
        self.assertEqual((again.pulled, again.linked, again.pushed, again.errors), (0, 0, 0, 0))
        self.assertEqual(len(store.scan()), 300)

    def test_qsl_refresh_downloads_fresh_view_after_upload(self):
        temp = self._tempdir()
        store, db, client, engine = self._engine(temp, [remote_row(1, "DL1AAA", 1)])
        store.add(sample("G4NEW", 40))
        db.reconcile_index(store.scan())
        summary = engine.sync(1, {1: {"callsign": "DA6IT"}})
        self.assertEqual(summary.pushed, 1)
        self.assertEqual(client.calls.get("list_qsos"), 2)

    def test_remote_change_delete_and_restore_are_batched(self):
        temp = self._tempdir()
        remote = [remote_row(i + 1, f"DL{i}ABC", i) for i in range(6)]
        store, db, client, engine = self._engine(temp, remote)
        engine.sync(1, {1: {"callsign": "DA6IT"}})
        by_wid = {m["wavelog_id"]: m["local_id"] for m in db.list_meta()}
        client.remote[0] = {**client.remote[0], "comment": "changed remotely"}
        del client.remote[1]
        store.delete(by_wid[3])  # ADI record lost outside the app
        with patch.object(store, "_write_file", wraps=store._write_file) as writer:
            summary = engine.sync(1, {1: {"callsign": "DA6IT"}})
        self.assertEqual(summary.remote_updated, 2)
        self.assertEqual(summary.remote_deleted, 1)
        self.assertLessEqual(writer.call_count, 2)
        self.assertEqual(store.find(by_wid[1])["comment"], "changed remotely")
        self.assertIsNone(store.find(by_wid[2]))
        self.assertIsNotNone(store.find(by_wid[3]))
        self.assertEqual(len(store.scan()), 5)

    def test_buffer_turns_concurrent_local_edit_into_conflict(self):
        with TemporaryDirectory() as temp:
            store = LogStore(Path(temp) / "logs")
            db = MetadataDB(Path(temp) / "meta.sqlite")
            q = store.add(sample("DL1AAA"))
            db.set_status(q["local_id"], "synced", wavelog_id=5, last_synced_hash=qso_hash(q), remote_hash="r")
            snapshot = db.version_snapshot()[q["local_id"]]

            class Summary:
                remote_updated = conflicts = errors = remote_deleted = 0

            summary = Summary()
            buffer = SyncWriteBuffer(store, db, qso_hash, summary)
            buffer.upsert(q["local_id"], {**q, "comment": "remote"}, wavelog_id=5, remote_hash="r2",
                          counter="remote_updated", snapshot=snapshot, check_snapshot=True)
            # Local edit arrives before the batch is applied.
            db.ensure_local(q["local_id"], "different-hash")
            buffer.flush()
            self.assertEqual(summary.conflicts, 1)
            self.assertEqual(summary.remote_updated, 0)
            self.assertEqual(store.find(q["local_id"]).get("comment", ""), "")
            self.assertEqual(db.get_meta(q["local_id"])["status"], "conflict")
            db.close()


if __name__ == "__main__":
    main()
