"""Prove the old one-shot Issue54 ticket maps into the new SQLite protocol.

No Drive API, deployed Worker, Cloudflare model or credentials are used.
"""
import copy
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import unittest

from tools.chat_issue_bridge import RequestBlocked, validate_generation_event
from tools.legacy_generation_coordination import (
    legacy_offline_admission, stage_offline_reservation,
)
from tests.test_generation_ticket import GenerationTicketTests

ROOT = Path(__file__).resolve().parents[1]
SQLITE_BRIDGE = ROOT / "infra/m3-coordinator/test-python-ticket-to-sqlite.mjs"


def prepared():
    f=GenerationTicketTests()
    f.setUp()
    # The actual private ledger already has 6 attempts; these are deliberately
    # fictional entries and never substituted into the user's Drive journal.
    f.history["attempts"].extend([
        {"key": "SYNTHETIC-HIST-5"}, {"key": "SYNTHETIC-HIST-6"}
    ])
    f.ticket["historical_attempts"]=6
    f.ticket["total_attempt_limit"]=7
    f.ticket["history_sha256"]=hashlib.sha256(json.dumps(
        f.history,sort_keys=True,separators=(",",":")
    ).encode()).hexdigest()
    ticket=validate_generation_event(f.event(),f.policy,f.history,f.now)
    return ticket,f.history


class FakeOfflineCoordinator:
    def __init__(self):
        self.begin_calls=[]
        self.reserve_calls=[]
        self.replayed=False

    def begin_offline(self,scope):
        self.begin_calls.append(copy.deepcopy(scope))
        return {"status":"OFFLINE_READY","replay":self.replayed,
                "live_dispatch_enabled":False}

    def reserve_offline(self,rid,shot):
        self.reserve_calls.append((rid,shot))
        self.replayed=True
        return {"status":"OFFLINE_RESERVED_UNCERTAIN_NO_RETRY",
                "live_dispatch_enabled":False,"external_inference_requests":0}


class LegacyGenerationCoordinationTests(unittest.TestCase):
    def test_exact_existing_owner_ticket_becomes_offline_m3_scope(self):
        ticket,history=prepared()
        scope=legacy_offline_admission(ticket,history)
        self.assertEqual(scope["scene_id"],"ACT1-PROLOGUE")
        self.assertEqual(scope["shot_ids"],["OPN02"])
        self.assertEqual(scope["asset_keys"],{"OPN02":ticket["spec_sha256"]})
        self.assertEqual(scope["historical_attempts"],6)
        self.assertEqual(scope["total_attempt_limit"],7)
        self.assertFalse(scope["live_dispatch_enabled"])
        self.assertEqual(scope["max_charge_usd"],0)

    def test_offline_reservation_is_once_only_never_a_provider_permit(self):
        ticket,history=prepared()
        coord=FakeOfflineCoordinator()
        out=stage_offline_reservation(ticket,history,coord)
        self.assertEqual(out["status"],"M3_LEGACY_TICKET_RESERVED_OFFLINE_ONLY")
        self.assertFalse(out["provider_submission_authorized"])
        self.assertEqual(out["external_inference_requests"],0)
        self.assertEqual(len(coord.begin_calls),1)
        self.assertEqual(len(coord.reserve_calls),1)
        with self.assertRaisesRegex(RequestBlocked,"BEGIN_NOT_FRESH"):
            stage_offline_reservation(ticket,history,coord)
        self.assertEqual(len(coord.reserve_calls),1)

    def test_changed_scope_history_cost_and_replay_block(self):
        ticket,history=prepared()
        changes=(
            ({"max_charge_usd":1},history),
            ({"total_attempt_limit":8},history),
            ({"spec_sha256":"not-sha"},history),
            ({"shot_id":"OPN04"},history),
            ({"status":"FAKE_OWNER_APPROVAL"},history),
            ({},dict(history,attempts=history["attempts"][:-1])),
            ({},dict(history,attempts=history["attempts"] + [
                {"request_id":ticket["request_id"]}
            ])),
        )
        for mutation,h in changes:
            with self.subTest(mutation=mutation,n=len(h["attempts"])):
                t={**ticket,**mutation}
                with self.assertRaises(RequestBlocked):
                    legacy_offline_admission(t,h)

    def test_forged_coordinator_results_are_rejected(self):
        ticket,history=prepared()
        for field,value in (
            ("status","APPROVED_FOR_AI"),("live_dispatch_enabled",True),
            ("external_inference_requests",1),
        ):
            class Forged(FakeOfflineCoordinator):
                def reserve_offline(self,rid,shot):
                    r=super().reserve_offline(rid,shot)
                    r[field]=value
                    return r
            with self.subTest(field=field):
                with self.assertRaisesRegex(RequestBlocked,"RESERVATION_UNVERIFIED"):
                    stage_offline_reservation(ticket,history,Forged())

    @unittest.skipUnless(shutil.which("node"), "Node required for SQLite integration")
    def test_legacy_validated_ticket_runs_through_actual_node_sqlite(self):
        ticket,history=prepared()
        scope=legacy_offline_admission(ticket,history)
        p=subprocess.run(
            ["node",str(SQLITE_BRIDGE)],input=json.dumps(scope),
            capture_output=True,text=True,cwd=ROOT,timeout=15,
        )
        self.assertEqual(p.returncode,0,p.stdout+p.stderr)
        out=json.loads(p.stdout)
        self.assertEqual(out["status"],"OFFLINE_VERIFIED_OWNER_TICKET_REACHED_SQLITE")
        self.assertEqual(out["historical_attempts"],6)
        self.assertEqual(out["new_reserved_attempts"],1)
        self.assertFalse(out["live_dispatch_enabled"])
        self.assertEqual(out["external_inference_requests"],0)

    def test_repository_runner_keeps_old_live_path_closed(self):
        code=(ROOT/"tools/generation_issue_runtime.py").read_text()
        self.assertIn("M3_LIVE_ATOMIC_COORDINATOR_NOT_CONNECTED_NO_INFERENCE",code)
        self.assertIn("stage_offline_reservation(ticket,history,coordinator)",code)
        self.assertIn("M3_OFFLINE_RESERVATION_IS_NOT_LIVE_DISPATCH_PERMISSION",code)
        workflow=(ROOT/".github/workflows/chat-readonly-command.yml").read_text()
        self.assertIn("python ../control/tools/generation_issue_runtime.py",workflow)
        self.assertIn("ref: 80ba1559b785855a1f9f4cbd90083fd0228eec96",workflow)
        self.assertIn("needs.generation-preflight.outputs.ready == 'true'",workflow)
        # Reject future unguarded direct calls to pinned runtime CLI instead
        # of the reviewed control-side entrypoint and its M3 safety gate.
        self.assertNotIn("python -m tools.generation_issue_runtime",workflow)


if __name__=="__main__":
    unittest.main()
