"""Deterministic zero-spend tests; imports preflight only, never a model provider."""
import copy
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from tools.validate_external_shotpack import validate

PACK = ROOT / 'episodes/berakhot-01-01/fal-prepaid-shotpack-v1.json'


class ShotPackSafetyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pack = json.loads(PACK.read_text(encoding='utf-8'))

    def check_bad(self, f):
        data=copy.deepcopy(self.pack)
        f(data)
        self.assertFalse(validate(data)['valid'])

    def test_valid_dry_plan(self):
        r=validate(self.pack)
        self.assertEqual(r['status'], 'SAFE_DRY_PLAN',r['errors'])
        self.assertEqual(r['duration_frames'],1800)
        self.assertEqual(r['planned_original_images'],16)

    def test_chatgpt_image_generation_cannot_be_enabled(self):
        self.check_bad(lambda d: d['authorization'].__setitem__('image_generation_in_chatgpt_allowed',True))

    def test_paid_call_cannot_be_enabled(self):
        self.check_bad(lambda d: d['authorization'].__setitem__('paid_request_authorized',True))

    def test_approval_budget_cannot_increase(self):
        self.check_bad(lambda d: d['authorization'].__setitem__('authorized_external_spend_usd',5))

    def test_provider_cannot_change(self):
        self.check_bad(lambda d: d['authorization'].__setitem__('provider','chatgpt'))

    def test_private_reference_is_not_public(self):
        self.check_bad(lambda d: d['shots'][0].__setitem__('references',['https://private.example.com/abc']))

    def test_no_duplicate_shots(self):
        self.check_bad(lambda d: d['shots'][0].__setitem__('id','SH02'))

    def test_frame_gap_rejected(self):
        self.check_bad(lambda d: d['shots'][2].__setitem__('start_frame',400))

    def test_no_contradicting_negative_prompt(self):
        self.check_bad(lambda d: d['shots'][8].__setitem__('negative_prompt','no door, no house, no people'+'x'*70))

    def test_accepted_image_cannot_be_faked(self):
        self.check_bad(lambda d: d['shots'][4].__setitem__('asset_status','accepted'))

    def test_secret_cannot_be_written_into_prompt(self):
        self.check_bad(lambda d: d['shots'][3].__setitem__('prompt',d['shots'][3]['prompt']+' https://example.org/token.png'))


if __name__ == '__main__':
    unittest.main()
