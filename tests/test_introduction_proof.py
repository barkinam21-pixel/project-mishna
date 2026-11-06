import copy
import json
from pathlib import Path
import unittest
from tools.introduction_proof import plan, assembly_command
ROOT=Path(__file__).resolve().parents[1]
class OpeningTests(unittest.TestCase):
 def setUp(self): self.config=json.loads((ROOT/'episodes/berakhot-01-01/introduction-proof.json').read_text())
 def test_missing_truthful(self):
  r=plan(self.config,ROOT);self.assertEqual(r['status'],'BLOCKED_MISSING_REAL_MEDIA');self.assertEqual(len(r['missing']),11);self.assertFalse(r['render_enabled'])
 def test_spend_release_profile(self):
  for key,value in [('profile','rejected'),('external_spend_usd',1),('release_authorized',True)]:
   c=copy.deepcopy(self.config);c[key]=value;self.assertEqual(plan(c,ROOT)['status'],'INVALID')
 def test_path_escape(self):
  self.config['assets']['OPN01']={'path':'../outside.png'};self.assertEqual(plan(self.config,ROOT)['status'],'INVALID')
 def test_unknown_asset(self):
  self.config['assets']['SH09']={};self.assertTrue(plan(self.config,ROOT)['errors'])
 def test_adapter_seven_shots(self):
  self.config['shots']=[{'id':f'OPN{i:02}','duration_frames':240} for i in range(1,8)]
  self.config['assets']={f'OPN{i:02}':{'path':f'private-media/{i}.png'} for i in range(1,8)}
  self.config['voice_takes']=[{'path':'private-media/voice.wav','start_frame':0}]
  args=assembly_command(self.config,ROOT,ROOT/'build');self.assertIn('1680',args);self.assertIn('concat=n=7:v=1:a=0[video]',' '.join(args))
