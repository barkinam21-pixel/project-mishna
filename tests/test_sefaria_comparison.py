from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from compare_sefaria_editions import TITLES, compare, clean_text


UNIT = "מאימתי קורין את שמע בערבית משעה שהכהנים נכנסים לאכול בתרומתן " + \
       "עד סוף האשמורה הראשונה דברי רבי אליעזר וחכמים אומרים עד חצות " + \
       "רבן גמליאל אומר עד שיעלה עמוד השחר מעשה שבאו בניו מבית המשתה " + \
       "אמרו לו לא קרינו את שמע אמר להם אם לא עלה עמוד השחר {response} אתם לקרות " + \
       "ולא זו בלבד אלא כל שאמרו חכמים עד חצות מצותן עד שיעלה עמוד השחר " + \
       "הקטר חלבים ואברים מצותן עד שיעלה עמוד השחר " + \
       "אם כן למה אמרו חכמים עד חצות כדי להרחיק את האדם מן העבירה"


class ComparisonTests(unittest.TestCase):
    def example(self):
        return {"ref": "Mishnah Berakhot 1:1", "versions": [
            {"versionTitle": title, "license": "PD" if i == 2 else "Public Domain",
             "text": [UNIT.format(response="מותרין" if i == 2 else "חייבין")]}
            for i, title in enumerate(TITLES)
        ]}

    def test_all_versions_and_meaningful_variant(self):
        report = compare(self.example())
        self.assertEqual(report["status"], "three_versions_received_pending_human_review")
        self.assertEqual([x["sons_response_token"] for x in report["editions"]],
                         ["חייבין", "חייבין", "מותרין"])
        self.assertFalse(report["text_locked"])
        self.assertFalse(report["release_authorized"])

    def test_missing_edition_cannot_pass(self):
        payload = self.example()
        payload["versions"].pop()
        report = compare(payload)
        self.assertEqual(report["status"], "review_required")
        self.assertTrue(report["warnings"])

    def test_unverified_rights_block_comparison_ready(self):
        payload = self.example()
        payload["versions"][1]["license"] = "unknown"
        self.assertEqual(compare(payload)["status"], "review_required")

    def test_incomplete_story_is_detected(self):
        payload = self.example()
        payload["versions"][0]["text"] = ["מאימתי קורין את שמע בערבית"]
        self.assertEqual(compare(payload)["status"], "review_required")

    def test_bad_payload_not_crash(self):
        self.assertEqual(compare({"versions": None})["status"], "review_required")
        self.assertEqual(clean_text({"text": [["nested"]]}), "")


if __name__ == "__main__":
    unittest.main()
