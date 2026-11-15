"""Real P07 MIME compiler -> real SQLite production ledger -> fake provider/Drive.
Only image pixels/transport are synthetic. Reopens SQLite on EVERY RPC.
"""
import concurrent.futures,copy,datetime as dt,io,json,shutil,subprocess,unittest
from pathlib import Path
from unittest.mock import patch
from tests import test_p07_cloudflare_only as fixtures
from tools import m3_production_runner as m

class Coordinator:
 def __init__(self,path,config):self.path=str(path);self.config=config
 def call(self,operation,payload):
  r=subprocess.run(['node','tests/fixtures/m3_production_sqlite.mjs'],input=json.dumps(dict(path=self.path,config=self.config,operation=operation,payload=payload)),text=True,capture_output=True)
  if r.returncode:raise m.ProductionBlocked(json.loads(r.stdout)['error'])
  return json.loads(r.stdout)

class Provider:
 def __init__(self):self.calls=0
 def submit(self,packet):
  from PIL import Image
  self.calls+=1
  if b'input_image_2' not in packet['body']:raise AssertionError('missing actual references')
  b=io.BytesIO();Image.new('RGB',(1024,576),(60,70,80)).save(b,format='WEBP');return b.getvalue()

class Drive:
 def __init__(self,history):
  import zipfile
  b=io.BytesIO()
  with zipfile.ZipFile(b,'w') as z:z.writestr('snapshot.json','{}')
  self.files={'state':history.encode(),'snapshot':b.getvalue()};self.fail=False
 def metadata(self,id):return {'shared':False,'permissions':[{'type':'user','role':'owner'}]}
 def download(self,id):return self.files[id]
 def replace(self,id,raw,mime):
  if self.fail:raise OSError('test network failure')
  self.files[id]=raw

@unittest.skipUnless(shutil.which('node') and int(subprocess.check_output(['node','-p','process.versions.node.split(".")[0]']).strip())>=24, 'Node24 required for actual SQLite')
class ProductionTests(unittest.TestCase):
 def setUp(self):
  self.fixture=fixtures.CloudflareOnlyMultipartTests();self.fixture.setUp();self.addCleanup(self.fixture.doCleanups)
  self.root=self.fixture.root;self.draft=self.fixture.draft;self.req='a'*32
  _,self.spec=m.prepare(self.draft,self.root,self.req)
  self.history=json.dumps({'entries':{},'attempts':[{'key':str(i)} for i in range(6)]})
  self.config=dict(version=1,model=m.MODEL,scene_id='ACT1-PROLOGUE',shot_id='EP-P07',request_id=self.req,max_attempts=1,total_attempt_limit=7,max_charge_usd=0,baseline_attempts=6,history_sha256=m.sha(self.history.encode()),body_sha256=self.spec['body_sha256'],draft_sha256=self.spec['draft_sha256'],references_sha256=self.spec['references_sha256'],expires_at=(dt.datetime.now(dt.timezone.utc)+dt.timedelta(minutes=4)).isoformat())
  for k in ('owner_approved','synthesis_rights_verified','privacy_verified','free_hard_stop_verified','quota_verified','legacy_writers_fenced','private_storage_verified'):self.config[k]=True
  self.c=Coordinator(self.root/'real.sqlite',self.config);self.p=Provider();self.d=Drive(self.history)
 def test_full_compile_real_sqlite_and_delivery_resume(self):
  r=m.run_once(self.draft,self.root,self.req,self.history,self.c,self.p);self.assertFalse(r['accepted']);self.assertEqual(self.p.calls,1)
  self.d.fail=True
  with self.assertRaises(OSError):m.resume_delivery(self.root,self.req,self.c,self.d,'state','snapshot')
  self.d.fail=False
  for _ in range(2):self.assertEqual(m.resume_delivery(self.root,self.req,self.c,self.d,'state','snapshot')['status'],'DELIVERED_PRIVATE')
  self.assertEqual(self.p.calls,1);h=json.loads(self.d.files['state']);self.assertEqual(len(h['attempts']),7);self.assertEqual(h['attempts'][:6],json.loads(self.history)['attempts'])
 def test_timeout_after_possible_post_holds_after_restart(self):
  def uncertain(packet):self.p.calls+=1;raise TimeoutError('possible submission')
  self.p.submit=uncertain
  with self.assertRaises(TimeoutError):m.run_once(self.draft,self.root,self.req,self.history,self.c,self.p)
  with self.assertRaisesRegex(m.ProductionBlocked,'NO_RETRY'):m.run_once(self.draft,self.root,self.req,self.history,self.c,self.p)
  with self.assertRaises(m.ProductionBlocked):self.c.call('reserve',self.spec)
  self.assertEqual(self.p.calls,1);self.assertEqual(self.c.call('status',{})['status'],'SUBMISSION_UNCERTAIN_NO_RETRY')
 def test_crash_after_durable_raw_save_recovers_without_post(self):
  with patch.object(m,'reconcile_saved',side_effect=SystemExit('crash after bytes fsync')):
   with self.assertRaises(SystemExit):m.run_once(self.draft,self.root,self.req,self.history,self.c,self.p)
  m.resume_delivery(self.root,self.req,self.c,self.d,'state','snapshot');self.assertEqual(self.p.calls,1)
 def test_competing_process_connections_one_reservation(self):
  self.c.call('bootstrap',{'history_json':self.history})
  def call(_):
   try:self.c.call('reserve',self.spec);return True
   except m.ProductionBlocked:return False
  with concurrent.futures.ThreadPoolExecutor(2) as pool:self.assertEqual(sum(pool.map(call,range(2))),1)
  self.assertEqual(len(self.c.call('journal',{})['attempts']),7)
 def test_wrong_history_cannot_import_or_dispatch(self):
  with self.assertRaisesRegex(m.ProductionBlocked,'HASH_MISMATCH'):m.run_once(self.draft,self.root,self.req,self.history+' ',self.c,self.p)
  self.assertEqual(self.p.calls,0)
 def test_scoped_gates_and_request_hashes_reject(self):
  for key in ('legacy_writers_fenced','owner_approved','free_hard_stop_verified','synthesis_rights_verified'):
   self.config[key]=False
   with self.assertRaises(m.ProductionBlocked):self.c.call('bootstrap',{'history_json':self.history})
   self.config[key]=True
  self.c.call('bootstrap',{'history_json':self.history});wrong=copy.deepcopy(self.spec);wrong['body_sha256']='b'*64
  with self.assertRaises(m.ProductionBlocked):self.c.call('reserve',wrong)
  self.assertEqual(self.p.calls,0)
 def test_receipt_tamper_and_expired_authority_delivery(self):
  m.run_once(self.draft,self.root,self.req,self.history,self.c,self.p)
  a=self.c.call('status',{})['attempt'];receipt=json.loads(a['receipt']);receipt['accepted']=True
  with self.assertRaises(m.ProductionBlocked):self.c.call('receipt',{'token':a['token'],'receipt':receipt})
  self.config['expires_at']='2020-01-01T00:00:00Z'
  m.resume_delivery(self.root,self.req,self.c,self.d,'state','snapshot');self.assertEqual(self.p.calls,1)
 def test_public_ci_blocks_before_reference_read(self):
  with patch.dict('os.environ',{'GITHUB_ACTIONS':'true'}):
   with self.assertRaisesRegex(m.ProductionBlocked,'PUBLIC_CI'):m.run_once(self.draft,self.root,self.req,self.history,self.c,self.p)
  self.assertEqual(self.p.calls,0)

 def test_lost_reservation_reply_cannot_create_on_resume(self):
  original=self.c.call
  def lost(operation,payload):
   result=original(operation,payload)
   if operation=='reserve':raise TimeoutError('reservation committed but response lost')
   return result
  self.c.call=lost
  with self.assertRaises(TimeoutError):m.run_once(self.draft,self.root,self.req,self.history,self.c,self.p)
  self.c.call=original
  with self.assertRaises(m.ProductionBlocked):m.run_once(self.draft,self.root,self.req,self.history,self.c,self.p)
  self.assertEqual(self.p.calls,0);self.assertEqual(len(self.c.call('journal',{})['attempts']),7)
 def test_snapshot_preserves_old_bytes_and_refuses_changed_members(self):
  previous=m.append_snapshot(self.d.files['snapshot'],{'private-media/old-candidate.png':b'old-original-unchanged'})
  self.d.files['snapshot']=previous
  m.run_once(self.draft,self.root,self.req,self.history,self.c,self.p)
  m.resume_delivery(self.root,self.req,self.c,self.d,'state','snapshot')
  import zipfile
  with zipfile.ZipFile(io.BytesIO(self.d.files['snapshot'])) as z:self.assertEqual(z.read('private-media/old-candidate.png'),b'old-original-unchanged')
  with self.assertRaisesRegex(m.ProductionBlocked,'WOULD_OVERWRITE'):m.append_snapshot(previous,{'private-media/old-candidate.png':b'changed'})

class TransportTests(unittest.TestCase):
 def test_signatures_bind_production_route_and_no_redirects(self):
  class Opener:
   def open(self,req,timeout):
    self.req=req
    raise TimeoutError()
  o=Opener();c=m.SignedCoordinator('https://private.workers.dev','ab'*32,o)
  with self.assertRaisesRegex(m.ProductionBlocked,'UNCERTAIN'):c.call('reserve',{})
  self.assertTrue(o.req.full_url.endswith('/m3/v1/production'))
  import hashlib,hmac
  stamp=o.req.get_header('X-m3-timestamp')
  expected=hmac.new(bytes.fromhex('ab'*32),b'POST\n/m3/v1/production\n'+stamp.encode()+b'\n'+o.req.data,hashlib.sha256).hexdigest()
  self.assertEqual(o.req.get_header('X-m3-signature'),expected)
 def test_cloudflare_unknown_response_sends_once_only(self):
  class Opener:
   def __init__(self):self.calls=0
   def open(self,req,timeout):
    self.calls+=1;self.req=req;raise TimeoutError()
  o=Opener();p=m.CloudflareOnlyTransport('a'*32,'fake-test-token',o)
  with self.assertRaisesRegex(m.ProductionBlocked,'NO_RETRY'):p.submit({'body':b'fake','endpoint_suffix':'/ai/run/'+m.MODEL,'content_type':'application/octet-stream'})
  self.assertEqual(o.calls,1);self.assertTrue(o.req.full_url.startswith('https://api.cloudflare.com/'))
  with self.assertRaises(m.ProductionBlocked):p.submit({'endpoint_suffix':'https://other-provider.invalid'})
  self.assertEqual(o.calls,1)
