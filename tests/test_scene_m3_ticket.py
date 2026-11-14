"""Owner-scoped scene ticket validation — all tests offline, no model calls."""
import copy
import datetime as dt
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from tools.scene_factory import SceneBlocked, digest, keys
from tools.scene_m3_ticket import verify, _stage_issues, _history_digest, OWNER_PHRASE

ROOT = Path(__file__).resolve().parents[1]


class M3SceneTicketTests(unittest.TestCase):
    def setUp(self):
        self.m = json.loads((ROOT/"episodes/berakhot-01-01/scene-prologue-v02.json").read_text())
        self.b = json.loads((ROOT/self.m["bible"]["path"]).read_text())
        self.now = dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
        self.history = {"attempts": [{"request_id": "historical-"+str(i)} for i in range(6)]}
        self.policy = {
            "privacy_verified": True, "free_hard_cap_verified": True,
            "quota_verified": True, "verified_at": self.now.isoformat(),
        }
        self.shots = ["EP-P01", "EP-P02"]
        self.ticket = {
            "version": 1, "request_id": "a"*32, "scene_id": self.m["id"],
            "script_sha256": self.m["script"]["sha256"],
            "bible_sha256": digest(self.b), "shot_ids": self.shots,
            "asset_keys": {x: keys(self.m, self.b)["asset_keys"][x] for x in self.shots},
            "issued_at": self.now.isoformat(), "approval": OWNER_PHRASE,
            "max_attempts": 2, "max_charge_usd": 0,
            "history_sha256": _history_digest(self.history),
            "historical_attempts": 6, "total_attempt_limit": 8,
        }

    def event(self):
        return {
            "action": "edited",
            "repository": {"full_name": "barkinam21-pixel/project-mishna",
                           "owner": {"login": "barkinam21-pixel"}},
            "sender": {"login": "barkinam21-pixel"},
            "issue": {"number": 54, "state": "open",
                      "body": "```mishnah-scene-request\n"+
                              json.dumps(self.ticket)+"\n```"},
            "changes": {"body": {"from": "old issue body"}},
        }

    def reviewed_stage_fixture(self):
        # Fake stage approvals only in local test memory; never production.
        self.m["script"].update(approved=True, reviewer="UNIT_TEST_ONLY")
        self.m["bible"]["sha256"] = digest(self.b)
        for decision in self.m["decisions"]:
            decision.update(approved=True, reviewer="UNIT_TEST_ONLY")
        for s in self.m["shots"]:
            s["pre_state"] = "DAWN_BEFORE"
            s["post_state"] = "DAWN_BEFORE"
            s["exception"] = None
            s["source"]["verified"] = True
            s["asset"].update(id=None, origin="missing", state=None,
                              accepted=False, path=None, sha256=None)
        self.ticket["asset_keys"] = {
            x: keys(self.m,self.b)["asset_keys"][x] for x in self.shots
        }
        blocked, waived = _stage_issues(self.m, self.b, ROOT)
        self.assertEqual(blocked, [], blocked)
        self.assertTrue(waived)

    def verify(self, event=None):
        return verify(event or self.event(),self.policy,self.history,
                      self.m,self.b,ROOT,now=self.now)

    def test_current_prologue_stays_blocked_not_assumed_approved(self):
        out = self.verify()
        self.assertEqual(out["status"], "BLOCKED")
        self.assertIn("ASSET_CONTINUITY_TIME_OF_DAY:EP-P07", out["issues"])
        self.assertEqual(out["external_inference_requests"], 0)
        self.assertFalse(out["live_dispatch_enabled"])

    def test_verified_test_stage_returns_no_live_ticket(self):
        self.reviewed_stage_fixture()
        out = self.verify()
        self.assertEqual(out["status"], "OFFLINE_TICKET_CHECKED_NO_LIVE_DISPATCH")
        self.assertEqual(out["shot_ids"],self.shots)
        self.assertEqual(out["max_attempts"],2)
        self.assertFalse(out["live_dispatch_enabled"])

    def test_owner_event_is_required(self):
        self.reviewed_stage_fixture()
        event=self.event();event["sender"]["login"]="attacker"
        with self.assertRaisesRegex(SceneBlocked,"TRUSTED_OWNER"):
            self.verify(event)
        event=self.event();event["issue"]["number"]=77
        with self.assertRaisesRegex(SceneBlocked,"OWNER_ISSUE"):
            self.verify(event)

    def test_replay_event_rejected(self):
        self.reviewed_stage_fixture()
        event=self.event();event["changes"]["body"]["from"]=self.ticket["request_id"]
        with self.assertRaisesRegex(SceneBlocked,"FRESH_OWNER_EDIT"):
            self.verify(event)

    def test_changed_scene_or_asset_keys_are_rejected(self):
        self.reviewed_stage_fixture()
        self.ticket["asset_keys"][self.shots[0]]="0"*64
        with self.assertRaisesRegex(SceneBlocked,"IMAGE_SPEC_CHANGED"):
            self.verify()
        self.ticket["asset_keys"]={x:keys(self.m,self.b)["asset_keys"][x] for x in self.shots}
        self.ticket["script_sha256"]="0"*64
        with self.assertRaisesRegex(SceneBlocked,"SOURCE_OR_BIBLE"):
            self.verify()

    def test_shot_cap_and_charge_are_strict(self):
        self.reviewed_stage_fixture()
        self.ticket["max_charge_usd"]=1
        with self.assertRaisesRegex(SceneBlocked,"ZERO_CHARGE"):
            self.verify()
        self.ticket["max_charge_usd"]=0
        self.ticket["max_attempts"]=3
        with self.assertRaisesRegex(SceneBlocked,"ATTEMPT_LIMIT"):
            self.verify()
        self.ticket["max_attempts"]=2
        self.ticket["total_attempt_limit"]=20
        with self.assertRaisesRegex(SceneBlocked,"TOTAL_ATTEMPT"):
            self.verify()

    def test_stale_or_missing_safety_evidence_rejected(self):
        self.reviewed_stage_fixture()
        self.policy["free_hard_cap_verified"]=False
        with self.assertRaisesRegex(SceneBlocked,"NOT_VERIFIED"):
            self.verify()
        self.policy["free_hard_cap_verified"]=True
        self.policy["verified_at"]=(self.now-dt.timedelta(hours=2)).isoformat()
        with self.assertRaisesRegex(SceneBlocked,"EVIDENCE_STALE"):
            self.verify()

    def test_reserved_history_cannot_trigger_another_request(self):
        self.reviewed_stage_fixture()
        self.history["attempts"].append({"request_id":self.ticket["request_id"]})
        self.ticket["history_sha256"]=_history_digest(self.history)
        self.ticket["historical_attempts"]=7
        self.ticket["total_attempt_limit"]=9
        with self.assertRaisesRegex(SceneBlocked,"ALREADY_RESERVED"):
            self.verify()

    def test_stale_history_hash_rejected(self):
        self.reviewed_stage_fixture()
        self.history["attempts"][0]["request_id"]="mutated"
        with self.assertRaisesRegex(SceneBlocked,"PRIVATE_JOURNAL_CHANGED"):
            self.verify()

    def test_selected_legacy_candidate_not_silent_cache_hit(self):
        self.reviewed_stage_fixture()
        self.m["shots"][0]["asset"].update(
            id="OPN02",origin="original",state="SUNSET_CANDIDATE",accepted=False)
        self.ticket["asset_keys"]={x:keys(self.m,self.b)["asset_keys"][x] for x in self.shots}
        with self.assertRaisesRegex(SceneBlocked,"ALREADY_HAS_ART"):
            self.verify()

    def test_unapproved_historical_scene_reconstruction_blocks(self):
        self.reviewed_stage_fixture()
        self.m["shots"][0]["source"]["verified"]=False
        self.ticket["asset_keys"]={x:keys(self.m,self.b)["asset_keys"][x] for x in self.shots}
        out=self.verify()
        self.assertIn("SOURCE_REVIEW_PENDING:EP-P01",out["issues"])

    def test_incorrect_shot_order_or_duplicate_fields_block(self):
        self.reviewed_stage_fixture()
        self.ticket["shot_ids"]=self.shots[::-1]
        with self.assertRaisesRegex(SceneBlocked,"SHOT_ORDER_CHANGED"):
            self.verify()
        self.ticket["shot_ids"]=self.shots
        event=self.event()
        event["issue"]["body"]=event["issue"]["body"].replace(
            '"version": 1', '"version": 1, "version": 1')
        with self.assertRaisesRegex(SceneBlocked,"DUPLICATE_TICKET_FIELD"):
            self.verify(event)


if __name__=="__main__":
    unittest.main()
