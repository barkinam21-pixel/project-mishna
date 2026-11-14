import copy,json,multiprocessing,os,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from tools.scene_factory import validate,keys,digest,SceneStore,SceneBlocked,writer_lock
ROOT=Path(__file__).resolve().parents[1]

class SceneFactoryTests(unittest.TestCase):
 def setUp(self):
  self.m=json.loads((ROOT/'episodes/berakhot-01-01/scene-prologue-v02.json').read_text());self.b=json.loads((ROOT/self.m['bible']['path']).read_text())
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.store=SceneStore(Path(self.tmp.name)/'private')
 def test_actual_prologue_conflicts_fail_closed(self):
  issues=validate(self.m,self.b,ROOT)
  self.assertIn('SCRIPT_NOT_APPROVED',issues);self.assertIn('ASSET_CONTINUITY_TIME_OF_DAY:EP-P07',issues)
  for name in ['daylight','voice-entry','shot-crosswalk','six-act-crosswalk']:self.assertIn('EDITORIAL_DECISION_PENDING:'+name,issues)
  self.assertEqual(len(self.m['shots']),15);self.assertEqual(self.m['shots'][-1]['end_frame'],2184)
 def test_script_and_bible_hashes_checked(self):
  self.m['script']['sha256']='0'*64;self.assertIn('SCRIPT_HASH_MISMATCH',validate(self.m,self.b,ROOT))
  self.b['states']['DAWN_BEFORE']['characters']['elder']['costume']='changed'
  self.assertIn('BIBLE_HASH_MISMATCH',validate(self.m,self.b,ROOT))
 def test_shot_swap_and_frame_gap(self):
  self.m['shots'][0],self.m['shots'][1]=self.m['shots'][1],self.m['shots'][0]
  issues=validate(self.m,self.b,ROOT);self.assertTrue(any(x.startswith('SHOT_ADJACENCY') for x in issues));self.assertTrue(any(x.startswith('FRAME_GAP') for x in issues))
 def test_wardrobe_axis_weather_prop_eyeline_changes(self):
  for field,value in [('characters',{}),('axis','north'),('weather','rain'),('props',{'waterskin':'left'}),('eyelines','camera')]:
   b=copy.deepcopy(self.b);b['states']['WRONG']=copy.deepcopy(b['states']['DAWN_BEFORE']);b['states']['WRONG'][field]=value
   m=copy.deepcopy(self.m);m['bible']['sha256']=digest(b);m['shots'][1]['pre_state']='WRONG'
   if field=='characters':
    with self.assertRaises(SceneBlocked):validate(m,b,ROOT)
   else:self.assertIn('CONTINUITY_'+field.upper()+':EP-P02',validate(m,b,ROOT))
 def test_invented_dialogue_not_ancient_quote(self):
  self.m['shots'][0]['source']['layer']='exact_source';self.assertIn('INVENTED_SOURCE_PRESENTED_AS_FACT:EP-P01',validate(self.m,self.b,ROOT))
 def test_chronology_gate(self):
  self.b['states']['DAWN_BEFORE']['era']='temple_destruction_70_ce';self.m['bible']['sha256']=digest(self.b)
  self.assertIn('CHRONOLOGY_70_CE_ACT4:EP-P01',validate(self.m,self.b,ROOT))
 def test_no_implicit_acceptance_or_unknown_fields(self):
  self.m['authorization']['generation_approved']=True
  with self.assertRaises(SceneBlocked):validate(self.m,self.b,ROOT)
  self.m['authorization']['generation_approved']=False;self.m['shots'][0]['ignore_safety']=True
  with self.assertRaises(SceneBlocked):validate(self.m,self.b,ROOT)
 def test_caption_safety_and_exact_text(self):
  self.m['shots'][0]['captions']=[{'text':'\u202e invented','start_frame':0,'end_frame':1}]
  errors=validate(self.m,self.b,ROOT);self.assertIn('CAPTION_RTL_INVALID:EP-P01',errors);self.assertIn('CAPTION_NOT_IN_LOCKED_SCRIPT:EP-P01',errors)
 def test_audio_timing(self):
  self.m['shots'][0]['sound'][0]['end_sample']=10**9
  self.assertIn('SOUND_TIMING:EP-P01',validate(self.m,self.b,ROOT))
 def test_subtitle_change_keeps_asset_keys(self):
  a=keys(self.m,self.b);self.m['shots'][0]['captions']=[{'text':'different'}];b=keys(self.m,self.b)
  self.assertEqual(a['asset_keys'],b['asset_keys']);self.assertNotEqual(a['build_key'],b['build_key'])
 def test_duplicate_and_changed_request(self):
  first=self.store.plan(self.m,self.b,ROOT,'test');second=self.store.plan(self.m,self.b,ROOT,'test')
  self.assertFalse(first['cache_hit']);self.assertTrue(second['cache_hit']);self.assertEqual(self.store.recover()[2],1)
  self.m['shots'][0]['description']='changed'
  with self.assertRaisesRegex(SceneBlocked,'SPEC_CHANGED'):self.store.plan(self.m,self.b,ROOT,'test')
 def test_resume_after_journal_fsync_before_snapshot(self):
  real=Path.replace
  def fail(src,dst):
   if src.name=='state.tmp':raise OSError('SIMULATED_CRASH')
   return real(src,dst)
  with patch.object(Path,'replace',fail):
   with self.assertRaises(OSError):self.store.plan(self.m,self.b,ROOT,'resume')
  result=SceneStore(self.store.path).plan(self.m,self.b,ROOT,'resume');self.assertTrue(result['cache_hit']);self.assertEqual(self.store.recover()[2],1)
 def test_corrupt_journal_blocks_without_replay(self):
  self.store.plan(self.m,self.b,ROOT,'original');(self.store.path/'events.jsonl').write_text('broken')
  with self.assertRaises(SceneBlocked):self.store.plan(self.m,self.b,ROOT,'another')
 def test_checkpoint_changed_output_not_reused(self):
  f=Path(self.tmp.name)/'out';f.write_text('first');h=__import__('hashlib').sha256(f.read_bytes()).hexdigest()
  self.store.checkpoint('continuity',{'bible':'1'},{str(f):h});self.assertTrue(self.store.checkpoint('continuity',{'bible':'1'},{str(f):h})['cache_hit'])
  f.write_text('changed')
  with self.assertRaises(SceneBlocked):self.store.checkpoint('continuity',{'bible':'1'},{str(f):h})
 def test_writer_lock_blocks_racing_process(self):
  from subprocess import run
  with writer_lock(self.store.path/'writer.lock'):
   p=run([__import__('sys').executable,'-c','from pathlib import Path;from tools.scene_factory import writer_lock;\nwith writer_lock(Path('+repr(str(self.store.path/'writer.lock'))+')):pass'],cwd=ROOT,capture_output=True)
  self.assertNotEqual(p.returncode,0)
 def test_generation_stage_never_available(self):
  with self.assertRaisesRegex(SceneBlocked,'NOT_IMPLEMENTED'):self.store.checkpoint('generating',{}, {})
 def test_revalidation_never_trusts_old_cache_after_asset_change(self):
  root=Path(self.tmp.name);(root/'script.txt').write_bytes((ROOT/self.m['script']['path']).read_bytes());self.m['script']['path']='script.txt'
  p=root/'asset.png';p.write_bytes(b'TEST_HASH_ONLY');self.m['shots'][0]['asset'].update(path='asset.png',sha256=__import__('hashlib').sha256(p.read_bytes()).hexdigest())
  self.store.plan(self.m,self.b,root,'asset-change');p.write_bytes(b'CORRUPT')
  result=self.store.plan(self.m,self.b,root,'asset-change');self.assertFalse(result['cache_hit']);self.assertIn('ASSET_HASH_MISMATCH:EP-P01',result['issues'])
 def test_path_escape_blocked(self):
  self.m['script']['path']='../outside'
  with self.assertRaises(SceneBlocked):validate(self.m,self.b,ROOT)
 def test_lock_releases_after_real_process_crash(self):
  import subprocess,sys
  code='import os;from pathlib import Path;from tools.scene_factory import writer_lock;\nwith writer_lock(Path('+repr(str(self.store.path/'writer.lock'))+')):os._exit(7)'
  p=subprocess.run([sys.executable,'-c',code],cwd=ROOT);self.assertEqual(p.returncode,7)
  with writer_lock(self.store.path/'writer.lock'):pass
