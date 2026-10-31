"""Prevent duplicate user loops: one active studio, one externally verified SH01 receipt."""
import json
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[1]
EP=ROOT/"episodes"/"berakhot-01-01"

class SingleControlRoomTest(unittest.TestCase):
    def test_evidence_is_one_unapproved_image_trial(self):
        data=json.loads((EP/"trials.json").read_text(encoding="utf-8"))
        self.assertEqual(data["episode_id"],"berakhot-01-01")
        self.assertEqual(len(data["trials"]),1)
        shot=data["trials"][0]
        self.assertEqual(shot["shot_id"],"SH01")
        self.assertEqual(shot["status"],"generated_unapproved")
        self.assertEqual(shot["image_sha256"],"e3647bad6668aebd69810a105dba4df4bd2cfa73ba78cf18269171e73444166d")
        self.assertFalse(shot["production_asset_accepted"])
        self.assertFalse(shot["archive_in_repository"])

    def test_one_dashboard_and_no_stale_first_trial_claim(self):
        main=(ROOT/"README.md").read_text(encoding="utf-8")
        alias=(ROOT/"START_HERE.md").read_text(encoding="utf-8")
        gpu=(ROOT/"docs/free-cloud-gpu-images.md").read_text(encoding="utf-8")
        agent=(ROOT/"AGENTS.md").read_text(encoding="utf-8")
        for content in (main,alias,gpu,agent):
            self.assertIn("SH01",content)
        self.assertIn("README.md",alias)
        self.assertIn("trials.json",main)
        for content in (main,alias,gpu):
            self.assertNotIn("טרם בוצע ניסוי GPU מוצלח",content)
            self.assertNotIn("הרצת GPU אמיתית טרם אומתה",content)
        manifest=json.loads((EP/"manifest.json").read_text(encoding="utf-8"))
        self.assertFalse(manifest["production"]["release_authorized"])
        self.assertFalse(manifest["sources"]["torah_review"]["approved"])
        self.assertEqual(manifest["assets"],[])
        self.assertFalse(manifest["cost"]["external_spend_enabled"])

if __name__=="__main__":
    unittest.main()
