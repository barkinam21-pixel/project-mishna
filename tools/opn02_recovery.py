"""Recover the recorded OPN02 bundle without executing bundled code or overwriting assets."""
import argparse
import hashlib
import io
import json
from pathlib import Path
import zipfile
from PIL import Image
from tools.comfy_scene_images import under, sha, atomic

PREFIX='private-media/opn02-20261111/'
TARGET='private-media/studio/recovered-opn02-20261111'


def recover(root,archive):
    root=Path(root).resolve();archive=Path(archive)
    evidence=json.loads((root/'docs/evidence/opn02-cloudflare-layout-2026-11-11.json').read_text())
    if sha(archive)!=evidence['private_bundle_sha256']:raise ValueError('RECOVERY_BUNDLE_HASH_MISMATCH')
    manifest=json.loads((root/'episodes/berakhot-01-01/comfy-opening-images.json').read_text())
    shot=next(s for s in manifest['shots'] if s['id']=='OPN02')
    crops=shot['director']['reference_preparation']['crops']
    expected={'OPN02_Cloudflare_20261111.png':evidence['png_sha256'],
              'OPN02_Cloudflare_20261111.jpg':evidence['native_sha256'],
              'layout.png':evidence['layout_sha256'],
              'elder.png':crops[0]['sha256'],'younger.png':crops[1]['sha256']}
    with zipfile.ZipFile(archive) as z:
        info=z.infolist()
        if len(info)!=len({i.filename for i in info}) or any(i.file_size>16*1024*1024 for i in info):raise ValueError('UNSAFE_RECOVERY_ARCHIVE')
        if z.testzip() is not None:raise ValueError('RECOVERY_CRC_FAILED')
        spec=json.loads(z.read(PREFIX+'spec.json'))
        if spec['seed']!=evidence['seed'] or spec['size']!=evidence['dimensions']:raise ValueError('RECOVERY_SPEC_MISMATCH')
        if {r['sha256'] for r in spec['references']}!={expected[n] for n in ('layout.png','elder.png','younger.png')}:raise ValueError('RECOVERY_REFERENCE_RELATION_MISMATCH')
        prepared=[];sizes={}
        for name,digest in expected.items():
            raw=z.read(PREFIX+name)
            if hashlib.sha256(raw).hexdigest()!=digest:raise ValueError('RECOVERY_ASSET_HASH_MISMATCH')
            with Image.open(io.BytesIO(raw)) as im:
                im.load();sizes[name]=list(im.size)
                if name.startswith('OPN02_') and sizes[name]!=evidence['dimensions']:raise ValueError('RECOVERY_SIZE_MISMATCH')
            target=under(root,TARGET+'/'+name)
            # Resolve/validate all destinations before creating any output.
            if target.exists() and sha(target)!=digest:raise ValueError('RECOVERY_WOULD_OVERWRITE')
            prepared.append((target,raw))
        with Image.open(io.BytesIO(z.read(PREFIX+'OPN02_Cloudflare_20261111.png'))) as png, Image.open(io.BytesIO(z.read(PREFIX+'OPN02_Cloudflare_20261111.jpg'))) as native:
            if png.mode!=native.mode or png.size!=native.size or png.tobytes()!=native.tobytes():raise ValueError('RECOVERY_PIXEL_EQUALITY_FAILED')
    receipt={'status':'RECOVERED_EXISTING_UNAPPROVED_ASSETS','bundle_sha256':evidence['private_bundle_sha256'],
             'files':{n:{'path':TARGET+'/'+n,'sha256':d,'dimensions':sizes[n]} for n,d in expected.items()},
             'seed':spec['seed'],'generation_requests':0,'accepted':False,'remote_writes':0,
             'bundled_code_executed':False,'old_authorization_reused':False}
    path=under(root,TARGET+'/recovery.json')
    if path.exists():
        if json.loads(path.read_text())!=receipt:raise ValueError('RECOVERY_RECEIPT_CONFLICT')
    for target,raw in prepared:
        target.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
        if not target.exists():
            with target.open('xb') as out:out.write(raw)
            target.chmod(0o600)
    if not path.exists():atomic(path,receipt)
    return receipt


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('archive');p.add_argument('--root',default='.')
    a=p.parse_args();print(json.dumps(recover(a.root,a.archive),indent=2))


if __name__=='__main__':main()
