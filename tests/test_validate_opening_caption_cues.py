"""Offline opening captions: chronology, dramatization, phone-safety and timing.

No provider/API calls, image creation, TTS or private files.
"""
import copy
import importlib.util
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "opening_caption_cues", ROOT / "tools/validate_opening_caption_cues.py"
)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)
DIRECTOR = json.loads(
    (ROOT / "episodes/berakhot-01-01/opening-45s-director-pack-v1.json")
    .read_text(encoding="utf-8")
)
CAPTIONS = json.loads(
    (ROOT / "episodes/berakhot-01-01/opening-45s-caption-cues-draft.json")
    .read_text(encoding="utf-8")
)


class OpeningCaptionCuesTest(unittest.TestCase):
    def setUp(self):
        self.c = copy.deepcopy(CAPTIONS)
        self.d = copy.deepcopy(DIRECTOR)

    def assert_rejected(self):
        self.assertEqual(MODULE.validate(self.c, self.d)["status"], "BLOCKED")

    def test_first_seven_shots_dry_run_passes(self):
        result = MODULE.validate(self.c, self.d)
        self.assertEqual(result["status"], "PASS_DRY_RUN_ONLY", result["errors"])
        self.assertEqual(result["cue_count"], 4)
        self.assertEqual(result["dialogue_cues"], 3)
        self.assertFalse(result["actual_voice_timing_verified"])
        self.assertFalse(result["actual_phone_render_verified"])

    def test_cannot_drop_dramatization_label(self):
        self.c["cues"].pop(0)
        self.assert_rejected()

    def test_cannot_claim_first_caption_is_historical(self):
        self.c["cues"][0]["display_text_he"] = "זהו תיעוד היסטורי"
        self.assert_rejected()

    def test_cannot_switch_to_sons_first(self):
        self.c["next_paid_shot_candidate"] = "SH09"
        self.assert_rejected()

    def test_cannot_claim_fal_paid_authorization(self):
        self.c["no_cloud_spend_authorized"] = False
        self.assert_rejected()

    def test_cannot_claim_voice_was_recorded(self):
        self.c["dialogue_audio_recorded"] = True
        self.assert_rejected()

    def test_wrong_dialogue_or_speaker_is_rejected(self):
        self.c["cues"][1]["speaker"] = "המבוגר"
        self.assert_rejected()

    def test_dialogue_must_stay_identical_to_director_pack(self):
        self.c["cues"][2]["spoken_text_he"] = "נוכל ללכת יחד."
        self.assert_rejected()

    def test_caption_cannot_escape_its_shot(self):
        self.c["cues"][1]["end_frame"] = 600
        self.assert_rejected()

    def test_caption_cannot_escape_audio_window(self):
        self.c["cues"][3]["audio_spot_id"] = "AUD01"
        self.assert_rejected()

    def test_overlapping_cues_blocked(self):
        self.c["cues"][2]["start_frame"] = 400
        self.assert_rejected()

    def test_overfast_reading_rejected(self):
        self.c["cues"][3]["end_frame"] = self.c["cues"][3]["start_frame"] + 30
        self.assert_rejected()

    def test_more_than_two_lines_rejected(self):
        self.c["cues"][1]["display_text_he"] = "ואם מחר\nלא תהיה איתי...\nאיך אדע את הדרך?"
        self.assert_rejected()

    def test_hidden_bidi_override_rejected(self):
        self.c["cues"][1]["display_text_he"] += "\u202e"
        self.assert_rejected()

    def test_non_nfc_hebrew_rejected(self):
        self.c["cues"][1]["display_text_he"] += "ש\u05c1"
        self.c["cues"][1]["display_text_he"] += "\u05b8"  # non-canonical order
        self.assert_rejected()

    def test_phone_safe_margins_cannot_disappear(self):
        self.c["font_policy"]["phone_safe_bottom_margin_ratio"] = 0.0
        self.assert_rejected()

    def test_timeline_cannot_claim_completed_render(self):
        self.c["caption_video_rendered"] = True
        self.assert_rejected()


if __name__ == "__main__":
    unittest.main()
