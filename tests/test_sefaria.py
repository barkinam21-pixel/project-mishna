import sys
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from fetch_sefaria import summarize_source

class SourceProbeTests(unittest.TestCase):
    def test_exact_public_domain_version_is_not_auto_approved(self):
        response = {"ref": "Mishnah Berakhot 1:1", "versions": [
            {"versionTitle": "Torat Emet 357", "license": "Public Domain",
             "text": ["מאימתי קורין את שמע בערבית רבן גמליאל אומר חייבין אתם לקרות"]}
        ]}
        result = summarize_source(response)
        self.assertEqual(result["status"], "text_received_pending_human_review")
        self.assertTrue(result["has_chayavin"])
        self.assertFalse(result["text_locked"])
        self.assertTrue(result["human_review_required"])
        self.assertNotIn("text", result)

    def test_different_edition_is_not_silently_substituted(self):
        response = {"versions": [{"versionTitle": "Other", "license": "Public Domain", "text": ["מאימתי"]}]}
        self.assertEqual(summarize_source(response)["status"], "unverified")

    def test_restricted_license_cannot_be_cleared(self):
        response = {"versions": [{"versionTitle": "Torat Emet 357", "license": "CC-BY-NC", "text": ["מאימתי"]}]}
        self.assertEqual(summarize_source(response)["status"], "rights_not_verified")

if __name__ == "__main__":
    unittest.main()
