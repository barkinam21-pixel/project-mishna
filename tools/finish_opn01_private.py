#!/usr/bin/env python3
"""One-step PRIVATE OPN01 artifact -> verified phone MP4 + ZIP. No paid calls.

This consumes an already-encrypted one-image fal.ai Actions artifact and existing
opening blockout. It MUST NOT turn an unreviewed frame into a public asset.
Default mode is a no-decrypt dry check. --finish performs assembly. Real inputs
are encrypted out of GitHub; decrypted PNG exists in a temporary private dir.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import re
import tempfile
import zipfile

from tools import seal_private_media
from tools import replace_opn01_preview
from tools import fal_private_opening_opn01
from tools import visual_gate_opn01

MAGIC = seal_private_media.MAGIC
ALLOWED_IMAGE = 'OPN01_UNREVIEWED_PRIVATE.png'
ALLOWED_FILES = {'attempt.json', 'success.json', ALLOWED_IMAGE}

class UnsafePipeline(ValueError):
    pass


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as f:
        for b in iter(lambda: f.read(1024 * 1024), b''):
            h.update(b)
    return h.hexdigest()


def inspect_encrypted(path: Path) -> dict:
    if not path.is_file() or path.stat().st_size < 512 or path.stat().st_size > 150*1024*1024:
        raise UnsafePipeline('Missing, too small or excessive encrypted artifact')
    with path.open('rb') as f:
        if f.read(len(MAGIC)) != MAGIC:
            raise UnsafePipeline('Not a Mishnah encrypted production artifact')
    return {'encrypted_artifact_sha256': sha(path), 'encrypted_bytes': path.stat().st_size,
            'protected_media_not_published': True, 'charged_calls_in_this_pipeline': 0}


def verify_receipt(private_dir: Path) -> tuple[Path, dict]:
    files = {p.name for p in private_dir.iterdir()}
    if files != ALLOWED_FILES or any(not p.is_file() or p.is_symlink() for p in private_dir.iterdir()):
        raise UnsafePipeline('Encrypted payload has missing/unexpected files')
    try:
        attempt = json.loads((private_dir/'attempt.json').read_text(encoding='utf-8'))
        success = json.loads((private_dir/'success.json').read_text(encoding='utf-8'))
    except (ValueError, OSError) as e:
        raise UnsafePipeline('Unparseable fal.ai receipt') from e
    if attempt.get('status') != 'SUBMITTED_OR_UNKNOWN' or success.get('status') != 'ONE_PRIVATE_UNREVIEWED_IMAGE':
        raise UnsafePipeline('No successful exact one-image generation receipt')
    if attempt.get('attempted_provider_requests') != 1 or success.get('attempted_provider_requests') != 1:
        raise UnsafePipeline('Refuse attempts other than exactly one')
    if attempt.get('shot') != 'OPN01' or success.get('shot') != 'OPN01':
        raise UnsafePipeline('Wrong scene target')
    if attempt.get('prompt_sha256') != success.get('prompt_sha256'):
        raise UnsafePipeline('Prompt hash changed across request')
    if success.get('accepted_as_movie_asset') is not False or success.get('human_visual_approval') is not False:
        raise UnsafePipeline('No automatic claims of visual approval')
    if success.get('private_output_only') is not True or success.get('public_release_allowed') is not False:
        raise UnsafePipeline('Private-only policy mismatch')
    if not re.fullmatch('[0-9a-f]{64}', str(success.get('image_sha256', ''))):
        raise UnsafePipeline('Image checksum missing')
    image = private_dir/ALLOWED_IMAGE
    if sha(image) != success['image_sha256'] or image.stat().st_size != success.get('image_bytes'):
        raise UnsafePipeline('Image differs from the signed receipt')
    return image, success


def finish(encrypted: Path, key: Path, manifest: Path, blockout: Path,
           output_prefix: Path, *, do_finish: bool = False, visual_review: Path | None = None) -> dict:
    info = inspect_encrypted(encrypted)
    if not key.is_file():
        raise UnsafePipeline('Private key must be locally accessible; never put it in GitHub')
    if not manifest.is_file() or not blockout.is_file():
        raise UnsafePipeline('Mishnah scene pack or verified blockout is missing')
    if not re.fullmatch(r'[a-zA-Z0-9_]+', output_prefix.name):
        raise UnsafePipeline('Phone delivery filename must be simple ASCII')
    if str(output_prefix.parent.resolve()) != '/mnt/data':
        raise UnsafePipeline('Delivery must be a short-root /mnt/data MP4, not a public GitHub repo')
    mp4 = output_prefix.with_suffix('.mp4')
    bundle = output_prefix.with_name(output_prefix.name+'_backup').with_suffix('.zip')
    if mp4.exists() or bundle.exists():
        raise UnsafePipeline('Refusing to overwrite delivered media')
    if not do_finish:
        return {**info, 'status':'DRY_CHECK_ONLY_NO_DECRYPT_NO_PAID_CALLS', 'expected_scene':'OPN01',
                'target_mp4': str(mp4), 'will_create_zip': True, 'visual_review_required': True,
                'voice_actors_present': False, 'movie_finished': False}
    if visual_review is None:
        raise UnsafePipeline('Private-preview render blocked until separate human visual review passes')
    with tempfile.TemporaryDirectory(prefix='mishnah_opn01_decrypt_',dir='/mnt/data') as d:
        folder = Path(d)/'private'; seal_private_media.unseal(encrypted,key,folder)
        image, receipt = verify_receipt(folder)
        visual_gate_opn01.verify_visual_gate(visual_review, receipt['image_sha256'])
        # Prevent a valid encrypted artifact for an unrelated prompt or scene.
        manifest_data = json.loads(manifest.read_text(encoding='utf-8'))
        intended = fal_private_opening_opn01.prepare(manifest_data)
        if (receipt.get('prompt_sha256') != intended['prompt_sha256']
                or receipt.get('model') != intended['model']
                or receipt.get('shot') != intended['shot']):
            raise UnsafePipeline('Cipher content does not match the locked OPN01 production prompt')
        # Prevent pretending that a mock artifact or photo crop is finished art.
        report = replace_opn01_preview.render(image,receipt['image_sha256'],blockout,manifest,mp4,dry_run=False,visual_review=visual_review)
        if report.get('status') != 'PRIVATE_DRAFT_1_OF_7_ILLUSTRATIONS_ATTACHED':
            raise UnsafePipeline('Renderer did not report provisional scene state')
    with zipfile.ZipFile(bundle,mode='x',compression=zipfile.ZIP_STORED) as z:
        z.write(mp4,arcname=mp4.name)
    with zipfile.ZipFile(bundle) as z:
        if z.namelist()!=[mp4.name] or z.testzip() is not None:
            raise UnsafePipeline('Delivery ZIP verification failed')
    return {**info, 'status':'PRIVATE_UNREVIEWED_OPN01_IN_45S_PREVIS',
            'shot':'OPN01', 'illustrations_approved':0, 'illustrations_in_movie_preview':1,
            'illustrations_still_missing':6, 'voice_actors_present': False,
            'movie_finished':False, 'public_release_allowed':False,
            'mp4':str(mp4), 'mp4_bytes':mp4.stat().st_size,'mp4_sha256':sha(mp4),
            'zip':str(bundle), 'zip_bytes':bundle.stat().st_size,'zip_sha256':sha(bundle),
            'new_paid_requests':0, 'actual_provider_charge_this_generation':'unknown - consult fal.ai account'}


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--encrypted',type=Path,required=True)
    p.add_argument('--private-key',type=Path,required=True)
    p.add_argument('--manifest',type=Path,default=Path('episodes/berakhot-01-01/opening-45s-director-pack-v1.json'))
    p.add_argument('--blockout',type=Path,required=True)
    p.add_argument('--output-prefix',type=Path,default=Path('/mnt/data/mishnah_opn01'))
    p.add_argument('--finish',action='store_true')
    p.add_argument('--visual-review-json',type=Path,default=None,help='Private human visual-acceptance JSON; required for --finish')
    a=p.parse_args(argv)
    try:
        result=finish(a.encrypted,a.private_key,a.manifest,a.blockout,a.output_prefix,do_finish=a.finish,visual_review=a.visual_review_json)
        print(json.dumps(result,ensure_ascii=False,indent=2))
        return 0
    except (ValueError,OSError,RuntimeError) as e:
        print(json.dumps({'status':'BLOCKED','type':type(e).__name__,'reason':str(e)},ensure_ascii=False))
        return 2

if __name__=='__main__':raise SystemExit(main())