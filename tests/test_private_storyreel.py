"""Offline structural tests for 75s technical storyreel (no image generation)."""
import unittest, json, copy, importlib.util
from pathlib import Path
from tempfile import TemporaryDirectory

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('reel',ROOT/'tools/private_storyreel.py')
reel=importlib.util.module_from_spec(spec)
spec.loader.exec_module(reel)
PACK=ROOT/'episodes/berakhot-01-01/fal-prepaid-shotpack-v1.json'
CAP=ROOT/'episodes/berakhot-01-01/private-storyreel-captions.json'

class ReelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pack=json.loads(PACK.read_text(encoding='utf-8'))
        cls.caps=json.loads(CAP.read_text(encoding='utf-8'))

    def test_valid_plan_is_explicitly_unapproved(self):
        result=reel.plan(self.pack,self.caps)
        self.assertEqual(result['frames'],1800)
        self.assertFalse(result['source_approved'])
        self.assertEqual(result['original_ai_illustrations_generated'],0)
        self.assertEqual(result['external_paid_api_calls'],0)

    def test_missing_caption(self):
        caps=copy.deepcopy(self.caps);caps['cues'].pop()
        with self.assertRaises(ValueError):reel.plan(self.pack,caps)

    def test_caption_shot_mismatch(self):
        caps=copy.deepcopy(self.caps);caps['cues'][0]['shot_id']='SH02'
        with self.assertRaises(ValueError):reel.plan(self.pack,caps)

    def test_bidi_controls_rejected(self):
        caps=copy.deepcopy(self.caps);caps['cues'][0]['text']='שלום\u202eעולם'
        with self.assertRaises(ValueError):reel.plan(self.pack,caps)

    def test_no_paid_requests(self):
        pack=copy.deepcopy(self.pack);pack['authorization']['paid_request_authorized']=True
        with self.assertRaises(ValueError):reel.plan(pack,self.caps)

    def test_mismatched_timeline_rejected(self):
        pack=copy.deepcopy(self.pack);pack['shots'][0]['end_frame']=145
        with self.assertRaises(ValueError):reel.plan(pack,self.caps)

    def test_srt_vtt_have_full_timing(self):
        with TemporaryDirectory() as td:
            dest=Path(td);reel.write_subtitle_files(self.pack,self.caps,dest)
            srt=(dest/'private_storyreel_draft.srt').read_text(encoding='utf-8')
            vtt=(dest/'private_storyreel_draft.vtt').read_text(encoding='utf-8')
            self.assertIn('00:01:15,000',srt)
            self.assertIn('00:01:15.000',vtt)
            self.assertEqual(srt.count(' --> '),16)
            self.assertEqual(vtt.count(' --> '),16)
            self.assertTrue(vtt.startswith('WEBVTT'))

if __name__=='__main__':unittest.main()