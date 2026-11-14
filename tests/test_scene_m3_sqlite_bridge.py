"""Strict offline interoperability: Python M3 owner validator -> Node SQLite DO core."""
import copy
import json
from pathlib import Path
import subprocess
import unittest

from tests.test_scene_m3_remote import M3RemoteTests

ROOT = Path(__file__).resolve().parents[1]
BRIDGE = ROOT / "infra/m3-coordinator/test-python-ticket-to-sqlite.mjs"


class OwnerTicketSqliteBridgeTests(unittest.TestCase):
    def setUp(self):
        # Uses the EXISTING M3 unit-test fixture's complete source/safety/
        # historical-journal checks. It does not approve a real scene.
        fixture = M3RemoteTests(methodName="test_prepared_batch_preserves_all_historical_attempts")
        fixture.setUp()
        self.admission = fixture.admission()
        self.assertEqual(self.admission["status"], "OFFLINE_TICKET_CHECKED_NO_LIVE_DISPATCH")

    def call_node(self, admission):
        return subprocess.run(
            ["node", str(BRIDGE)],
            input=json.dumps(admission, ensure_ascii=False),
            cwd=ROOT, text=True, capture_output=True, timeout=15,
            check=False,
        )

    def test_python_owner_scope_is_accepted_by_real_sqlite(self):
        p = self.call_node(self.admission)
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        j = json.loads(p.stdout)
        self.assertEqual(j["status"], "OFFLINE_VERIFIED_OWNER_TICKET_REACHED_SQLITE")
        self.assertEqual(j["historical_attempts"], 6)
        self.assertEqual(j["new_reserved_attempts"], 1)
        self.assertEqual(j["request_id"], self.admission["request_id"])
        self.assertTrue(j["requires_review"])  # A reservation cannot silently retry.
        self.assertEqual(j["external_inference_requests"], 0)
        self.assertFalse(j["live_dispatch_enabled"])

    def test_never_accepts_live_approval_or_cost(self):
        for mutation in (
            {"status": "PRODUCTION_APPROVED"},
            {"live_dispatch_enabled": True},
            {"max_charge_usd": 0.01},
            {"max_charge_usd": "0"},
            {"total_attempt_limit": 999},
            {"historical_attempts": -1},
            {"shot_ids": list(reversed(self.admission["shot_ids"])) +
                [self.admission["shot_ids"][0]]},
        ):
            with self.subTest(mutation=mutation):
                candidate = copy.deepcopy(self.admission)
                candidate.update(mutation)
                p = self.call_node(candidate)
                self.assertEqual(p.returncode, 2, p.stdout + p.stderr)
                j = json.loads(p.stdout)
                self.assertEqual(j["status"], "BLOCKED")
                self.assertEqual(j["external_inference_requests"], 0)
                self.assertFalse(j["live_dispatch_enabled"])


if __name__ == "__main__":
    unittest.main()
