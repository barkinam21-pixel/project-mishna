"""M3 admission tests: mock-only, no provider calls, no expense."""
import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from tools.scene_factory import SceneBlocked, digest, validate, SceneStore
from tools.scene_m3 import BatchCoordinator, OfflineFakeImageBackend, selection

ROOT = Path(__file__).resolve().parents[1]


class M3BatchTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.m = json.loads((ROOT / "episodes/berakhot-01-01/scene-prologue-v02.json").read_text())
        self.b = json.loads((ROOT / self.m["bible"]["path"]).read_text())
        self.queue = BatchCoordinator(self.root / "private-media" / "m3-tests")
        self.ids = ["EP-P01", "EP-P02"]
        self.request_id = "scene-first-test"

    def ready_fixture(self):
        # A structurally valid TEST-ONLY film spec, never a claim of verified art.
        script = ROOT / self.m["script"]["path"]
        target = self.root / "fake-script.md"
        target.write_bytes(script.read_bytes())
        self.m["script"].update(
            path="fake-script.md", sha256=hashlib.sha256(target.read_bytes()).hexdigest(),
            approved=True, reviewer="OFFLINE_UNIT_TEST"
        )
        self.m["bible"]["sha256"] = digest(self.b)
        for decision in self.m["decisions"]:
            decision.update(approved=True, reviewer="OFFLINE_UNIT_TEST")
        image = self.root / "fixture.image"
        image.write_bytes(b"SIMULATED_UNIT_TEST_NOT_AN_IMAGE")
        sound = self.root / "fixture.wav"
        sound.write_bytes(b"SIMULATED_UNIT_TEST_NOT_AUDIO")
        for shot in self.m["shots"]:
            shot["pre_state"] = "DAWN_BEFORE"
            shot["post_state"] = "DAWN_BEFORE"
            shot["exception"] = None
            shot["source"].update(verified=True, confidence="TEST_ONLY",
                                  reference="TEST_ONLY_SYMBOLIC_SOURCE")
            shot["asset"].update(
                id=shot["id"], origin="human_art", state="DAWN_BEFORE",
                accepted=True, path="fixture.image",
                sha256=hashlib.sha256(image.read_bytes()).hexdigest(),
            )
            for cue in shot["sound"]:
                cue.update(license="TEST_ONLY", path="fixture.wav",
                           sha256=hashlib.sha256(sound.read_bytes()).hexdigest())
        problems = validate(self.m, self.b, self.root)
        self.assertEqual(problems, [], problems)

    def test_actual_prologue_blocks_before_any_mock_inference(self):
        result = self.queue.simulate(self.m, self.b, ROOT, self.request_id, self.ids, 2)
        self.assertEqual(result["status"], "BLOCKED")
        self.assertIn("ASSET_CONTINUITY_TIME_OF_DAY:EP-P07", result["issues"])
        self.assertEqual(result["attempted"], 0)
        self.assertEqual(result["external_inference_requests"], 0)

    def test_no_live_backend_surface(self):
        self.assertFalse(hasattr(self.queue, "submit"))
        self.assertFalse(hasattr(self.queue, "generate"))
        self.assertEqual(OfflineFakeImageBackend().produce("s", "i", "k")["kind"],
                         "OFFLINE_FAKE_NOT_IMAGE")

    def test_ready_two_shots_one_request_no_replay(self):
        self.ready_fixture()
        first = self.queue.simulate(self.m, self.b, self.root, self.request_id, self.ids, 2)
        self.assertEqual(first["status"], "SIMULATED_NOT_ART")
        self.assertEqual(first["attempted"], 2)
        self.assertEqual(set(first["results"]), set(self.ids))
        self.assertEqual({r["status"] for r in first["results"].values()}, {"CANDIDATE"})
        self.assertEqual({r["receipt"]["accepted"] for r in first["results"].values()}, {False})
        self.assertEqual(first["external_inference_requests"], 0)
        again = self.queue.simulate(self.m, self.b, self.root, self.request_id, self.ids, 2)
        self.assertEqual(again["attempted"], 2)
        self.assertEqual(again["results"], first["results"])
        self.assertEqual(again["external_charge_usd"], 0)

    def test_crash_after_reservation_does_not_repeat(self):
        self.ready_fixture()
        with self.assertRaisesRegex(SceneBlocked, "SIMULATED_CRASH"):
            self.queue.simulate(self.m, self.b, self.root, "crash", self.ids, 2,
                                fail_after_reservation_at="EP-P01")
        on_disk = BatchCoordinator(self.queue.store.path).status("crash")
        self.assertEqual(on_disk["attempted"], 1)
        self.assertEqual(on_disk["results"]["EP-P01"]["status"], "RESERVED_UNCERTAIN")
        recovered = BatchCoordinator(self.queue.store.path).simulate(
            self.m, self.b, self.root, "crash", self.ids, 2)
        self.assertEqual(recovered["status"], "HALTED_UNCERTAIN")
        self.assertEqual(recovered["attempted"], 1)
        self.assertNotIn("EP-P02", recovered["results"])
        self.assertEqual(BatchCoordinator(self.queue.store.path).status("crash")["status"],
                         "HALTED_UNCERTAIN")

    def test_limit_zero_means_no_reservation(self):
        self.ready_fixture()
        result = self.queue.simulate(self.m, self.b, self.root, "zero", self.ids, 0)
        self.assertEqual(result["attempted"], 0)
        self.assertEqual(result["results"], {})

    def test_spec_changed_request_id_rejected(self):
        self.ready_fixture()
        self.queue.plan(self.m, self.b, self.root, self.request_id, self.ids, 1)
        changed = copy.deepcopy(self.m)
        changed["shots"][0]["description"] += " changed"
        with self.assertRaisesRegex(SceneBlocked, "M3_REQUEST_SPEC_CHANGED"):
            self.queue.plan(changed, self.b, self.root, self.request_id, self.ids, 1)

    def test_asset_corruption_revalidated_even_if_cached(self):
        self.ready_fixture()
        p = self.root / "fixture.image"
        self.queue.plan(self.m, self.b, self.root, "cache", self.ids, 1)
        p.write_bytes(b"CORRUPTED")
        with self.assertRaisesRegex(SceneBlocked, "M3_PREFLIGHT_CHANGED"):
            self.queue.plan(self.m, self.b, self.root, "cache", self.ids, 1)

    def test_wrong_order_unknown_duplicate_and_bad_limits(self):
        for shots in ([self.ids[1], self.ids[0]], ["EP-P999"], ["EP-P01", "EP-P01"]):
            with self.assertRaises(SceneBlocked):
                self.queue.plan(self.m, self.b, ROOT, "wrong", shots, 1)
        for max_attempts in (True, -1, 3, 1.5):
            with self.assertRaises(SceneBlocked):
                self.queue.plan(self.m, self.b, ROOT, "wrong", self.ids, max_attempts)

    def test_nonzero_budget_and_owner_gate_fail_closed(self):
        self.m["authorization"]["budget_usd"] = 1
        with self.assertRaisesRegex(SceneBlocked, "NONZERO_COST"):
            self.queue.plan(self.m, self.b, ROOT, "pay", self.ids, 1)
        self.m["authorization"]["budget_usd"] = 0
        self.m["authorization"]["generation_approved"] = True
        with self.assertRaisesRegex(SceneBlocked, "PRODUCTION_GATE"):
            self.queue.plan(self.m, self.b, ROOT, "pay", self.ids, 1)

    def test_corrupt_append_only_journal_fails_closed(self):
        self.ready_fixture()
        self.queue.plan(self.m, self.b, self.root, "journal", self.ids, 1)
        (self.queue.store.path / "events.jsonl").write_text("not json")
        with self.assertRaisesRegex(SceneBlocked, "JOURNAL_CORRUPT"):
            self.queue.simulate(self.m, self.b, self.root, "journal", self.ids, 1)

    def test_identity_scopes_shots_and_attempts(self):
        self.ready_fixture()
        self.queue.plan(self.m, self.b, self.root, "scope", self.ids, 1)
        with self.assertRaisesRegex(SceneBlocked, "SPEC_CHANGED"):
            self.queue.plan(self.m, self.b, self.root, "scope", self.ids, 2)
        with self.assertRaisesRegex(SceneBlocked, "SPEC_CHANGED"):
            self.queue.plan(self.m, self.b, self.root, "scope", self.ids[:1], 1)


if __name__ == "__main__":
    unittest.main()
