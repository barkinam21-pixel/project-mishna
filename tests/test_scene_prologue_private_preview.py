"""No-network regression tests for the real scene-native M2 private rough cut.

Not a film approval: synthetic inputs are generated only inside TemporaryDirectory.
"""
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from tools.scene_factory import SceneBlocked
from tools.scene_production_packet import build_packet
from tools.scene_prologue_private_preview import (
    SCENE, _private_path, build_plan, render_private_draft,
)
from tools.private_proof_assembler import ffmpeg_args

ROOT = Path(__file__).resolve().parents[1]


class ScenePrivatePreviewTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="mishna-draft-fixture-")
        self.root = Path(self.tmp.name)
        scene = json.loads((ROOT / SCENE).read_text(encoding="utf-8"))
        paths = [SCENE, scene["bible"]["path"], scene["script"]["path"]]
        for name in paths:
            output = self.root / name
            output.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ROOT / name, output)
        (self.root / "private-media").mkdir()
        bible = json.loads((self.root / scene["bible"]["path"]).read_text(encoding="utf-8"))
        self.packet = build_packet(scene, bible, self.root)
        self.first = self.packet["jobs"][0]

    def tearDown(self):
        self.tmp.cleanup()

    def test_actual_fifteen_shot_scene_is_the_timeline(self):
        p = build_plan(self.root)
        self.assertEqual(p["scene_id"], "ACT1-PROLOGUE")
        self.assertEqual(p["total_frames"], 2184)
        self.assertEqual(len(p["shots"]), 15)
        self.assertEqual(p["missing_or_unapproved_images"], 15)
        self.assertEqual(p["verified_hebrew_voice_clips"], 0)
        self.assertEqual(p["original_image_inference_requests"], 0)
        self.assertFalse(p["editorial_source_rights_approval"])
        self.assertEqual(p["shots"][0]["start_frame"], 0)
        self.assertEqual(p["shots"][-1]["end_frame"], 2184)
        self.assertEqual([s["shot_id"] for s in p["shots"]],
                         [f"EP-P{i:02d}" for i in range(1, 16)])

    def test_empty_plan_stable_does_not_require_cloud_or_drive(self):
        self.assertEqual(build_plan(self.root)["preview_key"],
                         build_plan(self.root, {"images": [], "voices": []})["preview_key"])

    def test_m2_ffmpeg_receives_scene_native_shots_without_aliases(self):
        p = build_plan(self.root)
        blueprint = {"target_duration_frames": p["total_frames"],
                     "shots": [{"id": s["shot_id"], "duration_frames": s["duration_frames"]}
                               for s in p["shots"]]}
        config = {"images": [{"shot_id": s["shot_id"], "path": "private-media/test.png"}
                             for s in p["shots"]],
                  "voice_takes": [{"start_frame": 0, "path": "private-media/silence.wav"}]}
        argv = ffmpeg_args(config, blueprint, self.root, self.root)
        self.assertIn("2184", argv)
        self.assertEqual(argv.count("-loop"), 15)
        self.assertEqual(argv[argv.index("-frames:v") + 1], "2184")
        self.assertNotIn("OPN02", " ".join(argv))

    def test_two_shot_private_preview_real_ffmpeg_short_smoke(self):
        if not all(shutil.which(x) for x in ("ffmpeg", "ffprobe", "fc-match")):
            self.skipTest("FFmpeg/font tooling unavailable")
        from unittest.mock import patch
        import tools.scene_prologue_private_preview as preview
        slates = [{"shot_id": f"EP-P{i:02d}", "start_frame": (i-1)*24,
                   "end_frame": i*24, "duration_frames": 24,
                   "purpose": "לוח בדיקה בלבד", "source_layer": "symbolic_dramatization",
                   "image": None, "media_status": "MISSING_OR_UNAPPROVED_SLATE"}
                  for i in (1, 2)]
        plan = {"scene_id": "ACT1-PROLOGUE", "preview_key": "f"*64,
                "total_frames": 48, "shots": slates, "voices": [], "sounds": [],
                "verified_private_preview_images": 0,
                "missing_or_unapproved_images": 2,
                "verified_hebrew_voice_clips": 0,
                "verified_private_sound_stems": 0}
        with patch.object(preview, "build_plan", return_value=plan):
            report = render_private_draft(self.root, "private-media/smoke.mp4")
            self.assertEqual(report["status"], "PRIVATE_DRAFT_TECH_PASS_NOT_ART_OR_SOURCE_APPROVAL")
            self.assertEqual(report["frames"], 48)
            self.assertEqual(report["slates_for_missing_images"], 2)
            self.assertTrue(report["placeholder_silence"])
            self.assertEqual(report["provider_calls"], 0)
            self.assertTrue((self.root / "private-media/smoke.mp4").is_file())
            self.assertTrue((self.root / "private-media/smoke.srt").is_file())
            cached = render_private_draft(self.root, "private-media/smoke.mp4")
            self.assertTrue(cached["cache_hit"])
            srt = self.root / "private-media/smoke.srt"
            original = srt.read_bytes()
            srt.write_text("TAMPERED SUBTITLE", encoding="utf-8")
            with self.assertRaisesRegex(SceneBlocked, "PREVIEW_CACHED_OUTPUT_CHANGED"):
                render_private_draft(self.root, "private-media/smoke.mp4")
            srt.write_bytes(original)
            ass = self.root / "private-media/smoke.ass"
            ass.unlink()
            with self.assertRaisesRegex(SceneBlocked, "PREVIEW_PARTIAL_OUTPUT_EXISTS"):
                render_private_draft(self.root, "private-media/smoke.mp4")

    def test_unknown_duplicate_legacy_or_outside_bindings_blocked(self):
        entry = {"shot_id": "OPN02", "asset_key": self.first["asset_key"]}
        with self.assertRaisesRegex(SceneBlocked, "PREVIEW_UNKNOWN_SHOT_BINDING"):
            build_plan(self.root, {"images": [entry]})
        sid = self.first["shot_id"]
        entry.update({"shot_id": sid})
        with self.assertRaisesRegex(SceneBlocked, "PREVIEW_IMAGE_SCOPE_OR_RIGHTS"):
            build_plan(self.root, {"images": [entry]})
        from unittest.mock import patch
        entry["path"] = "private-media/fixture.png"
        with patch("tools.scene_prologue_private_preview._checked_image",
                   return_value=(self.root / "private-media/fixture.png", "0" * 64)):
            with self.assertRaisesRegex(SceneBlocked, "PREVIEW_DUPLICATE_SHOT_BINDING"):
                build_plan(self.root, {"images": [entry, entry]})

    def test_valid_private_image_binding_uses_exact_bytes_and_sha(self):
        # Tiny hand-authored PNG from existing test utility: never dispatched.
        import struct, zlib
        def chunk(tag, raw):
            return struct.pack(">I", len(raw)) + tag + raw + struct.pack(">I", zlib.crc32(tag + raw) & 0xffffffff)
        raw = b"".join(b"\0" + bytes((30, 40, 50)) * 2 for _ in range(2))
        path = self.root / "private-media/fixture.png"
        path.write_bytes(
            b"\x89PNG\r\n\x1a\n"
            + chunk(b"IHDR", struct.pack(">IIBBBBB", 2, 2, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw))
            + chunk(b"IEND", b"")
        )
        from tools.scene_factory import file_sha
        sid = self.first["shot_id"]
        entry = {
            "shot_id": sid, "source_asset_id": sid,
            "asset_key": self.first["asset_key"],
            "time_of_day": "dawn",
            "path": "private-media/fixture.png", "sha256": file_sha(path),
            "accepted_for_private_preview": True,
            "rights_verified_for_private_preview": True,
            "rights_evidence": "TEST ONLY: self-authored synthetic image",
        }
        plan = build_plan(self.root, {"images": [entry]})
        self.assertEqual(plan["verified_private_preview_images"], 1)
        self.assertEqual(plan["missing_or_unapproved_images"], 14)
        self.assertEqual(plan["shots"][0]["media_status"], "VERIFIED_PRIVATE_PREVIEW_ONLY")
        entry["sha256"] = "0" * 64
        with self.assertRaisesRegex(SceneBlocked, "PREVIEW_IMAGE_BYTES_NOT_VERIFIED"):
            build_plan(self.root, {"images": [entry]})
        entry["sha256"] = file_sha(path)
        entry["source_asset_id"] = "OPN02"  # sunset legacy candidate is NOT v02.
        with self.assertRaisesRegex(SceneBlocked, "PREVIEW_IMAGE_SCOPE_OR_RIGHTS"):
            build_plan(self.root, {"images": [entry]})

    def test_voice_requires_real_bound_script_and_private_license(self):
        entry = {"path": "private-media/voice.wav", "start_frame": 0, "end_frame": 24}
        with self.assertRaisesRegex(SceneBlocked, "PREVIEW_VOICE_SCRIPT_OR_RIGHTS"):
            build_plan(self.root, {"voices": [entry]})

    def test_outside_paths_and_public_output_never_render(self):
        with self.assertRaisesRegex(SceneBlocked, "PREVIEW_PRIVATE_MEDIA_PATH_REQUIRED"):
            _private_path(self.root, "https://example.com/image.png")
        with self.assertRaisesRegex(SceneBlocked, "PREVIEW_PRIVATE_MEDIA_PATH_REQUIRED"):
            _private_path(self.root, "../../private-media/image.png")
        with self.assertRaisesRegex(SceneBlocked, "PREVIEW_PRIVATE_MEDIA_PATH_REQUIRED"):
            render_private_draft(self.root, "public-preview.mp4")

    def test_reviewed_sound_spot_requires_exact_local_wav_rights_and_sample_alignment(self):
        import wave
        from tools.scene_factory import file_sha
        spot = self.first["sound_spotting"][0]
        wav_path = self.root / "private-media/reviewed-synthetic-foley.wav"
        with wave.open(str(wav_path), "wb") as sound:
            sound.setnchannels(1)
            sound.setsampwidth(2)
            sound.setframerate(48000)
            sound.writeframes(b"\x10\x27" * 4000)
        entry = {
            "shot_id": self.first["shot_id"],
            "spot_id": spot["id"],
            "kind": "foley",
            "path": "private-media/reviewed-synthetic-foley.wav",
            "sha256": file_sha(wav_path),
            "start_sample": spot["start_sample"],
            "end_sample": spot["start_sample"] + 4000,
            "gain_db": -20,
            "private_preview_rights_verified": True,
            "reviewed_for_private_preview": True,
            "license": "Self-authored synthetic test only",
            "rights_evidence": "Test fixture generated in private TemporaryDirectory",
        }
        baseline = build_plan(self.root)
        planned = build_plan(self.root, {"sounds": [entry]})
        self.assertEqual(planned["verified_private_sound_stems"], 1)
        self.assertEqual(planned["verified_hebrew_voice_clips"], 0)
        self.assertNotEqual(planned["preview_key"], baseline["preview_key"])
        self.assertEqual(planned["sounds"][0]["start_frame"], spot["start_sample"] // 2000)
        with self.assertRaisesRegex(SceneBlocked, "PREVIEW_DUPLICATE_SOUND_BINDING"):
            build_plan(self.root, {"sounds": [entry, entry]})
        for field, wrong, error in (
            ("sha256", "0" * 64, "PREVIEW_SOUND_BYTES_NOT_VERIFIED"),
            ("gain_db", 0, "PREVIEW_SOUND_GAIN_INVALID"),
            ("reviewed_for_private_preview", False, "PREVIEW_SOUND_RIGHTS_OR_REVIEW_MISSING"),
            ("private_preview_rights_verified", False, "PREVIEW_SOUND_RIGHTS_OR_REVIEW_MISSING"),
            ("spot_id", "OPN02", "PREVIEW_SOUND_SPOT_NOT_IN_SCENE"),
            ("end_sample", entry["end_sample"] + 1, "PREVIEW_SOUND_SPOTTING_TIMING_INVALID"),
        ):
            corrupt = dict(entry, **{field: wrong})
            with self.subTest(field=field), self.assertRaisesRegex(SceneBlocked, error):
                build_plan(self.root, {"sounds": [corrupt]})
        with self.assertRaisesRegex(SceneBlocked, "PREVIEW_UNSUPPORTED_MEDIA_BINDING"):
            build_plan(self.root, {"unauthorized_media": []})

    def test_real_ffmpeg_sound_stem_two_shot_short_smoke(self):
        if not all(shutil.which(x) for x in ("ffmpeg", "ffprobe", "fc-match")):
            self.skipTest("FFmpeg/font tooling unavailable")
        import wave
        from unittest.mock import patch
        import tools.scene_prologue_private_preview as preview
        wav_path = self.root / "private-media/synthetic-test-ambience.wav"
        with wave.open(str(wav_path), "wb") as sound:
            sound.setnchannels(1)
            sound.setsampwidth(2)
            sound.setframerate(48000)
            sound.writeframes(b"\x10\x27" * 24000)
        slates = [{"shot_id": f"EP-P{i:02d}", "start_frame": (i-1)*24,
                   "end_frame": i*24, "duration_frames": 24,
                   "purpose": "לוח בדיקת סאונד",
                   "source_layer": "symbolic_dramatization",
                   "image": None, "media_status": "MISSING_OR_UNAPPROVED_SLATE"}
                  for i in (1, 2)]
        plan = {"scene_id": "ACT1-PROLOGUE", "preview_key": "d"*64,
                "total_frames": 48, "shots": slates, "voices": [],
                "sounds": [{"path": "private-media/synthetic-test-ambience.wav",
                            "start_frame": 0, "gain_db": -18}],
                "verified_private_preview_images": 0,
                "missing_or_unapproved_images": 2,
                "verified_hebrew_voice_clips": 0,
                "verified_private_sound_stems": 1}
        with patch.object(preview, "build_plan", return_value=plan):
            report = render_private_draft(self.root, "private-media/audio-smoke.mp4")
            self.assertTrue((self.root / "private-media/audio-smoke.mp4").is_file())
            self.assertEqual(report["verified_private_sound_stems"], 1)
            self.assertTrue(report["voice_missing"])
            self.assertFalse(report["placeholder_silence"])
            self.assertEqual(report["provider_calls"], 0)
            self.assertTrue(render_private_draft(
                self.root, "private-media/audio-smoke.mp4")["cache_hit"])


if __name__ == "__main__":
    unittest.main()
