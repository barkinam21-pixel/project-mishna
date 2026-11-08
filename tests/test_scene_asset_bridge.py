"""Safety regression tests for the private scene asset bridge."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tools.scene_asset_bridge import reconcile


class SceneAssetBridgeTests(unittest.TestCase):
    def test_missing_private_assets_never_ready(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            target = root / "episodes/berakhot-01-01"
            target.mkdir(parents=True)
            assets = {f"OPN{i:02d}": {"path": f"private-media/introduction/OPN{i:02d}.png",
                     "sha256": None, "accepted": False, "rights_verified": False}
                      for i in range(1, 8)}
            (target / "introduction-proof.json").write_text(json.dumps({"assets": assets}))
            shots = [{"shot_id": f"OPN{i:02d}", "key": f"key{i}",
                      "status": "BLOCKED_MISSING_PRIVATE_INPUT"} for i in range(1, 8)]
            with patch("tools.scene_asset_bridge.build", return_value={"shots": shots}):
                result = reconcile(root)
            self.assertFalse(result["ready"])
            self.assertEqual(len(result["shots"]), 7)
            self.assertFalse(any(s["ready_for_render"] for s in result["shots"]))
            self.assertEqual(result["provider_calls"], 0)
            self.assertEqual(len(result["missing_or_unapproved_media"]), 10)
            self.assertFalse(result["shot_timing_ready"])
            self.assertFalse(result["voice_timing_ready"])
            self.assertFalse(result["script_and_visual_approvals_ready"])

    def test_matching_hash_without_director_acceptance_still_blocked(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            target = root / "episodes/berakhot-01-01"
            target.mkdir(parents=True)
            private = root / "private-media/introduction"
            private.mkdir(parents=True)
            import hashlib
            (private / "OPN01.png").write_bytes(b"synthetic-test-only")
            sha = hashlib.sha256(b"synthetic-test-only").hexdigest()
            assets = {"OPN01": {"path": "private-media/introduction/OPN01.png",
                      "sha256": sha, "accepted": True, "rights_verified": True}}
            (target / "introduction-proof.json").write_text(json.dumps({"assets": assets}))
            shots = [{"shot_id": f"OPN{i:02d}", "key": f"key{i}",
                      "status": "CANDIDATE_NEEDS_HUMAN_REVIEW"} for i in range(1, 8)]
            with patch("tools.scene_asset_bridge.build", return_value={"shots": shots}):
                result = reconcile(root)
            self.assertTrue(result["shots"][0]["registry_hash_verified"])
            self.assertFalse(result["shots"][0]["ready_for_render"])
            self.assertFalse(result["ready"])
            self.assertIn("INTRO-A1-S01-N01", result["missing_or_unapproved_media"])


    def test_authoritative_proof_validator_is_required_for_ready(self):
        import hashlib
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            film = root / "episodes/berakhot-01-01"
            film.mkdir(parents=True)
            media = root / "private-media/introduction"
            media.mkdir(parents=True)
            shots = []
            assets = {}
            entries = {}
            for i in range(1, 8):
                uid = f"OPN{i:02d}"
                key = f"key{i}"
                shot_bytes = ("synthetic-illustration-" + uid).encode()
                target = media / (uid + ".png")
                target.write_bytes(shot_bytes)
                sha = hashlib.sha256(shot_bytes).hexdigest()
                entries[key] = {"sha256": sha}
                shots.append({"shot_id": uid, "key": key, "status": "CANDIDATE"})
                assets[uid] = {
                    "path": "private-media/introduction/" + uid + ".png",
                    "sha256": sha, "accepted": True, "rights_verified": True,
                    "provenance": "synthetic-test", "license": "test-fixture",
                }
            for uid, suffix in [("INTRO-A1-S01-N01", ".wav"),
                                ("INTRO-A1-S01-N02", ".wav"),
                                ("captions", ".json")]:
                data = ("synthetic-only-" + uid).encode()
                target = media / (uid + suffix)
                target.write_bytes(data)
                assets[uid] = {
                    "path": "private-media/introduction/" + target.name,
                    "sha256": hashlib.sha256(data).hexdigest(),
                    "accepted": True, "rights_verified": True,
                    "provenance": "synthetic-test", "license": "test-fixture",
                }
            (root / "private-media/director-images").mkdir(parents=True)
            (root / "private-media/director-images/state.json").write_text(
                json.dumps({"entries": entries}))
            registry = {
                "assets": assets, "script_approved": True, "visual_approved": True,
                "shots": [{"id": f"OPN{i:02d}", "duration_frames": 24}
                          for i in range(1, 8)],
                "voice_takes": [
                    {"start_sample": 0, "end_sample": 48000},
                    {"start_sample": 48000, "end_sample": 96000},
                ],
            }
            (film / "introduction-proof.json").write_text(json.dumps(registry))
            with patch("tools.scene_asset_bridge.build", return_value={"shots": shots}), \
                 patch("tools.scene_asset_bridge.verified_entry",
                       return_value=("VERIFIED_LOCAL_ACCEPTED", "verified")), \
                 patch("tools.introduction_proof.plan",
                       return_value={"status": "INVALID"}) as proof:
                blocked = reconcile(root)
                self.assertTrue(blocked["scene_images_ready"])
                self.assertFalse(blocked["ready"])
                self.assertEqual(blocked["film_gate_status"], "INVALID")
                proof.assert_called_once()
            with patch("tools.scene_asset_bridge.build", return_value={"shots": shots}), \
                 patch("tools.scene_asset_bridge.verified_entry",
                       return_value=("VERIFIED_LOCAL_ACCEPTED", "verified")), \
                 patch("tools.introduction_proof.plan",
                       return_value={"status": "READY_PRIVATE_RENDER_ONLY"}):
                ready = reconcile(root)
                self.assertTrue(ready["ready"])
                self.assertEqual(ready["film_gate_status"],
                                 "READY_PRIVATE_RENDER_ONLY")


if __name__ == "__main__":
    unittest.main()
