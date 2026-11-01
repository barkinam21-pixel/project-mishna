import unittest, json, copy, importlib.util
from pathlib import Path
spec=importlib.util.spec_from_file_location('fp',Path(__file__).resolve().parents[1]/'tools/fal_payload_preflight.py')
fp=importlib.util.module_from_spec(spec)
spec.loader.exec_module(fp)
PACK=Path(__file__).resolve().parents[1]/'episodes/berakhot-01-01/fal-prepaid-shotpack-v1.json'

class PayloadTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pack=json.loads(PACK.read_text(encoding='utf-8'))
    def test_one_valid_shot_schema(self):
        x=fp.request_for_shot(self.pack,'SH01')
        self.assertEqual(x['endpoint'],'fal-ai/flux-2-pro')
        self.assertFalse(x['can_execute'])
        self.assertEqual(set(x['payload']),{'prompt','image_size','output_format','enable_safety_checker','sync_mode'})
        self.assertIn('Avoid these visual errors:',x['payload']['prompt'])
    def test_all_sixteen(self):
        self.assertEqual(len({fp.request_for_shot(self.pack,f'SH{n:02d}')['payload_sha256'] for n in range(1,17)}),16)
    def test_reject_paid(self):
        x=copy.deepcopy(self.pack); x['authorization']['paid_request_authorized']=True
        with self.assertRaises(fp.UnsafePlan): fp.request_for_shot(x,'SH01')
    def test_reject_chatgpt(self):
        x=copy.deepcopy(self.pack);x['authorization']['image_generation_in_chatgpt_allowed']=True
        with self.assertRaises(fp.UnsafePlan):fp.request_for_shot(x,'SH01')
    def test_reject_public_media(self):
        x=copy.deepcopy(self.pack);x['output']['asset_visibility']='PUBLIC'
        with self.assertRaises(fp.UnsafePlan):fp.request_for_shot(x,'SH01')
    def test_reject_key_in_prompt(self):
        x=copy.deepcopy(self.pack);x['shots'][0]['prompt']='My secret https://signed.example.com/abc?token=1'+x['shots'][0]['prompt']
        with self.assertRaises(fp.UnsafePlan):fp.request_for_shot(x,'SH01')
    def test_unknown_id(self):
        with self.assertRaises(fp.UnsafePlan):fp.request_for_shot(self.pack,'SH17')
    def test_deterministic(self):
        self.assertEqual(fp.request_for_shot(self.pack,'SH04')['payload_sha256'],fp.request_for_shot(self.pack,'SH04')['payload_sha256'])
    def test_no_reference_urls(self):
        x=copy.deepcopy(self.pack);x['shots'][0]['references']=['https://example.org/private']
        with self.assertRaises(fp.UnsafePlan):fp.request_for_shot(x,'SH01')
    def test_bad_status(self):
        x=copy.deepcopy(self.pack);x['status']='ready'
        with self.assertRaises(fp.UnsafePlan):fp.request_for_shot(x,'SH01')

if __name__=='__main__':unittest.main()