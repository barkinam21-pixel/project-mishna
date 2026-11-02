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
       "וכל הנאכלין ליום אחד מצותן עד שיעלה עמוד השחר " + \
       "אם כן למה אמרו חכמים עד חצות כדי להרחיק את האדם מן העבירה"

LIVE_ONE_DAY_CLAUSES = (
    "וְכָל הַנֶּאֱכָלִים לְיוֹם אֶחָד, מִצְוָתָן עַד שֶׁיַּעֲלֶה עַמּוּד הַשָּׁחַר",
    "כָּל הַנֶּאֱכָלִים לְיוֹם אֶחָד, מִצְוָתָן עַד שֶׁיַּעֲלֶה עַמּוּד הַשַּׁחַר",
)
LIVE_KAUFMANN_OPENING = (
    "א מֵאֵמָּתַי קוֹרִין אֶת שְׁמַע בַּעֲרָבִים? "
    "מִשָּׁעָה שֶׁהַכֹּהֲנִים נִכְנָסִים לֹאכַל בִּתְרוּמָתָן, "
    "עַד סוֹף הָאַשְׁמֹרֶת הָרִאשׁוֹנָה. דִּבְרֵי רְבִּי אֱלִיעֶזֶר."
)


class ComparisonTests(unittest.TestCase):
    def example(self):
        readings = ("חיבין", "חייבין", "מתרין")
        return {"ref": "Mishnah Berakhot 1:1", "versions": [
            {"versionTitle": title, "license": "PD" if i == 2 else "Public Domain",
             "text": [UNIT.format(response=readings[i])]}
            for i, title in enumerate(TITLES)
        ]}

    def test_complete_unit_has_three_editions_and_all_required_markers(self):
        report = compare(self.example())
        self.assertEqual(report["status"], "three_versions_received_pending_human_review")
        self.assertEqual([x["sons_response_token"] for x in report["editions"]],
                         ["חיבין", "חייבין", "מתרין"])
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

    def test_rambam_one_day_clause_without_vav_and_with_comma_is_covered(self):
        payload = self.example()
        rambam_clause = "כל הנאכלים ליום אחד, מצותן עד שיעלה עמוד השחר"
        payload["versions"][0]["text"] = [
            UNIT.format(response="חיבין").replace(
                "וכל הנאכלין ליום אחד מצותן עד שיעלה עמוד השחר",
                rambam_clause,
            )
        ]
        report = compare(payload)
        edition = report["editions"][0]
        self.assertTrue(edition["coverage"]["one_day_offerings"])
        self.assertEqual(report["status"], "three_versions_received_pending_human_review")
        self.assertIn(rambam_clause, edition["full_text"])
        self.assertIn("כל/וכל", report["coverage_method_notes"]["one_day_offerings"])
        self.assertIn("original spellings and hashes remain separate",
                      report["coverage_method_notes"]["one_day_offerings"])
        self.assertIn("כל/וכל", render_html(report))

    def test_printed_one_day_clause_with_vav_and_em_dash_is_covered(self):
        payload = self.example()
        printed_clause = "וכל הנאכלין ליום אחד — מצוותן עד שיעלה עמוד השחר"
        payload["versions"][1]["text"] = [
            UNIT.format(response="חייבין").replace(
                "וכל הנאכלין ליום אחד מצותן עד שיעלה עמוד השחר",
                printed_clause,
            )
        ]
        report = compare(payload)
        edition = report["editions"][1]
        self.assertTrue(edition["coverage"]["one_day_offerings"])
        self.assertEqual(report["status"], "three_versions_received_pending_human_review")
        self.assertIn(printed_clause, edition["full_text"])

    def test_exact_live_vocalized_one_day_clauses_are_covered(self):
        baseline_clause = "וכל הנאכלין ליום אחד מצותן עד שיעלה עמוד השחר"
        for edition_index, live_clause in enumerate(LIVE_ONE_DAY_CLAUSES):
            with self.subTest(edition=TITLES[edition_index]):
                payload = self.example()
                payload["versions"][edition_index]["text"] = [
                    UNIT.format(response=("חיבין", "חייבין", "מתרין")[edition_index])
                    .replace(baseline_clause, live_clause)
                ]
                report = compare(payload)
                edition = report["editions"][edition_index]
                self.assertEqual(
                    report["status"],
                    "three_versions_received_pending_human_review",
                )
                self.assertTrue(edition["coverage"]["one_day_offerings"])
                self.assertIn(live_clause, edition["full_text"])
                self.assertIn(live_clause, render_html(report))
                self.assertTrue(edition["source_text_sha256"])
                self.assertFalse(edition["text_verified"])
                self.assertFalse(edition["torah_approved"])
                self.assertFalse(edition["release_authorized"])

    def test_exact_live_kaufmann_opening_and_first_watch_are_covered(self):
        baseline_opening = (
            "מאימתי קורין את שמע בערבית משעה שהכהנים נכנסים לאכול בתרומתן "
            "עד סוף האשמורה הראשונה דברי רבי אליעזר"
        )
        payload = self.example()
        payload["versions"][2]["text"] = [
            UNIT.format(response="מתרין").replace(
                baseline_opening,
                LIVE_KAUFMANN_OPENING,
            )
        ]
        report = compare(payload)
        edition = report["editions"][2]
        self.assertEqual(
            report["status"],
            "three_versions_received_pending_human_review",
        )
        self.assertTrue(all(edition["coverage"].values()))
        self.assertIn(LIVE_KAUFMANN_OPENING, edition["full_text"])
        self.assertIn(LIVE_KAUFMANN_OPENING, render_html(report))
        self.assertTrue(audit_ok(report))
        self.assertFalse(report["text_verified"])
        self.assertFalse(report["torah_approved"])
        self.assertFalse(report["release_authorized"])

    def test_missing_kaufmann_evening_or_first_watch_clause_fails_audit(self):
        missing_clauses = {
            "evening_shema_start": LIVE_KAUFMANN_OPENING.replace(
                "בַּעֲרָבִים", ""
            ),
            "eliezers_first_watch": LIVE_KAUFMANN_OPENING.replace(
                ", עַד סוֹף הָאַשְׁמֹרֶת הָרִאשׁוֹנָה.", "."
            ),
        }
        baseline_opening = (
            "מאימתי קורין את שמע בערבית משעה שהכהנים נכנסים לאכול בתרומתן "
            "עד סוף האשמורה הראשונה דברי רבי אליעזר"
        )
        for missing_marker, incomplete_opening in missing_clauses.items():
            with self.subTest(missing_marker=missing_marker):
                payload = self.example()
                payload["versions"][2]["text"] = [
                    UNIT.format(response="מתרין").replace(
                        baseline_opening,
                        incomplete_opening,
                    )
                ]
                report = compare(payload)
                edition = report["editions"][2]
                self.assertEqual(report["status"], "review_required")
                self.assertFalse(audit_ok(report))
                self.assertFalse(edition["coverage"][missing_marker])
                self.assertIn(
                    missing_marker,
                    {clause["key"] for clause in edition["missing_unit_clauses"]},
                )
                self.assertFalse(report["text_verified"])
                self.assertFalse(report["torah_approved"])
                self.assertFalse(report["release_authorized"])

    def test_one_day_clause_word_match_requires_attested_word_boundary(self):
        payload = self.example()
        payload["versions"][0]["text"] = [
            UNIT.format(response="חיבין").replace(
                "וכל הנאכלין",
                "ובכל הנאכלין",
            )
        ]
        report = compare(payload)
        self.assertFalse(report["editions"][0]["coverage"]["one_day_offerings"])
        self.assertEqual(report["status"], "review_required")

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

    def test_unexpected_meaningful_kaufmann_reading_fails_technical_audit(self):
        payload = self.example()
        payload["versions"][2]["text"] = [UNIT.format(response="חייבין")]
        result = compare(payload)
        self.assertEqual(result["status"], "review_required")
        self.assertEqual(result["editions"][2]["sons_response_token"], "חייבין")
        self.assertEqual(result["editions"][2]["sons_response_original"], "חייבין")
        self.assertTrue(result["editions"][2]["unexpected_meaningful_reading"])
        self.assertTrue(any(
            warning.startswith("unexpected_meaningful_reading:")
            for warning in result["warnings"]
        ))
        self.assertFalse(audit_ok(result))
        self.assertFalse(result["textual_variants_reviewed"])
        self.assertFalse(result["torah_approved"])

    def test_html_exposes_exact_word_level_variants_without_editorial_substitution(self):
        report = compare(self.example())
        differences = report["word_level_differences"]["comparisons"]
        self.assertEqual(len(differences), 2)
        kaufmann = differences[1]
        self.assertFalse(kaufmann["withheld_due_to_rights"])
        self.assertTrue(any(
            "חיבין" in difference["reference_words"]
            and "מתרין" in difference["edition_words"]
            for difference in kaufmann["differences"]
        ))
        rendered = render_html(report)
        self.assertIn("הבדלי מילים מול המהדורה הראשונה", rendered)
        self.assertIn("<mark><bdi dir=\"rtl\">חיבין</bdi></mark>", rendered)
        self.assertIn("<mark><bdi dir=\"rtl\">חייבין</bdi></mark>", rendered)
        self.assertIn("<mark><bdi dir=\"rtl\">מתרין</bdi></mark>", rendered)
        self.assertIn("אין זו הצעת תיקון או הכרעה", rendered)

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
        self.assertTrue(
            report["word_level_differences"]["comparisons"][0]["withheld_due_to_rights"]
        )

    def test_incomplete_story_is_detected(self):
        payload = self.example()
        payload["versions"][0]["text"] = ["מאימתי קורין את שמע בערבית"]
        report = compare(payload)
        self.assertEqual(report["status"], "review_required")
        self.assertFalse(report["editions"][0]["coverage"]["burning_fats_and_limbs"])

    def test_missing_one_day_offerings_clause_fails_and_is_exposed(self):
        payload = self.example()
        missing_clause = "וכל הנאכלין ליום אחד מצותן עד שיעלה עמוד השחר "
        payload["versions"][0]["text"] = [
            UNIT.format(response="חיבין").replace(missing_clause, "")
        ]
        report = compare(payload)
        edition = report["editions"][0]
        self.assertEqual(report["status"], "review_required")
        self.assertFalse(audit_ok(report))
        self.assertFalse(edition["coverage"]["one_day_offerings"])
        self.assertEqual(
            edition["missing_unit_clauses"],
            [{
                "key": "one_day_offerings",
                "description": "וכל הנאכלין/הנאכלים ליום אחד — מצוותן עד עמוד השחר",
            }],
        )
        self.assertTrue(any(
            "Missing required one-day-offerings clause" in warning
            for warning in report["warnings"]
        ))
        self.assertFalse(report["text_locked"])
        self.assertFalse(report["text_verified"])
        self.assertFalse(report["textual_variants_reviewed"])
        self.assertFalse(report["rights_reviewed"])
        self.assertFalse(report["torah_approved"])
        self.assertFalse(report["release_authorized"])
        page = render_html(report)
        self.assertIn("סעיפים נדרשים שחסרים", page)
        self.assertIn("וכל הנאכלין/הנאכלים ליום אחד", page)

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
