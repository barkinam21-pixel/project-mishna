import copy
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from studio import preflight

ROOT = Path(__file__).resolve().parents[1]

class PreflightTests(unittest.TestCase):
    def setUp(self):
        self.manifest = json.loads((ROOT / "episodes/berakhot-01-01/manifest.json").read_text(encoding="utf-8"))

    def test_research_stage_is_blocked_without_error(self):
        r = preflight(self.manifest)
        self.assertTrue(r["valid"])
        self.assertEqual(r["status"], "BLOCKED_AS_DESIGNED")
        self.assertEqual(r["external_generation_calls"], 0)
        self.assertGreaterEqual(len(r["blockers"]), 8)
        self.assertIn("Exact Mishnah text must be checked and locked", r["blockers"])
        self.assertIn("No approved image assets", r["blockers"])
        self.assertIn("No approved audio clips; silent proof only if explicitly declared", r["blockers"])

    def test_bad_caption_is_rejected(self):
        m = copy.deepcopy(self.manifest)
        m["captions"] = [{"display_text": "שגוי\u202e", "start_frame": 0, "end_frame": 24}]
        self.assertFalse(preflight(m)["valid"])

    def test_spending_cannot_be_enabled(self):
        m = copy.deepcopy(self.manifest)
        m["cost"]["external_spend_enabled"] = True
        self.assertFalse(preflight(m)["valid"])

    def test_malformed_input_not_crash(self):
        r = preflight([])
        self.assertEqual(r["status"], "INVALID")

    def test_missing_timing_is_invalid(self):
        m = copy.deepcopy(self.manifest)
        m["production"]["fps"] = 0
        self.assertFalse(preflight(m)["valid"])

if __name__ == "__main__":
    unittest.main()
