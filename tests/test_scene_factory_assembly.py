"""Offline real FFmpeg integration: no model, speech, or private source assets."""
import json, shutil, subprocess, tempfile, unittest, wave
from pathlib import Path
from tools.private_storyreel import assemble_technical_fixture
from tools.scene_factory import file_sha

@unittest.skipUnless(all(shutil.which(x) for x in ('ffmpeg','ffprobe','fc-match')), 'local FFmpeg tools required')
class AssemblyTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.temp=tempfile.TemporaryDirectory();cls.root=Path(cls.temp.name)
  cls.out=cls.root/'private-media'/'fixture';cls.result=assemble_technical_fixture(cls.root,cls.out)
 @classmethod
 def tearDownClass(cls):cls.temp.cleanup()
 def test_real_video_audio_subtitles_and_exact_timing(self):
  r=self.result;self.assertEqual(r['status'],'TECH_PASS_FIXTURE_ONLY');self.assertEqual(r['frames'],360)
  dest=(self.root/r['video']).parent;meta=json.loads((dest/'ffprobe.json').read_text())
  video,audio,subs=meta['streams'];self.assertEqual(video['nb_read_frames'],'360')
  self.assertEqual(float(audio['duration']),15);self.assertEqual(subs['tags']['language'],'heb')
  with wave.open(str(dest/'SYNTHETIC_TEST_ONLY.wav')) as wav:self.assertEqual(wav.getnframes(),720000)
  self.assertEqual(r['generation_requests'],0);self.assertFalse(r['artistic_scene_complete'])
 def test_second_run_cache_and_manifest_integrity(self):
  r=assemble_technical_fixture(self.root,self.out);self.assertTrue(r['cache_hit'])
  dest=(self.root/r['video']).parent
  for name,h in r['outputs'].items():self.assertEqual(file_sha(dest/name),h)
 def test_actual_rendered_motion(self):
  path=str(self.root/self.result['video'])
  def frame(t):
   return subprocess.check_output(['ffmpeg','-v','error','-ss',str(t),'-i',path,'-frames:v','1','-vf','crop=960:150:0:150','-f','rawvideo','-pix_fmt','rgb24','-'])
  a,b=frame(0),frame(.5);self.assertGreater(sum(abs(x-y) for x,y in zip(a,b))/len(a),3)
 def test_corrupt_cached_output_fails_closed(self):
  p=self.root/self.result['video'];original=p.read_bytes()
  try:
   p.write_bytes(b'corrupt')
   with self.assertRaisesRegex(ValueError,'CACHE_OUTPUT_CHANGED'):assemble_technical_fixture(self.root,self.out)
  finally:p.write_bytes(original)
 def test_unsafe_caption_rejected(self):
  with self.assertRaisesRegex(ValueError,'UNSAFE_TECHNICAL_CAPTION'):assemble_technical_fixture(self.root,self.out,'bad\u202e')
 def test_production_assembly_cannot_generate(self):
  p=subprocess.run(['python','-m','tools.scene_factory','assemble'],capture_output=True,text=True)
  self.assertEqual(p.returncode,2);self.assertIn('FIXTURES_ONLY',p.stdout)
