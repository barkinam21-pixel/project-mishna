"""Offline regressions for real Colab ZIP intake (all images here are synthetic TEST)."""
import copy
import hashlib
import json
from pathlib import Path
import struct
import tempfile
import unittest
import zipfile
import zlib

from tools import colab_image_intake as intake


def digest(data):
    return hashlib.sha256(data).hexdigest()


def png_chunk(name, payload):
    return (struct.pack(">I", len(payload)) + name + payload
            + struct.pack(">I", zlib.crc32(name + payload) & 0xffffffff))


def fake_png(width=1024, height=576):
    """Decodable solid RGB TEST PNG; absolutely not an illustration."""
    header = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    pixels = (b"\x00" + b"\x20\x30\x40" * width) * height
    return (intake.PNG_SIGNATURE + png_chunk(b"IHDR", header)
            + png_chunk(b"IDAT", zlib.compress(pixels))
            + png_chunk(b"IEND", b""))


class ColabImageIntakeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pack = json.loads(intake.PACK.read_text(encoding="utf-8"))

    def make_archive(self, folder, shot_id="SH09", mutate=None, more=None):
        folder = Path(folder)
        plan = copy.deepcopy(self.pack)
        image = fake_png()
        shot = next(s for s in plan["shots"] if s["shot_id"] == shot_id)
        scene_prompt = shot["render_lead"]
        style_prompt = shot.get("render_style", plan["render_style"])
        negative_prompt = shot.get("render_negative_prompt", plan["render_negative_prompt"])
        spec = {
            "model_id": plan["model_id"],
            "model_revision": "unknown",
            "variant": "fp16",
            "prompt_strategy": "dual_encoder_scene_style_v1",
            "prompt_sha256": digest(scene_prompt.encode("utf-8")),
            "prompt_2_sha256": digest(style_prompt.encode("utf-8")),
            "negative_prompt_sha256": digest(negative_prompt.encode("utf-8")),
            "negative_prompt_2_sha256": digest(negative_prompt.encode("utf-8")),
            "seed": shot["seed"], "width": 1024, "height": 576,
            "inference_steps": 24, "guidance_scale": shot.get("guidance_scale", 6.0),
        }
        record = {
            "shot_id": shot_id, "image_sha256": digest(image),
            "model_id": plan["model_id"], "model_license": plan["model_license"],
            "prompt_sha256": spec["prompt_sha256"],
            "prompt_2_sha256": spec["prompt_2_sha256"],
            "negative_prompt_sha256": spec["negative_prompt_sha256"],
            "negative_prompt_2_sha256": spec["negative_prompt_2_sha256"],
            "generation_spec_sha256": digest(json.dumps(spec, sort_keys=True).encode("utf-8")),
            "generation_spec": spec, "image_size": [1024, 576],
            "inference_steps": 24, "operation": "image_generate",
            "accepted": False, "public_release_authorized": False,
            "paid_api_calls": 0, "external_cash_spend_initiated_usd": 0,
        }
        if mutate:
            mutate(plan, record, image)
        entries = {
            "prompt-pack-snapshot.json": json.dumps(plan, ensure_ascii=False).encode("utf-8"),
            "usage-ledger.jsonl": (json.dumps(record, ensure_ascii=False) + "\n").encode("utf-8"),
            shot_id + ".png": image,
        }
        entries.update(more or {})
        archive = folder / "test-not-real-illustration.zip"
        with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as z:
            for name, data in entries.items():
                z.writestr(name, data)
        return archive, entries

    def test_one_sh09_real_delivery_format_creates_unapproved_review_candidate(self):
        with tempfile.TemporaryDirectory() as tmp:
            archive, entries = self.make_archive(tmp)
            report = intake.audit_archive(archive)
            self.assertEqual(report["status"], "DRAFT_IMAGES_FOUND")
            self.assertEqual(report["image_count"], 1)
            self.assertEqual(report["draft_images"][0]["shot_id"], "SH09")
            self.assertFalse(report["ready_for_render"])
            self.assertFalse(report["public_release_authorized"])
            self.assertFalse((Path(tmp) / "staged").exists())  # read-only default

            candidate = intake.stage_archive(archive, report, Path(tmp) / "staged")
            config = json.loads(candidate.read_text(encoding="utf-8"))
            self.assertEqual(len(config["images"]), 1)
            media = config["images"][0]
            self.assertEqual(Path(media["path"]).read_bytes(), entries["SH09.png"])
            self.assertEqual(media["sha256"], digest(entries["SH09.png"]))
            self.assertFalse(media["original_illustration"])
            self.assertFalse(media["accepted_for_private_preview"])
            self.assertFalse(media["rights_verified_for_private_preview"])
            self.assertFalse(config["private_preview_authorized"])
            self.assertFalse(config["private_caption_text_checked"])
            self.assertFalse(config["release_authorized"])
            self.assertEqual(config["voice_takes"], [])
            # Idempotent stage: verified files are reused, never overwritten.
            self.assertEqual(candidate, intake.stage_archive(archive, report, Path(tmp) / "staged"))

    def test_incomplete_or_untrusted_ledger_is_blocked(self):
        cases = {
            "no_spend_violation": lambda p, r, i: r.update({"paid_api_calls": 1}),
            "false_approval": lambda p, r, i: r.update({"accepted": True}),
            "wrong_model": lambda p, r, i: r.update({"model_id": "unknown"}),
            "bad_sha": lambda p, r, i: r.update({"image_sha256": "0" * 64}),
            "wrong_spec_sha": lambda p, r, i: r.update({"generation_spec_sha256": "0" * 64}),
            "no_spec": lambda p, r, i: r.pop("generation_spec"),
            "stale_prompt": lambda p, r, i: p["shots"][8].update({"shot_prompt": "stale"}),
            "stale_render_lead": lambda p, r, i: p["shots"][8].update({"render_lead": "stale"}),
            "wrong_second_encoder": lambda p, r, i: r.update({"prompt_2_sha256": "0" * 64}),
            "wrong_negative_2": lambda p, r, i: r.update({"negative_prompt_2_sha256": "0" * 64}),
            "wrong_sh09_guidance": lambda p, r, i: r["generation_spec"].update({"guidance_scale": 6.0}),
            "stale_sh09_guidance": lambda p, r, i: p["shots"][8].update({"guidance_scale": 6.0}),
            "release_gate": lambda p, r, i: p.update({"public_release_authorized": True}),
        }
        for label, mutation in cases.items():
            with self.subTest(label=label), tempfile.TemporaryDirectory() as tmp:
                archive, _ = self.make_archive(tmp, mutate=mutation)
                with self.assertRaises(intake.ArchiveError):
                    intake.audit_archive(archive)

    def test_sh09_guidance_value_is_part_of_real_zip_contract(self):
        with tempfile.TemporaryDirectory() as tmp:
            archive, _ = self.make_archive(tmp)
            result = intake.audit_archive(archive)
            self.assertEqual(result["image_count"], 1)
            with zipfile.ZipFile(archive) as zf:
                record = json.loads(zf.read("usage-ledger.jsonl").decode("utf-8"))
            self.assertEqual(record["generation_spec"]["guidance_scale"], 7.0)
            self.assertFalse(result["ready_for_render"])
            self.assertFalse(result["public_release_authorized"])

    def test_malformed_png_and_mismatched_dimensions_are_rejected(self):
        valid = fake_png()
        self.assertEqual(intake.verify_png(valid), [1024, 576])
        corrupted = bytearray(valid)
        corrupted[-6] ^= 1
        with self.assertRaises(intake.ArchiveError):
            intake.verify_png(bytes(corrupted))
        with self.assertRaises(intake.ArchiveError):
            intake.verify_png(fake_png(768, 448)[:-8])
        self.assertEqual(intake.verify_png(fake_png(768, 448)), [768, 448])

    def test_zip_slip_and_unexpected_entries_are_rejected_before_stage(self):
        for bad in ("../outside.png", "folder/evil.png", "SH09.png/evil", "evil.wav"):
            with self.subTest(bad=bad), tempfile.TemporaryDirectory() as tmp:
                archive, _ = self.make_archive(tmp, more={bad: b"unsafe"})
                with self.assertRaises(intake.ArchiveError):
                    intake.audit_archive(archive)
                self.assertFalse((Path(tmp) / "staged").exists())

    def test_rejected_sh01_is_not_reused_even_with_matching_new_ledger(self):
        with tempfile.TemporaryDirectory() as tmp:
            archive, _ = self.make_archive(tmp, shot_id="SH01")
            report = intake.audit_archive(archive)
            self.assertEqual(report["status"], "NO_NEW_ELIGIBLE_IMAGES")
            self.assertEqual(report["image_count"], 0)
            self.assertEqual(report["skipped"][0]["shot_id"], "SH01")
            with self.assertRaises(intake.ArchiveError):
                intake.stage_archive(archive, report, Path(tmp) / "staged")

    def test_derived_contact_sheet_is_staged_but_never_an_original_image(self):
        with tempfile.TemporaryDirectory() as tmp:
            preview = b"\xff\xd8\xff\xe0mock-review-sheet\xff\xd9"
            archive, _ = self.make_archive(
                tmp, more={intake.REVIEW_SHEET: preview}
            )
            report = intake.audit_archive(archive)
            self.assertTrue(report["review_contact_sheet_present"])
            self.assertEqual(report["image_count"], 1)
            candidate = intake.stage_archive(archive, report, Path(tmp) / "staged")
            config = json.loads(candidate.read_text(encoding="utf-8"))
            self.assertEqual(Path(config["review_contact_sheet"]).read_bytes(), preview)
            self.assertEqual(len(config["images"]), 1)
            self.assertNotIn("review_contact_sheet", config["images"][0])
            self.assertFalse(config["images"][0]["accepted_for_private_preview"])
            self.assertFalse(config["release_authorized"])

    def test_malformed_review_sheet_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            archive, _ = self.make_archive(
                tmp, more={intake.REVIEW_SHEET: b"not a JPEG"}
            )
            with self.assertRaises(intake.ArchiveError):
                intake.audit_archive(archive)

    def test_superseded_legacy_file_is_ignored(self):
        with tempfile.TemporaryDirectory() as tmp:
            archive, _ = self.make_archive(tmp, more={"SH09.superseded-aaaaaaaaaaaa.png": b"old"})
            report = intake.audit_archive(archive)
            self.assertEqual(report["image_count"], 1)

    def test_duplicate_member_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            archive, entries = self.make_archive(tmp)
            with zipfile.ZipFile(archive, "a") as zf:
                import warnings
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore", UserWarning)
                    zf.writestr("SH09.png", entries["SH09.png"])
            with self.assertRaises(intake.ArchiveError):
                intake.audit_archive(archive)


if __name__ == "__main__":
    unittest.main()
