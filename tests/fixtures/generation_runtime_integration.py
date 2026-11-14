# Synthetic protocol fixtures, NOT real model-generated images.
import sys,importlib.util,tempfile,json,hashlib,io,base64,copy
from pathlib import Path
control=Path(__file__).resolve().parents[2];runtime=Path(sys.argv[1]).resolve()
sys.path.insert(0,str(control));import tools;tools.__path__.append(str(runtime/'tools'))
from tools.generation_issue_runtime import execute
from tools.comfy_scene_images import specifications,sha
from tools.cloudflare_image_backend import CloudflareClient
from PIL import Image
from tests import test_generation_ticket as fixtures
f=fixtures.GenerationTicketTests();f.setUp();f.history["entries"]={};f.ticket["history_sha256"]=hashlib.sha256(json.dumps(f.history,sort_keys=True,separators=(",",":")).encode()).hexdigest()
with tempfile.TemporaryDirectory() as temp:
 root=Path(temp);m=json.loads((runtime/'episodes/berakhot-01-01/comfy-opening-images.json').read_text());m['backend']=m['available_backends']['cloudflare'];m['references']=[]
 for i,color in enumerate(['red','green','blue']):
  p=root/f'private-media/reference{i}.png';p.parent.mkdir(exist_ok=True);Image.new('RGB',(256,144),color).save(p)
  m['references'].append(dict(path=str(p.relative_to(root)),sha256=sha(p),expected_sha256=sha(p),expected_size=[256,144],synthesis_rights_confirmed=True,role='TEST_ONLY'))
 for c in m['characters'].values():c['references']=m['references']
 m['shots']=[m['shots'][1]];d=m['shots'][0]['director'];d.pop('reference_preparation',None);d['reference_images']=[r['sha256'] for r in m['references']];d['reference_roles']=['TEST_ONLY']*3
 d['style_lock']=hashlib.sha256(json.dumps({k:m[k] for k in ['style','characters','references']},sort_keys=True,ensure_ascii=False).encode()).hexdigest()
 target=root/'episodes/berakhot-01-01';target.mkdir(parents=True);(target/'comfy-opening-images.json').write_text(json.dumps(m))
 rows=specifications(m,root);assert not rows[0]['missing'],rows[0]['missing'];key=rows[0]['key'];f.policy['spec_sha256']=key;f.ticket['spec_sha256']=key
 class Fake(CloudflareClient):
  calls=0
  def readiness(self,spec):return {}
  def prepare(self,spec,paths):assert len(paths)==3;return {'TEST_ONLY':True}
  def submit(self,*args,**kw):
   self.calls+=1;b=io.BytesIO();Image.new('RGB',(1024,576),'gray').save(b,format='PNG');return {'raw_base64':base64.b64encode(b.getvalue()).decode()}
 class PrivateStore:
  def __init__(self):self.saved=[]
  def replace(self,fileid,raw,mime):self.saved.append((fileid,raw,mime))
 client=Fake(m['backend']);store=PrivateStore()
 # This is the actual production invocation shape (no synthetic adapter).
 # A successful old one-shot runtime must NOT reach model readiness or Drive
 # when no hosted atomic coordinator has been reviewed and connected.
 from tools.chat_issue_bridge import RequestBlocked
 try:execute(f.event(),f.policy,f.history,m,root,store,'STATE','SNAP')
 except RequestBlocked as e:
  assert str(e)=='M3_LIVE_ATOMIC_COORDINATOR_NOT_CONNECTED_NO_INFERENCE',str(e)
 else:raise AssertionError('Legacy provider bypass allowed without M3')
 assert client.calls==0 and store.saved==[]
 result=execute(f.event(),f.policy,f.history,m,root,store,'STATE','SNAP',client)
 assert result['history_attempts']==5 and client.calls==1 and result['accepted'] is False
 assert store.saved[0][0]=='STATE' and store.saved[-1][0]=='SNAP'
 state=json.loads(next(raw for fileid,raw,mime in reversed(store.saved) if fileid=='STATE'))
 try:execute(f.event(),f.policy,state,m,root,store,'STATE','SNAP',client)
 except Exception:pass
 else:raise AssertionError('Replay admitted')
 assert client.calls==1
 # Exercise the REAL pinned OPN runtime -> offline M3 handoff, with a
 # synthetic six-attempt ledger and NO provider/Drive calls in this branch.
 f2=fixtures.GenerationTicketTests();f2.setUp()
 f2.history['entries']={}
 f2.history['attempts'].extend([{'key':'history-5'},{'key':'history-6'}])
 f2.policy['spec_sha256']=key;f2.ticket['spec_sha256']=key
 f2.ticket['historical_attempts']=6;f2.ticket['total_attempt_limit']=7
 f2.ticket['history_sha256']=hashlib.sha256(json.dumps(
  f2.history,sort_keys=True,separators=(',',':')).encode()).hexdigest()
 class FakeOfflineCoordinator:
  def __init__(self):self.begins=0;self.reserves=0
  def begin_offline(self,a):
   self.begins+=1
   assert a['shot_ids']==['OPN02'] and a['historical_attempts']==6
   return {'status':'OFFLINE_READY','replay':False,'live_dispatch_enabled':False}
  def reserve_offline(self,rid,shot):
   self.reserves+=1
   assert shot=='OPN02'
   return {'status':'OFFLINE_RESERVED_UNCERTAIN_NO_RETRY',
           'live_dispatch_enabled':False,'external_inference_requests':0}
 fake_coordinator=FakeOfflineCoordinator()
 writes_before=len(store.saved);calls_before=client.calls
 try:execute(f2.event(),f2.policy,f2.history,m,root,store,'STATE','SNAP',
             client,coordinator=fake_coordinator)
 except RequestBlocked as e:
  assert str(e)=='M3_OFFLINE_RESERVATION_IS_NOT_LIVE_DISPATCH_PERMISSION'
 else:raise AssertionError('Offline reservation treated as provider permission')
 assert fake_coordinator.begins==1 and fake_coordinator.reserves==1
 assert client.calls==calls_before and len(store.saved)==writes_before
 print(json.dumps({'status':'SYNTHETIC_END_TO_END_PASSED','conditioning_inputs':3,'retained_historical_attempts':4,'final_attempts':5,'mock_submissions':1,'real_inference_requests':0,'replay_blocked':True,'snapshot_saved':True}))
