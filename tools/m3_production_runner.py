"""Owner-private P07 -> signed M3 -> Cloudflare -> durable outbox -> Drive.
No CLI auto-dispatch. Call run_once only with deployment-scoped approval.
Never imports legacy image workers/Horde. No inference retry, including resume.
"""
import datetime as dt
import hashlib
import hmac
import io
import json
import os
from pathlib import Path
import urllib.request
from tools.m3_owner_status_probe import safe_url, NoRedirect
from tools.p07_cloudflare_only import compile_cloudflare_only, MODEL
from tools.scene_factory import writer_lock

class ProductionBlocked(ValueError): pass

def sha(raw): return hashlib.sha256(raw).hexdigest()
def encode(v): return json.dumps(v,ensure_ascii=True,separators=(',',':')).encode()

def save(path,raw):
    """Private atomic write plus directory fsync, never follow user symlinks."""
    if path.is_symlink() or path.parent.is_symlink(): raise ProductionBlocked('PRIVATE_PATH_UNSAFE')
    temp=path.with_suffix(path.suffix+'.partial')
    fd=os.open(temp,os.O_WRONLY|os.O_CREAT|os.O_TRUNC|getattr(os,'O_NOFOLLOW',0),0o600)
    with os.fdopen(fd,'wb') as f: f.write(raw);f.flush();os.fsync(f.fileno())
    os.replace(temp,path)
    fd=os.open(path.parent,os.O_RDONLY)
    try:os.fsync(fd)
    finally:os.close(fd)

class SignedCoordinator:
    def __init__(self,url,key,transport=None):
        self.url=safe_url(url).replace('/offline','/production')
        if len(key)!=64 or any(c not in '0123456789abcdef' for c in key):raise ProductionBlocked('HMAC_KEY_INVALID')
        self.key=bytes.fromhex(key);self.opener=transport or urllib.request.build_opener(NoRedirect)
    def call(self,operation,payload):
        raw=encode(dict(version=1,owner='barkinam21-pixel',scene_id='ACT1-PROLOGUE',operation=operation,payload=payload))
        stamp=dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds').replace('+00:00','Z')
        sig=hmac.new(self.key,b'POST\n/m3/v1/production\n'+stamp.encode()+b'\n'+raw,hashlib.sha256).hexdigest()
        req=urllib.request.Request(self.url,data=raw,headers={'Content-Type':'application/json','X-M3-Timestamp':stamp,'X-M3-Signature':sig,'User-Agent':'Mishnah-M3-PrivateRunner/1'},method='POST')
        try:
            with self.opener.open(req,timeout=15) as r:
                raw=r.read(2_000_001)
                if r.status!=200 or len(raw)>2_000_000:raise ProductionBlocked('M3_RESPONSE_INVALID_NO_RETRY')
                result=json.loads(raw)
                if not isinstance(result,dict):raise ProductionBlocked('M3_RESPONSE_INVALID_NO_RETRY')
                return result
        except Exception:raise ProductionBlocked('M3_TRANSPORT_UNCERTAIN_INSPECT_STATUS_NO_RETRY') from None

class CloudflareOnlyTransport:
    """Exact direct API. No redirects, POST retries, URL outputs or fallback."""
    def __init__(self,account_id,token,opener=None):
        if len(account_id)!=32 or any(c not in '0123456789abcdef' for c in account_id):raise ProductionBlocked('CF_ACCOUNT_INVALID')
        if not token:raise ProductionBlocked('CF_CREDENTIAL_MISSING')
        self.account=account_id;self.token=token;self.opener=opener or urllib.request.build_opener(NoRedirect)
    def submit(self,packet):
        if packet['endpoint_suffix']!='/ai/run/'+MODEL:raise ProductionBlocked('CF_MODEL_DENIED')
        request=urllib.request.Request('https://api.cloudflare.com/client/v4/accounts/'+self.account+packet['endpoint_suffix'],data=packet['body'],headers={'Authorization':'Bearer '+self.token,'Content-Type':packet['content_type']},method='POST')
        try:
            with self.opener.open(request,timeout=120) as r:
                self.response_metadata={'http_status':r.status,'content_type':r.headers.get('Content-Type'),'cf_ray':r.headers.get('cf-ray'),'completed_at':dt.datetime.now(dt.timezone.utc).isoformat()}
                raw=r.read(20_000_001)
                if r.status!=200 or len(raw)>20_000_000:raise ProductionBlocked('CF_RESULT_INVALID')
                # Cloudflare FLUX can return JSON base64 OR direct image bytes.
                if r.headers.get('Content-Type','').startswith('application/json'):
                    import base64
                    obj=json.loads(raw)
                    if obj.get('success') is not True:raise ProductionBlocked('CF_RESULT_INVALID')
                    raw=base64.b64decode(obj['result']['image'],validate=True)
                return raw
        except Exception:raise ProductionBlocked('CF_SUBMISSION_UNCERTAIN_NO_RETRY') from None

def private_host(root):
    if os.environ.get('GITHUB_ACTIONS','').lower()=='true':raise ProductionBlocked('PUBLIC_CI_FORBIDDEN')
    root=Path(root).resolve();p=root/'private-media'
    if not p.is_dir() or p.is_symlink():raise ProductionBlocked('PRIVATE_ROOT_REQUIRED')
    return p

def prepare(draft,root,request_id):
    private_host(root)
    if len(request_id)!=32 or any(c not in '0123456789abcdef' for c in request_id):raise ProductionBlocked('REQUEST_ID_INVALID')
    packet=compile_cloudflare_only(draft,root)
    spec={'request_id':request_id,'shot_id':'EP-P07','body_sha256':sha(packet['body']),'draft_sha256':draft['draft_sha256'],'references_sha256':sha(encode(draft['proposed_provider_shape']['references']))}
    return packet,spec

def run_once(draft,root,request_id,history_json,coordinator,provider):
    """Bootstrap exact pinned history; consume atomic permit BEFORE provider POST.
    A lost reserve reply/crash is terminal hold even if POST never happened.
    Saved image recovery uses resume_delivery, which has no provider argument.
    """
    packet,spec=prepare(draft,root,request_id)
    if not isinstance(request_id,str) or len(request_id)!=32 or any(c not in '0123456789abcdef' for c in request_id):raise ProductionBlocked('REQUEST_ID_INVALID')
    out=private_host(root)/('m3-'+request_id);out.mkdir(mode=0o700,exist_ok=True)
    if out.is_symlink():raise ProductionBlocked('OUTBOX_UNSAFE')
    with writer_lock(out/'writer.lock'):
        if (out/'attempt.json').exists():raise ProductionBlocked('LOCAL_ATTEMPT_EXISTS_NO_RETRY')
        coordinator.call('bootstrap',{'history_json':history_json})
        save(out/'attempt.json',encode({'phase':'RESERVATION_PENDING_NO_RETRY','spec':spec}))
        reserved=coordinator.call('reserve',spec)
        if reserved.get('dispatch_permitted_once') is not True or reserved.get('status')!='SUBMISSION_UNCERTAIN_NO_RETRY':raise ProductionBlocked('ATOMIC_PERMIT_REQUIRED')
        token=reserved.get('token')
        if not isinstance(token,str) or len(token)!=64 or any(c not in '0123456789abcdef' for c in token):raise ProductionBlocked('ATOMIC_PERMIT_INVALID')
        save(out/'attempt.json',encode({'phase':'SUBMISSION_UNCERTAIN_NO_RETRY','spec':spec,'token':token}))
        raw=provider.submit(packet)  # ONE call. All failures hold permanently.
        save(out/'provider-original.bin',raw) # persist BEFORE decode or upload
        save(out/'provider-response-metadata.json',encode({'response':getattr(provider,'response_metadata',None),'spec':spec,'model':MODEL,'outcome':'RAW_SAVED_NOT_YET_QA'}))
        return reconcile_saved(root,request_id,coordinator)

def reconcile_saved(root,request_id,coordinator):
    """No dispatch path: reconcile even after crash immediately after byte save."""
    from PIL import Image
    if not isinstance(request_id,str) or len(request_id)!=32 or any(c not in '0123456789abcdef' for c in request_id):raise ProductionBlocked('REQUEST_ID_INVALID')
    out=private_host(root)/('m3-'+request_id)
    data=json.loads((out/'attempt.json').read_text());raw=(out/'provider-original.bin').read_bytes()
    try:
        with Image.open(io.BytesIO(raw)) as im:
            im.load()
            if im.size!=(1024,576) or im.format not in ('PNG','JPEG','WEBP'):raise ProductionBlocked('IMAGE_FORMAT_SIZE_INVALID')
            fmt=im.format;buf=io.BytesIO();im.convert('RGB').save(buf,format='PNG');png=buf.getvalue()
    except Exception:raise ProductionBlocked('IMAGE_DECODE_FAILED_PRIVATE_ORIGINAL_RETAINED') from None
    save(out/'candidate.png',png)
    receipt={'accepted':False,'body_sha256':data['spec']['body_sha256'],'format':fmt,'height':576,'image_sha256':sha(raw),'model':MODEL,'provider_calls':1,'width':1024}
    coordinator.call('receipt',{'token':data['token'],'receipt':receipt})
    save(out/'receipt.json',encode(receipt))
    return {'status':'RESULT_SAVED_PRIVATE','accepted':False,'image_sha256':sha(raw),'png_sha256':sha(png),'visual_qa':'NEEDS_HUMAN_REVIEW','provider_calls_this_reconciliation':0}

def append_snapshot(previous,files):
    """Preserve every old member in the existing Studio snapshot format."""
    import zipfile
    from pathlib import PurePosixPath
    with zipfile.ZipFile(io.BytesIO(previous)) as z:
        if len(z.namelist())!=len(set(z.namelist())) or len(z.namelist())>2000 or sum(i.file_size for i in z.infolist())>64*1024*1024:raise ProductionBlocked('SNAPSHOT_INVALID')
        hashes=json.loads(z.read('snapshot.json'))
        if set(z.namelist())!=set(hashes)|{'snapshot.json'}:raise ProductionBlocked('SNAPSHOT_MEMBERS_INVALID')
        content={}
        for info in z.infolist():
            if info.filename=='snapshot.json':continue
            name=info.filename
            if not name.startswith('private-media/') or '..' in PurePosixPath(name).parts or ((info.external_attr>>16)&0o170000)==0o120000:raise ProductionBlocked('SNAPSHOT_PATH_INVALID')
            raw=z.read(name)
            if sha(raw)!=hashes[name]:raise ProductionBlocked('SNAPSHOT_HASH_INVALID')
            content[name]=raw
    for name,raw in files.items():
        if name in content and content[name]!=raw:raise ProductionBlocked('SNAPSHOT_WOULD_OVERWRITE')
        content[name]=raw
    out=io.BytesIO()
    with zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED) as z:
        for name,raw in sorted(content.items()):
            info=zipfile.ZipInfo(name,(2026,1,1,0,0,0));info.compress_type=zipfile.ZIP_DEFLATED;z.writestr(info,raw)
        z.writestr(zipfile.ZipInfo('snapshot.json',(2026,1,1,0,0,0)),encode({name:sha(raw) for name,raw in sorted(content.items())}))
    return out.getvalue()


def resume_delivery(root,request_id,coordinator,drive,state_id,snapshot_id):
    """Same two existing mutable Drive destinations; reference archive untouched.
    Preserve all snapshot members. No new files/sharing, no inference.
    """
    if not isinstance(request_id,str) or len(request_id)!=32 or any(c not in '0123456789abcdef' for c in request_id):raise ProductionBlocked('REQUEST_ID_INVALID')
    if state_id==snapshot_id:raise ProductionBlocked('DRIVE_DESTINATIONS_MUST_DIFFER')
    out=private_host(root)/('m3-'+request_id)
    if out.is_symlink():raise ProductionBlocked('OUTBOX_UNSAFE')
    with writer_lock(out/'writer.lock'):
        r=reconcile_saved(root,request_id,coordinator)
        for uid in (state_id,snapshot_id):
            meta=drive.metadata(uid)
            if meta.get('shared') is not False or len(meta.get('permissions',[]))!=1 or meta['permissions'][0].get('type')!='user' or meta['permissions'][0].get('role')!='owner':raise ProductionBlocked('DRIVE_OWNER_ONLY_REQUIRED')
        journal=coordinator.call('journal',{})
        existing=json.loads(drive.download(state_id));old=existing.get('attempts',[]);new=journal['attempts']
        if len(old) not in (len(new)-1,len(new)) or old[:6]!=new[:6] or {k:v for k,v in existing.items() if k!='attempts'}!={k:v for k,v in journal.items() if k!='attempts'}:raise ProductionBlocked('DRIVE_HISTORY_CONFLICT')
        if len(old)==len(new) and old[-1]!=new[-1]:raise ProductionBlocked('DRIVE_WRITER_CONFLICT')
        names=('provider-original.bin','candidate.png','receipt.json')
        files={'private-media/m3-'+request_id+'/'+name:(out/name).read_bytes() for name in names}
        # Request-scoped source/conditioning hashes accompany the immutable image.
        spec=json.loads((out/'attempt.json').read_text())['spec']
        files['private-media/m3-'+request_id+'/spec.json']=encode(spec)
        snapshot=append_snapshot(drive.download(snapshot_id),files)
        save(out/'delivery-snapshot.zip',snapshot)
        drive.replace(snapshot_id,snapshot,'application/zip')
        if sha(drive.download(snapshot_id))!=sha(snapshot):raise ProductionBlocked('SNAPSHOT_ROUNDTRIP_FAILED')
        raw=encode(journal);drive.replace(state_id,raw,'application/json')
        if sha(drive.download(state_id))!=sha(raw):raise ProductionBlocked('JOURNAL_ROUNDTRIP_FAILED')
        data=json.loads((out/'attempt.json').read_text())
        coordinator.call('delivered',{'token':data['token'],'delivery':{'image_sha256':r['image_sha256'],'journal_sha256':sha(raw),'private_storage_verified':True}})
        return dict(r,status='DELIVERED_PRIVATE',snapshot_sha256=sha(snapshot),provider_calls_this_delivery=0)


from tools.scene_owner_reference_pipeline import PinnedReadOnlyDriveProcess
class PinnedPrivateDriveWriter(PinnedReadOnlyDriveProcess):
    """Explicit write adapter; inherited read adapter remains read-only."""
    def replace(self,file_id,raw,mime):
        import subprocess,sys
        from tools.scene_owner_archive_fetch import FILE_ID
        if not FILE_ID.fullmatch(file_id) or mime not in ('application/zip','application/json') or len(raw)>64*1024*1024:raise ProductionBlocked('DRIVE_WRITE_SCOPE_INVALID')
        script="import os,sys;sys.path.insert(0,os.getcwd());from tools.private_drive_runtime import Drive;d=Drive();d.login();d.replace(sys.argv[1],sys.stdin.buffer.read(),sys.argv[2])"
        try:subprocess.run([sys.executable,'-I','-c',script,file_id,mime],cwd=self.root,input=raw,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=90,check=True)
        except Exception:raise ProductionBlocked('DRIVE_DELIVERY_UNCERTAIN_RECONCILE_ONLY') from None


def main(argv=None):
    """Existing private host only; default compiles, never reserves or infers."""
    import argparse,importlib.util
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root',required=True);p.add_argument('--private-draft');p.add_argument('--request-id',required=True)
    mode=p.add_mutually_exclusive_group();mode.add_argument('--once',action='store_true');mode.add_argument('--resume-delivery',action='store_true')
    p.add_argument('--history');p.add_argument('--legacy-runtime');p.add_argument('--state-id');p.add_argument('--snapshot-id')
    a=p.parse_args(argv)
    try:
        private=private_host(a.root)
        if not a.resume_delivery:
            draft_path=Path(a.private_draft or '')
            if draft_path.is_symlink() or not draft_path.is_file() or not draft_path.resolve().is_relative_to(private):raise ProductionBlocked('DRAFT_NOT_PRIVATE')
            draft=json.loads(draft_path.read_text());packet,spec=prepare(draft,a.root,a.request_id)
            if not a.once:
                print(json.dumps(dict(status='PRIVATE_DRY_RUN_NO_NETWORK',body_sha256=spec['body_sha256'],draft_sha256=spec['draft_sha256'],provider_calls=0,authorization_to_generate=False)));return 0
        coordinator=SignedCoordinator(os.environ.get('M3_GATEWAY_URL',''),os.environ.get('M3_GATEWAY_HMAC_KEY',''))
        if not a.legacy_runtime or not all((a.state_id,a.snapshot_id)):raise ProductionBlocked('EXISTING_PRIVATE_DRIVE_ADAPTER_AND_DESTINATIONS_REQUIRED')
        drive=PinnedPrivateDriveWriter(Path(a.legacy_runtime).resolve())
        if a.once:
            history=Path(a.history or '')
            if not history.is_file() or history.is_symlink() or not history.resolve().is_relative_to(private):raise ProductionBlocked('HISTORY_NOT_PRIVATE')
            # Real private storage/source access MUST succeed before reservation.
            if drive.download(a.state_id)!=history.read_bytes():raise ProductionBlocked('PRIVATE_HISTORY_CHANGED')
            append_snapshot(drive.download(a.snapshot_id),{})
            run_once(draft,a.root,a.request_id,history.read_text(),coordinator,CloudflareOnlyTransport(os.environ.get('CLOUDFLARE_ACCOUNT_ID',''),os.environ.get('CLOUDFLARE_API_TOKEN','')))
        result=resume_delivery(a.root,a.request_id,coordinator,drive,a.state_id,a.snapshot_id)
        print(json.dumps(result));return 0
    except Exception:
        # Do not print provider text, filenames, credentials or remote payloads.
        print(json.dumps(dict(status='BLOCKED_INSPECT_PRIVATE_CHECKPOINT_NO_RETRY',provider_outcome='UNKNOWN_UNLESS_RECONCILED',automatic_retry=False)));return 2

if __name__=='__main__':raise SystemExit(main())
