"""Owner-private Drive files for the existing studio. No agent or public links."""
import argparse,hashlib,json,os,re,sys,urllib.parse,urllib.request
from pathlib import Path
from tools.comfy_scene_images import atomic,under

class DriveBlocked(ValueError):pass


def validate_journal(journal, previous=None, baseline=()):
    """Validate before replacing local state or making any remote checkpoint.

    Snapshot history may lag, but cannot disappear from the authoritative journal.
    The immutable historical floor also protects fresh runners with old snapshots.
    """
    if not isinstance(journal,dict) or not isinstance(journal.get('entries'),dict) or not isinstance(journal.get('attempts',[]),list):
        raise DriveBlocked('INVALID_PRIVATE_JOURNAL')
    attempts=journal.get('attempts',[])
    if any(not isinstance(a,dict) or not isinstance(a.get('key'),str) or not a['key'] for a in attempts):
        raise DriveBlocked('INVALID_PRIVATE_ATTEMPT')
    for k,e in journal['entries'].items():
        if not isinstance(k,str) or not isinstance(e,dict) or e.get('status') not in ('SUBMISSION_UNCERTAIN','QUEUED','CANDIDATE','ACCEPTED'):
            raise DriveBlocked('INVALID_PRIVATE_ENTRY')
    if not isinstance(baseline,(list,tuple)) or any(not isinstance(h,str) or not re.fullmatch('[a-f0-9]{64}',h) for h in baseline):
        raise DriveBlocked('INVALID_HISTORICAL_BASELINE')
    if not set(baseline).issubset({a.get('native_sha256') for a in attempts}):
        raise DriveBlocked('HISTORICAL_ATTEMPTS_MISSING')
    if previous is not None:
        validate_journal(previous)
        old=previous.get('attempts',[])
        if attempts[:len(old)] != old:
            raise DriveBlocked('JOURNAL_ATTEMPT_HISTORY_ROLLBACK')
        for k,e in previous['entries'].items():
            new=journal['entries'].get(k)
            if new is None:
                raise DriveBlocked('JOURNAL_ENTRY_HISTORY_LOST')
            for field in ('spec','workflow','sha256','path','native_sha256','native_path'):
                if field in e and new.get(field)!=e[field]:
                    raise DriveBlocked('JOURNAL_ENTRY_HISTORY_CHANGED')
            if e['status'] in ('CANDIDATE','ACCEPTED') and new['status'] not in ('CANDIDATE','ACCEPTED'):
                raise DriveBlocked('JOURNAL_ENTRY_STATUS_ROLLBACK')
            if e['status']=='ACCEPTED' and new['status']!='ACCEPTED':
                raise DriveBlocked('JOURNAL_ENTRY_STATUS_ROLLBACK')
    return journal


def prepare_opn02(root, clean, journal, baseline=()):
    """Local-only inspection of restored inputs; never calls a provider or renders."""
    from tools.studio_runtime import load
    from tools.comfy_scene_images import specifications, conditioning_inputs, prompt_text, sha, under, visual_request_key
    validate_journal(journal,load(clean/'private-media/studio/images/state.json',{'entries':{}}),baseline)
    manifest=json.loads((root/'episodes/berakhot-01-01/comfy-opening-images.json').read_text())
    manifest['backend']=manifest['available_backends']['cloudflare']
    manifest['shots']=[s for s in manifest['shots'] if s['id']=='OPN02']
    if len(manifest['shots'])!=1:raise DriveBlocked('OPN02_SHOT_MISSING_OR_DUPLICATE')
    candidates=verify_restored_candidates(clean,journal)
    row=specifications(manifest,clean)[0]
    if row['missing']:raise DriveBlocked('LOCAL_REFERENCE_PREFLIGHT_FAILED')
    board=manifest['direction_board'];board_path=under(clean,board['path'])
    if not board_path.is_file() or sha(board_path)!=board['sha256']:
        raise DriveBlocked('DIRECTION_BOARD_INTEGRITY_FAILED')
    inputs=conditioning_inputs(row['spec'],clean)
    from PIL import Image
    with Image.open(board_path) as image:
        image.load()
        if list(image.size)!=board['dimensions']:raise DriveBlocked('DIRECTION_BOARD_DIMENSIONS_FAILED')
    policy=manifest['authorization']
    blockers=['NEW_OWNER_GENERATION_APPROVAL_REQUIRED','FRESH_PROVIDER_PRIVACY_AND_QUOTA_EVIDENCE_REQUIRED']
    if len(journal.get('attempts',[]))>=policy.get('total_submissions_limit',0):
        blockers.append('RECORDED_SUBMISSION_LIMIT_CONSUMED_DO_NOT_RESET_JOURNAL')
    if any(e['status']=='SUBMISSION_UNCERTAIN' for e in journal['entries'].values()):
        blockers.append('UNCERTAIN_SUBMISSION_NO_RETRY')
    trials=json.loads((root/'episodes/berakhot-01-01/trials.json').read_text())
    latest=next((t for t in reversed(trials.get('trials',[])) if t.get('shot_id')=='OPN02'),{})
    evidence_path=latest.get('evidence_path')
    latest_evidence=load(under(root,evidence_path)) if evidence_path else {}
    layout_hash=latest_evidence.get('layout_sha256')
    layout_matches=bool(layout_hash and layout_hash in [digest for raw,digest in inputs])
    if layout_hash and not layout_matches:
        blockers.append('LATEST_TRIAL_LAYOUT_NOT_IN_CURRENT_CONDITIONING_INPUTS')
    expected=latest.get('image_sha256')
    available=bool(expected and any(sha(p)==expected for p in (clean/'private-media').rglob('*.png') if p.is_file()))
    return {'status':'OPN02_PREPARATION_VERIFIED_NOT_AUTHORIZED','inference_requests':0,'remote_writes':0,
        'conditioning_inputs':len(inputs),'conditioning_sha256':[digest for raw,digest in inputs],
        'prompt_sha256':hashlib.sha256(prompt_text(row['spec']).encode()).hexdigest(),
        'visual_request_sha256':visual_request_key(row['spec']),'manifest_sha256':sha(root/'episodes/berakhot-01-01/comfy-opening-images.json'),
        'historical_attempts':len(journal.get('attempts',[])), 'journal_continuity_verified':True,
        'restored_candidates':candidates,
        'direction_board':'VERIFIED_LOCAL_DIRECTION_ONLY_NOT_PROVIDER_INPUT',
        'latest_recorded_candidate_available':available,'latest_recorded_candidate_sha256':expected,
        'latest_trial_layout_in_current_inputs':layout_matches,
        'latest_trial_layout_sha256':layout_hash,
        'candidate_availability_note':'Snapshot may predate later trials; a missing newer candidate is not recovered by a journal entry',
        'generation_authorized':False,'generation_blockers':blockers,
        'semantic_qa':'NOT_EVALUATED','composition_target_height_fraction':[0.25,0.35],
        'next_correction':'Preserve existing identities and painted style; smaller adults and village, not fortress. New direction/seed are not authorized by preparation.'}


def verify_restored_candidates(clean,journal):
    from tools.studio_runtime import load
    from tools.scene_pack_preflight import verified_entry
    from PIL import Image
    candidates=load(clean/'private-media/studio/candidates.json')
    if not isinstance(candidates,dict):raise DriveBlocked('INVALID_CANDIDATE_REGISTRY')
    inventory=[]
    for entry in list(candidates.values())+list(journal['entries'].values()):
        if not isinstance(entry,dict):raise DriveBlocked('INVALID_CANDIDATE_REGISTRY')
        if entry.get('status') not in ('CANDIDATE','ACCEPTED'):continue
        status,_=verified_entry(entry,clean)
        if status=='LOCAL_STATE_ASSET_MISMATCH':raise DriveBlocked('RESTORED_CANDIDATE_INTEGRITY_FAILED')
        try:
            with Image.open(under(clean,entry['path'])) as image:
                image.load()
                dimensions=list(image.size)
                if image.format!='PNG' or image.mode not in ('RGB','RGBA'):raise ValueError()
        except Exception:raise DriveBlocked('RESTORED_CANDIDATE_DECODE_FAILED') from None
        inventory.append({'sha256':entry['sha256'],'status':status,
                          'dimensions':dimensions,
                          'native_original_verified':bool(entry.get('png_is_converted') and entry.get('native_path')),
                          'approval_granted_by_preparation':False})
    return inventory

class Drive:
    max_file_bytes=64*1024*1024
    def __init__(self, request=None):
        self.request=request or self._request;self.token=None
    def _request(self,method,url,body=None,headers=None):
        class NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self,*args,**kwargs):return None
        try:
            with urllib.request.build_opener(NoRedirect).open(urllib.request.Request(url,data=body,headers=headers or {},method=method),timeout=60) as r:
                raw=r.read(self.max_file_bytes+1)
                if len(raw)>self.max_file_bytes:raise DriveBlocked('DRIVE_FILE_TOO_LARGE')
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
        if len(raw)>self.max_file_bytes:raise DriveBlocked('DRIVE_WRITE_EXCEEDS_READBACK_LIMIT')
        self.metadata(file_id)
        self.request('PATCH','https://www.googleapis.com/upload/drive/v3/files/'+file_id+'?uploadType=media',raw,{'Authorization':'Bearer '+self.token,'Content-Type':mime})
        if hashlib.sha256(self.download(file_id)).digest()!=hashlib.sha256(raw).digest():raise DriveBlocked('DRIVE_READBACK_HASH_MISMATCH')


def check_cloudflare():
    """Read-only Workers AI access, independent of Drive and generation gates."""
    from tools.cloudflare_image_backend import CloudflareClient,MODEL
    if not all(os.environ.get(k) for k in ('CLOUDFLARE_ACCOUNT_ID','CLOUDFLARE_API_TOKEN')):raise DriveBlocked('CLOUDFLARE_CREDENTIALS_UNAVAILABLE')
    client=CloudflareClient({})
    models=client._request('GET',f'/accounts/{client.account}/ai/models/search?search=flux-2-klein-4b')
    if not any(m.get('name')==MODEL for m in models.get('result',[])):raise DriveBlocked('CLOUDFLARE_MODEL_UNAVAILABLE')
    import datetime as dt
    now=dt.datetime.now(dt.timezone.utc).isoformat()
    usage_status='UNKNOWN';neurons=None
    try:
        query='query { viewer { accounts(filter:{accountTag:'+json.dumps(client.account)+'}) { aiInferenceAdaptiveGroups(limit:1,filter:{datetime_geq:'+json.dumps(now[:10]+'T00:00:00Z')+',datetime_leq:'+json.dumps(now)+'}) { sum { totalNeurons } } } } }'
        u=client._request('POST','/graphql',{'query':query})
        groups=u['data']['viewer']['accounts']
        if len(groups)!=1 or u.get('errors'):raise ValueError()
        values=[g['sum']['totalNeurons'] for g in groups[0]['aiInferenceAdaptiveGroups']]
        import math
        if any(type(v) not in (int,float) or not math.isfinite(v) or v<0 for v in values):raise ValueError()
        neurons=sum(values);usage_status='RECORDED_USAGE_NOT_LIVE_BALANCE'
    except Exception:pass
    return {'status':'CLOUDFLARE_READ_ACCESS_VERIFIED','model':MODEL,'checked_at':now,'usage_status':usage_status,'recorded_neurons':neurons,'inference_requests':0,'inference_permission':'NOT_PROVEN_WITHOUT_GENERATION','billing_clearance':False}


def main():
    p=argparse.ArgumentParser();p.add_argument('command',choices=['check-cloudflare','check-drive','prepare-opn02','check','run']);a=p.parse_args()
    from tools.studio_runtime import Studio
    root=Path.cwd();studio=Studio(root);d=Drive()
    try:
        if a.command=='check-cloudflare':print(json.dumps(check_cloudflare()));return 0
        # File IDs are metadata, not access credentials. Verified owner-only defaults
        # eliminate manual copying; explicit nonempty Secrets retain precedence.
        locators=json.loads((root/'episodes/berakhot-01-01/private-storage-locators.json').read_text()) if (root/'episodes/berakhot-01-01/private-storage-locators.json').is_file() else {}
        baseline=locators.get('historical_attempt_native_sha256',[])
        for k,v in locators.items():
            if k in ('MISHNAH_REFERENCE_FILE_ID','MISHNAH_STATE_FILE_ID','MISHNAH_SNAPSHOT_FILE_ID') and not os.environ.get(k):os.environ[k]=v
        names=['MISHNAH_DRIVE_OAUTH_JSON','MISHNAH_REFERENCE_FILE_ID','MISHNAH_STATE_FILE_ID','MISHNAH_SNAPSHOT_FILE_ID']
        if a.command not in ('check-drive','prepare-opn02'):names=['CLOUDFLARE_ACCOUNT_ID','CLOUDFLARE_API_TOKEN']+names
        missing=[n for n in names if not os.environ.get(n)]
        if missing:raise DriveBlocked('MISSING_CONFIGURATION:'+','.join(missing))
        d.login();refs,state,snapshot=[os.environ[n] for n in names[-3:]]
        if len({refs,state,snapshot})!=3:raise DriveBlocked('DRIVE_FILE_IDS_MUST_DIFFER')
        for uid in (refs,state,snapshot):d.metadata(uid)
        # Check never writes Drive, loads no image model and consumes no inference quota.
        if a.command in ('check','check-drive','prepare-opn02'):
            if a.command in ('check-drive','prepare-opn02'):
                # Validate stored bytes in a clean temporary root; no remote writes.
                import tempfile
                from tools.studio_runtime import Studio as LocalStudio
                with tempfile.TemporaryDirectory() as tmp:
                    clean=Path(tmp)
                    m=json.loads((root/'episodes/berakhot-01-01/comfy-opening-images.json').read_text())
                    target=clean/'episodes/berakhot-01-01';target.mkdir(parents=True)
                    (target/'comfy-opening-images.json').write_text(json.dumps(m))
                    local=LocalStudio(clean)
                    p=local.work/'refs.zip';p.write_bytes(d.download(refs));local.restore_references(str(p.relative_to(clean)))
                    p=local.work/'snapshot.zip';p.write_bytes(d.download(snapshot));local.restore(str(p.relative_to(clean)))
                    saved=json.loads(d.download(state))
                    # The complete local audit uses only files restored above.
                    result=prepare_opn02(root,clean,saved,baseline)
                if a.command=='check-drive':result['status']='DRIVE_RESTORE_AND_LOCAL_PREFLIGHT_VERIFIED'
                print(json.dumps(result));return 0
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
        from tools.studio_runtime import load
        validate_journal(journal,load(studio.work/'images/state.json',{'entries':{}}),baseline)
        atomic(studio.work/'images/state.json',journal)
        # Checkpoint durable state before the billable POST. Failure prevents submission.
        from tools import comfy_scene_images
        original=comfy_scene_images.atomic
        previous=journal
        def checkpoint(path,value):
            nonlocal previous
            if Path(path)==studio.work/'images/state.json':validate_journal(value,previous,baseline)
            original(path,value)
            if Path(path)==studio.work/'images/state.json':
                d.replace(state,json.dumps(value).encode(),'application/json')
                import copy
                previous=copy.deepcopy(value)
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
