import copy
import json
import shutil
import tempfile
import unittest
from pathlib import Path
from tools.opening_caption_prepare import build, cue_cards, extract, MAX_LINE, VOICE

ROOT = Path(__file__).resolve().parents[1]


class OpeningCaptionPreparationTests(unittest.TestCase):
    def test_script_hash_and_exact_unapproved_captions(self):
        report = build(ROOT)
        self.assertEqual([s["id"] for s in report["segments"]], list(VOICE))
        self.assertGreater(report["card_count"], 0)
        self.assertEqual(report["provider_calls"], 0)
        self.assertFalse(report["timing_measured"])
        self.assertFalse(report["narration_generated"])
        self.assertFalse(report["scene_assets_approved"])
        self.assertFalse(report["release_authorized"])
        for segment in report["segments"]:
            self.assertFalse(segment["source_text_approved"])
            self.assertEqual(segment["recording_status"], "NOT_RECORDED")
            self.assertEqual(" ".join(c["spoken_text"] for c in segment["cards"]),
                             " ".join(segment["source_text"].split()))
            for card in segment["cards"]:
                self.assertIsNone(card["start_frame"])
                self.assertIsNone(card["end_frame"])
                self.assertFalse(card["approved"])
                self.assertEqual(card["timing_status"], "UNALIGNED_WITH_REAL_WAV")
                lines = card["display_text"].splitlines()
                self.assertTrue(1 <= len(lines) <= 2)
                self.assertTrue(all(0 < len(line) <= MAX_LINE for line in lines))
        self.assertEqual(report, build(ROOT))

    def test_changed_script_is_detected_before_emitting_captions(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "scripts").mkdir()
            (root / "docs/evidence").mkdir(parents=True)
            shutil.copy(ROOT / "docs/evidence/introduction-script-audit-2026-11-06.json",
                        root / "docs/evidence/introduction-script-audit-2026-11-06.json")
            original = (ROOT / "scripts/introduction-working-draft.md").read_text()
            (root / "scripts/introduction-working-draft.md").write_text(original + "\nשינוי")
            with self.assertRaisesRegex(ValueError, "Script master modified"):
                build(root)

    def test_unknown_or_duplicated_cue_is_rejected(self):
        source = (ROOT / "scripts/introduction-working-draft.md").read_text()
        with self.assertRaisesRegex(ValueError, "exactly one narration"):
            extract(source, "INTRO-A1-S01-N99")
        with self.assertRaisesRegex(ValueError, "exactly one narration"):
            extract(source + "\n\n**קריינות מקורית · INTRO-A1-S01-N01**\n> כפילות",
                    "INTRO-A1-S01-N01")

    def test_overlong_word_is_not_silently_truncated(self):
        with self.assertRaisesRegex(ValueError, "line limit"):
            cue_cards("א" * (MAX_LINE + 1), "INTRO-A1-S01-N01")

    def test_two_line_rtl_preserves_exact_punctuation(self):
        text = "מה יקרה כאשר האדם שלימד כבר לא יהיה שם כדי להשיב? זה המסע."
        cards = cue_cards(text, VOICE[0])
        self.assertEqual(" ".join(c["spoken_text"] for c in cards), text)
        self.assertTrue(all(len(c["display_text"].splitlines()) <= 2 for c in cards))


if __name__ == "__main__":
    unittest.main()
