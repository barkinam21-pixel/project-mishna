"""Scene preflight reporter: no silent omission of cinematic production problems."""
import json
import subprocess
import sys
import unittest
from pathlib import Path

from tools.scene_factory import SceneBlocked, load, validate
from tools.scene_preflight_report import classify, summarize

ROOT = Path(__file__).resolve().parents[1]


class SceneReportTests(unittest.TestCase):
    def setUp(self):
        self.scene = load(ROOT/"episodes/berakhot-01-01/scene-prologue-v02.json")
        self.bible = load(ROOT/self.scene["bible"]["path"])
        self.problems = validate(self.scene, self.bible, ROOT)

    def test_current_prologue_report_is_lossless_and_blocks(self):
        r = summarize(self.problems, scene_id=self.scene["id"])
        self.assertEqual(r["status"], "BLOCKED")
        self.assertEqual(r["total_blockers"], len(self.problems))
        self.assertEqual(r["all_issue_ids"], self.problems)
        self.assertEqual(sum(r["category_counts"].values()), len(self.problems))
        self.assertFalse(r["has_lost_findings"])
        self.assertEqual(r["unclassified_critical_count"], 0, r["sections"])
        self.assertGreater(r["critical_preproduction_blockers"], 0)
        self.assertFalse(r["live_generation_authorized"])
        self.assertFalse(r["media_art_approved"])
        self.assertEqual(r["external_inference_requests"], 0)

    def test_actual_known_conflicts_are_prioritized(self):
        r = summarize(self.problems)
        self.assertIn("EDITORIAL_DECISION_PENDING:daylight",
                      r["sections"][0]["issues"])
        self.assertIn("ASSET_CONTINUITY_TIME_OF_DAY:EP-P07",
                      next(s for s in r["sections"]
                           if s["category"] == "VISUAL_CONTINUITY")["issues"])
        self.assertIn("SOURCE_REVIEW_PENDING:EP-P01",
                      next(s for s in r["sections"]
                           if s["category"] == "SOURCES_AND_CHRONOLOGY")["issues"])
        self.assertLess(
            [s["category"] for s in r["sections"]].index("SCRIPT_AND_EDITORIAL"),
            [s["category"] for s in r["sections"]].index("VISUAL_ASSETS")
        )

    def test_visual_continuity_never_misclassified_as_missing_image(self):
        self.assertEqual(classify("ASSET_CONTINUITY_TIME_OF_DAY:EP-P07"),
                         "VISUAL_CONTINUITY")
        self.assertEqual(classify("ASSET_NOT_APPROVED:EP-P01"), "VISUAL_ASSETS")
        self.assertEqual(classify("CAPTION_NOT_IN_LOCKED_SCRIPT:EP-P08"),
                         "SCRIPT_AND_EDITORIAL")
        self.assertEqual(classify("SOUND_HASH_MISMATCH:SFX-1"),
                         "VOICE_AUDIO_AND_RIGHTS")

    def test_unknown_is_critical_not_ignored(self):
        original = ["SCRIPT_NOT_APPROVED", "UNEXPECTED_VENDOR_FAILURE:EP-P01"]
        r = summarize(original)
        self.assertEqual(r["total_blockers"], 2)
        self.assertEqual(r["unclassified_critical_count"], 1)
        self.assertEqual(r["all_issue_ids"], original)
        self.assertIn("UNEXPECTED_VENDOR_FAILURE:EP-P01",
                      next(s for s in r["sections"]
                           if s["category"] == "UNCLASSIFIED_CRITICAL")["issues"])

    def test_duplicates_or_nonstring_fail_closed(self):
        for bad in (["a", "a"], [1], "string", None):
            with self.subTest(bad=bad), self.assertRaises(SceneBlocked):
                summarize(bad)

    def test_no_declared_issue_never_means_art_is_approved(self):
        r = summarize([], scene_id="TEST")
        self.assertEqual(r["status"], "PREFLIGHT_NO_DECLARED_BLOCKERS_NOT_ART_APPROVAL")
        self.assertEqual(r["total_blockers"], 0)
        self.assertFalse(r["live_generation_authorized"])
        self.assertFalse(r["media_art_approved"])

    def test_cli_exits_blocked_and_never_calls_provider(self):
        p = subprocess.run([sys.executable, "-m", "tools.scene_preflight_report"],
                           cwd=ROOT, capture_output=True, text=True, timeout=15)
        self.assertEqual(p.returncode, 2, p.stderr)
        data = json.loads(p.stdout)
        self.assertEqual(data["scene_id"], self.scene["id"])
        self.assertEqual(data["total_blockers"], len(self.problems))
        self.assertFalse(data["live_generation_authorized"])
        self.assertEqual(data["external_inference_requests"], 0)
        self.assertEqual(data["all_issue_ids"], self.problems)


if __name__ == "__main__":
    unittest.main()
