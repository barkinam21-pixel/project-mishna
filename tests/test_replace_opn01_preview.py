"""Fast no-network contracts for exact 45s opening shot replacement."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
SPEC=importlib.util.spec_from_file_location('replace_opn01_preview',ROOT/'tools/replace_opn01_preview.py')
MOD=importlib.util.module_from_spec(SPEC);SPEC.loader.exec_module(MOD)
DATA=json.loads((ROOT/'episodes/berakhot-01-01/opening-45s-director-pack-v1.json').read_text())

class ShotReplacement(unittest.TestCase):
    def test_expected_story_order(self):
        self.assertEqual(DATA['shots'][0]['id'],'OPN01')
        self.assertEqual(DATA['shots'][0]['frames'],MOD.FIRST)
        self.assertEqual(DATA['shots'][-1]['end_frame'],MOD.TOTAL)
    def test_ass_source_label_is_explicit(self):
        with tempfile.TemporaryDirectory() as td:
            f=Path(td)/'stamp.ass';MOD.ass_stamp(f)
            s=f.read_text()
            self.assertIn('המחזה סמלית',s)
            self.assertIn('טרם אושר',s)
            self.assertIn('Noto Sans Hebrew',s)
    def test_stamp_not_fabricated_historical_quote(self):
        with tempfile.TemporaryDirectory() as td:
            f=Path(td)/'stamp.ass';MOD.ass_stamp(f)
            s=f.read_text();self.assertNotIn('חייבין',s)
            self.assertNotIn('מותרין',s)
    def test_exact_sha_needed(self):
        with tempfile.TemporaryDirectory() as td:
            img=Path(td)/'img.png';img.write_bytes(b'PNG')
            master=Path(td)/'master.mp4';master.write_bytes(b'video')
            with self.assertRaises(MOD.UnsafeMedia):
                MOD.preflight(DATA,img,'bad-hash',master)
    def test_missing_media_never_autosubstitutes(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)
            with self.assertRaises(MOD.UnsafeMedia):
                MOD.preflight(DATA,p/'wrong.png','0'*64,p/'wrong.mp4')
    def test_output_keeps_hebrew_tags_and_phone_friendly_codec(self):
        s=(ROOT/'tools/replace_opn01_preview.py').read_text()
        self.assertIn("'language=heb'",s)
        self.assertIn("'colorprim=bt709:transfer=bt709:colormatrix=bt709'",s)
        self.assertIn("'-movflags','+faststart'",s)
        self.assertIn('end_frame={FIRST}',s)
        self.assertIn('start_frame={FIRST}:end_frame={TOTAL}',s)

if __name__=='__main__':unittest.main()