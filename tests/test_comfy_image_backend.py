import tempfile
import unittest
from tools.comfy_image_backend import ComfyClient, key, plan

class ComfyBackendTests(unittest.TestCase):
    def test_dry_plan_no_generation(self):
        with tempfile.TemporaryDirectory() as root:
            report = plan({'shots': [{'id': 'OPN02', 'prompt': 'test'}]}, root)
        self.assertEqual(report['generation_submissions'], 0)
        self.assertFalse(report['shots'][0]['accepted'])

    def test_reference_and_rights_missing(self):
        with tempfile.TemporaryDirectory() as root:
            report = plan({'shots': [{'id': 'OPN02', 'references': [{'path': 'absent.png', 'sha256': 'x'}]}]}, root)
        self.assertEqual(len(report['shots'][0]['missing']), 2)

    def test_no_submission_without_gates(self):
        with self.assertRaises(ValueError):
            ComfyClient('http://localhost:8188').submit({})

    def test_insecure_remote_rejected(self):
        with self.assertRaises(ValueError):
            ComfyClient('http://remote.example:8188')

    def test_key_changes_with_reference(self):
        self.assertNotEqual(key({'reference': 'a'}), key({'reference': 'b'}))

    def test_duplicate_ids(self):
        with self.assertRaises(ValueError):
            plan({'shots': [{'id': 'a'}, {'id': 'a'}]}, '.')
