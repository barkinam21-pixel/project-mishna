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
f=fixtures.GenerationTicketTests();f.setUp();f.history["entries"]={};f.history['attempts'].append({'key':'consumed-opn02'})
f.ticket.update(shot_id='OPN03',operation='generate-opn03-once',approval='APPROVE_ONE_OPN03_FREE_ATTEMPT',historical_attempts=5,total_attempt_limit=6)f.ticket["history_sha256"]=hashlib.sha256(json.dumps(f.history,sort_keys=True,separators=(",",":")).encode()).hexdigest()
with tempfile.TemporaryDirectory() as temp:
 root=Path(temp);m=json.loads((runtime/'episodes/berakhot-01-01/comfy-opening-images.json').read_text());m['backend']=m['available_backends']['cloudflare'];m['references']=[]
 for i,color in enumerate(['red','green','blue']):
  p=root/f'private-media/reference{i}.png';p.parent.mkdir(exist_ok=True);Image.new('RGB',(256,144),color).save(p)
  m['references'].append(dict(path=str(p.relative_to(root)),sha256=sha(p),expected_sha256=sha(p),expected_size=[256,144],synthesis_rights_confirmed=True,role='TEST_ONLY'))
 for c in m['characters'].values():c['references']=m['references']
 m['shots']=[m['shots'][2]];d=m['shots'][0]['director'];d.pop('reference_preparation',None);d['reference_images']=[r['sha256'] for r in m['references']];d['reference_roles']=['TEST_ONLY']*3
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
 result=execute(f.event(),f.policy,f.history,m,root,store,'STATE','SNAP',client)
 assert result['history_attempts']==6 and result['status']=='OPN03_PRIVATE_CANDIDATE_SAVED' and client.calls==1 and result['accepted'] is False
 assert store.saved[0][0]=='STATE' and store.saved[-1][0]=='SNAP'
 state=json.loads(next(raw for fileid,raw,mime in reversed(store.saved) if fileid=='STATE'))
 try:execute(f.event(),f.policy,state,m,root,store,'STATE','SNAP',client)
 except Exception:pass
 else:raise AssertionError('Replay admitted')
 assert client.calls==1
 print(json.dumps({'status':'SYNTHETIC_END_TO_END_PASSED','conditioning_inputs':3,'retained_historical_attempts':5,'final_attempts':6,'mock_submissions':1,'real_inference_requests':0,'replay_blocked':True,'snapshot_saved':True}))
