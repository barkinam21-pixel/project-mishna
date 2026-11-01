"""Prevent duplicate user loops: one active studio, multiple real trials, no false approvals."""
import json
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[1]
EP=ROOT/"episodes"/"berakhot-01-01"

class SingleControlRoomTest(unittest.TestCase):
    def test_trial_ledger_records_both_sh01_and_sh09_without_false_approval(self):
        data=json.loads((EP/"trials.json").read_text(encoding="utf-8"))
        self.assertEqual(data["episode_id"],"berakhot-01-01")
        expected = {
            "SH01": "e3647bad6668aebd69810a105dba4df4bd2cfa73ba78cf18269171e73444166d",
            "SH09": "61f1eaa344ebf344169fd35ec9b392cf818e9c9734b51118c5bf0255b8f29717",
        }
        self.assertEqual({t["shot_id"] for t in data["trials"]}, set(expected))
        self.assertEqual(len({t["image_sha256"] for t in data["trials"]}), len(expected))
        for shot in data["trials"]:
            self.assertEqual(shot["status"], "generated_unapproved")
            self.assertEqual(shot["image_sha256"], expected[shot["shot_id"]])
            self.assertFalse(shot["production_asset_accepted"])
            self.assertFalse(shot["archive_in_repository"])
        self.assertIn("one", data["trials"][-1]["artistic_issue"].lower())

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
            "actions/workflows/studio-check.yml",
            "docs/operator-decisions.md", "episodes/berakhot-01-01/source-dossier.md",
            "episodes/berakhot-01-01/manifest.json", "episodes/berakhot-01-01/trials.json",
            "sefaria-three-edition-audit", "Chrome", "אין צורך להתקין",
            "אינו מאשר נוסח/זכויות/קריינות",
        ):
            self.assertIn(expected, main)
        # Do not freeze navigation to historical PR/issue numbers (PR #2 is already merged).
        self.assertRegex(main, r"issues/\d+")
        self.assertRegex(main, r"pull/\d+")
        # A blocked hosted run must not be described as passing or as an approved film.
        self.assertIn("action_required", main)
        self.assertIn("אין לטעון שהריצה הצליחה", main)
        self.assertIn("אין עדיין סרט אמיתי", main)

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
