"""No-network regressions for paid-image visual acceptance and private assembly."""
import json
import sys
import tempfile
import unittest
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.visual_gate_opn01 import verify_visual_gate, VisualGateError, REQUIRED_CHECKS
from tools import finish_opn01_private

SHA = 'a' * 64


def gate():
    return {'shot': 'OPN01', 'image_sha256': SHA,
            'decision': 'ACCEPT_FOR_PRIVATE_PREVIEW',
            'reviewer_type': 'human', 'reviewer_name': 'QA reviewer',
            'reviewed_at_utc': '2026-11-01T16:00:00Z',
            'checks': {k: True for k in REQUIRED_CHECKS},
            'public_release_authorized': False}


class HumanGate(unittest.TestCase):
    def run_case(self, data, sha=SHA):
        with tempfile.TemporaryDirectory() as t:
            p = Path(t) / 'private.json'
            p.write_text(json.dumps(data), encoding='utf-8')
            return verify_visual_gate(p, sha)

    def test_no_finish_or_decrypt_without_visual_approval(self):
        with tempfile.TemporaryDirectory() as t:
            d = Path(t)
            encrypted, key, manifest, blockout = [d / n for n in ('enc', 'key', 'manifest', 'blockout')]
            for p in (encrypted, key, manifest, blockout):
                p.write_bytes(b'placeholder')
            with patch.object(finish_opn01_private, 'inspect_encrypted', return_value={}), \
                 patch.object(finish_opn01_private.seal_private_media, 'unseal') as unseal:
                with self.assertRaises(finish_opn01_private.UnsafePipeline):
                    finish_opn01_private.finish(encrypted, key, manifest, blockout,
                                               Path('/mnt/data/opn01_blocked_test'), do_finish=True)
                unseal.assert_not_called()

    def test_missing_approval_fails_closed(self):
        with self.assertRaises(VisualGateError):
            verify_visual_gate(None, SHA)

    def test_current_rejected_frame_cannot_be_accepted(self):
        v = gate(); v['decision'] = 'REJECT'
        with self.assertRaises(VisualGateError): self.run_case(v)

    def test_changed_image_hash_cannot_reuse_approval(self):
        with self.assertRaises(VisualGateError): self.run_case(gate(), 'b'*64)

    def test_human_reviewer_required(self):
        v = gate(); v['reviewer_type'] = 'agent'
        with self.assertRaises(VisualGateError): self.run_case(v)

    def test_all_visual_checks_required(self):
        for key in REQUIRED_CHECKS:
            with self.subTest(key=key):
                v = gate(); v['checks'][key] = False
                with self.assertRaises(VisualGateError): self.run_case(v)

    def test_public_release_not_authorized(self):
        v = gate(); v['public_release_authorized'] = True
        with self.assertRaises(VisualGateError): self.run_case(v)

    def test_timestamp_must_be_valid(self):
        v = gate(); v['reviewed_at_utc'] = (datetime.now(timezone.utc)+timedelta(days=2)).isoformat()
        with self.assertRaises(VisualGateError): self.run_case(v)

    def test_valid_private_review_does_not_approve_publication(self):
        r = self.run_case(gate())
        self.assertFalse(r['public_release_allowed'])
        self.assertEqual(r['shot'], 'OPN01')


if __name__ == '__main__': unittest.main()
