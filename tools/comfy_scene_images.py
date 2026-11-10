"""Manifest-driven private ComfyUI image production. No provisioning or paid fallback."""
import argparse
import copy
import hashlib
import io
import json
import re
from pathlib import Path
from PIL import Image
from tools.comfy_image_backend import ComfyClient, key


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def under(root, name):
    path = (Path(root) / name).resolve()
    if not path.is_relative_to(Path(root).resolve()):
        raise ValueError('Path escapes asset root')
    return path


def atomic(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix('.tmp')
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2)+'\n')
    tmp.replace(path)
    if 'private-media' in path.parts: path.chmod(0o600)


def conditioning_inputs(spec, root):
    """Verify originals and deterministically derive recorded identity crops in memory.

    No file upload or invented model control. Empty list means original references.
    """
    prep=spec.get('director',{}).get('reference_preparation')
    if prep is None:return []
    crops=prep.get('crops',[])
    if not isinstance(crops,list) or not 1<=len(crops)<=4:raise ValueError('Invalid conditioning crop count')
    originals={r['sha256']:r for r in spec['references']};result=[]
    for crop in crops:
        ref=originals.get(crop.get('source_sha256'))
        if ref is None or ref.get('synthesis_rights_confirmed') is not True:raise ValueError('Unapproved crop source')
        source=under(root,ref['path'])
        if not source.is_file() or sha(source)!=ref['sha256']:raise ValueError('Changed crop source')
        box=crop.get('crop_box')
        with Image.open(source) as im:
            im.load()
            if not isinstance(box,list) or len(box)!=4 or any(type(x) is not int for x in box) or not 0<=box[0]<box[2]<=im.width or not 0<=box[1]<box[3]<=im.height:raise ValueError('Invalid conditioning crop box')
            derived=im.crop(box).convert('RGB');derived.thumbnail((511,511),Image.Resampling.LANCZOS)
            buffer=io.BytesIO();derived.save(buffer,format='PNG');raw=buffer.getvalue()
            if list(derived.size)!=crop.get('size') or hashlib.sha256(raw).hexdigest()!=crop.get('sha256'):raise ValueError('Conditioning pixels/encoder differ from recorded hash')
        result.append((raw,crop['sha256']))
    return result


def specifications(manifest, root):
    """Resolve visual dependencies only; narration/timing do not invalidate pictures."""
    if manifest.get('schema_version') != 1:
        raise ValueError('Unsupported manifest version')
    model = manifest['model']
    if model['id'] != 'black-forest-labs/FLUX.2-klein-4B':
        raise ValueError('Only verified Klein 4B family supported')
    backend = manifest.get('backend', {'type':'comfyui'})
    if backend.get('type') not in ('comfyui', 'hf-zero', 'cloudflare', 'modal'):
        raise ValueError('Unsupported image backend')
    seen = set()
    results = []
    for shot in manifest['shots']:
        uid = shot['id']
        if not re.fullmatch(r'OPN0[1-7]', uid) or uid in seen:
            raise ValueError('Invalid/duplicate shot ID')
        seen.add(uid)
        if not isinstance(shot['prompt'], str) or not shot['prompt'].strip():
            raise ValueError('Missing shot prompt')
        if type(shot['seed']) is not int or not 0 <= shot['seed'] < 2**64:
            raise ValueError('Invalid seed')
        width, height = manifest['size']
        if any(type(x) is not int or x < 256 or x > 2048 or x % 16 for x in (width,height)) or width*9 != height*16:
            raise ValueError('Require 16:9 dimensions, multiples of 16')
        characters = {c: manifest['characters'][c] for c in shot['characters']}
        references = manifest['references'] + [r for c in characters.values() for r in c['references']]
        unique = {r['path']: r for r in references}
        missing = []
        if backend['type'] == 'comfyui' and (not model.get('revision') or model['revision'] == 'UNVERIFIED'):
            missing.append('Model revision unverified')
        if backend['type'] == 'comfyui' and (not isinstance(model.get('component_sha256'),dict) or any(not re.fullmatch(r'[0-9a-f]{64}', str(model['component_sha256'].get(k,''))) for k in ('unet','text_encoder','vae'))):
            missing.append('Model component hashes unverified')
        if backend['type'] == 'modal' and not re.fullmatch(r'[0-9a-f]{40}', str(backend.get('revision', ''))):
            missing.append('Modal model revision not pinned')
        if backend['type'] == 'hf-zero' and (not re.fullmatch(r'[0-9a-f]{40}', str(backend.get('revision',''))) or not re.fullmatch(r'[0-9a-f]{64}', str(backend.get('app_sha256','')))):
            missing.append('Hosted deployment provenance unverified')
        for ref in unique.values():
            if ref.get('expected_sha256') and ref.get('sha256') != ref['expected_sha256']:
                missing.append('Original reference not hash-verified: '+ref['path'])
            path = under(root, ref['path'])
            if not path.is_file() or sha(path) != ref['sha256']:
                missing.append('Missing/changed reference: '+ref['path'])
            if path.is_file() and ref.get('expected_size'):
                with Image.open(path) as image:
                    if list(image.size) != ref['expected_size']: missing.append('Reference dimensions mismatch: '+ref['path'])
            if ref.get('synthesis_rights_confirmed') is not True:
                missing.append('Reference rights: '+ref['path'])
        if not references:
            missing.append('Approved style reference missing')
        if any(not c['references'] for c in characters.values()):
            missing.append('Character reference missing')
        spec = {'compiler_version': 1, 'model': model, 'size': manifest['size'],
                'style': manifest['style'], 'characters': characters,
                'prompt': shot['prompt'], 'seed': shot['seed'], 'references': list(unique.values())}
        if shot.get('visual_direction'): spec['visual_direction'] = shot['visual_direction']
        if shot.get('director'):
            from tools.shot_controls import validate
            missing.extend(validate(shot['director'],shot,manifest))
            spec['director']=shot['director']
        if backend['type']=='cloudflare' and not shot.get('director'): missing.append('Director controls required')
        if backend['type'] != 'comfyui': spec['backend'] = backend
        if not missing:
            try: conditioning_inputs(spec,root)
            except (ValueError,OSError) as error: missing.append('Conditioning preparation failed: '+type(error).__name__)
        results.append({'id': uid, 'key': key(spec), 'spec': spec, 'missing': missing})
    return results


def prompt_text(spec):
    text = spec['style']+' '+spec['prompt']+' '+json.dumps(
        {c:v['description'] for c,v in spec['characters'].items()}, ensure_ascii=False)
    if spec.get('visual_direction'): text += ' '+json.dumps(spec['visual_direction'],ensure_ascii=False)
    if spec.get('director'): text += ' STRUCTURED DIRECTION: '+json.dumps(spec['director'],ensure_ascii=False,sort_keys=True)
    return text


def compile_klein(spec, references):
    """Native Comfy core nodes, following official Klein distilled workflow topology."""
    model = spec['model']
    def node(kind, **inputs): return {'class_type': kind, 'inputs': inputs}
    w,h = spec['size']
    prompt = prompt_text(spec)
    graph = {
        '1': node('UNETLoader', unet_name=model['unet'], weight_dtype='default'),
        '2': node('CLIPLoader', clip_name=model['text_encoder'], type='flux2', device='default'),
        '3': node('VAELoader', vae_name=model['vae']),
        '4': node('CLIPTextEncode', clip=['2',0], text=prompt),
        '5': node('ConditioningZeroOut', conditioning=['4',0]),
        '6': node('EmptyFlux2LatentImage', width=w,height=h,batch_size=1),
        '7': node('RandomNoise', noise_seed=spec['seed']),
        '8': node('KSamplerSelect', sampler_name='euler'),
        '9': node('Flux2Scheduler', steps=4,width=w,height=h),
    }
    positive, negative = ['4',0], ['5',0]
    for i, name in enumerate(references):
        base = 20+i*4
        graph[str(base)] = node('LoadImage', image=name)
        graph[str(base+1)] = node('VAEEncode', pixels=[str(base),0],vae=['3',0])
        graph[str(base+2)] = node('ReferenceLatent', conditioning=positive,latent=[str(base+1),0])
        graph[str(base+3)] = node('ReferenceLatent', conditioning=negative,latent=[str(base+1),0])
        positive,negative = [str(base+2),0],[str(base+3),0]
    graph.update({
        '10': node('CFGGuider',model=['1',0],positive=positive,negative=negative,cfg=1.0),
        '11': node('SamplerCustomAdvanced',noise=['7',0],guider=['10',0],sampler=['8',0],sigmas=['9',0],latent_image=['6',0]),
        '12': node('VAEDecode',samples=['11',0],vae=['3',0]),
        '13': node('SaveImage',images=['12',0],filename_prefix='mishnah_candidate'),
    })
    return graph


def run(manifest, root, out, client=None, generate=False):
    """Persist queue IDs before polling. Uncertain POST is never automatically retried."""
    root, out = Path(root).resolve(), Path(out).resolve()
    if not out.is_relative_to(root): raise ValueError('Output must be private directory under root')
    out.mkdir(parents=True, exist_ok=True)
    # Prevent concurrent invocations from spending twice on the same unresolved work.
    lock = out/'running.lock'
    try: handle = lock.open('x')
    except FileExistsError: raise ValueError('Another run or stale lock; inspect before resuming')
    try:
        handle.close()
        return _run(manifest,root,out,client,generate)
    except Exception as error:
        import datetime
        atomic(out/'last-error.json', {'status':'BLOCKED_OR_UNCERTAIN','error_type':type(error).__name__,
            'code':str(error) if type(error).__name__=='CloudflareBlocked' else 'INSPECT_STATE_NO_BLIND_RETRY',
            'finished_at':datetime.datetime.now(datetime.timezone.utc).isoformat()})
        raise
    finally:
        lock.unlink(missing_ok=True)


def _run(manifest, root, out, client, generate):
    rows = specifications(manifest,root)
    state_path = out/'state.json'
    state = json.loads(state_path.read_text()) if state_path.exists() else {'entries':{}}
    report = {'shots': [], 'submissions':0, 'accepted_cache_hits':0,
              'candidate_reuses':0, 'external_charge_usd':None if manifest.get('backend',{}).get('type') in ('cloudflare','modal') else 0, 'workspace_usage':'unknown'}
    for row in rows:
        entry = state['entries'].get(row['key'])
        if entry and entry.get('status') in ('CANDIDATE','ACCEPTED'):
            path = under(root,entry['path'])
            if not path.is_file() or sha(path) != entry['sha256']:
                raise ValueError('Cached image missing/changed; review before regenerating')
            if entry.get('png_is_converted') and (not under(root,entry['native_path']).is_file() or sha(under(root,entry['native_path']))!=entry['native_sha256']):
                raise ValueError('Native provider original missing/changed')
            report['accepted_cache_hits' if entry['status']=='ACCEPTED' else 'candidate_reuses'] += 1
        elif not generate:
            entry = entry or {'status':'BLOCKED' if row['missing'] else 'NEEDS_GENERATION'}
        else:
            synchronous = False
            pid = None
            policy = manifest['authorization']
            if row['id'] not in policy.get('approved_shot_ids', []):
                raise ValueError('Shot not authorized for generation: '+row['id'])
            # Modal uses a separately owner-approved bounded trial: never
            # misrepresent paid/credit-backed GPU time as verified zero-cost compute.
            compute_approved = (policy.get('bounded_modal_trial_approved') is True
                                if manifest.get('backend',{}).get('type')=='modal'
                                else policy.get('zero_cost_compute_verified') is True)
            if row['missing'] or not compute_approved or policy.get('generation_approved') is not True or policy.get('component_licenses_verified') is not True:
                raise ValueError('Missing references, rights, compute verification or authorization')
            if client is None: raise ValueError('No ComfyUI endpoint configured')
            if entry and entry['status']=='SUBMISSION_UNCERTAIN':
                raise ValueError('Uncertain submission; inspect server queue, never blindly retry')
            if entry and (getattr(client,'synchronous_response',False) or getattr(client,'engine_name','')=='Cloudflare Workers AI'):
                # A Cloudflare response has no provider queue ID to resume.
                # Legacy QUEUED entries may hold private base64: never replay
                # or serialise them into new reports.
                raise ValueError('SYNCHRONOUS_RESPONSE_REQUIRES_MANUAL_RECOVERY')
            if not entry:
                if report['submissions'] >= policy['max_submissions']:
                    raise ValueError('Submission limit reached')
                if len(state.get('attempts',[])) >= policy.get('total_submissions_limit',2**63):
                    raise ValueError('Total authorized submission limit reached; no new attempt')
                prepared=conditioning_inputs(row['spec'],root)
                reference_paths=[under(root,r['path']) for r in row['spec']['references']]
                if prepared:
                    reference_paths=[]
                    for raw,digest in prepared:
                        target=out/(digest+'.conditioning.png')
                        if target.exists() and sha(target)!=digest:raise ValueError('Conditioning cache corrupted')
                        if not target.exists():target.write_bytes(raw);target.chmod(0o600)
                        reference_paths.append(target)
                graph = client.prepare(row['spec'],reference_paths)
                entry = {'status':'SUBMISSION_UNCERTAIN','spec':row['spec'],'workflow':graph, 'backend':getattr(client,'engine_name','ComfyUI')}
                state['entries'][row['key']] = entry
                state.setdefault('attempts',[]).append({'key':row['key'],'shot':row['id'],'backend':entry['backend']})
                atomic(state_path,state)
                pid = client.submit(graph,zero_cost_verified=compute_approved,authorized=True)
                # Cloudflare returns the entire image synchronously. Never journal the
                # base64 image (or receipt with private prompts) as a queue identifier.
                # A crash before saving the final candidate is non-replayable and
                # must remain uncertain; automatic resubmission could burn quota.
                synchronous = getattr(client,'synchronous_response',False) or getattr(client,'engine_name','') == 'Cloudflare Workers AI'
                if synchronous:
                    entry.update(status='SUBMISSION_UNCERTAIN',prompt_id='SYNCHRONOUS_RESPONSE_NOT_REPLAYABLE')
                else:
                    entry.update(status='QUEUED',prompt_id=pid)
                report['submissions'] += 1
                atomic(state_path,state)
                with (out/'usage.jsonl').open('a') as log:
                    log.write(json.dumps({'operation':'received_unpersisted' if synchronous else 'queued',
                                          'key':row['key'],'prompt_id':entry['prompt_id'],
                                          'external_charge_usd':None if synchronous else 0,
                                          'workspace_usage':'unknown'})+'\n')
            # Synchronous bytes exist in memory only for this submission.
            # Existing asynchronous providers still resume through a durable ID.
            history = client.wait(pid if synchronous else entry['prompt_id'])
            result = client.result(history)
            if result.get('seed') not in (None,row['spec']['seed']):
                raise ValueError('Provider changed requested seed')
            raw = client.download(result)
            native_sha = hashlib.sha256(raw).hexdigest()
            if result.get('receipt',{}).get('native_sha256') and result['receipt']['native_sha256']!=native_sha:
                raise ValueError('Native provider image hash mismatch')
            with Image.open(io.BytesIO(raw)) as im:
                im.load()
                native_format = im.format
                if list(im.size)!=manifest['size'] or im.mode not in ('RGB','RGBA'):
                    raise ValueError('Unexpected image dimensions or color mode')
                if native_format not in ('PNG','WEBP','JPEG') or (native_format=='WEBP' and row['spec'].get('backend',{}).get('type') not in ('hf-zero','cloudflare')) or (native_format=='JPEG' and row['spec'].get('backend',{}).get('type')!='cloudflare'):
                    raise ValueError('Unexpected provider image format')
                pixels = im.tobytes()
                if native_format in ('WEBP','JPEG'):
                    original=out/(row['key']+'.original.'+('webp' if native_format=='WEBP' else 'jpg'))
                    temp=original.with_suffix('.tmp');temp.write_bytes(raw);temp.replace(original)
                    buffer=io.BytesIO();im.save(buffer,format='PNG');raw=buffer.getvalue()
                    with Image.open(io.BytesIO(raw)) as converted:
                        converted.load()
                        if converted.mode!=im.mode or converted.size!=im.size or converted.tobytes()!=pixels:
                            raise ValueError('PNG conversion changed decoded pixels')
            if any(e.get('sha256')==hashlib.sha256(raw).hexdigest() and k!=row['key'] for k,e in state['entries'].items()):
                raise ValueError('Duplicate original across shots')
            path = out/(row['key']+'.png')
            tmp = path.with_suffix('.tmp');tmp.write_bytes(raw);tmp.replace(path)
            entry.update(status='CANDIDATE',path=str(path.relative_to(root)),sha256=sha(path),
                         prompt_id=('synchronous-response:'+native_sha if synchronous else entry['prompt_id']),
                         accepted=False,rights_verified=False,continuity_review='PENDING_HUMAN',
                         model=manifest['model'],seed=row['spec']['seed'],
                         native_format=native_format,native_sha256=native_sha,
                         png_is_converted=native_format in ('WEBP','JPEG'),
                         native_path=str(original.relative_to(root)) if native_format in ('WEBP','JPEG') else str(path.relative_to(root)))
            from tools.shot_controls import visual_qa
            entry['qa']=visual_qa(path,[under(root,r['path']) for r in row['spec']['references']])
            if result.get('receipt'): entry['provider_receipt']=result['receipt']
            atomic(state_path,state)
        public_entry=dict(entry or {})
        if row['spec'].get('backend',{}).get('type')=='cloudflare' and isinstance(public_entry.get('prompt_id'),dict):
            public_entry['prompt_id']='synchronous-response:'+public_entry.get('native_sha256','pending')
        report['shots'].append({'id':row['id'],'key':row['key'],'missing':row['missing'],'spec':row['spec'],**public_entry})
    atomic(out/'report.json',report)
    return report


def accept(root, out, cache_key, reviewer, continuity, rights):
    """Explicit human-review operation; never called by generation."""
    if not reviewer.strip() or continuity is not True or rights is not True:
        raise ValueError('Named human continuity and rights review required')
    p = Path(out)/'state.json'; state=json.loads(p.read_text());e=state['entries'][cache_key]
    if e['status']!='CANDIDATE' or sha(under(root,e['path']))!=e['sha256']:
        raise ValueError('Candidate changed or unavailable')
    e.update(status='ACCEPTED',accepted=True,rights_verified=True,continuity_review=reviewer)
    atomic(p,state)


def attach(config, report):
    """Return renderer-compatible config; do not silently promote scene approvals."""
    result=copy.deepcopy(config)
    for item in report['shots']:
        if item.get('status')!='ACCEPTED' or not item.get('accepted') or not item.get('rights_verified'):
            continue
        uid=item['id']
        if uid not in result['assets']: raise ValueError('Unknown renderer asset')
        result['assets'][uid].update(path=item['path'],sha256=item['sha256'],accepted=True,
            rights_verified=True,license='reviewed model and references; see provenance',
            provenance={'engine':item.get('backend','ComfyUI'),'spec_key':item['key'],'model':item['model'],
                        'prompt_id':item['prompt_id'],'seed':item['seed']})
    return result


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('manifest');p.add_argument('--root',default='.')
    p.add_argument('--out',default='private-media/comfy-images')
    p.add_argument('--endpoint');p.add_argument('--generate',action='store_true')
    p.add_argument('--backend',choices=['comfyui','hf-zero','modal'])
    p.add_argument('--shot', help='Restrict this invocation to one manifest shot')
    p.add_argument('--renderer-config');p.add_argument('--renderer-out')
    a=p.parse_args();root=Path(a.root).resolve()
    manifest=json.loads(Path(a.manifest).read_text())
    if a.backend:
        manifest['backend']=({'type':'comfyui'} if a.backend=='comfyui' else manifest['available_backends'][a.backend])
    if a.shot:
        manifest['shots']=[s for s in manifest['shots'] if s['id']==a.shot]
        if not manifest['shots']: p.error('Shot not found')
    client=None
    if manifest.get('backend',{}).get('type')=='hf-zero':
        if a.endpoint: p.error('Hosted endpoint is pinned by manifest; --endpoint not allowed')
        from tools.klein_space_backend import KleinSpaceClient
        client=KleinSpaceClient(manifest['backend'])
    elif manifest.get('backend',{}).get('type')=='modal':
        if a.endpoint: p.error('Modal worker is selected by app name, not --endpoint')
        from tools.modal_image_backend import ModalKleinClient
        client=ModalKleinClient(manifest['backend'])
    elif a.endpoint: client=ComfyClient(a.endpoint)
    report=run(manifest,root,under(root,a.out),client,a.generate)
    if a.renderer_config:
        if not a.renderer_out: p.error('--renderer-out required')
        atomic(under(root,a.renderer_out),attach(json.loads(Path(a.renderer_config).read_text()),report))
    print(json.dumps({'shots':[{'id':r['id'],'status':r['status'],'missing':r['missing']} for r in report['shots']],
                      'submissions':report['submissions'],'accepted_cache_hits':report['accepted_cache_hits']}))

if __name__=='__main__':
    try: main()
    except (ValueError, TimeoutError, OSError) as error:
        # Request errors can contain URLs/headers: emit only safe fixed codes/types.
        import sys
        code=str(error) if type(error).__name__=='ProviderBlocked' else type(error).__name__
        print(json.dumps({'status':'BLOCKED','code':code,'next':'inspect dry-run report and saved state; do not blindly resubmit'}))
        sys.exit(2)
