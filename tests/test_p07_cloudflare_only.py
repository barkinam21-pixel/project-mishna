"""Real multipart-encoding QA, zero network/provider calls (fake JPEG pixels)."""
import copy
import hashlib
import io
import json
import os
import tempfile
import unittest
from email.parser import BytesParser
from email.policy import default
from pathlib import Path
from unittest import mock

from tools import p07_cloudflare_only as cloud
from tools.scene_native_conditioning_preview import NAMES, ROLES, PRIVATE, digest

try:
    from PIL import Image
except ImportError:
    Image = None


@unittest.skipIf(Image is None, "Pillow optional on public CI; required on private host")
class CloudflareOnlyMultipartTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root / "private-media/visual-reference-master-20261115").mkdir(parents=True)
        self.safe_env = mock.patch.dict(os.environ, {"GITHUB_ACTIONS": "false"})
        self.safe_env.start()
        self.addCleanup(self.safe_env.stop)
        refs = []
        for i, name in enumerate(NAMES):
            path = self.root / PRIVATE / name
            im = Image.new("RGB", (900 + i * 10, 620 + i * 20),
                           (55 + i, 60 + i, 75 + i))
            im.save(path, format="JPEG")
            raw = path.read_bytes()
            sha = hashlib.sha256(raw).hexdigest()
            refs.append({"path": PRIVATE + name, "role": ROLES[i], "sha256": sha,
                         "expected_sha256": sha, "synthesis_rights_confirmed": False})
        self.draft = {
            "status": "DRAFT_OWNER_PRIVATE_CONDITIONING_NOT_APPROVED_NOT_EXECUTABLE",
            "shot_id": "EP-P07",
            "candidate_count": 3,
            "candidate_reference_filenames": list(NAMES),
            "provider_dispatch_authorized": False, "provider_calls": 0,
            "rights_for_synthesis": "NOT_EVALUATED", "no_automatic_retry": True,
            "proposed_provider_shape": {
                "model": {"id": "black-forest-labs/FLUX.2-klein-4B"},
                "backend": {"type": "cloudflare", "model": cloud.MODEL},
                "size": [1024, 576],
                "prompt": "Wide back view, cool dawn, elderly blue cloak left, young brown right",
                "seed": 3901028371185374429,
                "visual_direction": {"owner_conditional_review_only": True},
                "director": {"shot_id": "EP-P07", "time_of_day": "dawn",
                             "review_status": "DRAFT_REQUIRES_REVIEW",
                             "characters_present": ["elder", "younger"],
                             "positions": {"elder": "screen-left", "younger": "screen-right"}},
                "references": refs,
            }
        }
        self.rehash()

    def rehash(self):
        self.draft["draft_sha256"] = digest(
            {k: v for k, v in self.draft.items() if k != "draft_sha256"})

    def test_real_multipart_three_resized_jpegs_and_correct_fields(self):
        out = cloud.compile_cloudflare_only(self.draft, self.root)
        report = out["safe_report"]
        self.assertTrue(report["no_fallback_provider"])
        self.assertFalse(report["provider_dispatch_authorized"])
        self.assertEqual(report["provider_calls"], 0)
        self.assertTrue(all(max(shape) <= 511 for shape in report["reference_dimensions"]))
        self.assertEqual(report["request_body_sha256"], hashlib.sha256(out["body"]).hexdigest())
        self.assertEqual(out["endpoint_suffix"], "/ai/run/" + cloud.MODEL)
        raw = ("MIME-Version: 1.0\r\nContent-Type: " +
               out["content_type"] + "\r\n\r\n").encode() + out["body"]
        msg = BytesParser(policy=default).parsebytes(raw)
        self.assertTrue(msg.is_multipart())
        fields = {p.get_param("name", header="content-disposition"): p
                  for p in msg.iter_parts()}
        self.assertEqual(set(fields), {"prompt", "width", "height", "guidance",
                                        "seed", "input_image_0", "input_image_1", "input_image_2"})
        self.assertEqual(fields["width"].get_content(), "1024")
        self.assertEqual(fields["height"].get_content(), "576")
        self.assertIn("dawn", fields["prompt"].get_content())
        for i in range(3):
            data = fields[f"input_image_{i}"].get_payload(decode=True)
            with Image.open(io.BytesIO(data)) as img:
                self.assertEqual(img.format, "JPEG")
                self.assertLess(img.width, 512)
                self.assertLess(img.height, 512)
        self.assertEqual(out["body"], cloud.compile_cloudflare_only(self.draft, self.root)["body"])

    def test_rejected_on_changed_private_original_even_if_draft_hash_unchanged(self):
        path = self.root / PRIVATE / NAMES[0]
        path.write_bytes(path.read_bytes() + b"x")
        with self.assertRaisesRegex(cloud.P07CloudflareOnlyBlocked, "SHA_MISMATCH"):
            cloud.compile_cloudflare_only(self.draft, self.root)

    def test_rejected_on_unattested_reference_promotion(self):
        self.draft["proposed_provider_shape"]["references"][0]["synthesis_rights_confirmed"] = True
        self.rehash()
        with self.assertRaisesRegex(cloud.P07CloudflareOnlyBlocked, "RIGHTS_CHANGED"):
            cloud.compile_cloudflare_only(self.draft, self.root)

    def test_no_provider_side_effect_when_public_actions(self):
        with mock.patch.dict(os.environ, {"GITHUB_ACTIONS": "true"}):
            with self.assertRaisesRegex(cloud.P07CloudflareOnlyBlocked, "PUBLIC_ACTIONS"):
                cloud.compile_cloudflare_only(self.draft, self.root)

    def test_cannot_repurpose_as_approved_dispatch(self):
        self.draft["provider_dispatch_authorized"] = True
        self.rehash()
        with self.assertRaisesRegex(cloud.P07CloudflareOnlyBlocked, "NOT_CLOSED"):
            cloud.compile_cloudflare_only(self.draft, self.root)

    def test_stale_draft_digest_and_wrong_backend_denied(self):
        self.draft["proposed_provider_shape"]["prompt"] = "tampered"
        with self.assertRaisesRegex(cloud.P07CloudflareOnlyBlocked, "HASH_CHANGED"):
            cloud.compile_cloudflare_only(self.draft, self.root)
        self.rehash()
        self.draft["proposed_provider_shape"]["backend"]["model"] = "@external/horde"
        self.rehash()
        with self.assertRaisesRegex(cloud.P07CloudflareOnlyBlocked, "NOT_EXACT_CLOUDFLARE"):
            cloud.compile_cloudflare_only(self.draft, self.root)

    def test_symlink_reference_denied(self):
        path = self.root / PRIVATE / NAMES[0]
        other = path.read_bytes()
        target = self.root / "outside.jpg"
        target.write_bytes(other)
        path.unlink()
        path.symlink_to(target)
        with self.assertRaisesRegex(cloud.P07CloudflareOnlyBlocked, "PRIVATE_REFERENCE_UNSAFE"):
            cloud.compile_cloudflare_only(self.draft, self.root)


if __name__ == "__main__":
    unittest.main()
