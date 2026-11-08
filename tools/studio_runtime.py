"""Deterministic Mishnah studio runtime. No agent, paid fallback or automatic approval."""
import argparse
import copy
import datetime as dt
import hashlib
import html
import json
import os
import shutil
import sys
import zipfile
from pathlib import Path, PurePosixPath
from tools.comfy_scene_images import atomic, under, sha, specifications, run as images, attach
from tools.scene_pack_preflight import report_scene, verified_entry
from tools.scene_review_board import render_board

IMAGE_MANIFEST='episodes/berakhot-01-01/comfy-opening-images.json'
PROOF='episodes/berakhot-01-01/introduction-proof.json'


def load(path, default=None):
    return json.loads(path.read_text(encoding='utf-8')) if path.is_file() else (default if default is not None else {})


def reply(status, completed=None, blocked=None, outputs=None, next_action=None):
    return dict(status=status, what_completed=completed or [], blocked_reason=blocked or [],
                next_action=next_action or 'Review private report; no automatic approval',
                outputs=outputs or {}, cost={'provider_requests':0,'external_usd':0,'workspace_usage':'unknown'})


class Studio:
    def __init__(self, root, workspace='private-media/studio', manifest=IMAGE_MANIFEST, proof=PROOF):
        self.root=Path(root).resolve(); self.work=under(self.root,workspace)
        if 'private-media' not in self.work.relative_to(self.root).parts: raise ValueError('PRIVATE_WORKSPACE_REQUIRED')
        self.work.mkdir(parents=True,exist_ok=True,mode=0o700)
        self.manifest=under(self.root,manifest); self.proof=under(self.root,proof)
        self.runtime=load(self.work/'runtime.json')
        self.endpoint=os.environ.get('COMFY_ENDPOINT') or self.runtime.get('endpoint')
        # Explicit opt-in only. Never silently switch from unavailable ComfyUI
        # to another model provider or infer permissions from the Free plan.
        self.image_backend=os.environ.get('MISHNAH_IMAGE_BACKEND','comfyui')
        if self.image_backend not in ('comfyui','cloudflare'):
            raise ValueError('UNSUPPORTED_IMAGE_BACKEND')
        for field,env in [('private_endpoint_verified','COMFY_PRIVATE_ENDPOINT_VERIFIED'),('zero_cost_verified','COMFY_ZERO_COST_VERIFIED')]:
            if env in os.environ:self.runtime[field]=os.environ[env]=='true'

    def inputs(self):
        m=load(self.manifest)
        m['backend']=(m['available_backends']['cloudflare'] if self.image_backend=='cloudflare'
                      else {'type':'comfyui'})
        return m, specifications(m,self.root), load(self.proof)

    def plan(self):
        m,rows,p=self.inputs(); state=load(self.work/'images/state.json')
        report=report_scene(m,rows,state,p,load(self.root/'docs/evidence/opn02-rear-wide-2026-11-08.json'),self.root)
        tasks=[]
        for row in rows:
            entry=state.get('entries',{}).get(row['key'],{})
            verified,_=verified_entry(entry,self.root)
            status=entry.get('status')
            action=('REVIEW' if verified=='CANDIDATE_NEEDS_HUMAN_REVIEW' else
                    'REUSE' if verified=='VERIFIED_LOCAL_ACCEPTED' else
                    'INSPECT_UNCERTAIN' if status=='SUBMISSION_UNCERTAIN' else
                    'RESUME' if status=='QUEUED' else 'GENERATE')
            tasks.append(dict(shot=row['id'],key=row['key'],action=action,missing=row['missing']))
        repairs=load(self.work/'repairs.json',[])
        for repair in repairs:
            # No inferred inpainting workflow or unauthorized reference upload.
            tasks.append({'shot':repair.get('shot'),'action':'REPAIR','missing':['VERIFIED_INPAINT_WORKFLOW_NOT_CONFIGURED']})
        sources={str(p.relative_to(self.root)):sha(p) for p in (self.root/'scripts/introduction-working-draft.md',self.root/'scripts/introduction-scene-map.md') if p.is_file()}
        atomic(self.work/'queue.json',{'version':1,'tasks':tasks,'scene':m['scene'],'script_and_map_hashes':sources})
        atomic(self.work/'scene-report.json',report)
        return reply('PLANNED',['Read manifests, script and shot references; checked local cache'],
            outputs={'queue':str((self.work/'queue.json').relative_to(self.root)),'tasks':tasks,
                     'scene_report':str((self.work/'scene-report.json').relative_to(self.root))})

    def doctor(self, online=False):
        result=self.plan(); blocks=[]
        for command in ('ffmpeg','ffprobe','fc-match'):
            if not shutil.which(command): blocks.append('MISSING_TOOL:'+command)
        if self.image_backend=='cloudflare':
            # Local doctor never contacts a paid API or uploads private data.
            if not (os.environ.get('CLOUDFLARE_ACCOUNT_ID') and os.environ.get('CLOUDFLARE_API_TOKEN')):
                blocks.append('CLOUDFLARE_CREDENTIALS_UNAVAILABLE')
            m,_,_=self.inputs()
            safety=m['backend'].get('safety',{})
            if safety.get('free_hard_cap_verified') is not True:
                blocks.append('NO_CHARGE_HARD_CAP_UNVERIFIED')
            if not all(m['authorization'].get(k) is True for k in
                       ('generation_approved','component_licenses_verified','zero_cost_compute_verified')):
                blocks.append('GENERATION_OR_RIGHTS_NOT_AUTHORIZED')
        elif not self.endpoint: blocks.append('BLOCKED_NO_GPU: no ComfyUI endpoint configured')
        elif online:
            if not self.runtime.get('private_endpoint_verified'):
                blocks.append('PRIVATE_ENDPOINT_NOT_VERIFIED')
            else:
                from tools.comfy_runtime import inspect
                readiness=inspect(self.endpoint); result['outputs']['gpu']=readiness
                if not readiness['ready']: blocks.append('BLOCKED_NO_GPU')
        result['outputs']['network_checked']=bool(
            self.image_backend=='comfyui' and online and self.endpoint and self.runtime.get('private_endpoint_verified'))
        result['outputs']['image_backend']=self.image_backend
        result['outputs']['backup']='Local portable ZIP supported; unattended remote storage is not configured'
        result['outputs']['inpainting']='BLOCKED_VERIFIED_WORKFLOW_REQUIRED'
        if any(t['missing'] for t in result['outputs']['tasks']): blocks.append('MISSING_OR_UNVERIFIED_INPUTS')
        result.update(status='BLOCKED' if blocks else 'READY_LOCAL_ONLY',blocked_reason=blocks)
        return result

    def review(self):
        self.plan(); m,_,_=self.inputs(); state=load(self.work/'images/state.json')
        candidates=load(self.work/'candidates.json')
        board=render_board(load(self.work/'scene-report.json'),state,self.root,
                           str((self.work/'review/contact-sheet.png').relative_to(self.root)),candidates)
        observations=load(self.work/'composition-measurements.json')
        composition={}
        from tools.shot_controls import assess_composition
        for uid,measurement in observations.items():
            if uid!='OPN02':raise ValueError('Only OPN02 composition acceptance bounds configured')
            candidate=candidates.get(uid)
            if not candidate:
                row=next(r for r in load(self.work/'scene-report.json')['shots'] if r['shot_id']==uid)
                candidate=state.get('entries',{}).get(row['key'])
            if not candidate:raise ValueError('Composition measurement has no local candidate')
            composition[uid]=assess_composition(under(self.root,candidate['path']),measurement)
        atomic(self.work/'review/composition-report.json',composition)
        directory=self.work/'review';out=directory/'index.html'
        # Relative local links only; no public HTTP server or remote embeds.
        text='<html lang="he" dir="rtl"><meta charset="utf-8"><title>ביקורת פרטית</title><h1>מסע אל המשנה — מועמדים בלבד</h1><p>אין אישור אוטומטי. משבצת חסרה אינה איור.</p><img style="max-width:100%" src="contact-sheet.png">'
        text+='<pre dir="ltr">'+html.escape(json.dumps(load(self.work/'queue.json'),ensure_ascii=False,indent=2))+'</pre></html>'
        out.write_text(text,encoding='utf-8');out.chmod(0o600)
        return reply('REVIEW_READY',['Rendered private board from checksum-verified local media'],outputs={'html':str(out.relative_to(self.root)),'board':board,'composition_checks':composition})

    def run(self, resume=False):
        self.plan(); m,rows,_=self.inputs(); state=load(self.work/'images/state.json'); blocks=[]
        if any(e.get('status')=='SUBMISSION_UNCERTAIN' for e in state.get('entries',{}).values()):
            return reply('BLOCKED',blocked=['UNCERTAIN_SUBMISSION_NO_RETRY'])
        if (self.work/'images/running.lock').exists():
            owner=load(self.work/'process-owner.json')
            if resume and type(owner.get('pid')) is int:
                try: os.kill(owner['pid'],0)
                except ProcessLookupError:
                    (self.work/'images/running.lock').unlink()
                except (PermissionError,OSError):
                    return reply('BLOCKED',blocked=['LOCK_OWNER_STATUS_UNKNOWN'])
                else: return reply('BLOCKED',blocked=['IMAGE_PROCESS_STILL_RUNNING'])
            else: return reply('BLOCKED',blocked=['UNKNOWN_LOCK_OWNER_NO_AUTOMATIC_REMOVAL'])
        targets=[]
        for row in rows:
            entry=state.get('entries',{}).get(row['key'],{})
            verified,_=verified_entry(entry,self.root)
            if verified=='LOCAL_STATE_ASSET_MISMATCH': blocks.append('CACHE_INTEGRITY_FAILURE:'+row['id']);continue
            if verified:continue
            if resume and entry.get('status')!='QUEUED':continue
            if row['missing']: blocks.append('MISSING_INPUTS:'+row['id']);continue
            if not m['authorization'].get('generation_approved') or row['id'] not in m['authorization'].get('approved_shot_ids',[]):
                blocks.append('GENERATION_NOT_AUTHORIZED:'+row['id']);continue
            targets.append(row['id'])
        if not targets:
            result=self.review();result['blocked_reason']=blocks
            result['status']='BLOCKED' if blocks else ('NO_QUEUED_TASKS' if resume else 'NO_GENERATION_NEEDED');return result
        if self.image_backend=='cloudflare':
            # The existing Cloudflare adapter already performs its model, quota
            # and privacy checks; share the same private cache/queue/review path.
            # No independent credential means stop, never fall back to a paid API.
            if resume:
                return reply('BLOCKED',blocked=blocks+['SYNCHRONOUS_CLOUDFLARE_NEVER_AUTO_RETRIED'])
            if not all(m['authorization'].get(k) is True for k in
                       ('generation_approved','zero_cost_compute_verified','component_licenses_verified')):
                return reply('BLOCKED',blocked=blocks+['GENERATION_OR_RIGHTS_NOT_AUTHORIZED'])
            from tools.cloudflare_image_backend import CloudflareClient,CloudflareBlocked
            client=CloudflareClient(m['backend'])
            if not client.account or not client.token:
                return reply('BLOCKED',blocked=blocks+['CLOUDFLARE_CREDENTIALS_UNAVAILABLE'])
            if len(targets)!=1 or m['authorization'].get('max_submissions')!=1:
                return reply('BLOCKED',blocked=blocks+['CLOUDFLARE_SINGLE_SHOT_ONLY'])
            m['shots']=[s for s in m['shots'] if s['id'] in targets]
            try:
                # Fails closed on unknown quota, missing privacy/legal evidence
                # or a stale hard-cap attestation, before any image request.
                client.readiness(next(r['spec'] for r in rows if r['id']==targets[0]))
            except (CloudflareBlocked,ValueError) as error:
                return reply('BLOCKED',blocked=blocks+[
                    str(error) if type(error).__name__=='CloudflareBlocked' else 'CLOUDFLARE_READINESS_FAILED'])
            report=images(m,self.root,self.work/'images',client,True)
            result=self.review()
            result['what_completed'].append('Ran existing synchronous Cloudflare adapter')
            result['cost']['provider_requests']=report['submissions']
            result['cost']['external_usd']='unknown'
            return result
        if not self.endpoint:return reply('BLOCKED',blocked=blocks+['BLOCKED_NO_GPU'])
        if not all(self.runtime.get(k) is True for k in ('private_endpoint_verified','zero_cost_verified')):
            return reply('BLOCKED',blocked=blocks+['RUNTIME_PRIVACY_OR_ZERO_COST_UNVERIFIED'])
        # Existing license/approval gates are never upgraded by runtime configuration.
        from tools.comfy_runtime import inspect
        from tools.comfy_image_backend import ComfyClient
        if not inspect(self.endpoint)['ready']:return reply('BLOCKED',blocked=blocks+['BLOCKED_NO_GPU'])
        m['shots']=[s for s in m['shots'] if s['id'] in targets]
        # A queued job belongs to its original server, even after an endpoint switch.
        saved=load(self.work/'execution-endpoint.json')
        endpoint_hash=hashlib.sha256(self.endpoint.encode()).hexdigest()
        if any(e.get('status')=='QUEUED' for e in state.get('entries',{}).values()) and saved.get('sha256')!=endpoint_hash:
            return reply('BLOCKED',blocked=['QUEUED_JOB_BELONGS_TO_DIFFERENT_ENDPOINT'])
        atomic(self.work/'execution-endpoint.json',{'sha256':endpoint_hash})
        atomic(self.work/'process-owner.json',{'pid':os.getpid()})
        report=images(m,self.root,self.work/'images',ComfyClient(self.endpoint),True)
        result=self.review();result['what_completed'].append('Executed existing ComfyUI orchestrator')
        result['cost']['provider_requests']=report['submissions'];return result

    def proof_video(self):
        from tools.introduction_render import render
        from tools.introduction_proof import plan
        config=load(self.proof)
        state=load(self.work/'images/state.json'); entries=[]
        _,rows,_=self.inputs()
        for row in rows:
            e=state.get('entries',{}).get(row['key'])
            if e:entries.append(dict(e,id=row['id'],key=row['key']))
        config=attach(config,{'shots':entries})
        ready=plan(config,self.root)
        if ready['errors'] or ready['missing']:
            atomic(self.work/'proof-blockers.json',ready)
            return reply('BLOCKED',blocked=['PROOF_INPUTS_OR_APPROVALS_MISSING'],outputs={'report':str((self.work/'proof-blockers.json').relative_to(self.root))})
        output=render(config,self.root,self.work/'proof')
        return reply('PROOF_RENDERED',['Assembled existing approved media without AI'],outputs=output)

    def restore_references(self, archive):
        """Owner-authorized original two-image ZIP; never grants generation permission."""
        from tools.comfy_runtime import intake_package
        m=load(self.manifest)
        if not all(r.get('synthesis_rights_confirmed') is True and r.get('rights_uri') for r in m['references']):
            raise ValueError('EXISTING_REFERENCE_RIGHTS_REQUIRED')
        archive=under(self.root,archive)
        if 'private-media' not in archive.relative_to(self.root).parts:raise ValueError('PRIVATE_REFERENCE_PACKAGE_REQUIRED')
        bound,receipt=intake_package(archive,self.root,m,rights_uri=m['references'][0]['rights_uri'],synthesis_rights_confirmed=True)
        atomic(self.work/'reference-intake.json',receipt)
        return reply('REFERENCES_RESTORED',['Verified original reference hashes/dimensions; no approval or manifest change'],outputs={'receipt':str((self.work/'reference-intake.json').relative_to(self.root))})

    def backup(self, destination):
        destination=under(self.root,destination)
        if 'private-media' not in destination.relative_to(self.root).parts:raise ValueError('PRIVATE_BACKUP_REQUIRED')
        if destination.exists():raise ValueError('BACKUP_EXISTS')
        # All local private media, including queue and prior versions; no environment secrets.
        base=self.root/'private-media';files=[p for p in base.rglob('*') if p.is_file() and p!=destination and p.suffix!='.zip']
        if any(p.name=='running.lock' for p in files):raise ValueError('BACKUP_REQUIRES_IDLE_RUNTIME')
        files=[p for p in files if p.name!='runtime.json' and p.suffix.lower() not in ('.key','.pem','.env') and not any(x in p.name.lower() for x in ('credential','token','secret'))]
        if any(p.is_symlink() or not p.resolve().is_relative_to(self.root) for p in files):raise ValueError('UNSAFE_BACKUP_SYMLINK')
        snapshot={str(p.relative_to(self.root)):sha(p) for p in files}
        destination.parent.mkdir(parents=True,exist_ok=True)
        tmp=destination.with_suffix('.tmp')
        with zipfile.ZipFile(tmp,'w',zipfile.ZIP_DEFLATED) as z:
            for p in files:
                if p.is_symlink() or not p.resolve().is_relative_to(self.root):raise ValueError('UNSAFE_BACKUP_SYMLINK')
                raw=p.read_bytes();name=str(p.relative_to(self.root))
                if hashlib.sha256(raw).hexdigest()!=snapshot[name]:raise ValueError('FILE_CHANGED_DURING_BACKUP')
                z.writestr(name,raw)
            z.writestr('snapshot.json',json.dumps(snapshot,sort_keys=True))
        tmp.replace(destination);destination.chmod(0o600)
        return reply('BACKUP_CREATED',['Saved portable private data; runtime endpoint/secrets excluded'],outputs={'archive':str(destination.relative_to(self.root)),'sha256':sha(destination),'files':len(snapshot)})

    def restore(self, archive):
        archive=under(self.root,archive)
        with zipfile.ZipFile(archive) as z:
            if len(z.namelist())!=len(set(z.namelist())) or sum(i.file_size for i in z.infolist())>4*1024**3:raise ValueError('INVALID_ARCHIVE')
            if any(((i.external_attr>>16)&0o170000)==0o120000 for i in z.infolist()):raise ValueError('UNSAFE_ARCHIVE_SYMLINK')
            snapshot=json.loads(z.read('snapshot.json'));verified=[]
            if set(z.namelist())!=set(snapshot)|{'snapshot.json'}:raise ValueError('ARCHIVE_MEMBERS_MISMATCH')
            for name,expected in snapshot.items():
                path=under(self.root,name)
                if not name.startswith('private-media/') or name.endswith(('running.lock','runtime.json')):raise ValueError('UNSAFE_RESTORE_PATH')
                raw=z.read(name)
                if hashlib.sha256(raw).hexdigest()!=expected:raise ValueError('BACKUP_HASH_MISMATCH')
                if path.exists() and sha(path)!=expected:raise ValueError('RESTORE_WOULD_OVERWRITE')
                verified.append((path,raw))
            for path,raw in verified:
                path.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
                if not path.exists():path.write_bytes(raw);path.chmod(0o600)
        return reply('RESTORED',['Verified complete archive before non-overwriting restore'],outputs={'files':len(verified)})


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('command',choices=['doctor','plan','run','resume','review','proof','backup','restore','restore-references'])
    p.add_argument('--root',default='.');p.add_argument('--workspace',default='private-media/studio')
    p.add_argument('--online',action='store_true');p.add_argument('--archive')
    a=p.parse_args()
    try:
        s=Studio(a.root,a.workspace)
        if a.command=='doctor':r=s.doctor(a.online)
        elif a.command in ('run','resume'):r=s.run(a.command=='resume')
        elif a.command=='proof':r=s.proof_video()
        elif a.command in ('backup','restore','restore-references'):
            if not a.archive:p.error('--archive required')
            r=getattr(s,a.command.replace('-','_'))(a.archive)
        else:r=getattr(s,a.command)()
    except Exception as error:
        if 's' in locals():atomic(s.work/'runtime-error.json',{'error_type':type(error).__name__,'at':dt.datetime.now(dt.timezone.utc).isoformat(),'command':a.command,'automatic_retry':False})
        r=reply('BLOCKED',blocked=['RUNTIME_ERROR:'+type(error).__name__],next_action='Inspect private inputs and saved queue; never blindly resubmit')
        if a.command in ('run','resume'):r['cost'].update(provider_requests='unknown',external_usd='unknown')
    print(json.dumps(r,ensure_ascii=False,indent=2))
    return 2 if r['status']=='BLOCKED' else 0

if __name__=='__main__':sys.exit(main())
