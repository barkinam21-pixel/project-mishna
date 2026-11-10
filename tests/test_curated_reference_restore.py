"""Offline integrity tests for the owner's 8-image reference-pack intake.

Fixtures are synthetic pixels. No user images, provider calls, GPU, or credentials.
"""
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from PIL import Image
from tools import curated_reference_restore as restore


def digest(data):
    return hashlib.sha256(data).hexdigest()


def fixture_records(*, permissions=False):
    files = {}
    records = []
    for index, name in enumerate(restore.FILE_SHA256):
        out = io.BytesIO()
        is_png = name.endswith(".png")
        Image.new("RGB", (16, 16), (30 + index * 10, 70, 100)).save(
            out, format="PNG" if is_png else "JPEG"
        )
        raw = out.getvalue()
        files[name] = raw
        records.append({
            "archive_path": name, "sha256": digest(raw),
            "width": 16, "height": 16,
            "provider_upload_allowed": permissions,
        })
    return files, records


def make_pack(path, files, records, extra=None):
    data = {
        "status": "PRIVATE_REFERENCE_ONLY_NOT_APPROVED_FOR_PROVIDER_UPLOAD",
        "included_reference_count": 8,
        "records": records,
    }
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_STORED) as z:
        for name, raw in files.items():
            z.writestr(name, raw)
        z.writestr("manifest.json", json.dumps(data))
        z.writestr("README.txt", "Test fixture - do not publish")
        if extra:
            z.writestr(extra, "not allowed")
    return digest(path.read_bytes())


def fake_manifest(files):
    return {
        "references": [{
            "path": "private-media/introduction/references/" + digest(files[restore.MASTER]) + ".png",
            "sha256": digest(files[restore.MASTER]),
            "expected_size": [16, 16],
            "synthesis_rights_confirmed": True,
            "rights_uri": "synthetic fixture rights only",
        }],
        "direction_board": {
            "path": "private-media/introduction/references/" + digest(files[restore.BOARD]) + ".png",
            "sha256": digest(files[restore.BOARD]),
            "dimensions": [16, 16],
        },
    }


class CuratedEightReferenceRestoreTest(unittest.TestCase):
    def run_fixture(self, *, bad_hash=False, extra=None, permissions=False):
        with tempfile.TemporaryDirectory() as home:
            root = Path(home)
            private = root / "private-media" / "incoming"
            private.mkdir(parents=True)
            archive = private / "references.zip"
            files, records = fixture_records(permissions=permissions)
            zip_hash = make_pack(archive, files, records, extra=extra)
            allowed_hashes = {path: digest(raw) for path, raw in files.items()}
            if bad_hash:
                allowed_hashes[restore.MASTER] = "0" * 64
            with patch.object(restore, "ARCHIVE_SHA256", zip_hash), patch.dict(
                restore.FILE_SHA256, allowed_hashes, clear=True
            ):
                if bad_hash:
                    with self.assertRaisesRegex(ValueError, "MANIFEST_HASH_MISMATCH"):
                        restore.restore_eight_reference_pack(archive, root, fake_manifest(files))
                elif extra:
                    with self.assertRaisesRegex(ValueError, "MEMBERS_INVALID"):
                        restore.restore_eight_reference_pack(archive, root, fake_manifest(files))
                elif permissions:
                    with self.assertRaisesRegex(ValueError, "RIGHTS_OR_HASH_INVALID"):
                        restore.restore_eight_reference_pack(archive, root, fake_manifest(files))
                else:
                    manifest = fake_manifest(files)
                    result = restore.restore_eight_reference_pack(archive, root, manifest)
                    self.assertEqual(result["verified_images"], 8)
                    self.assertEqual(result["created_files"], 8)
                    self.assertIs(result["generation_authorized"], False)
                    self.assertIs(result["provider_upload_allowed"], False)
                    self.assertTrue((root / manifest["references"][0]["path"]).is_file())
                    second = restore.restore_eight_reference_pack(archive, root, manifest)
                    self.assertEqual(second["created_files"], 0)
                    (root / manifest["references"][0]["path"]).write_bytes(b"corrupted")
                    with self.assertRaisesRegex(ValueError, "OVERWRITE_BLOCKED"):
                        restore.restore_eight_reference_pack(archive, root, manifest)

    def test_verified_eight_images_and_idempotent_restore(self):
        self.run_fixture()

    def test_wrong_primary_hash_rejected_before_writes(self):
        self.run_fixture(bad_hash=True)

    def test_extra_archive_member_rejected(self):
        self.run_fixture(extra="unwanted.txt")

    def test_provider_permission_cannot_be_inherited_from_archive(self):
        self.run_fixture(permissions=True)

    def test_nonprivate_destination_blocked(self):
        with tempfile.TemporaryDirectory() as root:
            with self.assertRaisesRegex(ValueError, "PRIVATE_REFERENCE_PATH_REQUIRED"):
                restore.private_target(root, "build/public.png")
            with self.assertRaisesRegex(ValueError, "OUTSIDE_PRIVATE_ROOT"):
                restore.private_target(root, "private-media/introduction/../../outside.png")

    def test_archive_digest_lock(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "fake.zip"
            path.write_bytes(b"mismatched")
            with self.assertRaisesRegex(ValueError, "CURATED_ARCHIVE_SHA256_MISMATCH"):
                restore.restore_eight_reference_pack(path, root, {})


if __name__ == "__main__":
    unittest.main()
