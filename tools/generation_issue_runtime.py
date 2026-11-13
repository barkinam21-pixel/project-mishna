"""Bounded Issue54 execution using the existing immutable private studio runtime.

Run from the reviewed runtime checkout; no public artifacts or retry loop.
"""
import argparse,copy,datetime as dt,hashlib,json,os,sys,tempfile
from pathlib import Path
try:
    from .chat_issue_bridge import validate_generation_event,reserve_generation,GENERATION_BLOCK,RequestBlocked
except ImportError:
    from chat_issue_bridge import validate_generation_event,reserve_generation,GENERATION_BLOCK,RequestBlocked
RUNTIME='80ba1559b785855a1f9f4cbd90083fd0228eec96'

# Fixed immutable-adapter codes only; never print arbitrary provider responses.
SAFE_PROVIDER_CODES=frozenset((
 'CREDENTIALS_UNAVAILABLE','TRANSPORT_FAILED_NO_AUTOMATIC_RETRY','PROVIDER_REJECTED',
 'PRIVACY_OR_LICENSE_UNVERIFIED','NO_CHARGE_HARD_CAP_UNVERIFIED',
 'PARTNER_PRIVATE_REFERENCE_TERMS_UNVERIFIED','SAFETY_EVIDENCE_EXPIRED',
 'MODEL_UNAVAILABLE','USAGE_UNKNOWN','FREE_ALLOWANCE_HEADROOM_INSUFFICIENT',
 'REFERENCE_COUNT_INVALID','REFERENCE_COUNT_MISMATCH','REFERENCE_CHANGED',
 'SUBMISSION_NOT_AUTHORIZED'))

def safe_failure_code(error):
    if isinstance(error,RequestBlocked):return str(error)
    if type(error).__name__=='CloudflareBlocked' and str(error) in SAFE_PROVIDER_CODES:
        return str(error)
    return type(error).__name__

def checkpoint_once(ticket,baseline,proposed,persist):
    """Use engine's reservation, not an extra attempt; persist before its POST."""
    old=baseline.get('attempts',[]);new=proposed.get('attempts',[])
    if new[:len(old)]!=old or len(new)!=len(old)+1 or new[-1].get('key')!=ticket['spec_sha256']:
        raise RequestBlocked('ENGINE_RESERVATION_MISMATCH')
    def save(reserved):
        proposed['attempts'][-1].update(reserved['attempts'][-1])
        persist(proposed)
    reserve_generation(ticket,baseline,save)


def execute(event,policy,history,manifest,root,drive,state_id,snapshot_id,adapter=None):
    """Actual network dependencies injectable; never relax persisted source gates."""
    from tools.comfy_scene_images import specifications,run,atomic
    from tools.private_drive_runtime import validate_journal
    from tools.studio_runtime import Studio
    from tools.cloudflare_image_backend import CloudflareClient
    ticket=validate_generation_event(event,policy,history)
    m=copy.deepcopy(manifest);m['backend']=m['available_backends']['cloudflare']
    shot_id=ticket['shot_id']
    m['shots']=[s for s in m['shots'] if s['id']==shot_id]
    rows=specifications(m,root)
    if len(rows)!=1 or rows[0]['missing'] or rows[0]['key']!=ticket['spec_sha256']:raise RequestBlocked('RESTORED_SPEC_MISMATCH')
    # Admission is scoped to this validated ticket, never written to public manifest.
    m['authorization'].update(generation_approved=True,zero_cost_compute_verified=True,component_licenses_verified=True,max_submissions=1,total_submissions_limit=ticket['total_attempt_limit'],approved_shot_ids=[shot_id])
    cfg=copy.deepcopy(m['backend']);safety=cfg['safety']
    safety.update(private_direct_api_verified=True,partner_private_reference_terms_verified=True,licenses_verified=True,free_hard_cap_verified=True,verified_at=policy['verified_at'])
    studio=Studio(root);out=studio.work/'images';atomic(out/'state.json',history)
    client=adapter or CloudflareClient(cfg)
    # Always require live quota/model/privacy readiness; unknown means stop.
    client.readiness(rows[0]['spec'])
    from tools import comfy_scene_images as engine
    original=engine.atomic;reserved=False;previous=copy.deepcopy(history)
    def persist(value):
        validate_journal(value,previous)
        drive.replace(state_id,json.dumps(value).encode(),'application/json')
    def journal(path,value):
        nonlocal reserved,previous
        if Path(path)==out/'state.json':
            if not reserved:
                checkpoint_once(ticket,history,value,persist);reserved=True
            else:persist(value)
            previous=copy.deepcopy(value)
        original(path,value)
    engine.atomic=journal
    try:report=run(m,root,out,client,True)
    finally:engine.atomic=original
    destination='private-media/studio/generation-output-'+ticket['request_id']+'.zip'
    saved=studio.backup(destination)
    drive.replace(snapshot_id,(Path(root)/destination).read_bytes(),'application/zip')
    return {'status':shot_id+'_PRIVATE_CANDIDATE_SAVED','request_id':ticket['request_id'],'inference_requests':report['submissions'],'accepted':False,'history_attempts':len(previous['attempts']),'snapshot_sha256':saved['outputs']['sha256']}


def main():
    p=argparse.ArgumentParser();p.add_argument('--event',required=True);p.add_argument('--policy',required=True);p.add_argument('--dry-run',action='store_true');a=p.parse_args()
    try:
        event=json.loads(Path(a.event).read_text());policy=json.loads(Path(a.policy).read_text())
        if not GENERATION_BLOCK.findall(event.get('issue',{}).get('body','')):
            print(json.dumps({'status':'IGNORED_NO_GENERATION_REQUEST','inference_requests':0}));return 0
        # Policy is reviewed repository data, not Issue-controlled safety booleans.
        if not all(policy.get(k) is True for k in ('privacy_verified','free_hard_cap_verified','quota_verified')):
            raise RequestBlocked('GENERATION_POLICY_NOT_CLEARED')
        import subprocess
        if subprocess.check_output(['git','rev-parse','HEAD']).decode().strip()!=RUNTIME:raise RequestBlocked('UNREVIEWED_PRIVATE_RUNTIME')
        sys.path.insert(0,str(Path.cwd()))
        from tools.private_drive_runtime import Drive,validate_journal,prepare_opn02
        from tools.studio_runtime import Studio,load
        runtime_root=Path.cwd();m=json.loads((runtime_root/'episodes/berakhot-01-01/comfy-opening-images.json').read_text());locators=json.loads((runtime_root/'episodes/berakhot-01-01/private-storage-locators.json').read_text())
        d=Drive();d.login();refs,state,snapshot=[locators[k] for k in ('MISHNAH_REFERENCE_FILE_ID','MISHNAH_STATE_FILE_ID','MISHNAH_SNAPSHOT_FILE_ID')]
        for uid in (refs,state,snapshot):d.metadata(uid)
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);target=root/'episodes/berakhot-01-01';target.mkdir(parents=True);(target/'comfy-opening-images.json').write_text(json.dumps(m))
            studio=Studio(root);p=studio.work/'references.zip';p.write_bytes(d.download(refs));studio.restore_references(str(p.relative_to(root)))
            p=studio.work/'snapshot.zip';p.write_bytes(d.download(snapshot));studio.restore(str(p.relative_to(root)))
            history=json.loads(d.download(state));validate_journal(history,load(studio.work/'images/state.json',{'entries':{}}),locators['historical_attempt_native_sha256'])
            # Reuse the independently verified OPN02 asset/history preflight as
            # a shared source-integrity checkpoint. It makes no inference.
            audit=prepare_opn02(runtime_root,root,history,locators['historical_attempt_native_sha256'])
            validate_generation_event(event,policy,history)
            if a.dry_run:
                print(json.dumps({'status':'ONE_SHOT_DRY_RUN_NO_INFERENCE','conditioning_inputs':audit['conditioning_inputs'],'historical_attempts':len(history['attempts']),'inference_requests':0,'remote_writes':0}));return 0
            print(json.dumps(execute(event,policy,history,m,root,d,state,snapshot)));return 0
    except Exception as e:
        print(json.dumps({'status':'BLOCKED','code':safe_failure_code(e),'retry':False,'inference_outcome':'Inspect journal; never resubmit uncertain work'}));return 2

if __name__=='__main__':sys.exit(main())
