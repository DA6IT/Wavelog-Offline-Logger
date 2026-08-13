import base64
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from logger_core import LogStore, MetadataDB, SyncEngine, qso_hash

class FakeClient:
    def __init__(self):
        self.rows = {}
        self.n = 100
        self.scopes = ["qso:read", "qso:write", "qso:delete", "station:read", "confirmation:read"]
    def token_info(self):
        return {"owner":"DK0GN", "scopes": list(self.scopes)}
    def stations(self):
        return [{"id":1,"name":"Home","callsign":"DA6IT","gridsquare":"JO31EJ","city":"Wachtendonk","pota":"","sota":"","wwff":"","power":100,"active":True}]
    def _norm(self, p, wid):
        r = dict(p)
        r["id"] = wid
        r["station_id"] = p.get("station_profile_id", 1)
        d = str(p.get("qso_date", "2026-08-12"))[:10]
        t = str(p.get("time_on", "000000")).replace(":", "")
        if len(t) < 6: t = (t + "000000")[:6]
        r["qso_date"] = d + " " + t[:2] + ":" + t[2:4] + ":" + t[4:6]
        return r
    def create_qso(self, p):
        self.n += 1
        r = self._norm(p, self.n)
        self.rows[self.n] = r
        return dict(r)
    def patch_qso(self, wid, p):
        if wid not in self.rows:
            raise RuntimeError("404")
        merged = dict(self.rows[wid])
        merged.update(p)
        r = self._norm(merged, wid)
        self.rows[wid] = r
        return dict(r)
    def delete_qso(self, wid):
        self.rows.pop(wid, None)
    def list_qsos(self, **kw):
        sid = int(kw.get("since_id", 0) or 0)
        out = []
        for k, v in sorted(self.rows.items()):
            if k <= sid:
                continue
            row = dict(v)
            # Simulate Wavelog's compact JSON QSO representation omitting
            # ADIF identity fields; the sync must recover OPERATOR from ADIF.
            row.pop("operator", None)
            row.pop("station_callsign", None)
            out.append(row)
        return out
    def get_qso(self, wid):
        return dict(self.rows[wid])
    def export_qsos_adif(self, **kw):
        out = []
        for wid, r in sorted(self.rows.items()):
            dt = str(r.get("qso_date", ""))
            date = dt[:10].replace("-", "")
            tm = dt.split(" ",1)[1].replace(":", "") if " " in dt else "000000"
            f = {
                "CALL": r.get("call", ""), "QSO_DATE": date, "TIME_ON": tm[:6], "BAND": r.get("band", ""),
                "LOTW_QSL_SENT": "Y", "EQSL_QSL_SENT": "Q", "QRZCOM_QSO_UPLOAD_STATUS": "Y", "DCL_QSL_SENT": "N",
                "OPERATOR": r.get("operator", ""), "STATION_CALLSIGN": "DK0GN",
                "CONTEST_ID": r.get("contest_id", ""), "STX": str(r.get("stx", "")), "SRX": str(r.get("srx", "")),
                "STX_STRING": r.get("stx_string", ""), "SRX_STRING": r.get("srx_string", ""),
            }
            out.append(f)
        return out
    def list_confirmations(self, **kw):
        # Mark the first current QSO as confirmed by LoTW and QRZ.
        if not self.rows:
            return []
        wid = sorted(self.rows)[0]
        r = self.rows[wid]
        return [
            {"qso_id": wid, "callsign": r.get("call"), "type": "LoTW", "confirmation_date":"2026-08-12"},
            {"qso_id": wid, "callsign": r.get("call"), "type": "QRZ.com", "confirmation_date":"2026-08-12"},
        ]


def sample(call="DL1ABC", comment="Hello"):
    return {
        "call":call,"qso_date":"2026-08-12","time_on":"201500","band":"20m","mode":"SSB","freq":"14.205",
        "rst_sent":"59","rst_rcvd":"57","gridsquare":"JO30AA","name":"Test","qth":"Bonn","comment":comment,"notes":"",
        "pota_ref":"","sota_ref":"","wwff_ref":"","tx_pwr":"100","operator_call":"DA6IT","station_call":"DA6IT",
        "my_gridsquare":"JO31EJ","my_qth":"Wachtendonk","my_pota_ref":"","my_sota_ref":"","my_wwff_ref":""
    }

with TemporaryDirectory() as d:
    root = Path(d)
    store = LogStore(root/"logs")
    db = MetadataDB(root/"meta.db")
    fc = FakeClient()
    eng = SyncEngine(store, db, fc)

    # LOCAL ONLY -> WAVELOG
    q = store.add(sample())
    db.ensure_local(q["local_id"], qso_hash(q))
    assert db.get_meta(q["local_id"])["status"] == "local_only"
    s = eng.sync(1, {1:fc.stations()[0]})
    assert s.pushed == 1, s
    m = db.get_meta(q["local_id"])
    wid = m["wavelog_id"]
    assert m["status"] == "synced" and wid == 101
    qsl = db.get_qsl_status(wid)
    assert qsl["lotw"] == "confirmed" and qsl["qrz"] == "confirmed", qsl
    assert qsl["eqsl"] == "pending" and qsl["dcl"] == "none", qsl

    # Remote edit -> local ADI update
    fc.rows[wid]["comment"] = "REMOTE CHANGE"
    s = eng.sync(1, {1:fc.stations()[0]})
    assert s.remote_updated == 1, s
    assert store.find(q["local_id"])["comment"] == "REMOTE CHANGE"

    # Local edit -> patch Wavelog
    q2 = store.find(q["local_id"])
    q2["comment"] = "LOCAL CHANGE"
    q2.pop("_file", None)
    store.update(q["local_id"], q2)
    db.ensure_local(q["local_id"], qso_hash(q2))
    s = eng.sync(1, {1:fc.stations()[0]})
    assert s.patched == 1, s
    assert fc.rows[wid]["comment"] == "LOCAL CHANGE"

    # Remote delete unchanged -> local delete
    fc.rows.pop(wid)
    s = eng.sync(1, {1:fc.stations()[0]})
    assert s.remote_deleted == 1, s
    assert store.find(q["local_id"]) is None
    assert db.get_meta(q["local_id"]) is None

    # New remote -> local pull
    r = fc.create_qso({"station_profile_id":1,"call":"PA3XYZ","qso_date":"2026-08-12","time_on":"203000","band":"40m","mode":"SSB","freq":7100000,"rst_sent":"59","rst_rcvd":"59","operator":"DO5STY"})
    s = eng.sync(1, {1:fc.stations()[0]})
    assert s.pulled == 1, s
    pulled = [x for x in store.scan() if x["call"] == "PA3XYZ"][0]
    assert db.get_meta(pulled["local_id"])["status"] == "synced"
    assert pulled["operator_call"] == "DO5STY", pulled

    # Both sides changed -> conflict, no overwrite
    p = dict(pulled); p["comment"] = "LOCAL CONFLICT"; p.pop("_file", None)
    store.update(pulled["local_id"], p)
    db.ensure_local(pulled["local_id"], qso_hash(p))
    pwid = db.get_meta(pulled["local_id"])["wavelog_id"]
    fc.rows[pwid]["comment"] = "REMOTE CONFLICT"
    s = eng.sync(1, {1:fc.stations()[0]})
    assert s.conflicts == 1, s
    assert db.get_meta(pulled["local_id"])["status"] == "conflict"
    assert store.find(pulled["local_id"])["comment"] == "LOCAL CONFLICT"

    # Remote delete while locally changed -> conflict, preserve local
    # First reset conflict baseline to synchronized remote version manually for test.
    current_remote = fc.rows[pwid]
    from logger_core import remote_hash
    local = store.find(pulled["local_id"])
    db.set_status(pulled["local_id"], "synced", wavelog_id=pwid, last_synced_hash=qso_hash(local), remote_hash=remote_hash(current_remote))
    local2 = dict(local); local2["notes"] = "offline edit"; local2.pop("_file", None)
    store.update(pulled["local_id"], local2)
    db.ensure_local(pulled["local_id"], qso_hash(local2))
    fc.rows.pop(pwid)
    s = eng.sync(1, {1:fc.stations()[0]})
    assert s.conflicts == 1, s
    mm = db.get_meta(pulled["local_id"])
    assert mm["status"] == "conflict" and mm["last_error"] == "remote_deleted"
    assert store.find(pulled["local_id"]) is not None

    db.close()


# Clubstation visibility safety: a member-scoped token must not treat another
# operator's invisible QSO as remotely deleted. With club:read (officer/admin),
# full 1:1 deletion becomes safe again.
with TemporaryDirectory() as d:
    root = Path(d)
    store = LogStore(root/"logs")
    db = MetadataDB(root/"meta.db")
    db.set_setting("operator_call", "DA6IT")
    fc = FakeClient()
    club_station = {"id":2,"name":"L17","callsign":"DK0GN","gridsquare":"JO31","city":"Geldern"}
    q = sample(call="DL9TEST")
    q["operator_call"] = "DO5STY"
    q["station_call"] = "DK0GN"
    q = store.add(q)
    db.ensure_local(q["local_id"], qso_hash(q))
    db.set_status(q["local_id"], "synced", wavelog_id=555, last_synced_hash=qso_hash(q), remote_hash=qso_hash(q))
    eng = SyncEngine(store, db, fc)
    s = eng.sync(2, {2:club_station})
    assert store.find(q["local_id"]) is not None, "member token must preserve other operator QSO"
    fc.scopes.append("club:read")
    s = eng.sync(2, {2:club_station})
    assert store.find(q["local_id"]) is None, "officer/full visibility should mirror remote deletion"
    db.close()

print("SELFTEST OK")

# A QSO that disappears outside the app must be restored from Wavelog. Only an
# explicit tombstone created by the UI may propagate a deletion to Wavelog.
with TemporaryDirectory() as d:
    root = Path(d)
    store = LogStore(root/"logs")
    db = MetadataDB(root/"meta.db")
    fc = FakeClient()
    eng = SyncEngine(store, db, fc)

    q = store.add(sample(call="DL7SAFE", comment="restore me"))
    db.ensure_local(q["local_id"], qso_hash(q))
    assert eng.sync(1, {1:fc.stations()[0]}).pushed == 1
    wid = int(db.get_meta(q["local_id"])["wavelog_id"])

    # Simulate a manually removed or temporarily unreadable ADI record.
    store.delete(q["local_id"])
    db.reconcile_index(store.scan())
    assert db.get_meta(q["local_id"])["status"] != "pending_delete"
    s = eng.sync(1, {1:fc.stations()[0]})
    assert s.remote_updated == 1, s
    assert store.find(q["local_id"]) is not None
    assert wid in fc.rows, "external ADI loss must never delete the remote QSO"

    # The application's confirmed delete action still propagates as intended.
    db.mark_pending_delete(q["local_id"])
    store.delete(q["local_id"])
    s = eng.sync(1, {1:fc.stations()[0]})
    assert s.deleted == 1, s
    assert wid not in fc.rows
    db.close()

print("LOCAL LOSS SAFETY SELFTEST OK")

# Multi-profile isolation / duplication / rename tests.
from logger_core import ProfileManager
with TemporaryDirectory() as d:
    root = Path(d)
    pm = ProfileManager(root, log_root=root/"profile-logs")
    p1 = pm.active_profile()
    db1 = MetadataDB(pm.metadata_path(p1["id"]))
    db1.set_setting("operator_call", "DA6IT")
    db1.set_setting("station_call", "DA6IT")
    db1.set_setting("wavelog_url", "https://example.invalid")
    try:
        db1.set_token("wl2_testtoken")
        if sys.platform == "win32":
            assert db1.get_setting("wavelog_token").startswith("dpapi:"), "Windows token storage must use DPAPI"
    except RuntimeError:
        # Sandboxed Windows test runners may deny CryptProtectData. A visible
        # failure is the secure production behavior. Seed a legacy value only
        # so the profile-duplication/migration test can continue independently.
        assert sys.platform == "win32"
        encoded = base64.b64encode(b"wl2_testtoken").decode("ascii")
        db1.set_setting("wavelog_token", "plain:" + encoded)
    log1 = Path(db1.get_setting("log_dir"))
    db1.close()

    p2 = pm.create("DK0GN", duplicate_from=p1["id"])
    assert p2["id"] != p1["id"]
    db2 = MetadataDB(pm.metadata_path(p2["id"]))
    assert db2.get_setting("operator_call") == "DA6IT"
    assert db2.get_setting("wavelog_url") == "https://example.invalid"
    assert db2.get_token() == "wl2_testtoken"
    log2 = Path(db2.get_setting("log_dir"))
    assert log1 != log2, (log1, log2)
    assert db2.list_meta() == [], "duplicated profile must not inherit sync/QSO metadata"
    db2.set_setting("station_call", "DK0GN")
    db2.close()

    db1 = MetadataDB(pm.metadata_path(p1["id"]))
    assert db1.get_setting("station_call") == "DA6IT", "profile settings must be isolated"
    db1.close()

    pm.rename(p2["id"], "Club DK0GN")
    assert pm.get(p2["id"])["name"] == "Club DK0GN"
    pm.set_active(p2["id"])
    assert pm.active_id == p2["id"]
    pm.set_active(p1["id"])
    # Default profile deletion is strictly local metadata only; ADI stays.
    log2.mkdir(parents=True, exist_ok=True)
    kept_adi = log2 / "DK0GN.2026-08-13.adi"
    kept_adi.write_text("<EOH>\n", encoding="utf-8")
    result = pm.delete(p2["id"])
    assert result["log_dir"] == log2
    assert result["adi_deleted"] == 0
    assert kept_adi.exists(), "default profile deletion must preserve ADI logs"
    assert pm.get(p2["id"]) is None

    # Explicit local ADI deletion removes only .adi files and still has no
    # Wavelog/remote side effects. Non-ADI files are deliberately preserved.
    p3 = pm.create("Fieldday")
    db3 = MetadataDB(pm.metadata_path(p3["id"]))
    log3 = Path(db3.get_setting("log_dir")); db3.close()
    log3.mkdir(parents=True, exist_ok=True)
    (log3 / "DA6IT.2026-08-13.adi").write_text("<EOH>\n", encoding="utf-8")
    (log3 / "README.txt").write_text("keep", encoding="utf-8")
    result = pm.delete(p3["id"], delete_adi=True)
    assert result["adi_deleted"] == 1
    assert not (log3 / "DA6IT.2026-08-13.adi").exists()
    assert (log3 / "README.txt").exists(), "profile deletion must only delete local ADI files"

print("PROFILE SELFTEST OK")

# Legacy v0.9 migration: copy single-profile metadata without touching rollback file.
with TemporaryDirectory() as d:
    root = Path(d)
    legacy = MetadataDB(root / "metadata_v04.db")
    legacy.set_setting("station_call", "DK0GN")
    legacy.set_setting("operator_call", "DA6IT")
    legacy.set_setting("log_dir", str(root / "legacy-logs"))
    legacy.close()
    pm = ProfileManager(root, log_root=root/"profile-logs")
    assert pm.active_profile()["name"] == "DK0GN"
    assert (root / "metadata_v04.db").exists(), "legacy db must remain for rollback"
    migrated = MetadataDB(pm.metadata_path(pm.active_id))
    assert migrated.get_setting("station_call") == "DK0GN"
    assert migrated.get_setting("operator_call") == "DA6IT"
    assert migrated.get_setting("log_dir") == str(root / "legacy-logs")
    migrated.close()

print("MIGRATION SELFTEST OK")


# Contest field round-trip and Wavelog payload test.
from logger_core import qso_to_adif_record, parse_adif, adif_fields_to_qso, local_to_wavelog
contest = sample(call="DL2TEST")
contest.update({"contest_id":"DARC-TEST", "stx":"17", "srx":"42", "stx_string":"L17", "srx_string":"K32", "operator_call":"DA6IT", "station_call":"DK0GN"})
record = qso_to_adif_record({"local_id":"contest-test", **contest})
parsed = parse_adif("<ADIF_VER:5>3.1.7<EOH>\n" + record)[0]
roundtrip = adif_fields_to_qso(parsed)
assert roundtrip["contest_id"] == "DARC-TEST"
assert roundtrip["stx"] == "17" and roundtrip["srx"] == "42"
assert roundtrip["stx_string"] == "L17" and roundtrip["srx_string"] == "K32"
payload = local_to_wavelog(contest, 1, include_operator=True)
assert payload["contest_id"] == "DARC-TEST"
assert payload["stx"] == 17 and payload["srx"] == 42
assert payload["stx_string"] == "L17" and payload["srx_string"] == "K32"
patch_payload = local_to_wavelog(contest, 1)
assert "contest_id" not in patch_payload, "CONTEST_ID is create-only because Wavelog PATCH does not document it"
assert patch_payload["stx"] == 17 and patch_payload["srx"] == 42
print("CONTEST SELFTEST OK")

# v0.11.1 hash-schema migration: v0.10 baselines must not turn into mass
# conflicts merely because contest fields were added to the sync hash.
from logger_core import legacy_qso_hash_v010, legacy_remote_hash_v010, local_to_wavelog
with TemporaryDirectory() as d:
    root = Path(d)
    store = LogStore(root/"logs")
    db = MetadataDB(root/"meta.db")
    fc = FakeClient()
    q = store.add(sample(call="F6FHZ", comment="legacy baseline"))
    remote = fc.create_qso(local_to_wavelog(q, 1, include_operator=True))
    wid = int(remote["id"])
    # Simulate exactly what v0.10 had stored, and v0.11.0 having already
    # marked the row as conflict after changing the hash schema.
    db.ensure_local(q["local_id"], qso_hash(q))
    db.set_status(q["local_id"], "conflict", wavelog_id=wid,
                  last_synced_hash=legacy_qso_hash_v010(q),
                  remote_hash=legacy_remote_hash_v010(remote),
                  error="both_changed")
    eng = SyncEngine(store, db, fc)
    s = eng.sync(1, {1:fc.stations()[0]})
    m = db.get_meta(q["local_id"])
    assert m["status"] == "synced", m
    assert m["last_synced_hash"] == qso_hash(store.find(q["local_id"])), m
    assert s.conflicts == 0, s
    db.close()
print("HASH MIGRATION SELFTEST OK")

# CAT/Hamlib configuration, model parsing and logger-field mapping. These
# tests deliberately need neither a connected radio nor a Hamlib installation.
from cat_control import (
    CatConfig, build_rigctld_args, format_frequency_mhz, map_hamlib_mode,
    parse_rigctld_models,
)

model_output = """\
 Rig #  Mfg                    Model                   Version         Status      Macro
     1  Hamlib                 Dummy                   20240709.0      Stable      RIG_MODEL_DUMMY
  1035  Yaesu                  FT-991A                 20260301.0      Stable      RIG_MODEL_FT991A
  3073  Icom                   IC-7300                 20260101.0      Stable      RIG_MODEL_IC7300
"""
models = parse_rigctld_models(model_output)
assert [m.model_id for m in models] == [1, 1035, 3073], models
assert models[1].manufacturer == "Yaesu" and models[1].model == "FT-991A"
assert models[2].label == "Icom · IC-7300 [ID 3073]"

settings = {
    "cat_enabled": "1", "cat_model_id": "1035", "cat_device": "COM7",
    "cat_baud": "38400", "cat_data_bits": "8", "cat_stop_bits": "1",
    "cat_parity": "None", "cat_handshake": "Hardware",
    "cat_dtr_state": "OFF", "cat_rts_state": "ON",
    "cat_port": "4538", "cat_poll_interval_ms": "750",
}
config = CatConfig.from_getter(lambda key, default="": settings.get(key, default))
config.validate()
assert config.settings() == settings
args = build_rigctld_args(config)
assert args[:6] == ["-m", "1035", "-r", "COM7", "-s", "38400"], args
serial_arg = args[args.index("-C") + 1]
assert "serial_handshake=Hardware" in serial_arg
assert "dtr_state=OFF" in serial_arg and "rts_state=ON" in serial_arg

assert format_frequency_mhz(14_074_000) == "14.074"
assert format_frequency_mhz(145_500_000) == "145.5"
assert map_hamlib_mode("USB", "FT8") == "FT8", "CAT must preserve an explicitly selected digital submode"
assert map_hamlib_mode("USB", "SSB") == "USB"
assert map_hamlib_mode("PKTLSB", "FT4") == "FT4"
assert map_hamlib_mode("CWR", "SSB") == "CW"
assert map_hamlib_mode("RTTYR", "SSB") == "RTTY"
assert map_hamlib_mode("FMN", "SSB") == "FM", "FTX-1 narrow FM must be logged as FM"
assert map_hamlib_mode("NFM", "SSB") == "FM"

print("CAT SELFTEST OK")

# Release discovery must compare project versions correctly and remain silent
# when the computer is offline or GitHub returns unusable data.
import json
import urllib.error
from update_check import find_newer_release, is_prerelease, version_key

assert version_key("v0.12.0-rc2") > version_key("0.12.0-rc1")
assert version_key("0.12.0") > version_key("0.12.0-rc9")
assert version_key("0.12.0-rc1") > version_key("0.12.0-dev2")
assert is_prerelease("0.12.0-rc1") and not is_prerelease("0.12.0")

class FakeResponse:
    def __init__(self, payload):
        self.payload = json.dumps(payload).encode("utf-8")
    def __enter__(self):
        return self
    def __exit__(self, *args):
        return False
    def read(self):
        return self.payload

releases = [
    {"tag_name": "v0.12.0", "name": "Stable", "html_url": "https://example/stable", "draft": False, "prerelease": False},
    {"tag_name": "v0.13.0-rc1", "name": "Preview", "html_url": "https://example/preview", "draft": False, "prerelease": True},
]
stable_update = find_newer_release("0.11.2", opener=lambda *args, **kwargs: FakeResponse(releases))
assert stable_update and stable_update.version == "0.12.0"
preview_update = find_newer_release("0.12.0-rc1", opener=lambda *args, **kwargs: FakeResponse(releases))
assert preview_update and preview_update.version == "0.13.0-rc1"

def offline(*args, **kwargs):
    raise urllib.error.URLError("offline")

assert find_newer_release("0.12.0-rc1", opener=offline) is None
assert find_newer_release("not-a-version", opener=offline) is None

print("UPDATE CHECK SELFTEST OK")
