"""Offline safety and continuity regression checks for Berakhot Act II shotpack.

Checks are editorial planning assertions only. They do NOT generate media or
claim artwork, voice, human Torah review or publication approval.
"""
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACK = ROOT / "episodes/berakhot-01-01/sons-return-performance-shotpack-v1.json"
SCRIPT = ROOT / "episodes/berakhot-01-01/feature-screenplay-act2-draft.md"


class SonsReturnContinuityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pack = json.loads(PACK.read_text(encoding="utf-8"))
        cls.script = SCRIPT.read_text(encoding="utf-8")

    def test_distinct_unmade_original_artwork(self):
        shots = self.pack["shots"]
        originals = [s["original_art"] for s in shots]
        self.assertEqual(len(shots), 16)
        self.assertEqual(len(set(originals)), len(originals))
        self.assertTrue(all(s["asset_status"] == "not_generated" for s in shots))
        self.assertTrue(all(p["is_distinct_original_illustration"] for p in self.pack["pose_keys"]))
        self.assertTrue(all(p["asset_status"] == "not_generated" for p in self.pack["pose_keys"]))
        group_ids = {g["id"] for g in self.pack["groups"]}
        self.assertEqual({s["group"] for s in shots}, group_ids)
        for group in self.pack["groups"]:
            n = len({s["original_art"] for s in shots if s["group"] == group["id"]})
            self.assertEqual(n, group["required_originals"])
            self.assertGreaterEqual(n, 4)
            self.assertLessEqual(n, 7)

    def test_four_distinct_pose_keys_and_leftward_walk(self):
        poses = self.pack["pose_keys"]
        self.assertEqual([p["id"] for p in poses], ["P1", "P2", "P3", "P4"])
        a = [p["son_a_x"] for p in poses]
        b = [p["son_b_x"] for p in poses]
        self.assertTrue(all(a[i] > a[i + 1] for i in range(3)))
        self.assertTrue(all(b[i] > b[i + 1] for i in range(3)))
        self.assertTrue(all(0 < x < 1 for x in a + b))
        self.assertEqual(
            {s.get("pose_key") for s in self.pack["shots"] if s.get("pose_key")},
            {p["id"] for p in poses},
        )
        self.assertEqual(self.pack["set_lock"]["exterior"]["travel_direction"], "right_to_left")
        self.assertEqual(self.pack["set_lock"]["exterior"]["door_side"], "left")

    def test_axis_reset_is_visible_before_interior(self):
        ids = [s["id"] for s in self.pack["shots"]]
        self.assertLess(ids.index("G02-03"), ids.index("G03-01"))
        self.assertIn("threshold", self.pack["set_lock"])
        self.assertTrue(self.pack["set_lock"]["interior"]["no_axis_flip"])
        self.assertEqual(self.pack["set_lock"]["interior"]["sons_side"], "left")
        self.assertEqual(self.pack["set_lock"]["interior"]["father_side"], "right")
        self.assertEqual(self.pack["set_lock"]["interior"]["door_side"], "rear_left")
        self.assertEqual(self.pack["set_lock"]["threshold"]["bridge"].split(",")[0], "frontally neutral crossing shot")

    def test_no_generation_spending_or_publish_authorization(self):
        safety = self.pack["safety"]
        self.assertEqual(self.pack["status"], "editorial_dry_run_only")
        self.assertTrue(safety["private_media_only"])
        self.assertFalse(safety["new_image_generation_allowed"])
        self.assertFalse(safety["paid_external_request_allowed"])
        self.assertFalse(safety["paid_video_allowed"])
        self.assertFalse(safety["publication_allowed"])
        self.assertFalse(safety["provider_called_in_this_run"])
        self.assertEqual(safety["asset_generation_count_this_run"], 0)
        self.assertTrue(safety["imagegen_forbidden"])
        self.assertTrue(safety["tinyfish_forbidden"])
        self.assertTrue(safety["public_repo_text_only"])
        self.assertFalse(safety["keys_or_signed_urls_present"])
        self.assertFalse(self.pack["sources"]["direct_quote_allowed"])
        self.assertEqual(self.pack["sources"]["torah_review"], "not_approved")

    def test_technical_motion_contract(self):
        contract = self.pack["render_contract"]
        self.assertEqual(contract["fps"], 24)
        self.assertEqual(contract["audio_sample_rate_hz"], 48000)
        self.assertEqual(contract["camera_shake_px"], 0)
        self.assertEqual(contract["camera_speed_factor_vs_v10_for_relevant_moves"], 1.15)
        self.assertEqual(contract["walking_speed_multiplier"], 1)
        self.assertEqual(contract["speech_speed_multiplier"], 1)
        self.assertTrue(contract["no_frame_skips"])
        for shot in self.pack["shots"]:
            self.assertIsInstance(shot["frames"], int)
            self.assertGreater(shot["frames"], 0)
            self.assertEqual(shot["frames"] % 24, 0)
            self.assertTrue(shot["camera"] == "locked" or "1.15" in shot["camera"])

    def test_coverage_cannot_be_misreported_as_finished_feature(self):
        coverage = self.pack["coverage_scope"]
        total = sum(s["frames"] for s in self.pack["shots"])
        self.assertEqual(coverage["placeholder_frames_total"], total)
        self.assertEqual(coverage["placeholder_seconds_total"], total / 24)
        self.assertTrue(coverage["not_a_complete_film"])
        self.assertTrue(coverage["not_the_75_second_technical_animatic"])
        self.assertTrue(coverage["not_act_runtime"])
        self.assertTrue(coverage["timing_estimate_unverified"])
        self.assertIn("לא סרט", coverage["notice_he"])

    def test_source_layers_and_dramatization_not_historical_dialogue(self):
        self.assertEqual(
            self.pack["dramatic_contract"]["historically_attested_number_of_sons"], "unknown"
        )
        self.assertEqual(
            self.pack["dramatic_contract"]["physical_meeting_of_different_named_tannaim"],
            "not_shown",
        )
        self.assertEqual(
            self.pack["dramatic_contract"]["spoken_variant_quotation"],
            "prohibited_pending_review",
        )
        self.assertIn("חייבין/מותרין", self.script)
        self.assertIn("המחזה", self.script)
        self.assertIn("לא להקלטה", self.script)
        self.assertIn("ברטנורא", self.script)
        self.assertIn("רמב״ם", self.script)
        for shot in self.pack["shots"]:
            self.assertIn(
                shot["source_status"],
                {"dramatization", "educational_metaphor", "interpretation_attributed"},
            )


if __name__ == "__main__":
    unittest.main()
