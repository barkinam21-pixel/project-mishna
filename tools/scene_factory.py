"""M1 deterministic scene control. No network, model calls or creative approval."""
import argparse,copy,hashlib,json,os,re,sys,time,unicodedata
from contextlib import contextmanager
from pathlib import Path

class SceneBlocked(ValueError):pass

def digest(value):return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()
def file_sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def within(root,name):
    p=(Path(root)/name).resolve()
    if not p.is_relative_to(Path(root).resolve()):raise SceneBlocked('PATH_OUTSIDE_ROOT')
    return p

def load(p):return json.loads(Path(p).read_text(encoding='utf-8'))
def required(obj,fields,where):
    if not isinstance(obj,dict) or set(obj)!=set(fields):raise SceneBlocked('SCHEMA_FIELDS:'+where)

def validate(scene,bible,root):
    """Structural failures raise; production gates return distinct stable reasons."""
    required(scene,'version id hierarchy script bible shots decisions authorization'.split(),'scene')
    if type(scene['version']) is not int or type(bible.get('version')) is not int or scene['version']!=1 or bible.get('version')!=1:raise SceneBlocked('SCHEMA_VERSION')
    required(scene['script'],['path','sha256','approved','reviewer','voice_entry'],'script')
    required(scene['bible'],['path','sha256'],'bible')
    required(scene['hierarchy'],['episode','act','sequence','scene'],'hierarchy')
    if scene['hierarchy']['scene']!=scene['id'] or type(scene['hierarchy']['act']) is not int:raise SceneBlocked('HIERARCHY_INVALID')
    required(scene['authorization'],['max_inference','budget_usd','generation_approved'],'authorization')
    if type(scene['authorization']['max_inference']) is not int or scene['authorization']['max_inference']<0 or type(scene['authorization']['budget_usd']) not in (int,float) or scene['authorization']['budget_usd']!=0 or scene['authorization']['generation_approved'] is not False:raise SceneBlocked('M1_NO_GENERATION_ALLOWED')
    issues=[]
    p=within(root,scene['script']['path'])
    if not p.is_file() or file_sha(p)!=scene['script']['sha256']:issues.append('SCRIPT_HASH_MISMATCH')
    if digest(bible)!=scene['bible']['sha256']:issues.append('BIBLE_HASH_MISMATCH')
    if scene['script']['approved'] is not True or not scene['script']['reviewer']:issues.append('SCRIPT_NOT_APPROVED')
    for decision in scene['decisions']:
        if not isinstance(decision,dict) or not all(k in decision for k in ('id','approved','reason','recommendation')):raise SceneBlocked('DECISION_INVALID')
        if decision['approved'] is not True or not decision.get('reviewer'):issues.append('EDITORIAL_DECISION_PENDING:'+decision['id'])
    lines=p.read_text(encoding='utf-8').splitlines() if p.is_file() else []
    shots=scene['shots'];ids=[s.get('id') for s in shots]
    if not shots or len(set(ids))!=len(ids) or any(not isinstance(x,str) or not re.fullmatch(r'[A-Z0-9-]+',x) for x in ids):raise SceneBlocked('SHOT_IDS_INVALID')
    previous=None;cursor=0;states=bible.get('states',{})
    for i,shot in enumerate(shots):
        required(shot,'id beat why description script_span source camera pre_state post_state exception asset sound captions start_frame end_frame previous next'.split(),'shot')
        required(shot['camera'],['intent','movement'],'camera')
        if not all(isinstance(shot['camera'][k],str) and shot['camera'][k].strip() for k in ('intent','movement')):raise SceneBlocked('CAMERA_INTENT_MISSING')
        if not shot['why'].strip() or not shot['beat'] or not shot['description'].strip():issues.append('SHOT_HAS_NO_STORY_FUNCTION:'+shot['id'])
        if shot['previous']!=(ids[i-1] if i else None) or shot['next']!=(ids[i+1] if i+1<len(ids) else None):issues.append('SHOT_ADJACENCY:'+shot['id'])
        start,end=shot['start_frame'],shot['end_frame']
        if type(start) is not int or type(end) is not int or start!=cursor or end<=start:issues.append('FRAME_GAP_OR_OVERLAP:'+shot['id'])
        cursor=end
        span=shot['script_span']
        if not isinstance(span,list) or len(span)!=2 or any(type(x) is not int for x in span) or not 1<=span[0]<=span[1]<=len(lines):issues.append('SCRIPT_SPAN_INVALID:'+shot['id'])
        source=shot['source']
        required(source,['layer','confidence','reference','verified','speaker_type','invented'],'source')
        if source['layer'] not in ('exact_source','attributed_commentary','historical_reconstruction','symbolic_dramatization','traditional_account'):issues.append('SOURCE_LAYER_INVALID:'+shot['id'])
        if not source['reference'] or not source['confidence'] or source['verified'] is not True:issues.append('SOURCE_REVIEW_PENDING:'+shot['id'])
        if source['invented'] is True and source['layer']!='symbolic_dramatization':issues.append('INVENTED_SOURCE_PRESENTED_AS_FACT:'+shot['id'])
        for field in ('pre_state','post_state'):
            if shot[field] not in states:raise SceneBlocked('UNKNOWN_CONTINUITY_STATE')
        pre,post=states[shot['pre_state']],states[shot['post_state']]
        exc=shot['exception']
        valid_exc=isinstance(exc,dict) and exc.get('approved') is True and bool(exc.get('reviewer')) and bool(exc.get('reason')) and bool(exc.get('transition')) and bool(exc.get('fields'))
        if exc and not valid_exc:issues.append('CONTINUITY_EXCEPTION_UNAPPROVED:'+shot['id'])
        if previous is not None:
            differences=[k for k in set(previous)|set(pre) if previous.get(k)!=pre.get(k)]
            for k in differences:
                if not valid_exc or k not in exc['fields']:issues.append('CONTINUITY_'+k.upper()+':'+shot['id'])
        for k in ('characters','location','era','time_of_day','sun_direction','weather','palette','style','axis','screen_direction'):
            if pre.get(k)!=post.get(k) and (not valid_exc or k not in exc['fields']):issues.append('WITHIN_SHOT_'+k.upper()+':'+shot['id'])
        previous=post
        # State is a declaration, never a computer-vision claim.
        for state in (pre,post):
            for field in ('characters','location','era','time_of_day','sun_direction','weather','palette','style','axis','screen_direction','eyelines','props','emotion','knowledge','sound_state'):
                if field not in state or state[field] is None:raise SceneBlocked('CONTINUITY_FIELD_MISSING:'+field)
            if not state['characters']:raise SceneBlocked('CHARACTER_BIBLE_MISSING')
            for char in state['characters'].values():
                if not all(k in char for k in ('face_lock','age','proportions','costume','reference_sha256')):raise SceneBlocked('CHARACTER_LOCK_MISSING')
        act=scene['hierarchy']['act']
        if pre['era']=='temple_destruction_70_ce' and act!=4:issues.append('CHRONOLOGY_70_CE_ACT4:'+shot['id'])
        if pre['era']=='rabbi_redaction_200_ce' and act!=5:issues.append('CHRONOLOGY_REDACTION_ACT5:'+shot['id'])
        if source['layer']=='exact_source' and pre['era']=='symbolic_sinai':issues.append('SYMBOLIC_EVENT_AS_FACT:'+shot['id'])
        asset=shot['asset']
        required(asset,['id','origin','state','accepted','path','sha256'],'asset')
        if asset['origin'] not in ('original','derivative','repaired','mock','human_art','missing'):raise SceneBlocked('ASSET_ORIGIN_INVALID')
        if asset['state'] is not None:
            if asset['state'] not in states:raise SceneBlocked('UNKNOWN_ASSET_CONTINUITY_STATE')
            for field in pre:
                if states[asset['state']].get(field)!=pre[field]:issues.append('ASSET_CONTINUITY_'+field.upper()+':'+shot['id'])
        if asset['path']:
            ap=within(root,asset['path'])
            if not ap.is_file() or file_sha(ap)!=asset['sha256']:issues.append('ASSET_HASH_MISMATCH:'+shot['id'])
        if asset['accepted'] is not True or asset['origin'] in ('mock','missing') or not asset['path']:issues.append('ASSET_NOT_APPROVED:'+shot['id'])
        for cue in shot['sound']:
            if not all(k in cue for k in ('id','kind','start_sample','end_sample','license','path','sha256')):raise SceneBlocked('SOUND_SCHEMA_INVALID')
            if type(cue['start_sample']) is not int or type(cue['end_sample']) is not int or not 0<=cue['start_sample']<cue['end_sample']<=cursor*2000:issues.append('SOUND_TIMING:'+shot['id'])
            if not cue['license'] or not cue['path']:issues.append('SOUND_MISSING_OR_UNLICENSED:'+cue['id'])
            elif not within(root,cue['path']).is_file() or file_sha(within(root,cue['path']))!=cue['sha256']:issues.append('SOUND_HASH_MISMATCH:'+cue['id'])
        for cue in shot['captions']:
            text=cue['text']
            if not isinstance(text,str) or unicodedata.normalize('NFC',text)!=text or re.search('[\u202a-\u202e\u2066-\u2069\ufffd]',text):issues.append('CAPTION_RTL_INVALID:'+shot['id'])
            if len(text.splitlines())>2 or any(len(l)>42 for l in text.splitlines()):issues.append('CAPTION_LENGTH:'+shot['id'])
            if type(cue.get('start_frame')) is not int or type(cue.get('end_frame')) is not int or not start<=cue['start_frame']<cue['end_frame']<=end:issues.append('CAPTION_TIMING:'+shot['id'])
            if not lines or span[0]<1 or span[1]>len(lines) or text not in '\n'.join(lines[span[0]-1:span[1]]):issues.append('CAPTION_NOT_IN_LOCKED_SCRIPT:'+shot['id'])
    return sorted(set(issues))


def keys(scene,bible):
    assets={s['id']:digest({'asset':s['asset'],'camera':s['camera'],'pre':bible['states'][s['pre_state']],'post':bible['states'][s['post_state']],'description':s['description']}) for s in scene['shots']}
    return {'asset_keys':assets,'build_key':digest({'scene':scene,'bible':bible})}


@contextmanager
def writer_lock(path):
    """OS lock releases on crash. No unsafe deletion of another process's lock."""
    path.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
    with path.open('a+b') as f:
        if os.name=='nt':
            import msvcrt
            if f.tell()==0:f.write(b'0');f.flush()
            f.seek(0)
            try:msvcrt.locking(f.fileno(),msvcrt.LK_NBLCK,1)
            except OSError:raise SceneBlocked('SCENE_WRITER_BUSY') from None
            try:yield
            finally:f.seek(0);msvcrt.locking(f.fileno(),msvcrt.LK_UNLCK,1)
        else:
            import fcntl
            try:fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB)
            except OSError:raise SceneBlocked('SCENE_WRITER_BUSY') from None
            try:yield
            finally:fcntl.flock(f,fcntl.LOCK_UN)


class SceneStore:
    def __init__(self,path):
        self.path=Path(path);self.path.mkdir(parents=True,exist_ok=True,mode=0o700)
    def recover(self):
        events=[];prev='0'*64
        log=self.path/'events.jsonl'
        if log.exists():
            for line in log.read_text().splitlines():
                try:e=json.loads(line);h=e.pop('hash')
                except (ValueError,KeyError):raise SceneBlocked('JOURNAL_CORRUPT') from None
                if e['previous']!=prev or digest(e)!=h or e['sequence']!=len(events)+1:raise SceneBlocked('JOURNAL_CORRUPT')
                prev=h;events.append(e)
        if log.exists():log.chmod(0o600)
        current=events[-1]['state'] if events else {'requests':{},'checkpoints':{}}
        snapshot=self.path/'state.json'
        if snapshot.exists():
            s=load(snapshot)
            if s.get('sequence',0)>len(events) or (s.get('sequence')==len(events) and s.get('state')!=current):raise SceneBlocked('STATE_JOURNAL_MISMATCH')
        return current,prev,len(events)
    def commit(self,state,event):
        _,prev,n=self.recover();record={'sequence':n+1,'previous':prev,'event':event,'state':state};record['hash']=digest(record)
        with (self.path/'events.jsonl').open('a',encoding='utf-8') as f:f.write(json.dumps(record,ensure_ascii=False)+'\n');f.flush();os.fsync(f.fileno())
        tmp=self.path/'state.tmp';tmp.write_text(json.dumps({'sequence':n+1,'state':state},ensure_ascii=False));tmp.chmod(0o600);tmp.replace(self.path/'state.json')
    def plan(self,scene,bible,root,request_id):
        if not re.fullmatch('[a-zA-Z0-9_-]{1,80}',request_id):raise SceneBlocked('INVALID_REQUEST_ID')
        with writer_lock(self.path/'writer.lock'):
            state,_,_=self.recover();k=keys(scene,bible);identity=digest({'scene':scene['id'],'build_key':k['build_key'],'backend':'OFFLINE_M1'})
            old=state['requests'].get(request_id)
            if old and old['identity']!=identity:raise SceneBlocked('REQUEST_ID_SPEC_CHANGED')
            began=time.monotonic();issues=validate(scene,bible,root)
            if old and old['issues']==issues:return dict(old,cache_hit=True)
            result={'identity':identity,'scene_id':scene['id'],'status':'BLOCKED' if issues else 'PREFLIGHT_READY','issues':issues,'inference_requests':0,'external_charge_usd':0,'workspace_usage':'unknown','generation_authorized':False,'creative_qa':'NOT_EVALUATED','keys':k,'elapsed_ms':round((time.monotonic()-began)*1000,3),'cache_hit':False}
            state['requests'][request_id]=result;self.commit(state,'PLAN');return result
    def checkpoint(self,name,dependencies,outputs):
        """Offline stage completion only; never records approval or inference."""
        if name not in ('plan','continuity','source-validation','assembly'):raise SceneBlocked('STAGE_NOT_IMPLEMENTED')
        with writer_lock(self.path/'writer.lock'):
            state,_,_=self.recover()
            for file,h in outputs.items():
                if not Path(file).is_file() or file_sha(Path(file))!=h:raise SceneBlocked('CHECKPOINT_OUTPUT_INVALID')
            key=digest({'name':name,'dependencies':dependencies})
            old=state['checkpoints'].get(key)
            if old:
                if any(not Path(p).is_file() or file_sha(Path(p))!=h for p,h in old.items()):raise SceneBlocked('CHECKPOINT_OUTPUT_CHANGED')
                return {'cache_hit':True,'key':key}
            state['checkpoints'][key]=outputs;self.commit(state,'OFFLINE_CHECKPOINT');return {'cache_hit':False,'key':key}


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('command',choices=['plan','dry-run','status','assemble']);p.add_argument('--manifest',default='episodes/berakhot-01-01/scene-prologue-v02.json');p.add_argument('--root',default='.');p.add_argument('--request-id',default='prologue-v02-dry-run');p.add_argument('--state',default='private-media/scene-factory');p.add_argument('--technical-fixture',action='store_true')
    a=p.parse_args();root=Path(a.root).resolve()
    try:
        out=within(root,a.state)
        if 'private-media' not in out.relative_to(root).parts:raise SceneBlocked('PRIVATE_STATE_REQUIRED')
        store=SceneStore(out)
        if a.command=='assemble':
            if not a.technical_fixture:raise SceneBlocked('PRODUCTION_ASSEMBLY_NOT_IMPLEMENTED_M2_FIXTURES_ONLY')
            from tools.private_storyreel import assemble_technical_fixture
            r=assemble_technical_fixture(root,out/'technical-fixture')
            files={str(within(root,r['video'])):file_sha(within(root,r['video']))}
            store.checkpoint('assembly',{'build_key':r['key']},files)
        elif a.command=='status':
            with writer_lock(out/'writer.lock'):state,_,n=store.recover()
            r={'status':'STATE_READ','requests':state['requests'],'events':n,'inference_requests':0}
        else:
            m=load(within(root,a.manifest));b=load(within(root,m['bible']['path']));r=store.plan(m,b,root,a.request_id)
        print(json.dumps(r,ensure_ascii=False,indent=2));return 2 if r['status']=='BLOCKED' else 0
    except (ValueError,OSError,KeyError,TypeError) as error:
        print(json.dumps({'status':'BLOCKED','reason':str(error) if isinstance(error,SceneBlocked) else type(error).__name__,'inference_requests':0}));return 2

if __name__=='__main__':sys.exit(main())
