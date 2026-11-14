"""M3 remote journal protocol tests: offline CAS, mock shots, no Drive/Cloudflare."""
import copy
import datetime as dt
import json
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from tools.scene_factory import SceneBlocked, digest, keys
from tools.scene_m3 import OfflineFakeImageBackend
from tools.scene_m3_ticket import _history_digest, OWNER_PHRASE, verify
from tools.scene_m3_remote import (
    AtomicMemoryJournal, NoCASDriveAdapter, OfflineRemoteCoordinator, history_sha256
)

ROOT = Path(__file__).resolve().parents[1]


class M3RemoteTests(unittest.TestCase):
    def setUp(self):
        self.manifest = json.loads((ROOT / "episodes/berakhot-01-01/scene-prologue-v02.json").read_text())
        self.bible = json.loads((ROOT / self.manifest["bible"]["path"]).read_text())
        self.now = dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
        self.history = {
            "entries": {},
            "attempts": [
                {"key": "historical-"+str(i), "request_id": "prior-"+str(i),
                 "status": "HISTORICAL_RECORDED"} for i in range(6)
            ]
        }
        self.policy = {
            "privacy_verified": True, "free_hard_cap_verified": True,
            "quota_verified": True, "verified_at": self.now.isoformat()
        }
        self.ids = ["EP-P01", "EP-P02"]
        self.request_id = "b" * 32
        self.ticket = {
            "version": 1, "request_id": self.request_id,
            "scene_id": self.manifest["id"],
            "script_sha256": self.manifest["script"]["sha256"],
            "bible_sha256": digest(self.bible),
            "shot_ids": list(self.ids),
            "asset_keys": {x: keys(self.manifest, self.bible)["asset_keys"][x]
                           for x in self.ids},
            "issued_at": self.now.isoformat(),
            "approval": OWNER_PHRASE,
            "max_attempts": 2, "max_charge_usd": 0,
            "history_sha256": _history_digest(self.history),
            "historical_attempts": len(self.history["attempts"]),
            "total_attempt_limit": 8
        }
        # Approved/sourced ARTIFICIAL TEST ONLY stage; never a real creative lock.
        self.manifest["script"].update(approved=True, reviewer="CI_TEST_ONLY")
        for d in self.manifest["decisions"]:
            d.update(approved=True, reviewer="CI_TEST_ONLY")
        for s in self.manifest["shots"]:
            s["source"]["verified"] = True
            s["pre_state"] = "DAWN_BEFORE"
            s["post_state"] = "DAWN_BEFORE"
            s["exception"] = None
            s["asset"].update(
                id=None, origin="missing", state=None,
                accepted=False, path=None, sha256=None
            )
        self.ticket["asset_keys"] = {
            x: keys(self.manifest, self.bible)["asset_keys"][x] for x in self.ids
        }

    def event(self):
        return {
            "action": "edited",
            "sender": {"login": "barkinam21-pixel"},
            "repository": {"full_name": "barkinam21-pixel/project-mishna",
                           "owner": {"login": "barkinam21-pixel"}},
            "issue": {
                "number": 54, "state": "open",
                "body": "```mishnah-scene-request\n" +
                        json.dumps(self.ticket, sort_keys=True) + "\n```"
            },
            "changes": {"body": {"from": "old body"}}
        }

    def admission(self):
        a = verify(self.event(), self.policy, self.history,
                   self.manifest, self.bible, ROOT, now=self.now)
        self.assertEqual(a["status"], "OFFLINE_TICKET_CHECKED_NO_LIVE_DISPATCH", a)
        return a

    def coordinator(self):
        store = AtomicMemoryJournal(copy.deepcopy(self.history))
        return OfflineRemoteCoordinator(store), store

    def test_real_artistic_prologue_remains_blocked(self):
        m = json.loads((ROOT/"episodes/berakhot-01-01/scene-prologue-v02.json").read_text())
        b = json.loads((ROOT/m["bible"]["path"]).read_text())
        ticket = copy.deepcopy(self.ticket)
        ticket["asset_keys"] = {x: keys(m,b)["asset_keys"][x] for x in self.ids}
        ev = self.event()
        ev["issue"]["body"] = "```mishnah-scene-request\n"+json.dumps(ticket)+"\n```"
        out = verify(ev, self.policy, self.history, m, b, ROOT, now=self.now)
        self.assertEqual(out["status"], "BLOCKED")
        self.assertIn("ASSET_CONTINUITY_TIME_OF_DAY:EP-P07", out["issues"])
        self.assertEqual(out["external_inference_requests"], 0)

    def test_prepared_batch_preserves_all_historical_attempts(self):
        q, store = self.coordinator()
        a = self.admission()
        first = q.begin(a)
        self.assertEqual(first["status"], "READY")
        self.assertFalse(first["live_dispatch_enabled"])
        self.assertTrue(first["simulated_only"])
        self.assertEqual(store.read()[1]["attempts"], self.history["attempts"])
        cached = q.begin(a)
        self.assertTrue(cached["cache_hit"])
        self.assertEqual(store.writes, 1)

    def test_offline_two_shot_batch_never_calls_live_provider(self):
        q, store = self.coordinator()
        a = self.admission()
        q.begin(a)
        backend = OfflineFakeImageBackend()
        for shot in self.ids:
            r = q.reserve(self.request_id, shot)
            self.assertEqual(r["status"], "OFFLINE_RESERVATION_ONLY_NO_PROVIDER_CALL")
            self.assertFalse(r["live_dispatch_enabled"])
            receipt = backend.produce(a["scene_id"], shot, a["asset_keys"][shot])
            q.record_mock_receipt(self.request_id, shot, receipt)
        status = q.status(self.request_id)
        self.assertEqual(status["status"], "SIMULATED_NOT_ART")
        self.assertEqual(set(status["receipts"]), set(self.ids))
        self.assertEqual(store.read()[1]["attempts"][:6], self.history["attempts"])
        self.assertEqual(len(store.read()[1]["attempts"]), 8)
        self.assertEqual(status["external_inference_requests"], 0)
        self.assertEqual(len(status["reserved"]), 2)

    def test_crash_after_remote_reservation_always_halts(self):
        q, store = self.coordinator()
        q.begin(self.admission())
        q.reserve(self.request_id, self.ids[0])
        restarted = OfflineRemoteCoordinator(store)
        status = restarted.status(self.request_id)
        self.assertEqual(status["recovery_status"], "HALTED_UNCERTAIN_NO_RETRY")
        with self.assertRaises(SceneBlocked):
            restarted.reserve(self.request_id, self.ids[0])
        with self.assertRaises(SceneBlocked):
            restarted.reserve(self.request_id, self.ids[1])
        self.assertEqual(len(store.read()[1]["attempts"]), 7)

    def test_stale_atomic_CAS_race_allows_only_one_writer(self):
        store = AtomicMemoryJournal(self.history)
        rev1, d1 = store.read()
        rev2, d2 = store.read()
        d1["entries"]["winner"] = {"status": "QUEUED"}
        d2["entries"]["loser"] = {"status": "QUEUED"}
        self.assertTrue(store.compare_and_swap(rev1, d1))
        self.assertFalse(store.compare_and_swap(rev2, d2))
        self.assertIn("winner", store.read()[1]["entries"])
        self.assertNotIn("loser", store.read()[1]["entries"])
        self.assertEqual(store.writes, 1)

    def test_simultaneous_begin_cannot_create_two_batches(self):
        q, store = self.coordinator()
        a = self.admission()
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(q.begin, a) for _ in range(2)]
            results = []
            for f in futures:
                try:
                    results.append(f.result())
                except SceneBlocked as ex:
                    self.assertIn("CAS_CONFLICT_NO_RETRY", str(ex))
        self.assertGreaterEqual(len(results), 1)
        self.assertEqual(len(store.read()[1].get("m3_scene_batches", {})), 1)
        self.assertEqual(store.read()[1]["attempts"], self.history["attempts"])
        self.assertEqual(store.writes, 1)

    def test_no_verified_atomic_transport_blocks_untested_Drive_CAS(self):
        with self.assertRaisesRegex(SceneBlocked, "ATOMIC_REMOTE_CAS_UNAVAILABLE"):
            OfflineRemoteCoordinator(NoCASDriveAdapter())
        class FakeReadReplace:
            def read(self):
                return 0, copy.deepcopy(self.history)
            def replace(self, new):
                return True
        with self.assertRaisesRegex(SceneBlocked, "ATOMIC_REMOTE_CAS_UNAVAILABLE"):
            OfflineRemoteCoordinator(FakeReadReplace())

    def test_changed_prior_journal_blocks_start(self):
        a = self.admission()
        mutated = copy.deepcopy(self.history)
        mutated["attempts"][0]["key"] = "changed"
        q = OfflineRemoteCoordinator(AtomicMemoryJournal(mutated))
        with self.assertRaisesRegex(SceneBlocked, "HISTORY_CHANGED"):
            q.begin(a)

    def test_reused_owner_request_changed_spec_is_denied(self):
        q, _ = self.coordinator()
        a = self.admission()
        q.begin(a)
        different = copy.deepcopy(a)
        different["asset_keys"][self.ids[0]] = "0"*64
        with self.assertRaisesRegex(SceneBlocked, "REQUEST_SCOPE_CHANGED"):
            q.begin(different)

    def test_unexpected_additional_attempt_detected(self):
        q, store = self.coordinator()
        a = self.admission()
        q.begin(a)
        version, doc = store.read()
        doc["attempts"].append({"key":"foreign-attempt","request_id":"outsider"})
        self.assertTrue(store.compare_and_swap(version, doc))
        with self.assertRaisesRegex(SceneBlocked, "HISTORY_CHANGED"):
            q.status(self.request_id)
        with self.assertRaisesRegex(SceneBlocked, "FOREIGN_HISTORY_CHANGE"):
            q.reserve(self.request_id, self.ids[0])

    def test_bad_shot_id_and_out_of_order_reservation(self):
        q, store = self.coordinator()
        q.begin(self.admission())
        for bad in ("OPN03", self.ids[1]):
            with self.assertRaises(SceneBlocked):
                q.reserve(self.request_id, bad)
        self.assertEqual(len(store.read()[1]["attempts"]), 6)

    def test_cannot_start_new_batch_while_one_unfinished(self):
        q, _ = self.coordinator()
        q.begin(self.admission())
        a = self.admission()
        a["request_id"] = "c"*32
        with self.assertRaisesRegex(SceneBlocked, "OTHER_BATCH_ACTIVE"):
            q.begin(a)

    def test_wrong_receipt_cannot_mark_generated_or_accepted(self):
        q, store = self.coordinator()
        a = self.admission()
        q.begin(a)
        q.reserve(self.request_id, self.ids[0])
        fake = OfflineFakeImageBackend().produce(a["scene_id"], self.ids[0],
                                                a["asset_keys"][self.ids[0]])
        for mutation in (
            {"accepted": True},
            {"provider_calls": 1},
            {"external_cost_usd": 0.01},
            {"sha256": "f"*64}
        ):
            r = dict(fake, **mutation)
            with self.assertRaisesRegex(SceneBlocked, "ONLY_FAKE_RECEIPTS"):
                q.record_mock_receipt(self.request_id, self.ids[0], r)
        self.assertEqual(store.read()[1]["attempts"][-1]["status"],
                         "RESERVED_SUBMISSION_UNCERTAIN_NO_RETRY")
        self.assertEqual(q.status(self.request_id)["recovery_status"],
                         "HALTED_UNCERTAIN_NO_RETRY")

    def test_cannot_complete_without_receipts_or_retry_same_shot(self):
        q, store = self.coordinator()
        a = self.admission()
        q.begin(a)
        q.reserve(self.request_id, self.ids[0])
        fake = OfflineFakeImageBackend().produce(a["scene_id"], self.ids[0],
                                                a["asset_keys"][self.ids[0]])
        q.record_mock_receipt(self.request_id, self.ids[0], fake)
        with self.assertRaises(SceneBlocked):
            q.reserve(self.request_id, self.ids[0])
        self.assertEqual(len(store.read()[1]["attempts"]), 7)


if __name__ == "__main__":
    unittest.main()
