import unittest
from tools.pacing_audit import review, parse_clock


class PacingAuditTests(unittest.TestCase):
    def test_frames_integer_and_sequence_contiguous(self):
        md = (
            '### רצף 1 — התחלה (כ־0:00–0:10)\n[קריין]\n"שלום לכולם."\n'
            '### רצף 2 — המשך (כ־0:10–0:20)\n[קריין]\n"עוד רגע."\n'
        )
        result = review(md, target_wpm=125)
        self.assertEqual(result["total_frames"], 480)
        self.assertEqual(result["samples_per_frame"], 2000)
        self.assertEqual(result["sequence_count"], 2)
        self.assertFalse(result["recorded_audio_verified"])
        self.assertEqual(result["errors"], [])

    def test_gap_flagged(self):
        md = (
            '### רצף 1 — אחד (כ־0:00–0:10)\n"שלום"\n'
            '### רצף 2 — שניים (כ־0:11–0:20)\n"עולם"\n'
        )
        self.assertTrue(review(md)["errors"])

    def test_overfull_scene(self):
        text = " ".join(["מילה"] * 50)
        md = '### רצף 1 — דחוס (כ־0:00–0:10)\n"' + text + '"\n'
        result = review(md)
        self.assertEqual(result["needs_review"], [1])

    def test_clock_and_bad_parameters(self):
        self.assertEqual(parse_clock("13:30"), 810)
        with self.assertRaises(ValueError):
            parse_clock("0:61")
        with self.assertRaises(ValueError):
            review('### רצף 1 — א (כ־0:00–0:10)\n"שלום"', 200)


if __name__ == "__main__":
    unittest.main()
