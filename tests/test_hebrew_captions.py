from copy import deepcopy
from pathlib import Path
import sys
import unittest
import unicodedata

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from hebrew_captions import emit, graphemes, timestamp, validate


def sample():
    return {
        "fps": 24, "language": "he",
        "source_text_locked": True,
        "human_torah_review_approved": True,
        "caption_text_approved": True,
        "cues": [
            {"id": "TEST-01", "start_frame": 0, "end_frame": 72,
             "display_text": "בדיקה בעברית\nכתובית שנייה",
             "spoken_text": "בדיקה בעברית כתובית שנייה",
             "pronunciation_text": "בדיקה בעברית כתובית שנייה",
             "speaker": "synthetic_test_only",
             "source": "synthetic_fixture_not_a_Mishnah_quote", "shot_id": "test-shot"},
            {"id": "TEST-02", "start_frame": 96, "end_frame": 168,
             "display_text": "בדיקת זמן וכתוביות",
             "spoken_text": "בדיקת זמן וכתוביות",
             "pronunciation_text": "בדיקת זמן וכתוביות",
             "speaker": "synthetic_test_only",
             "source": "synthetic_fixture_not_a_Mishnah_quote", "shot_id": "test-shot"}
        ]
    }


class HebrewCaptionTests(unittest.TestCase):
    def test_sample_exports_all_three_formats(self):
        files, qa = emit(sample())
        self.assertTrue(qa["valid"])
        self.assertIn("00:00:03,000", files["srt"])
        self.assertIn("WEBVTT", files["vtt"])
        self.assertIn("00:00:04.000 --> 00:00:07.000", files["vtt"])
        self.assertIn("PlayResX: 1920", files["ass"])
        self.assertIn("Noto Sans Hebrew", files["ass"])
        self.assertIn(r"\N", files["ass"])
        self.assertNotIn("TEST-01", files["srt"])

    def test_unapproved_text_must_not_export(self):
        data = sample()
        data["human_torah_review_approved"] = False
        self.assertFalse(validate(data)["valid"])
        with self.assertRaises(ValueError):
            emit(data)

    def test_source_not_locked_blocks(self):
        data = sample()
        data["source_text_locked"] = False
        self.assertFalse(validate(data)["valid"])

    def test_bidi_override_and_replacement_rejected(self):
        data = sample()
        data["cues"][0]["display_text"] = "שלום\u202e עולם"
        self.assertFalse(validate(data)["valid"])
        data["cues"][0]["display_text"] = "שלום\ufffd"
        self.assertFalse(validate(data)["valid"])

    def test_latin_and_ass_injection_rejected(self):
        data = sample()
        data["cues"][0]["display_text"] = "HELLO שלום"
        self.assertFalse(validate(data)["valid"])
        data["cues"][0]["display_text"] = "שלום {\\alpha}"
        self.assertFalse(validate(data)["valid"])

    def test_line_length_and_three_lines_rejected(self):
        data = sample()
        data["cues"][0]["display_text"] = "ש" * 43
        self.assertFalse(validate(data)["valid"])
        data["cues"][0]["display_text"] = "שלום\nשלום\nשלום"
        self.assertFalse(validate(data)["valid"])

    def test_timing_overlap_rejected(self):
        data = sample()
        data["cues"][1]["start_frame"] = 60
        self.assertFalse(validate(data)["valid"])
        data["cues"][1]["start_frame"] = 168
        data["cues"][1]["end_frame"] = 169
        self.assertIn("duration", " ".join(validate(data)["warnings"]))

    def test_non_normalized_hebrew_rejected(self):
        data = sample()
        data["cues"][0]["display_text"] = "שָׁלוֹם"
        non_nfc = unicodedata.normalize("NFD", data["cues"][0]["display_text"])
        data["cues"][0]["display_text"] = non_nfc
        self.assertFalse(validate(data)["valid"])

    def test_niqqud_not_extra_graphemes(self):
        self.assertEqual(graphemes("שָׁלוֹם"), 4)

    def test_integer_frame_timestamp_never_accumulates_drift(self):
        self.assertEqual(timestamp(1800, "srt"), "00:01:15,000")
        self.assertEqual(timestamp(1800, "vtt"), "00:01:15.000")
        self.assertEqual(timestamp(1800, "ass"), "0:01:15.00")
        self.assertEqual(timestamp(1, "srt"), "00:00:00,042")

    def test_malformed_master_returns_error(self):
        self.assertFalse(validate(None)["valid"])
        data = sample()
        data["cues"][0]["start_frame"] = None
        self.assertFalse(validate(data)["valid"])


if __name__ == "__main__":
    unittest.main()
