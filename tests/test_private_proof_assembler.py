"""Safety regressions for the real-media-only private film assembler.

These are offline tests. Any artificial WAV/image bytes are deliberately TEST
FIXTURES, not footage, Hebrew speech, approved art or production assets.
"""
import copy
import json
from pathlib import Path
import tempfile
import unittest
import wave

from tools import private_proof_assembler as proof


class PrivateProofTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.blueprint = json.loads(proof.BLUEPRINT.read_text(encoding="utf-8"))
        cls.example = json.loads(proof.EXAMPLE.read_text(encoding="utf-8"))

    def test_actual_repository_is_blocked_and_cannot_claim_a_film(self):
        report = proof.audit(copy.deepcopy(self.example), self.blueprint)
        self.assertEqual(report["status"], "BLOCKED_MISSING_REAL_MEDIA")
        self.assertEqual(report["expected_shots"], 16)
        self.assertEqual(report["supplied_images"], 0)
        self.assertEqual(report["real_voice_takes"], 0)
        self.assertEqual(report["total_frames"], 1800)
        self.assertTrue(any("real Hebrew spoken WAV" in s for s in report["missing"]))
        self.assertFalse(report["release_authorized"])
        self.assertNotIn("video", report)

    def test_private_hebrew_caption_rehearsal_covers_all_16_shots_without_false_approval(self):
        from tools import hebrew_captions
        filename = proof.ROOT / "episodes/berakhot-01-01/private-proof-caption-draft.json"
        draft = json.loads(filename.read_text(encoding="utf-8"))
        self.assertFalse(draft["source_text_locked"])
        self.assertFalse(draft["human_torah_review_approved"])
        self.assertFalse(draft["caption_text_approved"])
        self.assertFalse(draft["release_authorized"])
        result = hebrew_captions.validate(draft, require_approval=False)
        self.assertTrue(result["valid"], result["errors"])
        self.assertFalse(result["warnings"], result["warnings"])
        shots = {item["id"]: item for item in self.blueprint["shots"]}
        self.assertEqual(len(draft["cues"]), 16)
        self.assertEqual(set(shots), {cue["shot_id"] for cue in draft["cues"]})
        for cue in draft["cues"]:
            shot = shots[cue["shot_id"]]
            self.assertEqual(cue["start_frame"], shot["start_frame"])
            self.assertEqual(cue["end_frame"], shot["end_frame"])
            self.assertFalse(cue["source_approved"])

    def test_private_caption_master_must_match_episode_and_each_shot(self):
        # The generic subtitle validator deliberately permits gaps and does
        # not know the video shot IDs. The private renderer must not silently
        # show valid Hebrew captions over the wrong illustration or episode.
        from tools import hebrew_captions
        draft = json.loads(
            (proof.ROOT / "episodes/berakhot-01-01/private-proof-caption-draft.json")
            .read_text(encoding="utf-8")
        )
        for case in ("timing_shift", "repeated_shot", "wrong_episode"):
            with self.subTest(case=case), tempfile.TemporaryDirectory() as directory:
                altered = copy.deepcopy(draft)
                if case == "timing_shift":
                    altered["cues"][2]["start_frame"] += 24  # legal gap, wrong shot timing
                elif case == "repeated_shot":
                    altered["cues"][2]["shot_id"] = altered["cues"][1]["shot_id"]
                else:
                    altered["episode_id"] = "berakhot-01-02"
                # Each mutation remains well-formed Hebrew subtitle data.
                self.assertTrue(hebrew_captions.validate(altered, require_approval=False)["valid"])
                root = Path(directory)
                (root / "captions.json").write_text(
                    json.dumps(altered, ensure_ascii=False), encoding="utf-8"
                )
                config = copy.deepcopy(self.example)
                config["caption_master"] = "captions.json"
                report = proof.audit(config, self.blueprint, root)
                self.assertEqual(report["status"], "INVALID", report)
                self.assertTrue(any("caption" in error.lower()
                                    for error in report["errors"]), report)

    def test_external_spend_or_release_cannot_be_enabled(self):
        for key in ("external_spend_enabled", "release_authorized"):
            config = copy.deepcopy(self.example)
            config[key] = True
            report = proof.audit(config, self.blueprint)
            self.assertEqual(report["status"], "INVALID")
            self.assertTrue(any("spending or release" in s for s in report["errors"]))

    def test_missing_images_and_path_traversal_are_not_accepted(self):
        config = copy.deepcopy(self.example)
        config["images"] = [{
            "shot_id": "SH01", "path": "../../some-other-file.png",
            "sha256": "0" * 64, "accepted_for_private_preview": True,
            "original_illustration": True,
            "rights_verified_for_private_preview": True,
            "license": "original", "provenance": "TEST ONLY"
        }]
        with tempfile.TemporaryDirectory() as directory:
            report = proof.audit(config, self.blueprint, directory)
            self.assertEqual(report["status"], "INVALID")
            self.assertIn("SH01: unsafe image path or type", report["errors"])

    def test_sh01_rejected_trial_hash_cannot_be_rebranded(self):
        trial = json.loads(
            (proof.ROOT / "episodes/berakhot-01-01/trials.json").read_text(encoding="utf-8")
        )["trials"][0]
        self.assertFalse(trial["production_asset_accepted"])
        config = copy.deepcopy(self.example)
        config["images"] = [{
            "shot_id": "SH01", "path": "assets/SH01.png",
            "sha256": trial["image_sha256"],
            "accepted_for_private_preview": True,
            "original_illustration": True,
            "rights_verified_for_private_preview": True,
            "license": "original", "provenance": "DO NOT USE SH01"
        }]
        report = proof.audit(config, self.blueprint, proof.ROOT)
        self.assertEqual(report["status"], "INVALID")
        self.assertTrue(any("unapproved SH01 trial" in x for x in report["errors"]))

    def test_duplicate_image_assets_do_not_count_as_original_coverage(self):
        config = copy.deepcopy(self.example)
        for shot_id in ("SH01", "SH02"):
            config["images"].append({
                "shot_id": shot_id, "path": "media/" + shot_id + ".png",
                "sha256": "a" * 64, "accepted_for_private_preview": True,
                "original_illustration": True, "rights_verified_for_private_preview": True,
                "license": "original", "provenance": "TEST ONLY"
            })
        report = proof.audit(config, self.blueprint, proof.ROOT)
        self.assertEqual(report["status"], "INVALID")
        self.assertTrue(any("duplicate asset" in x for x in report["errors"]))

    def test_private_render_refuses_unready_media_before_writing(self):
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory) / "film"
            with self.assertRaisesRegex(ValueError, "PRIVATE RENDER BLOCKED"):
                proof.render_private(self.example, self.blueprint, proof.ROOT, out)
            self.assertFalse(out.exists())

    def test_wav_header_audit_does_not_mistake_silence_for_voice(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "test_only_silent.wav"
            with wave.open(str(path), "wb") as wav:
                wav.setnchannels(1)
                wav.setsampwidth(2)
                wav.setframerate(48000)
                wav.writeframes(b"\x00\x00" * 2000)
            frames, error = proof.inspect_wav(path)
            self.assertIsNone(frames)
            self.assertIn("silent", error)

    def test_command_builds_real_image_voice_and_soft_subtitle_streams(self):
        # Construct argv only; no fake image/audio is rendered or uploaded.
        config = copy.deepcopy(self.example)
        config["images"] = [
            {"shot_id": item["id"], "path": "media/" + item["id"] + ".png"}
            for item in self.blueprint["shots"]
        ]
        config["voice_takes"] = [{"start_frame": 288, "path": "media/voice.wav"}]
        with tempfile.TemporaryDirectory() as directory:
            args = proof.ffmpeg_args(config, self.blueprint, Path(directory), Path(directory))
            joined = " ".join(args)
            self.assertEqual(args[0], "ffmpeg")
            self.assertIn("concat=n=16:v=1:a=0", joined)
            self.assertIn("adelay=delays=576000S:all=1", joined)
            self.assertIn("ass=filename=private-captions.ass", joined)
            self.assertIn("mov_text", args)
            self.assertIn("1800", args)
            self.assertNotIn("sync-test.wav", joined)
            self.assertNotIn("lavfi", joined)


if __name__ == "__main__":
    unittest.main()
