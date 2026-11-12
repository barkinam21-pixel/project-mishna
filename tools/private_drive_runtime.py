"""Owner-private Drive files for the existing studio. No agent or public links."""
import argparse,hashlib,json,os,re,sys,urllib.parse,urllib.request
from pathlib import Path
from tools.comfy_scene_images import atomic,under

class DriveBlocked(ValueError):pass

class Drive:
    def __init__(self, request=None):
        self.request=request or self._request;self.token=None
    def _request(self,method,url,body=None,headers=None):
        class NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self,*args,**kwargs):return None
        try:
            with urllib.request.build_opener(NoRedirect).open(urllib.request.Request(url,data=body,headers=headers or {},method=method),timeout=60) as r:
                raw=r.read(64*1024*1024+1)
                if len(raw)>64*1024*1024:raise DriveBlocked('DRIVE_FILE_TOO_LARGE')
                return raw
        except Exception:raise DriveBlocked('DRIVE_REQUEST_FAILED_NO_RETRY') from None
    def login(self):
        try:
            cfg=json.loads(os.environ['MISHNAH_DRIVE_OAUTH_JSON'])
            body=urllib.parse.urlencode({k:cfg[k] for k in ('client_id','client_secret','refresh_token')}|{'grant_type':'refresh_token'}).encode()
            self.token=json.loads(self.request('POST','https://oauth2.googleapis.com/token',body,{'Content-Type':'application/x-www-form-urlencoded'}))['access_token']
        except Exception:raise DriveBlocked('DRIVE_AUTH_UNAVAILABLE') from None
    def metadata(self,file_id):
        if not re.fullmatch(r'[\w-]+',file_id):raise DriveBlocked('INVALID_DRIVE_ID')
        h={'Authorization':'Bearer '+self.token}
        meta=json.loads(self.request('GET','https://www.googleapis.com/drive/v3/files/'+file_id+'?fields=id,mimeType,shared,permissions(type,role)',headers=h))
        # No public, domain, group or additional-user sharing; absent evidence blocks.
        perms=meta.get('permissions',[])
        if meta.get('shared') is not False or len(perms)!=1 or perms[0].get('type')!='user' or perms[0].get('role')!='owner':raise DriveBlocked('DRIVE_NOT_OWNER_ONLY')
        return meta
    def download(self,file_id):
        self.metadata(file_id)
        return self.request('GET','https://www.googleapis.com/drive/v3/files/'+file_id+'?alt=media',headers={'Authorization':'Bearer '+self.token})
    def replace(self,file_id,raw,mime):
        # Existing owner-only file only. No creation, ACL change or public storage.
        self.metadata(file_id)
        self.request('PATCH','https://www.googleapis.com/upload/drive/v3/files/'+file_id+'?uploadType=media',raw,{'Authorization':'Bearer '+self.token,'Content-Type':mime})
        if hashlib.sha256(self.download(file_id)).digest()!=hashlib.sha256(raw).digest():raise DriveBlocked('DRIVE_READBACK_HASH_MISMATCH')


def main():
    p=argparse.ArgumentParser();p.add_argument('command',choices=['check','run']);a=p.parse_args()
    from tools.studio_runtime import Studio
    root=Path.cwd();studio=Studio(root);d=Drive()
    try:
        names=['CLOUDFLARE_ACCOUNT_ID','CLOUDFLARE_API_TOKEN','MISHNAH_DRIVE_OAUTH_JSON','MISHNAH_REFERENCE_FILE_ID','MISHNAH_STATE_FILE_ID','MISHNAH_SNAPSHOT_FILE_ID']
        missing=[n for n in names if not os.environ.get(n)]
        if missing:raise DriveBlocked('MISSING_CONFIGURATION:'+','.join(missing))
        d.login();refs,state,snapshot=[os.environ[n] for n in names[-3:]]
        if len({refs,state,snapshot})!=3:raise DriveBlocked('DRIVE_FILE_IDS_MUST_DIFFER')
        for uid in (refs,state,snapshot):d.metadata(uid)
        # Check never writes Drive, loads no image model and consumes no inference quota.
        if a.command=='check':
            from tools.cloudflare_image_backend import CloudflareClient,MODEL
            client=CloudflareClient({})
            models=client._request('GET',f'/accounts/{client.account}/ai/models/search?search=flux-2-klein-4b')
            if not any(m.get('name')==MODEL for m in models.get('result',[])):raise DriveBlocked('CLOUDFLARE_MODEL_UNAVAILABLE')
            print(json.dumps({'status':'STORAGE_AND_MODEL_ACCESS_AUTHENTICATED','generation':False,'provider_requests':0,'inference_safety':'NOT_AUTHORIZED_BY_CHECK'}));return 0
        os.environ['MISHNAH_IMAGE_BACKEND']='cloudflare';studio=Studio(root)
        m,_,_=studio.inputs()
        if not all(m['authorization'].get(k) is True for k in ('generation_approved','zero_cost_compute_verified','component_licenses_verified')):raise DriveBlocked('GENERATION_APPROVALS_MISSING')
        # Reuse exact original-package intake. No untrusted URL or arbitrary extraction.
        pack=under(root,'private-media/studio/input-reference.zip');pack.write_bytes(d.download(refs));pack.chmod(0o600)
        studio.restore_references(str(pack.relative_to(root)))
        snap=under(root,'private-media/studio/input-snapshot.zip');snap.write_bytes(d.download(snapshot));snap.chmod(0o600)
        studio.restore(str(snap.relative_to(root)))
        journal=json.loads(d.download(state))
        if not isinstance(journal,dict) or not isinstance(journal.get('entries'),dict):raise DriveBlocked('INVALID_PRIVATE_JOURNAL')
        atomic(studio.work/'images/state.json',journal)
        # Checkpoint durable state before the billable POST. Failure prevents submission.
        from tools import comfy_scene_images
        original=comfy_scene_images.atomic
        def checkpoint(path,value):
            original(path,value)
            if Path(path)==studio.work/'images/state.json':d.replace(state,json.dumps(value).encode(),'application/json')
        comfy_scene_images.atomic=checkpoint
        try:result=studio.run()
        finally:comfy_scene_images.atomic=original
        if result['status']=='BLOCKED':print(json.dumps(result));return 2
        destination='private-media/studio/output-snapshot.zip'
        under(root,destination).unlink(missing_ok=True)
        backed=studio.backup(destination)
        d.replace(snapshot,under(root,destination).read_bytes(),'application/zip')
        print(json.dumps({'status':'PRIVATE_SNAPSHOT_SAVED','run_status':result['status'],'sha256':backed['outputs']['sha256'],'accepted':False}));return 0
    except Exception as error:
        code=str(error) if isinstance(error,DriveBlocked) else type(error).__name__
        print(json.dumps({'status':'BLOCKED','code':code,'retry':False,'cost':'unknown' if a.command=='run' else 'NO_INFERENCE_REQUEST'}));return 2

if __name__=='__main__':sys.exit(main())
