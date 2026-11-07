"""Read-only ComfyUI readiness and private reference intake; never submits generation."""
import argparse
import hashlib
import json
import shutil
import subprocess
from pathlib import Path
from PIL import Image
from tools.comfy_image_backend import ComfyClient
from tools.comfy_scene_images import atomic, under


def inspect(endpoint=None):
    report={'generation_submissions':0,'ready':False,'errors':[],
            'local_nvidia_device_count':len(list(Path('/dev').glob('nvidia[0-9]*'))),
            'local_gpu_memory':None,'remote_gpu_memory':None,
            'workspace_usage':'unknown'}
    memory=Path('/sys/fs/cgroup/memory.max')
    report['memory_limit_bytes']=memory.read_text().strip() if memory.exists() else None
    if shutil.which('nvidia-smi'):
        try:
            proc=subprocess.run(['nvidia-smi','--query-gpu=memory.total,memory.free',
                '--format=csv,noheader,nounits'],capture_output=True,text=True,timeout=10)
            if proc.returncode==0: report['local_gpu_memory']=proc.stdout.strip().splitlines()
        except (OSError,subprocess.TimeoutExpired): pass
    if not endpoint:
        report['errors'].append('NO_COMFY_ENDPOINT: no server selected; no GPU provisioned')
    else:
        try:
            client=ComfyClient(endpoint)
            stats=client.request('/system_stats')
            info=client.request('/object_info')
            devices=stats.get('devices',[])
            report['remote_gpu_memory']=[{k:d.get(k) for k in ('type','vram_total','vram_free')} for d in devices]
            if not any(d.get('type') in ('cuda','hip','xpu','mps') for d in devices):
                report['errors'].append('NO_REMOTE_ACCELERATOR')
            for name in ('UNETLoader','CLIPLoader','VAELoader','ReferenceLatent','Flux2Scheduler','SaveImage'):
                if name not in info: report['errors'].append('MISSING_NODE:'+name)
            report['ready']=not report['errors']
        except Exception as exc:
            # Do not serialize request/response bodies, headers or token-bearing errors.
            report['errors'].append('ENDPOINT_UNAVAILABLE:'+type(exc).__name__)
    report['remaining_checks']=['verified zero-cost compute','model component hashes/licences',
        'approved reference files and rights','actual GPU graph test and peak-memory measurement']
    return report


def intake(source, root, *, rights_uri=None, synthesis_rights_confirmed=False,
           expected_sha256=None, expected_size=None, role='unspecified', source_uri=None):
    """Copy original bytes; never approve a character design or alter a production manifest."""
    source=Path(source)
    with Image.open(source) as image:
        fmt=image.format;size=list(image.size);image.verify()
    if fmt not in ('PNG','JPEG','WEBP'): raise ValueError('Unsupported reference format')
    if synthesis_rights_confirmed and not rights_uri:
        raise ValueError('Rights provenance required for synthesis permission')
    raw=source.read_bytes();sha=hashlib.sha256(raw).hexdigest()
    if expected_sha256 is not None and sha != expected_sha256:
        raise ValueError('REFERENCE_HASH_MISMATCH')
    if expected_size is not None and size != list(expected_size):
        raise ValueError('REFERENCE_DIMENSIONS_MISMATCH')
    extension={'PNG':'.png','JPEG':'.jpg','WEBP':'.webp'}[fmt]
    rel='private-media/introduction/references/'+sha+extension
    dest=under(root,rel);dest.parent.mkdir(parents=True,exist_ok=True)
    if dest.exists() and hashlib.sha256(dest.read_bytes()).hexdigest()!=sha:
        raise ValueError('Private reference collision/corruption')
    if not dest.exists():
        tmp=dest.with_suffix('.tmp');tmp.write_bytes(raw);tmp.replace(dest)
    receipt={'path':rel,'sha256':sha,'dimensions':size,'original_bytes_preserved':True,
             'synthesis_rights_confirmed':synthesis_rights_confirmed,
             'rights_uri':rights_uri,'visual_identity_approved':False,
             'production_manifest_changed':False,'role':role,'source_uri':source_uri,
             'expected_sha256':expected_sha256,'expected_size':expected_size}
    # Keep an earlier rights receipt unchanged until separately reviewed.
    receipt_path=dest.with_suffix(dest.suffix+'.json')
    if not receipt_path.exists(): atomic(receipt_path,receipt)
    return json.loads(receipt_path.read_text())


def bind_reference(manifest, receipt):
    """Bind verified private bytes to a copy; never grant generated-image/release approval."""
    import copy
    result=copy.deepcopy(manifest)
    if not receipt.get('original_bytes_preserved') or not receipt.get('synthesis_rights_confirmed'):
        raise ValueError('Reference bytes and explicit synthesis rights required')
    role=receipt.get('role')
    if role=='approved_style_and_character_master':
        expected=manifest['references'][0]
        if receipt['sha256']!=expected['expected_sha256'] or receipt['dimensions']!=expected['expected_size']:
            raise ValueError('Approved original identity mismatch')
        ref={**expected,'path':receipt['path'],'sha256':receipt['sha256'],
             'synthesis_rights_confirmed':True,'access_status':'VERIFIED_ORIGINAL',
             'rights_uri':receipt['rights_uri']}
        result['references']=[ref]
        for character in result['characters'].values():character['references']=[copy.deepcopy(ref)]
    elif role=='direction_board':
        result['direction_board'].update(path=receipt['path'],sha256=receipt['sha256'],
            dimensions=receipt['dimensions'],access_status='VERIFIED_ORIGINAL',
            synthesis_rights_confirmed=True,rights_uri=receipt['rights_uri'])
    else:raise ValueError('Unknown reference role')
    return result


def intake_package(archive, root, manifest, *, rights_uri, synthesis_rights_confirmed,
                   expected_package_sha256=None):
    """Restore verified references from a private ZIP without arbitrary extraction."""
    import io
    import zipfile
    if not synthesis_rights_confirmed or not rights_uri:
        raise ValueError('Owner synthesis authorization and provenance required')
    raw=Path(archive).read_bytes()
    package_sha=hashlib.sha256(raw).hexdigest()
    if expected_package_sha256 and package_sha!=expected_package_sha256:
        raise ValueError('PACKAGE_HASH_MISMATCH')
    master_name='a_cinematic_detailed_illustration_in_the_same_rea.png'
    board_name='a_cinematic_storyboard_collage_with_four_panels_t.png'
    staged=[]
    with zipfile.ZipFile(io.BytesIO(raw)) as package:
        entries=package.infolist()
        if len(entries)!=2 or {x.filename for x in entries}!={master_name,board_name}:
            raise ValueError('Unexpected ZIP entries')
        for item in entries:
            if item.file_size>10*1024*1024 or ((item.external_attr>>16)&0o170000)==0o120000:
                raise ValueError('Unsafe ZIP entry')
            data=package.read(item);digest=hashlib.sha256(data).hexdigest()
            with Image.open(io.BytesIO(data)) as image:
                image.load();size=list(image.size)
                if image.format!='PNG':raise ValueError('Reference must be PNG')
            master=item.filename==master_name
            expected=manifest['references'][0] if master else manifest['direction_board']
            expected_hash=expected.get('expected_sha256') if master else expected.get('sha256')
            expected_size=expected.get('expected_size') if master else expected.get('dimensions')
            if expected_hash and digest!=expected_hash:raise ValueError('REFERENCE_HASH_MISMATCH')
            if expected_size and size!=expected_size:raise ValueError('REFERENCE_DIMENSIONS_MISMATCH')
            staged.append((item.filename,data,master))
    # Only write after all ZIP members, CRCs, image decodes and expected identities pass.
    receipts=[];bound=manifest
    for name,data,master in staged:
        source=under(root,'private-media/introduction/verified-inputs/'+name)
        source.parent.mkdir(parents=True,exist_ok=True);source.parent.chmod(0o700)
        source.write_bytes(data);source.chmod(0o600)
        receipt=intake(source,root,rights_uri=rights_uri,synthesis_rights_confirmed=True,
            expected_sha256=manifest['references'][0]['expected_sha256'] if master else None,
            expected_size=manifest['references'][0]['expected_size'] if master else None,
            role='approved_style_and_character_master' if master else 'direction_board',
            source_uri='owner-provided ZIP sha256:'+package_sha+' / '+name)
        under(root,receipt['path']).chmod(0o600)
        bound=bind_reference(bound,receipt);receipts.append(receipt)
    return bound,{'package_sha256':package_sha,'references':receipts,'release_authorized':False}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--endpoint');p.add_argument('--out',default='build/comfy-runtime.json')
    p.add_argument('--reference');p.add_argument('--rights-uri')
    p.add_argument('--package');p.add_argument('--expected-package-sha256')
    p.add_argument('--expected-sha256');p.add_argument('--expected-size',nargs=2,type=int)
    p.add_argument('--role',default='unspecified');p.add_argument('--source-uri')
    p.add_argument('--confirm-synthesis-rights',action='store_true')
    p.add_argument('--bind-manifest');p.add_argument('--bound-out')
    a=p.parse_args();root=Path.cwd()
    if a.package:
        if not a.bind_manifest or not a.bound_out or not a.bound_out.startswith('private-media/'):
            p.error('Package intake requires --bind-manifest and private --bound-out')
        bound,receipt=intake_package(a.package,root,json.loads(Path(a.bind_manifest).read_text()),
            rights_uri=a.rights_uri,synthesis_rights_confirmed=a.confirm_synthesis_rights,
            expected_package_sha256=a.expected_package_sha256)
        atomic(under(root,a.bound_out),bound)
        atomic(under(root,'private-media/introduction/verified-inputs/package-receipt.json'),receipt)
        print(json.dumps({'status':'VERIFIED_PRIVATE_INTAKE','package_sha256':receipt['package_sha256'],'reference_count':len(receipt['references'])}));return 0
    if a.reference:
        result=intake(a.reference,root,rights_uri=a.rights_uri,
                      synthesis_rights_confirmed=a.confirm_synthesis_rights,
                      expected_sha256=a.expected_sha256,expected_size=a.expected_size,
                      role=a.role,source_uri=a.source_uri)
        if a.bind_manifest:
            if not a.bound_out or not a.bound_out.startswith('private-media/'):
                p.error('--bound-out must be a private-media path')
            manifest=json.loads(Path(a.bind_manifest).read_text())
            atomic(under(root,a.bound_out),bind_reference(manifest,result))
        print(json.dumps(result));return 0
    result=inspect(a.endpoint);atomic(under(root,a.out),result);print(json.dumps(result))
    return 0 if result['ready'] else 2

if __name__=='__main__':raise SystemExit(main())
