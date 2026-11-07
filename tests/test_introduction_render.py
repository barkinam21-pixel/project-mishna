import copy,json,unittest,shutil
from pathlib import Path
from tools.introduction_render import validate,render
from tools.introduction_fixture import run
@unittest.skipUnless(all(shutil.which(x) for x in ['ffmpeg','ffprobe','fc-match']), 'Requires FFmpeg/FFprobe/fontconfig; dedicated assembly workflow installs them')
class RenderIntegration(unittest.TestCase):
 def test_actual_mp4_cache_and_replacement(self):
  root=Path(__file__).resolve().parents[1]
  import shutil
  shutil.rmtree(root/'build/introduction-fixture',ignore_errors=True)
  run(root)
  result=json.loads((root/'build/introduction-fixture/integration-result.json').read_text())
  self.assertTrue(result['second']['cache_hit']);self.assertEqual(result['one_image_replaced']['normalized_images_created'],1)
  config=json.loads((root/'build/introduction-fixture/manifest.json').read_text())
  with self.assertRaises(ValueError):render(config,root,root/'build/unsafe',False)
  for change in ['caption','voice','approval','missing']:
   c=copy.deepcopy(config)
   if change=='caption':c['shots'][0]['duration_frames']=1
   if change=='voice':c['voice_takes'][1]['start_frame']=0
   if change=='approval':c['release_authorized']=True
   if change=='missing':c['assets']['OPN01']['path']='missing.png'
   with self.assertRaises((ValueError,FileNotFoundError)):validate(c,root,True)
