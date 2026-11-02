"""Offline safety tests: no generation and no external APIs."""
import hashlib
from pathlib import Path
import tempfile
import unittest

from tools.private_motion_shot import make_plan


class PrivateMotionShotTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.image = self.root / 'private.png'
        self.image.write_bytes(b'\x89PNG\r\n\x1a\nFAKE TEST PAYLOAD')
        self.output = self.root / 'review.mp4'

    def test_dry_plan_does_not_render(self):
        digest = hashlib.sha256(self.image.read_bytes()).hexdigest()
        plan = make_plan(self.image, self.output, digest)
        self.assertEqual(plan['status'], 'plan_only')
        self.assertEqual(plan['frames'], 144)
        self.assertEqual(plan['duration_seconds'], 6)
        self.assertFalse(self.output.exists())

    def test_source_hash_change_rejected(self):
        with self.assertRaisesRegex(ValueError, 'SHA256'):
            make_plan(self.image, self.output, '0' * 64)

    def test_preexisting_output_is_preserved(self):
        self.output.write_bytes(b'important existing preview')
        with self.assertRaisesRegex(ValueError, 'already exists'):
            make_plan(self.image, self.output, None)
        self.assertEqual(self.output.read_bytes(), b'important existing preview')

    def test_missing_image_rejected(self):
        with self.assertRaisesRegex(ValueError, 'does not exist'):
            make_plan(self.root / 'missing.png', self.output, None)


if __name__ == '__main__':
    unittest.main()
