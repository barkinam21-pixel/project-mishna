"""Static, fail-closed checks for the only deployed legacy live producer.

No Cloudflare/Drive credentials in PR CI. Tests protect the serialized owner
workflow boundary, not external Drive's unsupported atomic-CAS guarantee.
"""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LIVE = ROOT / ".github/workflows/chat-readonly-command.yml"
M3_WORKFLOWS = [
    ROOT / ".github/workflows/scene-factory-m3.yml",
    ROOT / ".github/workflows/scene-factory-m3-ticket.yml",
]

class ProductionWorkflowSerializationTests(unittest.TestCase):
    def test_owner_live_workflow_queues_instead_of_replacing_pending(self):
        content = LIVE.read_text(encoding="utf-8")
        self.assertRegex(
            content,
            r"(?m)^concurrency:\n  group: mishnah-chat-readonly-command\n"
            r"  cancel-in-progress: false\n  queue: max\n",
        )
        self.assertIn("github.event.issue.number == 54", content)
        self.assertIn("github.actor == github.repository_owner", content)
        self.assertIn("generation-once:", content)
        self.assertIn("needs: generation-preflight", content)
        self.assertIn("needs.generation-preflight.outputs.ready == 'true'", content)
        self.assertIn("ref: 80ba1559b785855a1f9f4cbd90083fd0228eec96", content)

    def test_m3_offline_workflows_have_no_provider_secrets_or_live_dispatch(self):
        for path in M3_WORKFLOWS:
            content = path.read_text(encoding="utf-8")
            for forbidden in (
                "secrets.CLOUDFLARE_API_TOKEN", "secrets.MISHNAH_DRIVE_OAUTH_JSON",
                "tools.generation_issue_runtime", "private_drive_runtime",
            ):
                self.assertNotIn(forbidden, content, (path, forbidden))
            self.assertIn("permissions:\n  contents: read", content)

    def test_legacy_live_workflow_secret_only_in_gated_job(self):
        content = LIVE.read_text(encoding="utf-8")
        gated = content.split("\n  generation-once:", 1)
        self.assertEqual(len(gated), 2)
        self.assertNotIn("secrets.CLOUDFLARE_API_TOKEN", gated[0])
        self.assertIn("if: needs.generation-preflight.outputs.ready == 'true'", gated[1])
        self.assertIn("CLOUDFLARE_API_TOKEN: ${{ secrets.CLOUDFLARE_API_TOKEN }}", gated[1])


if __name__ == "__main__":
    unittest.main()
