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


if __name__ == "__main__":
    unittest.main()
