"""Safety regression: no money without explicit consent, only correct first shot."""
import copy
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('fal_private_opening_opn01', ROOT / 'tools' / 'fal_private_opening_opn01.py')
MOD = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MOD)
MANIFEST = ROOT / 'episodes' / 'berakhot-01-01' / 'opening-45s-director-pack-v1.json'
PACK = json.loads(MANIFEST.read_text(encoding='utf-8'))

class OPN01Security(unittest.TestCase):
    def test_pack_dry_plan_is_fixed_first_shot(self):
        p = MOD.prepare(copy.deepcopy(PACK))
        self.assertEqual(p['shot'], 'OPN01')
        self.assertEqual(p['external_requests'], 0)
        self.assertEqual(p['payload']['image_size'], 'landscape_16_9')
        self.assertEqual(p['payload']['output_format'], 'png')
        self.assertEqual(p['payload']['sync_mode'], False)
        self.assertNotIn('negative_prompt', p['payload'])
        self.assertTrue(p['private_output_only'])
    def test_dry_run_does_not_call_network_or_write_media(self):
        with tempfile.TemporaryDirectory() as td:
            d = Path(td) / 'private'
            with patch.dict(os.environ, {'FAL_KEY':'unused-secret','CONFIRM_PAID':'YES'}):
                result = MOD.execute(MANIFEST,d,authorize_paid=False,
                                     provider_open=lambda *a,**kw:self.fail('network accessed'))
            self.assertEqual(result['external_requests'],0)
            self.assertFalse(d.exists())
    def test_fresh_paid_consent_required(self):
        with tempfile.TemporaryDirectory() as td:
            with patch.dict(os.environ, {'FAL_KEY':'0123456789test','CONFIRM_PAID':'NO'}):
                with self.assertRaises(MOD.GateBlocked):
                    MOD.execute(MANIFEST,Path(td)/'new',authorize_paid=True)
    def test_missing_key_blocks_charge(self):
        with tempfile.TemporaryDirectory() as td:
            with patch.dict(os.environ, {'CONFIRM_PAID':'YES','FAL_KEY':''}):
                with self.assertRaises(MOD.GateBlocked):
                    MOD.execute(MANIFEST,Path(td)/'new',authorize_paid=True)
    def test_stale_history_and_wrong_shot_never_allowed(self):
        for field,value in [('next_paid_shot_candidate','SH09'),('sons_return_scene_is_later',False)]:
            p = copy.deepcopy(PACK);p[field]=value
            with self.subTest(field=field),self.assertRaises(MOD.GateBlocked):MOD.prepare(p)
    def test_paid_boolean_in_dry_manifest_is_unsafe(self):
        p=copy.deepcopy(PACK);p['privacy']['fal_paid_approval_granted']=True
        with self.assertRaises(MOD.GateBlocked):MOD.prepare(p)
    def test_private_output_lock(self):
        p=copy.deepcopy(PACK);p['privacy']['source_assets_private_only']=False
        with self.assertRaises(MOD.GateBlocked):MOD.prepare(p)
    def test_existing_run_folder_blocks_repeat(self):
        with tempfile.TemporaryDirectory() as td:
            with patch.dict(os.environ,{'FAL_KEY':'0123456789test','CONFIRM_PAID':'YES'}):
                with self.assertRaises(MOD.GateBlocked):
                    MOD.execute(MANIFEST,Path(td),authorize_paid=True)
    def test_url_security(self):
        self.assertEqual(MOD.approved_result_url('https://fal.media/a.png'),'https://fal.media/a.png')
        for url in ['http://fal.media/a.png','https://evil.example/a.png',
                    'https://fal.media.evil.example/a.png','file:///etc/passwd','https://user:pw@fal.media/x']:
            with self.subTest(url=url),self.assertRaises(MOD.GateBlocked):MOD.approved_result_url(url)
    def test_plan_does_not_include_identity_of_sons(self):
        p=MOD.prepare(PACK)
        prompt=p['payload']['prompt']
        self.assertNotIn('Gamliel',prompt)
        self.assertNotIn('sons return',prompt.lower())
        self.assertIn('EXACTLY ONE adult traveler',prompt)
        self.assertIn('EXACTLY TWO connected human legs',prompt)
        self.assertIn('EXACTLY TWO anatomically coherent feet',prompt)
        self.assertIn('NO other people',prompt)
        self.assertNotIn('TWO ANONYMOUS travelers',prompt)
    def test_old_ambiguous_two_traveler_foot_prompt_is_blocked(self):
        p = copy.deepcopy(PACK)
        p['shots'][0]['prompt_subject_en'] = 'TWO ANONYMOUS travelers in close-up with too many feet.' * 10
        with self.assertRaises(MOD.GateBlocked):
            MOD.prepare(p)

    def test_missing_anatomy_contract_is_blocked(self):
        p = copy.deepcopy(PACK)
        del p['shots'][0]['anatomy_contract']
        with self.assertRaises(MOD.GateBlocked):
            MOD.prepare(p)

    def test_no_extra_billable_job_in_workflow(self):
        # Legacy manual route is intentionally inert; the only live payment
        # pathway has an exact one-file, fresh, single-use approval gate.
        manual=(ROOT/'.github/workflows/fal-private-opn01.yml').read_text()
        self.assertIn('if: ${{ false }}',manual)
        self.assertEqual(manual.count('--authorize-paid'),1)
        self.assertIn('seal_private_media.py seal',manual)
        self.assertNotIn('upload-artifact@v4\n        with:\n          name: OPN01_UNREVIEWED_PRIVATE.png',manual)
        one_use=(ROOT/'.github/workflows/fal-private-opn01-single-use-push.yml').read_text()
        self.assertIn('validate_opn01_single_use_approval',one_use)
        self.assertIn('production_authorizations/OPN01_RETAKE_01_APPROVED_ONCE.json',one_use)
        self.assertNotIn('production_authorizations/OPN01_APPROVED_ONCE.json',one_use)
        self.assertIn('github.run_attempt == 1',one_use)
        self.assertEqual(one_use.count('--authorize-paid'),1)
        self.assertIn('seal_private_media.py seal',one_use)

if __name__ == '__main__':unittest.main()