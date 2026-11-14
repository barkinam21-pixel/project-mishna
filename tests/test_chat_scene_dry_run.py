"""Existing owner GitHub bridge -> offline-only scene preflight tests."""
import copy
import datetime as dt
import json
import re
import unittest
from pathlib import Path

from tools.chat_issue_bridge import (
    RequestBlocked, extract, make_request, validate_event
)

ROOT = Path(__file__).resolve().parents[1]


class ChatSceneDryRunTests(unittest.TestCase):
    def setUp(self):
        self.now = dt.datetime(2026, 11, 14, 12, tzinfo=dt.timezone.utc)
        self.request_id = "d" * 32
        self.issue_body = make_request(
            "Preserve original Issue #54 notes.", "scene-dry-run",
            self.request_id, self.now.isoformat(),
        )
        self.event = {
            "action": "edited",
            "repository": {"full_name": "barkinam21-pixel/project-mishna",
                           "owner": {"login": "barkinam21-pixel"}},
            "sender": {"login": "barkinam21-pixel"},
            "issue": {"number": 54, "state": "open", "body": self.issue_body},
            "changes": {"body": {"from": "Preserve original Issue #54 notes."}},
        }

    def test_owner_can_request_one_readonly_scene_check(self):
        r = validate_event(self.event, self.now)
        self.assertEqual(r["status"], "VALIDATED_READ_ONLY")
        self.assertEqual(r["operation"], "scene-dry-run")
        self.assertEqual(r["request_id"], self.request_id)
        self.assertFalse(r["generation_authorized"])
        self.assertEqual(r["remote_writes"], 0)
        self.assertIn("Preserve original Issue", self.issue_body)

    def test_no_duplicate_edit_or_foreign_actor(self):
        e = copy.deepcopy(self.event)
        e["changes"]["body"]["from"] = self.issue_body
        self.assertEqual(validate_event(e, self.now)["status"], "IGNORED_UNCHANGED_REQUEST_ID")
        e = copy.deepcopy(self.event)
        e["sender"]["login"] = "not-owner"
        with self.assertRaises(RequestBlocked):
            validate_event(e, self.now)

    def test_command_injection_and_unsafe_actions_are_not_allowlisted(self):
        v = extract(self.issue_body)
        for operation in (
            "scene-dry-run; curl https://evil.invalid",
            "scene-generate",
            "scene-approve",
            "scene-assemble-live",
            "scene-dry-run\n echo bad",
        ):
            bad = "```mishnah-readonly-request\n" + json.dumps({
                **v, "operation": operation,
            }) + "\n```"
            with self.subTest(operation=operation), self.assertRaises(RequestBlocked):
                extract(bad)

    def test_workflow_scene_job_is_no_secret_and_bounded(self):
        txt = (ROOT / ".github/workflows/chat-readonly-command.yml").read_text(encoding="utf-8")
        self.assertIn("group: mishnah-chat-readonly-command", txt)
        self.assertIn("queue: max", txt)
        self.assertIn("scene-dry-run:", txt)
        self.assertIn("needs.validate-request.outputs.operation == 'scene-dry-run'", txt)
        job = txt.split("\n  scene-dry-run:", 1)[1].split("\n  generation-preflight:", 1)[0]
        self.assertIn("github.actor == github.repository_owner", job)
        self.assertIn("tools.scene_factory','dry-run'", job)
        self.assertIn("SCENE_DRY_RUN_NOT_SAFELY_BLOCKED", job)
        self.assertIn("rm -rf private-media", job)
        for forbidden in (
            "secrets.", "CLOUDFLARE_API_TOKEN", "MISHNAH_DRIVE_OAUTH_JSON",
            "tools.generation_issue_runtime", "github.event.issue.body",
            "upload-artifact", "private_drive_runtime",
        ):
            self.assertNotIn(forbidden, job)
        self.assertIn("ref: ${{ github.sha }}", job)
        self.assertNotIn("contents: write", txt)
        self.assertNotIn("issues: write", txt)


if __name__ == "__main__":
    unittest.main()
