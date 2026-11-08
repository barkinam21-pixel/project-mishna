"""Offline regression suite for owner-private unapproved candidate recovery."""
import hashlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import zipfile

from PIL import Image

from tools.private_scene_review import (IMAGE, CANDIDATES,
    unpack_verified_bundle, review_private_scene)


def archive_fixture(image=None, metadata=None):
    if image is None:
        out = io.BytesIO()
        Image.new("RGB", (1024, 576), (92, 72, 45)).save(out, format="PNG")
        image = out.getvalue()
    digest = hashlib.sha256(image).hexdigest()
    if metadata is None:
        metadata = {"OPN02": {"status": "CANDIDATE", "accepted": False,
                              "path": IMAGE, "sha256": digest}}
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr(IMAGE, image)
        z.writestr(CANDIDATES, json.dumps(metadata))
    return out.getvalue(), digest


class PrivateSceneReviewTests(unittest.TestCase):
    def install(self, root, archive):
        path = root / "candidate.zip"
        path.write_bytes(archive)
        return path

    def restore(self, root, archive, digest):
        return unpack_verified_bundle(self.install(root, archive), root,
            expected_archive_sha256=hashlib.sha256(archive).hexdigest(),
            expected_image_sha256=digest)

    def test_valid_restore_is_private_unapproved_and_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            archive, digest = archive_fixture()
            receipt = self.restore(root, archive, digest)
            self.assertFalse(receipt["accepted"])
            self.assertFalse(receipt["rights_approved"])
            self.assertEqual(receipt["provider_calls"], 0)
            self.assertEqual(hashlib.sha256((root / IMAGE).read_bytes()).hexdigest(), digest)
            self.assertEqual(receipt["reused"], [])
            twice = self.restore(root, archive, digest)
            self.assertCountEqual(twice["reused"], [IMAGE, CANDIDATES])
            self.assertIs(json.loads((root / CANDIDATES).read_text())["OPN02"]["accepted"], False)

    def test_wrong_bundle_hash_rejects_without_writes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            archive, digest = archive_fixture()
            with self.assertRaisesRegex(ValueError, "BUNDLE_HASH"):
                unpack_verified_bundle(self.install(root, archive), root,
                    expected_archive_sha256="0" * 64, expected_image_sha256=digest)
            self.assertFalse((root / IMAGE).exists())

    def test_forged_approval_rejected_without_writes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            archive, digest = archive_fixture()
            forged = {"OPN02": {"status": "ACCEPTED", "accepted": True,
                                 "path": IMAGE, "sha256": digest}}
            archive, digest = archive_fixture(metadata=forged)
            with self.assertRaisesRegex(ValueError, "unapproved"):
                self.restore(root, archive, digest)
            self.assertFalse((root / CANDIDATES).exists())

    def test_zip_path_traversal_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            archive, digest = archive_fixture()
            for name in ("../../outside.png", "private-media/../wrong.png"):
                stream = io.BytesIO()
                with zipfile.ZipFile(stream, "w", zipfile.ZIP_DEFLATED) as z:
                    z.writestr(name, b"evil")
                    z.writestr(CANDIDATES, b"{}")
                with self.subTest(name=name), self.assertRaisesRegex(ValueError, "layout"):
                    self.restore(root, stream.getvalue(), digest)
            self.assertFalse((root / IMAGE).exists())

    def test_symlink_zip_entry_rejected(self):
        import stat
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _, digest = archive_fixture()
            stream = io.BytesIO()
            with zipfile.ZipFile(stream, "w") as z:
                item = zipfile.ZipInfo(IMAGE)
                item.create_system = 3
                item.external_attr = (stat.S_IFLNK | 0o777) << 16
                z.writestr(item, b"../../oops")
                z.writestr(CANDIDATES, b"{}")
            with self.assertRaisesRegex(ValueError, "Unsafe"):
                self.restore(root, stream.getvalue(), digest)
            self.assertFalse((root / IMAGE).exists())

    def test_conflict_blocks_both_writes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            archive, digest = archive_fixture()
            dest = root / CANDIDATES
            dest.parent.mkdir(parents=True)
            dest.write_bytes(b"unrelated-private-content")
            with self.assertRaisesRegex(ValueError, "CONFLICT"):
                self.restore(root, archive, digest)
            self.assertFalse((root / IMAGE).exists())
            self.assertEqual(dest.read_bytes(), b"unrelated-private-content")

    def test_bad_image_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            archive, digest = archive_fixture(image=b"not-png")
            with self.assertRaisesRegex(ValueError, "Invalid private candidate image"):
                self.restore(root, archive, digest)
            self.assertFalse((root / IMAGE).exists())

    def test_real_board_adapter_remains_candidate_only(self):
        from tools.scene_pack_preflight import EXPECTED_IDS
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            archive, digest = archive_fixture()
            self.restore(root, archive, digest)
            shots = [{"shot_id": uid, "key": "k" + uid, "status": "MISSING"}
                     for uid in EXPECTED_IDS]
            with patch("tools.private_scene_review.unpack_verified_bundle",
                       return_value={"status": "TEST_VERIFIED", "accepted": False,
                                     "provider_calls": 0}), \
                 patch("tools.scene_pack_preflight.build",
                       return_value={"shots": shots}):
                result = review_private_scene(root, root / "candidate.zip")
            self.assertEqual(result["review_board"]["images_shown"], ["OPN02"])
            self.assertEqual(result["review_board"]["placeholders"], 6)
            self.assertFalse(result["review_board"]["approval_granted"])
            self.assertFalse(result["film_ready"])
            self.assertTrue((root / result["review_board"]["output"]).is_file())


if __name__ == "__main__":
    unittest.main()
