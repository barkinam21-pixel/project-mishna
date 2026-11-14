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

    def test_unknown_duplicate_legacy_or_outside_bindings_blocked(self):
        entry = {"shot_id": "OPN02", "asset_key": self.first["asset_key"]}
        with self.assertRaisesRegex(SceneBlocked, "PREVIEW_UNKNOWN_SHOT_BINDING"):
            build_plan(self.root, {"images": [entry]})
        sid = self.first["shot_id"]
        entry.update({"shot_id": sid})
        with self.assertRaisesRegex(SceneBlocked, "PREVIEW_IMAGE_SCOPE_OR_RIGHTS"):
            build_plan(self.root, {"images": [entry]})
        with self.assertRaisesRegex(SceneBlocked, "PREVIEW_DUPLICATE_SHOT_BINDING"):
            build_plan(self.root, {"images": [entry, entry]})

    def test_valid_private_image_binding_uses_exact_bytes_and_sha(self):
        # Tiny hand-authored PNG from existing test utility: never dispatched.
        from tests.test_private_proof_ffmpeg_smoke import test_only_png
        from tools.scene_factory import file_sha
        path = self.root / "private-media/fixture.png"
        test_only_png(path, (30, 40, 50))
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


if __name__ == "__main__":
    unittest.main()
