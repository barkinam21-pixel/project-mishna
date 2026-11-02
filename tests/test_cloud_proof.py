import json
import tempfile
import unittest
from pathlib import Path
from tools import cloud_proof
from tools.private_proof_assembler import ROOT, EXAMPLE, BLUEPRINT


class CloudProofTests(unittest.TestCase):
    def test_missing_media_produces_durable_blocker_not_movie(self):
        with tempfile.TemporaryDirectory() as folder:
            out = Path(folder)
            report = cloud_proof.run(EXAMPLE, BLUEPRINT, ROOT, out)
            self.assertEqual(report['status'], 'BLOCKED_MISSING_REAL_MEDIA')
            self.assertFalse(report['movie_created'])
            self.assertEqual(report['real_voice_takes'], 0)
            self.assertEqual(report['supplied_images'], 0)
            self.assertEqual(len(report['input_hashes']), 4)
            self.assertIn('No real Hebrew spoken WAV takes', report['missing'])
            self.assertFalse(list(out.glob('*.mp4')))
            self.assertEqual(json.loads((out/'report.json').read_text()), report)
            self.assertIn('NOT A FILM', (out/'report.md').read_text())
            cloud_proof.run(EXAMPLE, BLUEPRINT, ROOT, out)
            self.assertEqual(len((out/'usage-ledger.jsonl').read_text().splitlines()), 2)

    def test_invalid_json_is_reported_and_does_not_render(self):
        with tempfile.TemporaryDirectory() as folder:
            out = Path(folder)
            invalid = out/'bad.json'
            invalid.write_text('{')
            report = cloud_proof.run(invalid, BLUEPRINT, ROOT, out/'result')
            self.assertEqual(report['status'], 'INVALID')
            self.assertFalse(report['movie_created'])
            self.assertTrue((out/'result/report.json').exists())

    def test_audit_does_not_relabel_old_video_as_new_result(self):
        with tempfile.TemporaryDirectory() as folder:
            out = Path(folder)
            (out/'private-review.mp4').write_bytes(b'old')
            report = cloud_proof.run(EXAMPLE, BLUEPRINT, ROOT, out)
            self.assertFalse(report['movie_created'])
            self.assertNotIn('video', report)
            self.assertEqual((out/'private-review.mp4').read_bytes(), b'old')
