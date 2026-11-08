import hashlib
import tempfile
import unittest
from pathlib import Path

from tools.scene_pack_preflight import (
    ACCEPTED, CANDIDATE, REMOTE, BLOCKED, EXPECTED_IDS,
    report_scene, verified_entry,
)


def fixture():
    shots = [
        {"id": sid, "source_layer": "symbolic_dramatization",
         "director": {"shot_id": sid, "purpose": "Purpose " + sid,
                      "camera_distance": "wide" if sid == "OPN02" else "medium",
                      "cut_motivation": "Different story beat",
                      "new_relative_to_previous": "Distinct action"}}
        for sid in EXPECTED_IDS
    ]
    rows = [{"id": sid, "key": "key_" + sid, "missing": ["Missing private reference"]}
            for sid in EXPECTED_IDS]
    manifest = {"scene": "INTRO-A1-S01", "shots": shots,
                "authorization": {"approved_shot_ids": ["OPN02"],
                                  "zero_cost_compute_verified": False,
                                  "generation_approved": True,
                                  "component_licenses_verified": True}}
    proof = {"assets": {}, "script_approved": False, "visual_approved": False}
    evidence = {"local_task_id": "OPN02-REAR-WIDE-20261108-01",
                "accepted": False, "png_sha256": "a" * 64,
                "private_png": "private Drive location"}
    return manifest, rows, proof, evidence


class ScenePackPreflightTests(unittest.TestCase):
    def test_existing_remote_candidate_is_never_accepted(self):
        manifest, rows, proof, evidence = fixture()
        with tempfile.TemporaryDirectory() as tmp:
            result = report_scene(manifest, rows, {}, proof, evidence, Path(tmp))
        self.assertEqual(result["scene_status"], "NOT_READY_FOR_PRIVATE_RENDER")
        self.assertEqual(result["known_remote_candidates"], 1)
        self.assertEqual(result["ready_local_accepted_shots"], 0)
        self.assertEqual(result["shots"][1]["status"], REMOTE)
        self.assertEqual(result["provider_submissions"], 0)
        self.assertTrue(all(not s["auto_accepted"] for s in result["shots"]))
        self.assertEqual(len(result["missing_or_unapproved_proof_assets"]), 10)

    def test_missing_remote_evidence_does_not_create_asset(self):
        manifest, rows, proof, evidence = fixture()
        with tempfile.TemporaryDirectory() as tmp:
            result = report_scene(manifest, rows, {}, proof, {}, Path(tmp))
        self.assertEqual(result["shots"][1]["status"], BLOCKED)
        self.assertEqual(result["known_remote_candidates"], 0)

    def test_local_accepted_requires_bytes_hash_and_human_fields(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            asset = root / "private-media" / "sample.png"
            asset.parent.mkdir()
            asset.write_bytes(b"fixture")
            checksum = hashlib.sha256(b"fixture").hexdigest()
            good = {"status": "ACCEPTED", "path": "private-media/sample.png",
                    "sha256": checksum, "accepted": True,
                    "rights_verified": True, "continuity_review": "human"}
            self.assertEqual(verified_entry(good, root)[0], ACCEPTED)
            without_rights = {**good, "rights_verified": False}
            self.assertEqual(verified_entry(without_rights, root)[0], CANDIDATE)
            forged = {**good, "sha256": "0" * 64}
            self.assertEqual(verified_entry(forged, root)[0], "LOCAL_STATE_ASSET_MISMATCH")
            unsafe = {**good, "path": "../../escape"}
            self.assertEqual(verified_entry(unsafe, root)[0], "LOCAL_STATE_ASSET_MISMATCH")

    def test_accepted_status_preserves_shot_scope(self):
        manifest, rows, proof, evidence = fixture()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            asset = root / "private-media" / "one.png"
            asset.parent.mkdir()
            asset.write_bytes(b"hello")
            digest = hashlib.sha256(b"hello").hexdigest()
            state = {"entries": {"key_OPN03": {"status": "ACCEPTED",
                        "path": "private-media/one.png", "sha256": digest,
                        "accepted": True, "rights_verified": True,
                        "continuity_review": "human"}}}
            result = report_scene(manifest, rows, state, proof, evidence, root)
        self.assertEqual(result["shots"][2]["status"], ACCEPTED)
        self.assertEqual(result["ready_local_accepted_shots"], 1)
        self.assertNotEqual(result["shots"][1]["status"], ACCEPTED)
        self.assertEqual(result["scene_status"], "NOT_READY_FOR_PRIVATE_RENDER")

    def test_reordered_ids_fail_closed(self):
        manifest, rows, proof, evidence = fixture()
        manifest["shots"] = list(reversed(manifest["shots"]))
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(ValueError, "OPN01"):
                report_scene(manifest, rows, {}, proof, evidence, Path(tmp))


if __name__ == "__main__":
    unittest.main()
