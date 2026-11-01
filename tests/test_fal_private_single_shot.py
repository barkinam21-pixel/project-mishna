import unittest, json, os, importlib, sys
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from tools.fal_private_single_shot import candidate, validate_result_url
PACK=ROOT/'episodes/berakhot-01-01/fal-prepaid-shotpack-v1.json'

class ProviderTests(unittest.TestCase):
    def test_dry_run_no_output_or_network(self):
        with TemporaryDirectory() as d:
            p=Path(d)/'never-created'
            with patch('tools.fal_private_single_shot.urllib_request.urlopen') as open_:
                ret=candidate(PACK,'SH01',p,False,0.15)
                self.assertEqual(ret['external_paid_requests'],0)
                self.assertFalse(p.exists())
                open_.assert_not_called()

    def test_reject_other_shots(self):
        with TemporaryDirectory() as d:
            with self.assertRaises(ValueError):candidate(PACK,'SH09',Path(d)/'out',False,0.15)

    def test_reject_paid_without_yes(self):
        with TemporaryDirectory() as d, patch.dict(os.environ,{'CONFIRM_PAID':'NO','FAL_KEY':'fake-key-but-should-not-be-used'}):
            with self.assertRaises(ValueError):candidate(PACK,'SH01',Path(d)/'out',True,0.15)

    def test_reject_over_budget(self):
        with TemporaryDirectory() as d,patch.dict(os.environ,{'CONFIRM_PAID':'YES','FAL_KEY':'1234567890123'}):
            with self.assertRaises(ValueError):candidate(PACK,'SH01',Path(d)/'out',True,0.16)

    def test_reject_missing_key(self):
        with TemporaryDirectory() as d,patch.dict(os.environ,{'CONFIRM_PAID':'YES','FAL_KEY':''}):
            with self.assertRaises(ValueError):candidate(PACK,'SH01',Path(d)/'out',True,0.15)

    def test_output_url_restrictions(self):
        self.assertEqual(validate_result_url('https://storage.googleapis.com/falserverless/name.png'), 'https://storage.googleapis.com/falserverless/name.png')
        self.assertEqual(validate_result_url('https://images.fal.media/one.png'), 'https://images.fal.media/one.png')
        for url in ('http://storage.googleapis.com/a.png','https://evil.example.com/a.png','file:///etc/passwd','https://storage.googleapis.com.evil.com/a'):
            with self.assertRaises(ValueError):validate_result_url(url)

if __name__=='__main__':unittest.main()