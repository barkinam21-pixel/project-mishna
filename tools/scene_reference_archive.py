"""Offline-only, private, exact-hash restore of Bar's archived scene references.

No Drive client, network, Cloudflare/model submit, creative acceptance or media upload.
The repository records the BUNDLE fingerprint only; the actual bytes and Drive
file IDs stay in the owner's private file library / private Drive locator.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import tempfile
import zipfile

BUNDLE_FILENAME = 'MISHNAH_REFERENCE_MASTER_BUNDLE_V1.zip'
BUNDLE_SHA256 = '53acf04ebdd0960d8adc5f0f2fbd75229857ea24eee6eab16bfa8c29d762f6ce'
REGISTRY = 'REFERENCE_MASTER_PRIVATE.json'
README = 'READ_ME_FIRST_HE.md'
EXPECTED_MEDIA = 11  # 7 distinct still refs, 2 existing videos, 2 historic rejected candidates
EXPECTED_USER_PHOTOS = 7
EXPECTED_USER_VIDEOS = 2
EXPECTED_HISTORIC_CANDIDATES = 2
SAFE_NAME = re.compile(r'^[A-Z][A-Za-z0-9_-]*\.(jpg|png|mp4)$')


class ReferenceArchiveError(ValueError):
    pass


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _is_valid_type(name: str, data: bytes) -> bool:
    if name.endswith('.jpg'):
        return data.startswith(b'\xff\xd8\xff') and data[-2:] == b'\xff\xd9'
    if name.endswith('.png'):
        return data.startswith(b'\x89PNG\r\n\x1a\n') and data.endswith(b'IEND\xaeB`\x82')
    if name.endswith('.mp4'):
        return len(data) > 32 and data[4:8] == b'ftyp'
    return False


def validate_bytes(blob: bytes, *, expected_bundle_sha256: str = BUNDLE_SHA256):
    if not re.fullmatch(r'[a-f0-9]{64}', expected_bundle_sha256):
        raise ReferenceArchiveError('REF_PACK_EXPECTED_HASH_INVALID')
    if sha256(blob) != expected_bundle_sha256:
        raise ReferenceArchiveError('REF_PACK_BUNDLE_HASH_MISMATCH')
    try:
        from io import BytesIO
        with zipfile.ZipFile(BytesIO(blob)) as z:
            members = z.infolist()
            names = [i.filename for i in members]
            if (len(names) != len(set(names)) or
                    any(i.is_dir() or '/' in i.filename or '\\' in i.filename or
                        i.filename.startswith('.') or i.file_size > 35_000_000
                        for i in members)):
                raise ReferenceArchiveError('REF_PACK_UNSAFE_ZIP_PATH_OR_DUPLICATE')
            if len(members) != EXPECTED_MEDIA + 2 or not {REGISTRY, README}.issubset(set(names)):
                raise ReferenceArchiveError('REF_PACK_UNEXPECTED_MEMBERS')
            if sum(i.file_size for i in members) > 85_000_000:
                raise ReferenceArchiveError('REF_PACK_TOO_LARGE')
            master = json.loads(z.read(REGISTRY).decode('utf-8'))
            assets = master.get('assets', [])
            if (master.get('schema_version') != 1 or
                    master.get('registry_id') != 'MIS-ART-VISUAL-REFERENCE-20261115-V1' or
                    master.get('generation_gate_closed') is not True or
                    master.get('no_paid_api_allowed') is not True or
                    master.get('accepted_production_shots') != 0 or
                    master.get('authoritative_media_count') != EXPECTED_MEDIA or
                    master.get('user_reference_unique_photos') != EXPECTED_USER_PHOTOS or
                    master.get('user_reference_videos') != EXPECTED_USER_VIDEOS or
                    master.get('historic_cloudflare_candidate_images') != EXPECTED_HISTORIC_CANDIDATES or
                    not isinstance(assets, list) or len(assets) != EXPECTED_MEDIA):
                raise ReferenceArchiveError('REF_PACK_REGISTRY_INVALID')
            actual_names = {REGISTRY, README}
            accepted = 0
            roles = {}
            for item in assets:
                if not isinstance(item, dict):
                    raise ReferenceArchiveError('REF_PACK_ASSET_ENTRY_INVALID')
                name, expected_sha = item.get('filename'), item.get('sha256')
                review = item.get('review', {})
                if (not isinstance(name, str) or SAFE_NAME.fullmatch(name) is None or
                        name in actual_names or name not in names or
                        not isinstance(expected_sha, str) or
                        not re.fullmatch(r'[a-f0-9]{64}', expected_sha) or
                        not isinstance(review, dict) or
                        review.get('production_shot_accepted') is not False or
                        review.get('owner_artistic_direction_approved_for_generation') is not False):
                    raise ReferenceArchiveError('REF_PACK_ASSET_SCOPE_OR_NAME_INVALID')
                data = z.read(name)
                if sha256(data) != expected_sha or not _is_valid_type(name, data):
                    raise ReferenceArchiveError('REF_PACK_ASSET_BYTES_MISMATCH')
                if len(data) != item.get('bytes'):
                    raise ReferenceArchiveError('REF_PACK_ASSET_SIZE_MISMATCH')
                media_type = ('video/mp4' if name.endswith('.mp4') else
                              'image/jpeg' if name.endswith('.jpg') else 'image/png')
                if item.get('mime_type') != media_type:
                    raise ReferenceArchiveError('REF_PACK_ASSET_MIME_MISMATCH')
                role = item.get('role')
                if not isinstance(role, str):
                    raise ReferenceArchiveError('REF_PACK_ASSET_ROLE_INVALID')
                roles[role] = roles.get(role, 0) + 1
                actual_names.add(name)
                accepted += int(review['production_shot_accepted'])
            if actual_names != set(names) or accepted:
                raise ReferenceArchiveError('REF_PACK_MEMBER_SET_OR_APPROVAL_INVALID')
            if (roles.get('historic_cloudflare_image') != 2 or
                    roles.get('motion_diagnostic_only') != 1 or
                    roles.get('motion_direction_only') != 1):
                raise ReferenceArchiveError('REF_PACK_REQUIRED_CLASSES_MISSING')
            if (master.get('visual_canon', {}).get('current_scene_light', '').lower().find('dawn') < 0 or
                    len(master.get('duplicate_aliases', [])) != 1):
                raise ReferenceArchiveError('REF_PACK_STYLE_OR_DUPLICATES_INVALID')
            return {'status':'PRIVATE_VISUAL_REFERENCES_VERIFIED_NOT_PRODUCTION_APPROVAL',
                    'bundle_sha256':sha256(blob),'registry_id':master['registry_id'],
                    'reference_photos':7,'reference_videos':2,
                    'historic_unapproved_candidates':2,
                    'unique_media_files':len(assets),
                    'production_shots_accepted':0,'new_image_inference_requests':0,
                    'model_calls':0,'remote_writes':0,'generation_gate_closed':True}
    except (zipfile.BadZipFile, UnicodeDecodeError, json.JSONDecodeError, KeyError, TypeError, OverflowError) as e:
        raise ReferenceArchiveError('REF_PACK_MALFORMED_BUNDLE') from e


def verify(path: Path):
    return validate_bytes(Path(path).read_bytes())


def restore_private(path: Path, root: Path, relative_dest: str = 'private-media/visual-reference-master-20261115'):
    root = Path(root).resolve()
    dest = Path(relative_dest)
    if (dest.is_absolute() or '..' in dest.parts or len(dest.parts) != 2 or
            dest.parts[0] != 'private-media' or dest.parts[1].startswith('.')):
        raise ReferenceArchiveError('REF_PACK_PRIVATE_DESTINATION_REQUIRED')
    private_root = root / 'private-media'
    # Explicitly forbid symlink paths and public or already-clobbered folders.
    if private_root.is_symlink():
        raise ReferenceArchiveError('REF_PACK_SYMLINK_DESTINATION')
    private_root.mkdir(exist_ok=True)
    target = private_root / dest.parts[1]
    if target.is_symlink():
        raise ReferenceArchiveError('REF_PACK_SYMLINK_DESTINATION')
    blob = Path(path).read_bytes()
    summary = validate_bytes(blob)
    if target.exists():
        if not target.is_dir():
            raise ReferenceArchiveError('REF_PACK_EXISTING_TARGET_NOT_DIR')
        from io import BytesIO
        with zipfile.ZipFile(BytesIO(blob)) as z:
            members = z.namelist()
            if {p.name for p in target.iterdir()} != set(members):
                raise ReferenceArchiveError('REF_PACK_PARTIAL_OR_EXTRA_CACHED_FILES')
            for name in members:
                candidate = target / name
                if not candidate.is_file() or candidate.is_symlink() or sha256(candidate.read_bytes()) != sha256(z.read(name)):
                    raise ReferenceArchiveError('REF_PACK_CACHED_BYTES_CHANGED')
        return dict(summary,cache_hit=True)
    from io import BytesIO
    with tempfile.TemporaryDirectory(prefix='.visual-ref-staging-', dir=private_root) as tmp:
        stage = Path(tmp) / 'complete'
        stage.mkdir()
        with zipfile.ZipFile(BytesIO(blob)) as z:
            for name in z.namelist():
                (stage / name).write_bytes(z.read(name))
        # Atomic directory arrival: no partially restored archive is ever a cache hit.
        try:
            stage.rename(target)
        except FileExistsError as e:
            raise ReferenceArchiveError('REF_PACK_DESTINATION_RACE') from e
    return dict(summary,cache_hit=False)


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--bundle', required=True)
    p.add_argument('--restore-private', action='store_true')
    p.add_argument('--root', default='.')
    args = p.parse_args(argv)
    try:
        result = (restore_private(Path(args.bundle),Path(args.root)) if args.restore_private
                  else verify(Path(args.bundle)))
        print(json.dumps(result,ensure_ascii=False,sort_keys=True))
        return 0
    except (ReferenceArchiveError, OSError) as e:
        print(json.dumps({'status':'BLOCKED','reason':str(e) if isinstance(e, ReferenceArchiveError)
                          else type(e).__name__,'new_image_inference_requests':0,'remote_writes':0}))
        return 2


if __name__=='__main__':
    sys.exit(main())