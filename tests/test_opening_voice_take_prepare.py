import copy
import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tools.opening_voice_take_prepare import (APPROVED_REFERENCE_SHA, PROFILE, SEGMENTS,
                                                build)

ROOT = Path(__file__).resolve().parents[1]


class OpeningVoicePreparationTests(unittest.TestCase):
    def test_source_locked_single_take_not_submittable(self):
        result = build(ROOT)
        self.assertEqual(result["type"], "PRIVATE_VOICE_PREPARATION_NOT_A_PROVIDER_REQUEST")
        self.assertEqual(result["narrator_profile"], PROFILE)
        self.assertEqual(result["expected_total_words"], 109)
        self.assertEqual([x["id"] for x in result["segment_boundaries"]], list(SEGMENTS))
        self.assertEqual(len(result["beat_anchors_provisional"]), 7)
        self.assertTrue(result["single_continuous_take"])
        self.assertTrue(result["one_speaker"])
        self.assertFalse(result["tts_submission_permitted"])
        self.assertFalse(result["real_scene_recording_exists"])
        self.assertFalse(result["source_text_approved"])
        self.assertFalse(result["release_authorized"])
        self.assertEqual(result["generation_requests_made"], 0)
        self.assertEqual(result["approved_sample_sha256"], APPROVED_REFERENCE_SHA)
        self.assertTrue(result["approved_sample_is_not_target_scene_audio"])
        self.assertFalse(result["verified_no_charge_tts_route_available"])
        self.assertEqual(result["baseline_settings_unchanged"]["seed"], "not exposed")
        self.assertIsNone(result["baseline_settings_unchanged"]["reference_audio"])
        for x in result["beat_anchors_provisional"]:
            self.assertIsNone(x["exact_cut_frame"])
            self.assertIsNone(x["estimated_seconds"])
            self.assertFalse(x["shot_approved"])
            voice = next(s["spoken_text"] for s in result["segment_boundaries"]
                         if s["id"] == x["voice_id"])
            self.assertIn(x["spoken_phrase_anchor"], voice)
        self.assertEqual([x["shot_id"] for x in result["beat_anchors_provisional"]],
                         ["OPN01", "OPN02", "OPN03", "OPN04", "OPN05", "OPN06", "OPN07"])
        self.assertEqual(result, build(ROOT))

    def test_previous_audition_is_not_repurposed_as_scene_recording(self):
        result = build(ROOT)
        old_audition = json.loads((ROOT / "episodes/berakhot-01-01/voice-rehearsal-draft.json")
                                  .read_text())["speakers"]["narrator"]["production_baseline_profile"]
        self.assertEqual(result["approved_performance_direction_unchanged"],
                         old_audition["exact_direction"])
        self.assertNotEqual(result["single_take_spoken_text"],
                            old_audition["original_audition_text"])
        self.assertNotIn("ואז הגיע החורבן", result["single_take_spoken_text"])
        self.assertEqual(result["approved_sample_sha256"],
                         old_audition["approved_wav"]["sha256"])

    def test_changed_voice_registry_blocks_automated_packet(self):
        registry_path = ROOT / "episodes/berakhot-01-01/voice-rehearsal-draft.json"
        original = json.loads(registry_path.read_text())
        changed = copy.deepcopy(original)
        changed["speakers"]["narrator"]["production_baseline_profile"]["voice_name"] = "Different"
        with patch("tools.opening_voice_take_prepare.json.loads", wraps=json.loads) as loads:
            def safe_loads(s, *a, **k):
                result = json.loads(s, *a, **k)
                if isinstance(result, dict) and "speakers" in result:
                    return changed
                return result
            loads.side_effect = safe_loads
            with self.assertRaisesRegex(ValueError, "baseline changed"):
                build(ROOT)

    def test_corrupt_script_hash_blocks_packet(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for path in ("scripts/introduction-working-draft.md",
                         "docs/evidence/introduction-script-audit-2026-11-06.json",
                         "episodes/berakhot-01-01/voice-rehearsal-draft.json"):
                dest = root / path
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy(ROOT / path, dest)
            path = root / "scripts/introduction-working-draft.md"
            path.write_text(path.read_text() + "\nשינוי לא מאושר", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "Script master modified"):
                build(root)


if __name__ == "__main__":
    unittest.main()
