"""Cross-document prologue editorial crosswalk regression tests."""
import copy
import json
import subprocess
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

from tools.scene_factory import SceneBlocked
from tools.scene_prologue_crosswalk import analyze

ROOT = Path(__file__).resolve().parents[1]


class CrosswalkTests(unittest.TestCase):
    def setUp(self):
        self.report = analyze(ROOT)

    def test_actual_15_shot_timeline_matches_24fps(self):
        r = self.report
        self.assertEqual(r["shot_count"], 15)
        self.assertEqual(r["shotmap_duration_sec"], 91)
        self.assertEqual(r["shot_ids"], [f"EP-P{i:02d}" for i in range(1, 16)])
        self.assertEqual(r["structural_issues"], [])
        self.assertEqual(r["inference_requests"], 0)
        self.assertFalse(r["approval_promoted"])
        self.assertFalse(r["generation_authorized"])

    def test_real_literary_and_art_conflicts_remain_unresolved(self):
        issues = self.report["issues"]
        for required in (
            "EDITORIAL_NARRATION_ENTRY_CONFLICT",
            "LITERARY_SCRIPT_NOT_LOCKED",
            "LITERARY_45S_VS_SHOTMAP_91S_TIMING_REVIEW",
            "DAWN_SCRIPT_VS_SUNSET_ASSET_CANDIDATES",
            "SOURCE_LINKAGE_NOT_APPROVED",
            "ALL_SHOTS_USE_GENERIC_SCRIPT_SPAN_REVIEW",
        ):
            with self.subTest(required=required):
                self.assertIn(required, issues)
        self.assertEqual(self.report["status"], "EDITORIAL_REVIEW_REQUIRED")

    def test_detect_timeline_mismatch_not_silent(self):
        original = json.loads((ROOT / "episodes/berakhot-01-01/scene-prologue-v02.json").read_text())
        altered = copy.deepcopy(original)
        altered["shots"][2]["start_frame"] += 24
        original_load = __import__("tools.scene_prologue_crosswalk", fromlist=["load"]).load
        def load_modified(path):
            if str(path).endswith("scene-prologue-v02.json"):
                return altered
            return original_load(path)
        with patch("tools.scene_prologue_crosswalk.load", side_effect=load_modified):
            r = analyze(ROOT)
        self.assertIn("SHOT_START_FRAME_MISMATCH:EP-P03", r["issues"])

    def test_detect_reordered_shot(self):
        original = json.loads((ROOT / "episodes/berakhot-01-01/scene-prologue-v02.json").read_text())
        altered = copy.deepcopy(original)
        altered["shots"][0], altered["shots"][1] = altered["shots"][1], altered["shots"][0]
        with patch("tools.scene_prologue_crosswalk.load", return_value=altered):
            r = analyze(ROOT)
        self.assertTrue(any(x.startswith("SHOT_ID_ORDER_MISMATCH") for x in r["issues"]))

    def test_missing_shotmap_is_failure_not_success(self):
        from tools import scene_prologue_crosswalk as m
        original = m._read
        def broken(root, path):
            data = original(root, path)
            if path == m.SHOTMAP:
                return data.replace("| EP-P15 |", "| BROKEN |")
            return data
        with patch("tools.scene_prologue_crosswalk._read", side_effect=broken):
            with self.assertRaisesRegex(SceneBlocked, "EXPECTED_15_UNIQUE_SHOTS"):
                analyze(ROOT)

    def test_cli_reports_review_needed_without_inference(self):
        p = subprocess.run([sys.executable, "-m", "tools.scene_prologue_crosswalk"],
                           cwd=ROOT, capture_output=True, text=True, timeout=15)
        self.assertEqual(p.returncode, 2, p.stderr)
        j = json.loads(p.stdout)
        self.assertEqual(j["status"], "EDITORIAL_REVIEW_REQUIRED")
        self.assertEqual(j["inference_requests"], 0)
        self.assertFalse(j["generation_authorized"])


if __name__ == "__main__":
    unittest.main()
