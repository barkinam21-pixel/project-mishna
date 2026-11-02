from copy import deepcopy
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from validate_proof_blueprint import validate


class EditorialBlueprintTests(unittest.TestCase):
    def setUp(self):
        path = ROOT / "episodes/berakhot-01-01/proof-blueprint.json"
        self.data = json.loads(path.read_text(encoding="utf-8"))

    def test_75_seconds_contiguous_and_blocked(self):
        report = validate(self.data)
        self.assertTrue(report["valid"], report["errors"])
        self.assertEqual(report["status"], "EDITORIAL_PLAN_VALID_BUT_BLOCKED")
        self.assertEqual(report["duration_frames"], 1800)
        self.assertEqual(report["duration_seconds"], 75)
        self.assertEqual(report["scene_count"], 5)
        self.assertEqual(report["shot_count"], 16)
        self.assertEqual(report["planned_original_images"], 16)
        self.assertEqual(report["actual_generated_images"], 0)
        self.assertEqual(report["actual_rendered_videos"], 0)

    def test_overlapping_shots_do_not_pass(self):
        blueprint = deepcopy(self.data)
        blueprint["shots"][1]["start_frame"] -= 1
        report = validate(blueprint)
        self.assertFalse(report["valid"])
        self.assertTrue(any("continuity" in e for e in report["errors"]))

    def test_gap_between_scenes_do_not_pass(self):
        blueprint = deepcopy(self.data)
        blueprint["scenes"][1]["start_frame"] += 10
        self.assertFalse(validate(blueprint)["valid"])

    def test_unreviewed_draft_cannot_set_release_approval(self):
        blueprint = deepcopy(self.data)
        blueprint["release_authorized"] = True
        self.assertFalse(validate(blueprint)["valid"])
        blueprint["release_authorized"] = False
        blueprint["human_torah_review_approved"] = True
        self.assertFalse(validate(blueprint)["valid"])

    def test_missing_source_evidence_does_not_pass(self):
        blueprint = deepcopy(self.data)
        blueprint["scenes"][3]["source_links"] = []
        report = validate(blueprint)
        self.assertFalse(report["valid"])
        self.assertTrue(any("source_links" in e for e in report["errors"]))

    def test_no_fake_generated_media(self):
        blueprint = deepcopy(self.data)
        blueprint["shots"][0]["asset_ready"] = True
        self.assertFalse(validate(blueprint)["valid"])
        blueprint = deepcopy(self.data)
        blueprint["images_status"] = "completed"
        self.assertFalse(validate(blueprint)["valid"])

    def test_invalid_audio_rate_fails_without_crash(self):
        blueprint = deepcopy(self.data)
        blueprint["sample_rate"] = None
        report = validate(blueprint)
        self.assertFalse(report["valid"])
        self.assertTrue(report["errors"])

    def test_scene_dramatic_pack_really_original(self):
        blueprint = deepcopy(self.data)
        for shot in blueprint["shots"]:
            if shot["scene_id"] == "S04":
                shot["original_illustration_required"] = False
                break
        self.assertFalse(validate(blueprint)["valid"])

    def test_rejects_non_object(self):
        report = validate(["bad"])
        self.assertFalse(report["valid"])
        self.assertEqual(report["status"], "INVALID")


if __name__ == "__main__":
    unittest.main()
