"""Guardrails: missing approvals must be a blocked status, not a fake success."""
import json
import tempfile
import unittest
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "tools" / "session_handoff.py"
spec = spec_from_file_location("session_handoff", SCRIPT)
tool = module_from_spec(spec)
spec.loader.exec_module(tool)


def manifest():
    return {
        "episode_id": "berakhot-01-01",
        "production": {"fps": 24, "sample_rate": 48000, "release_authorized": False},
        "sources": {
            "working_text": "", "text_verified": False, "textual_variants_reviewed": False,
            "rights_reviewed": False, "torah_review": {"approved": False},
            "production_text_candidate": {"text_locked": False},
            "independent_witnesses": [{"checked": True}, {"checked": True}],
        },
        "creative": {
            "script_approved": False, "visual_direction_approved": False,
            "voice_approved": False, "proof_approved": False,
        },
        "shots": [], "assets": [],
        "cost": {"max_external_usd": 0, "external_spend_enabled": False, "workspace_usage": "unknown"},
        "release": {"rights_cleared": False, "technical_qa_passed": False, "human_approval": False},
    }


def voice():
    return {
        "episode_id": "berakhot-01-01", "fps": 24, "sample_rate": 48000,
        "segments": [{"id": "N01", "audio_path": "audio/rehearsals/n01.wav"}],
    }


class HandoffTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.master = self.root / "manifest.json"
        self.voices = self.root / "voice.json"

    def report(self, master=None, voices=None):
        self.master.write_text(json.dumps(master if master is not None else manifest()), encoding="utf-8")
        self.voices.write_text(json.dumps(voices if voices is not None else voice()), encoding="utf-8")
        return tool.audit(self.root, self.master, self.voices)

    def test_initial_state_is_blocked_not_broken(self):
        r = self.report()
        self.assertEqual(r["stage"], "sources")
        self.assertEqual(r["health"], "WORKFLOW_HEALTHY_RELEASE_BLOCKED")
        self.assertEqual(r["evidence"]["voice_files_missing_in_checkout"], 1)
        self.assertEqual(r["errors"], [])
        self.assertFalse(r["codex_now"])

    def test_release_without_gates_fails(self):
        m = manifest()
        m["production"]["release_authorized"] = True
        self.assertIn("RELEASE_AUTHORIZED_WITH_UNSATISFIED_GATES", self.report(master=m)["errors"])

    def test_voice_false_approval_fails(self):
        m = manifest()
        m["creative"]["voice_approved"] = True
        self.assertIn("VOICE_APPROVED_BUT_NO_REHEARSAL_FILES", self.report(master=m)["errors"])

    def test_proof_false_approval_fails(self):
        m = manifest()
        m["creative"]["proof_approved"] = True
        self.assertIn("PROOF_APPROVED_BUT_NO_SHOTS_OR_ASSETS", self.report(master=m)["errors"])

    def test_invalid_path_is_rejected(self):
        v = voice()
        v["segments"][0]["audio_path"] = "../../secret.wav"
        self.assertIn("INVALID_VOICE_PATH_AT_0", self.report(voices=v)["errors"])

    def test_wrong_audio_clock_is_rejected(self):
        v = voice()
        v["sample_rate"] = 44100
        self.assertIn("VOICE_TIMING_STANDARD_MISMATCH", self.report(voices=v)["errors"])

    def test_report_language_and_limitations(self):
        markdown = tool.as_markdown(self.report())
        for required in ("Codex", "לא כעת", "אינם", "הצעד הבא"):
            self.assertIn(required, markdown)

    def test_corrupted_manifest_reports_error(self):
        self.master.write_text("{broken", encoding="utf-8")
        self.voices.write_text(json.dumps(voice()), encoding="utf-8")
        with self.assertRaises(ValueError):
            tool.audit(self.root, self.master, self.voices)


if __name__ == "__main__":
    unittest.main()
