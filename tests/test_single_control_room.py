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

    def test_mobile_dashboard_links_workflow_and_approval_evidence(self):
        main=(ROOT/"README.md").read_text(encoding="utf-8")
        for expected in (
            "actions/workflows/studio-check.yml", "issues/1", "pull/2",
            "docs/operator-decisions.md", "episodes/berakhot-01-01/source-dossier.md",
            "episodes/berakhot-01-01/manifest.json", "episodes/berakhot-01-01/trials.json",
            "Artifacts", "דפדפן בטלפון", "אין צורך להפעיל אותו ידנית",
        ):
            self.assertIn(expected,main)

    def test_ci_runs_on_pull_requests_and_keeps_handoff_before_tests(self):
        workflow=(ROOT/".github/workflows/studio-check.yml").read_text(encoding="utf-8")
        self.assertIn("  pull_request:\n    branches: [main]",workflow)
        self.assertLess(
            workflow.index("Generate truthful stage-gate and Codex session handoff"),
            workflow.index("Unit tests"),
        )
        self.assertIn("if-no-files-found: error",workflow)

if __name__=="__main__":
    unittest.main()
