import html
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from compare_sefaria_editions import (
    TITLES,
    UNIT_MARKERS,
    audit_ok,
    clean_text,
    compare,
    render_html,
)


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

    def test_complete_unit_has_three_editions_and_all_nine_markers(self):
        report = compare(self.example())
        self.assertEqual(report["status"], "three_versions_received_pending_human_review")
        self.assertEqual([x["sons_response_token"] for x in report["editions"]],
                         ["חייבין", "חייבין", "מותרין"])
        self.assertEqual(len(report["editions"]), 3)
        for edition in report["editions"]:
            self.assertEqual(set(edition["coverage"]), set(UNIT_MARKERS))
            self.assertTrue(all(edition["coverage"].values()))
            self.assertEqual(edition["word_count"], len(UNIT.split()))
            self.assertTrue(edition["source_text_sha256"])
            self.assertTrue(edition["normalized_text_sha256"])
            self.assertFalse(edition["text_verified"])
            self.assertFalse(edition["torah_approved"])
            self.assertFalse(edition["release_authorized"])
        self.assertFalse(report["text_locked"])
        self.assertFalse(report["text_verified"])
        self.assertFalse(report["textual_variants_reviewed"])
        self.assertFalse(report["rights_reviewed"])
        self.assertFalse(report["torah_approved"])
        self.assertFalse(report["release_authorized"])

    def test_niqqud_does_not_trigger_false_incomplete(self):
        payload = self.example()
        vocalized = UNIT.format(response="חַיָּבִין").replace(
            "מאימתי", "מֵאֵימָתַי"
        ).replace("אמר להם", "אָמַר לָהֶם").replace(
            "להרחיק", "לְהַרְחִיק"
        ).replace("העבירה", "הָעֲבֵירָה")
        payload["versions"][0]["text"] = [vocalized]
        report = compare(payload)
        self.assertEqual(report["status"], "three_versions_received_pending_human_review")
        self.assertEqual(report["editions"][0]["sons_response_token"], "חיבין")
        self.assertEqual(report["editions"][0]["sons_response_meaning"], "obligation")
        self.assertIn("חַיָּבִין", report["editions"][0]["sons_response_original"])
        self.assertIn("מֵאֵימָתַי", report["editions"][0]["full_text"])

    def test_real_world_defective_spelling(self):
        payload = self.example()
        payload["versions"][0]["text"] = [UNIT.format(response="חיבין")]
        payload["versions"][2]["text"] = [UNIT.format(response="מתרין")]
        report = compare(payload)
        self.assertEqual(report["status"], "three_versions_received_pending_human_review")
        self.assertEqual([x["sons_response_meaning"] for x in report["editions"]],
                         ["obligation", "obligation", "permission"])

    def test_alternate_reading_is_preserved_without_selecting_a_winner(self):
        payload = self.example()
        payload["versions"][2]["text"] = [UNIT.format(response="חייבין")]
        result = compare(payload)
        self.assertEqual(
            result["status"], "three_versions_received_pending_human_review"
        )
        self.assertEqual(result["editions"][2]["sons_response_token"], "חייבין")
        self.assertFalse(result["textual_variants_reviewed"])
        self.assertFalse(result["torah_approved"])

    def test_missing_edition_cannot_pass(self):
        payload = self.example()
        payload["versions"].pop()
        report = compare(payload)
        self.assertEqual(report["status"], "review_required")
        self.assertTrue(report["warnings"])
        self.assertEqual(len(report["editions"]), 3)
        self.assertFalse(report["editions"][2]["received"])

    def test_unverified_rights_block_comparison_ready(self):
        payload = self.example()
        payload["versions"][1]["license"] = "unknown"
        report = compare(payload)
        self.assertEqual(report["status"], "review_required")
        self.assertFalse(report["editions"][1]["full_text_included"])
        self.assertIsNone(report["editions"][1]["full_text"])

    def test_incomplete_story_is_detected(self):
        payload = self.example()
        payload["versions"][0]["text"] = ["מאימתי קורין את שמע בערבית"]
        report = compare(payload)
        self.assertEqual(report["status"], "review_required")
        self.assertFalse(report["editions"][0]["coverage"]["burning_fats_and_limbs"])

    def test_unknown_license_keeps_only_a_bounded_comparison_excerpt(self):
        payload = self.example()
        protected_suffix = "סיום מלא ייחודי שאסור לשכפל"
        payload["versions"][0]["text"] = [
            UNIT.format(response="חייבין") + " " + protected_suffix
        ]
        payload["versions"][0]["license"] = "unknown"
        report = compare(payload)
        edition = report["editions"][0]
        self.assertFalse(edition["full_text_included"])
        self.assertIsNone(edition["full_text"])
        self.assertIn("חייבין", edition["comparison_excerpt"])
        self.assertNotIn(protected_suffix, edition["comparison_excerpt"])
        self.assertNotIn(protected_suffix, render_html(report))

    def test_html_is_self_contained_rtl_and_escapes_text(self):
        report = compare(self.example())
        report["editions"][0]["full_text"] = '<script>alert("x")</script> & טקסט'
        output = render_html(report)
        self.assertIn('<html lang="he" dir="rtl">', output)
        self.assertIn('<meta name="viewport"', output)
        self.assertIn("&lt;script&gt;alert(&quot;x&quot;)&lt;/script&gt;", output)
        self.assertIn("&amp; טקסט", output)
        self.assertNotIn("<script>alert", output)
        self.assertNotIn("<link", output)
        self.assertNotIn("<script", output)

    def test_exact_edition_urls_and_version_specific_licenses_are_reported(self):
        report = compare(self.example())
        self.assertEqual(
            [edition["license_declared_by_sefaria"] for edition in report["editions"]],
            ["Public Domain", "Public Domain", "PD"],
        )
        self.assertTrue(all(
            "version=hebrew%7C" in edition["edition_url"]
            for edition in report["editions"]
        ))
        rendered = render_html(report)
        self.assertTrue(all(title in html.unescape(rendered) for title in TITLES))
        self.assertIn("רישיון לפי מטא־נתוני ספריא", rendered)
        self.assertIn("לא הכרעה", rendered)

    def test_network_unavailable_cannot_be_green(self):
        self.assertFalse(audit_ok({"status": "unavailable", "warnings": ["network failure"]}))
        self.assertFalse(audit_ok({"status": "review_required", "warnings": []}))
        self.assertTrue(audit_ok(compare(self.example())))

    def test_bad_payload_not_crash(self):
        self.assertEqual(compare({"versions": None})["status"], "review_required")
        self.assertEqual(clean_text({"text": [["nested"]]}), "")


if __name__ == "__main__":
    unittest.main()
