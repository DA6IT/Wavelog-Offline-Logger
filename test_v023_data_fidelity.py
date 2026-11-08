"""Regression tests for v0.23.0: lossless ADIF, merging Wavelog data, safe
remote deletions, midnight linking and the Wavelog API client changes."""
from __future__ import annotations

import json
import urllib.parse
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase, main
from unittest.mock import patch

import logger_core
from logger_core import (
    LogStore, MetadataDB, SyncEngine, WavelogClient, WavelogError, adif_fields_to_qso,
    legacy_qso_hash_v2, local_to_wavelog, merge_qso_records, parse_adif, qso_hash,
    qso_hash_matches, qso_to_adif_record, remote_hash, remote_to_local,
)

ADIF_WITH_EXTRAS = (
    "<ADIF_VER:5>3.1.7<EOH>\n"
    "<APP_AFUTOOLS_ID:3>abc<CALL:5>DL1AB<QSO_DATE:8>20261101<TIME_ON:4>1200<BAND:3>20m<MODE:3>SSB"
    "<DARC_DOK:3>F11<IOTA:6>EU-001<SAT_NAME:6>QO-100<QSL_VIA:4>BURO<LOTW_QSL_RCVD:1>Y<EOR>\n"
    "<APP_AFUTOOLS_ID:3>def<CALL:5>DL2CD<QSO_DATE:8>20261101<TIME_ON:4>1300<BAND:3>40m<MODE:2>CW"
    "<DARC_DOK:3>G22<EOR>\n"
)


def remote_row(wid: int, call: str, minute: int, **extra) -> dict:
    row = {
        "id": wid, "call": call, "band": "20m", "mode": "SSB", "submode": "USB", "freq": 14250000,
        "qso_date": f"2026-10-01 12:{minute:02d}:00", "station_id": 1, "rst_sent": "59", "rst_rcvd": "59",
        "gridsquare": "JO31", "name": "", "comment": "", "notes": "", "qth": "", "prop_mode": "",
        "sat_name": None, "sat_mode": None, "iota": None, "sig": None, "sig_info": None,
        "darc_dok": None, "state": None, "cnty": None, "qsl_via": None,
    }
    row.update(extra)
    return row


class FakeClient:
    def __init__(self, remote):
        self.remote = remote
        self.calls: dict[str, int] = {}
        self.patched: list[tuple[int, dict]] = []
        self.created: list[dict] = []
        self.hidden_from_list: set[int] = set()
        self.next_id = 500

    def _count(self, name):
        self.calls[name] = self.calls.get(name, 0) + 1

    def token_info(self):
        return {"scopes": []}

    def list_qsos(self, **_kwargs):
        self._count("list_qsos")
        return [dict(r) for r in self.remote if r["id"] not in self.hidden_from_list]

    def export_qsos_adif(self, **_kwargs):
        return []

    def list_confirmations(self, **_kwargs):
        return []

    def get_qso(self, wid):
        self._count("get_qso")
        for row in self.remote:
            if row["id"] == int(wid):
                return dict(row)
        raise WavelogError("HTTP 404: not_found: QSO not found", status=404)

    def create_qso(self, payload):
        self.created.append(dict(payload))
        self.next_id += 1
        return {"id": self.next_id, **payload}

    def patch_qso(self, wid, payload):
        self.patched.append((wid, dict(payload)))
        for row in self.remote:
            if row["id"] == wid:
                row.update({k: v for k, v in payload.items() if k != "station_profile_id"})
                return dict(row)
        raise WavelogError("HTTP 404", status=404)

    def delete_qso(self, wid):
        self.remote = [r for r in self.remote if r["id"] != wid]


class Fixture(TestCase):
    def setUp(self):
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.temp = Path(directory.name)

    def engine(self, remote):
        store = LogStore(self.temp / "logs")
        db = MetadataDB(self.temp / "meta.sqlite")
        self.addCleanup(db.close)
        client = FakeClient(remote)
        return store, db, client, SyncEngine(store, db, client)


class LosslessAdifTests(Fixture):
    def test_editing_one_qso_keeps_unknown_fields_of_all_qsos(self):
        store = LogStore(self.temp / "logs")
        store.canonical_path.write_text(ADIF_WITH_EXTRAS, encoding="utf-8")
        store = LogStore(self.temp / "logs")
        q = dict(store.find("def"))
        q["comment"] = "edit"
        store.update("def", q)
        text = store.canonical_path.read_text(encoding="utf-8")
        for fragment in ("<DARC_DOK:3>F11", "<IOTA:6>EU-001", "<SAT_NAME:6>QO-100", "<QSL_VIA:4>BURO",
                         "<LOTW_QSL_RCVD:1>Y", "<DARC_DOK:3>G22", "<COMMENT:4>edit"):
            self.assertIn(fragment, text)

    def test_import_and_delete_keep_unknown_fields(self):
        source = self.temp / "in.adi"
        source.write_text(ADIF_WITH_EXTRAS, encoding="utf-8")
        store = LogStore(self.temp / "logs")
        store.import_adif(source)
        rows = {q["call"]: q for q in store.scan()}
        store.delete(rows["DL2CD"]["local_id"])
        text = store.canonical_path.read_text(encoding="utf-8")
        self.assertIn("<DARC_DOK:3>F11", text)
        self.assertIn("<SAT_NAME:6>QO-100", text)
        self.assertNotIn("DL2CD", text)

    def test_roundtrip_and_header_version(self):
        fields = parse_adif(ADIF_WITH_EXTRAS)[0]
        q = adif_fields_to_qso(fields)
        self.assertEqual(q["adif_extra"]["DARC_DOK"], "F11")
        again = parse_adif(qso_to_adif_record(q))[0]
        self.assertEqual({k: v for k, v in again.items() if k != "TIME_ON"},
                         {k: v for k, v in fields.items() if k != "TIME_ON"})
        self.assertIn("<ADIF_VER:5>3.1.8", logger_core.adif_header())

    def test_merge_semantics(self):
        base = {"call": "DL1AB", "tx_pwr": "100", "adif_extra": {"DARC_DOK": "F11", "IOTA": "EU-001"}, "_file": "x"}
        merged = merge_qso_records(base, {"comment": "c", "adif_extra": {"IOTA": "", "SIG": "WWFF"}})
        self.assertEqual(merged["tx_pwr"], "100")
        self.assertEqual(merged["comment"], "c")
        self.assertEqual(merged["adif_extra"], {"DARC_DOK": "F11", "SIG": "WWFF"})
        self.assertNotIn("_file", merged)


class MappingTests(TestCase):
    def test_remote_to_local_only_maps_present_keys(self):
        q = remote_to_local(remote_row(1, "dl1ab", 5, darc_dok="F11", prop_mode="sat", sat_name="QO-100"))
        self.assertNotIn("tx_pwr", q)
        self.assertNotIn("operator_call", q)
        self.assertEqual(q["prop_mode"], "SAT")
        self.assertEqual(q["adif_extra"]["DARC_DOK"], "F11")
        self.assertEqual(q["adif_extra"]["SAT_NAME"], "QO-100")

    def test_upload_contains_sat_dok_and_end_time(self):
        q = {"call": "DL1AB", "band": "2m", "mode": "FM", "qso_date": "2026-11-01", "time_on": "235900",
             "time_off": "000300", "prop_mode": "sat",
             "adif_extra": {"SAT_NAME": "SO-50", "DARC_DOK": "F11", "LOTW_QSL_RCVD": "Y"}}
        payload = local_to_wavelog(q, 7)
        self.assertEqual(payload["prop_mode"], "SAT")
        self.assertEqual(payload["sat_name"], "SO-50")
        self.assertEqual(payload["darc_dok"], "F11")
        self.assertEqual(payload["time_off"], "000300")
        self.assertNotIn("lotw_qsl_rcvd", payload)

    def test_new_jsonfields_do_not_change_remote_hash_of_old_schema(self):
        row = remote_row(1, "DL1AB", 5)
        old = legacy_qso_hash_v2(remote_to_local(row))
        row_325 = {**row, "qsl_sent": "N", "qsl_sent_via": None, "email": "", "qslsdate": None}
        self.assertTrue(qso_hash_matches(old, remote_to_local(row_325)))
        self.assertEqual(remote_hash(row), remote_hash(row_325))


class SyncSafetyTests(Fixture):
    def test_remote_change_merges_and_keeps_local_only_fields(self):
        store, db, client, engine = self.engine([remote_row(1, "DL1AB", 5)])
        local = store.add({"call": "DL1AB", "band": "20m", "mode": "USB", "freq": "14.25", "qso_date": "2026-10-01",
                           "time_on": "120500", "tx_pwr": "100", "my_iota": "EU-005",
                           "adif_extra": {"MY_ANTENNA": "Dipol"}})
        db.ensure_local(local["local_id"], qso_hash(local))
        summary = engine.sync(1, {})
        self.assertEqual(summary.linked, 1)
        client.remote[0].update(comment="remote edit", darc_dok="F11")
        summary = engine.sync(1, {})
        self.assertEqual(summary.remote_updated, 1, summary)
        q = store.find(local["local_id"])
        self.assertEqual(q["comment"], "remote edit")
        self.assertEqual(q["tx_pwr"], "100")
        self.assertEqual(q["my_iota"], "EU-005")
        self.assertEqual(q["adif_extra"]["MY_ANTENNA"], "Dipol")
        self.assertEqual(q["adif_extra"]["DARC_DOK"], "F11")
        again = engine.sync(1, {})
        self.assertEqual((again.remote_updated, again.patched, again.conflicts), (0, 0, 0))

    def test_local_dok_edit_is_patched_to_wavelog(self):
        store, db, client, engine = self.engine([remote_row(1, "DL1AB", 5)])
        engine.sync(1, {})
        lid = db.list_meta()[0]["local_id"]
        q = dict(store.find(lid))
        q["adif_extra"] = {**q.get("adif_extra", {}), "DARC_DOK": "B01"}
        q.pop("_file", None)
        store.update(lid, q)
        db.ensure_local(lid, qso_hash(q))
        summary = engine.sync(1, {})
        self.assertEqual(summary.patched, 1, summary)
        self.assertEqual(client.patched[-1][1]["darc_dok"], "B01")

    def test_v022_baseline_is_not_a_change_and_heals_lost_fields(self):
        store, db, client, engine = self.engine([remote_row(1, "DL1AB", 5, darc_dok="F11", iota="EU-001")])
        # State as left behind by v0.22: the local copy lost DOK/IOTA and the
        # baselines use the v2 hash schema.
        q = store.add({"call": "DL1AB", "band": "20m", "mode": "USB", "freq": "14.25", "qso_date": "2026-10-01",
                       "time_on": "120500", "rst_sent": "59", "rst_rcvd": "59", "gridsquare": "JO31",
                       "station_call": "DA6IT"})
        db.set_status(q["local_id"], "synced", wavelog_id=1, last_synced_hash=legacy_qso_hash_v2(q),
                      remote_hash=legacy_qso_hash_v2(remote_to_local(client.remote[0], {})))
        summary = engine.sync(1, {})
        self.assertEqual((summary.patched, summary.remote_updated, summary.conflicts), (0, 0, 0), summary)
        self.assertEqual(summary.fields_restored, 1)
        healed = store.find(q["local_id"])
        self.assertEqual(healed["adif_extra"], {"DARC_DOK": "F11", "IOTA": "EU-001"})
        again = engine.sync(1, {})
        self.assertEqual((again.fields_restored, again.patched, again.remote_updated), (0, 0, 0))

    def test_qso_missing_from_list_but_present_is_kept(self):
        store, db, client, engine = self.engine([remote_row(1, "DL1AB", 5), remote_row(2, "DL2CD", 6)])
        engine.sync(1, {})
        client.hidden_from_list = {2}  # paged list skipped it
        summary = engine.sync(1, {})
        self.assertEqual(summary.remote_deleted, 0)
        self.assertEqual(summary.deletion_false_alarms, 1)
        self.assertEqual(len(store.scan()), 2)

    def test_confirmed_deletion_and_mass_delete_guard(self):
        remote = [remote_row(i, f"DL{i}AB", i) for i in range(1, 31)]
        store, db, client, engine = self.engine(remote)
        engine.sync(1, {})
        client.remote = client.remote[:2]  # 28 of 30 deleted in Wavelog?
        summary = engine.sync(1, {})
        self.assertEqual(summary.deletions_withheld, 28)
        self.assertEqual(summary.remote_deleted, 0)
        self.assertEqual(len(store.scan()), 30)
        summary = engine.sync(1, {}, allow_mass_delete=True)
        self.assertEqual(summary.remote_deleted, 28)
        self.assertEqual(len(store.scan()), 2)

    def test_single_confirmed_deletion_still_applies(self):
        store, db, client, engine = self.engine([remote_row(1, "DL1AB", 5), remote_row(2, "DL2CD", 6)])
        engine.sync(1, {})
        client.remote = client.remote[:1]
        summary = engine.sync(1, {})
        self.assertEqual(summary.remote_deleted, 1)
        self.assertEqual(client.calls.get("get_qso"), 1)

    def test_unconfirmed_deletion_is_skipped(self):
        store, db, client, engine = self.engine([remote_row(1, "DL1AB", 5), remote_row(2, "DL2CD", 6)])
        engine.sync(1, {})
        client.remote = client.remote[:1]
        with patch.object(client, "get_qso", side_effect=WavelogError("HTTP 502", status=502)):
            summary = engine.sync(1, {})
        self.assertEqual(summary.remote_deleted, 0)
        self.assertEqual(len(store.scan()), 2)

    def test_link_across_midnight(self):
        store, db, client, engine = self.engine([remote_row(1, "DL1AB", 0, qso_date="2026-10-02 00:00:20")])
        local = store.add({"call": "DL1AB", "band": "20m", "mode": "USB", "qso_date": "2026-10-01",
                           "time_on": "235950"})
        db.ensure_local(local["local_id"], qso_hash(local))
        summary = engine.sync(1, {})
        self.assertEqual((summary.linked, summary.pulled), (1, 0), summary)
        self.assertEqual(len(store.scan()), 1)


class ClientTests(TestCase):
    def _capture(self, responses):
        requests = []

        class Resp:
            def __init__(self, body):
                self.body = json.dumps(body).encode()
                self.headers = {}

            def read(self, _n=-1):
                return self.body

            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

        def fake(req, timeout=15):
            requests.append(req)
            return Resp(responses.pop(0))

        return requests, fake

    def test_sends_x_api_key_fallback(self):
        requests, fake = self._capture([{"data": {"scopes": ["qso:read"]}}])
        with patch.object(logger_core, "secure_urlopen", fake):
            WavelogClient("https://log.example.org/index.php", "wl2_test").token_info()
        req = requests[0]
        self.assertEqual(req.get_header("X-api-key"), "wl2_test")
        self.assertEqual(req.get_header("Authorization"), "Bearer wl2_test")
        self.assertTrue(req.full_url.startswith("https://log.example.org/index.php/api/v2/token"))

    def test_adif_export_pages_by_since_id(self):
        page1 = {"data": {"adif": "<EOH><CALL:4>AA1A<EOR>", "lastfetchedid": 10}, "meta": {"has_more": True}}
        page2 = {"data": {"adif": "<EOH><CALL:4>BB2B<EOR>", "lastfetchedid": 20}, "meta": {"has_more": False}}
        requests, fake = self._capture([page1, page2])
        with patch.object(logger_core, "secure_urlopen", fake):
            rows = WavelogClient("https://log.example.org", "wl2_x").export_qsos_adif(station_ids=[1])
        self.assertEqual([r["CALL"] for r in rows], ["AA1A", "BB2B"])
        second = urllib.parse.parse_qs(urllib.parse.urlsplit(requests[1].full_url).query)
        self.assertEqual(second["since_id"], ["10"])
        self.assertEqual(second["page"], ["1"])

    def test_adif_export_without_progress_fails(self):
        stuck = {"data": {"adif": "<EOH><CALL:4>AA1A<EOR>", "lastfetchedid": 0}, "meta": {"has_more": True}}
        requests, fake = self._capture([stuck, stuck])
        with patch.object(logger_core, "secure_urlopen", fake):
            with self.assertRaises(WavelogError):
                WavelogClient("https://log.example.org", "wl2_x").export_qsos_adif()

    def test_lookup_passes_qso_date(self):
        requests, fake = self._capture([{"data": {}}])
        with patch.object(logger_core, "secure_urlopen", fake):
            WavelogClient("https://log.example.org", "wl2_x").lookup_callsign("dl1ab", date="2026-11-01")
        query = urllib.parse.parse_qs(urllib.parse.urlsplit(requests[0].full_url).query)
        self.assertEqual(query["date"], ["2026-11-01"])


if __name__ == "__main__":
    main()
