"""Regression tests for shared Torah-film private preview renderer."""
import copy
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

S=Path(__file__).resolve().parents[1]/'tools'/'torah_cinema_engine.py'
spec=importlib.util.spec_from_file_location('film_engine',S)
mod=importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

class SharedCinemaContracts(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.doc=json.loads((Path(__file__).resolve().parents[1]/'examples'/'torah-cinema-editorial-preview.example.json').read_text(encoding='utf-8'))
 def fresh(self):return copy.deepcopy(self.doc)
 def assertBlocked(self,d):
  with self.assertRaises(ValueError): mod.validate_manifest(d)
 def test_valid_dry_run_contract(self):
  a=mod.validate_manifest(self.fresh());self.assertEqual(a['duration_frames'],792)
  self.assertEqual(a['shots'],5)
 def test_paid_requests_off(self):
  d=self.fresh();d['policy']['paid_requests_enabled']=True;self.assertBlocked(d)
 def test_no_image_generation(self):
  d=self.fresh();d['policy']['new_image_generation_enabled']=True;self.assertBlocked(d)
 def test_no_publication(self):
  d=self.fresh();d['policy']['publication_enabled']=True;self.assertBlocked(d)
 def test_no_public_images(self):
  d=self.fresh();d['assets']['SH01']['private']=False;self.assertBlocked(d)
 def test_no_embedded_private_key(self):
  d=self.fresh();d['private_key']='BEGIN SECRETS';self.assertBlocked(d)
 def test_footstep_outside_scene(self):
  d=self.fresh();d['audio_design']['footsteps_seconds']=[34.0];self.assertBlocked(d)
 def test_required_visible_source_tag(self):
  d=self.fresh();d['shots'][2]['tag']='';self.assertBlocked(d)
 def test_caption_too_long_for_mobile(self):
  d=self.fresh();d['shots'][1]['lines']=['א'*43];self.assertBlocked(d)
 def test_no_remote_urls(self):
  d=self.fresh();d['assets']['SH01']['path']='https://example.org/signed';self.assertBlocked(d)
 def test_gap_rejected(self):
  d=self.fresh();d['shots'][1]['start_frame']=169;self.assertBlocked(d)
 def test_unresolved_asset_rejected(self):
  d=self.fresh();d['shots'][1]['asset_id']='MISSING';self.assertBlocked(d)
 def test_motion_factor_must_be_finite(self):
  d=self.fresh();d['render']['camera_speed_vs_v10']=float('nan');self.assertBlocked(d)
 def test_h264_color_matrix_regression(self):
  self.assertIn('colour_primaries=1',mod.BT709_BSF)
  self.assertIn('transfer_characteristics=1',mod.BT709_BSF)
  self.assertIn('matrix_coefficients=1',mod.BT709_BSF)
  self.assertIn("'-bsf:v',BT709_BSF",S.read_text(encoding='utf8'))
 def test_correct_speed(self):
  self.assertEqual(self.doc['render']['camera_speed_vs_v10'],1.15)
 def test_must_mark_source_status(self):
  d=self.fresh();d['shots'][1]['source_status']='';self.assertBlocked(d)
 def test_bidi_injection_rejected(self):
  d=self.fresh();d['shots'][0]['lines']=['הי\u202eה'];self.assertBlocked(d)
 def test_source_path_not_verified_in_dry_run(self):
  self.assertTrue(mod.validate_manifest(self.doc)['ok'])
  with self.assertRaises(ValueError):mod.validate_manifest(self.doc,require_assets=True)
 def test_srt_time(self):
  self.assertEqual(mod.tstamp(792),'00:00:33,000')
  self.assertEqual(mod.tstamp(24),'00:00:01,000')
 def test_story_exclusively_legacy_art(self):
  self.assertEqual(self.doc['shots'][0]['asset_id'],'SH01')
  self.assertEqual(self.doc['shots'][1]['asset_id'],'SH09')
  self.assertNotIn('imagegen',str(self.doc).lower())
 def test_srt_written_in_hebrew(self):
  with tempfile.TemporaryDirectory() as t:
   path=Path(t)/'x.srt';mod.subtitles(self.doc['shots'],path)
   x=path.read_text(encoding='utf8')
   self.assertIn('קריאת שמע',x)
   self.assertIn('00:00:33,000',x)

if __name__=='__main__':unittest.main()