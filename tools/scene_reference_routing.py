"""Offline scene-native routing of a restored OWNER-PRIVATE visual reference master.

This connects the *verified* immutable 7-still master to 15 Cloudflare scene
preparation specs as review-only direction, without sending private art to a
model. Never grants synthesis rights or promotes old sunset OPN candidates.

The caller supplies the owner-scoped ZIP already downloaded through an approved
private Drive path. No network, Drive SDK, model imports or provider dispatch.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import re
import sys
import zipfile
from pathlib import Path

from tools.scene_reference_archive import (
    REGISTRY, BUNDLE_SHA256, ReferenceArchiveError, restore_private, validate_bytes,
)

SHA = re.compile(r'^[0-9a-f]{64}$')
SHOT = re.compile(r'^EP-P(0[1-9]|1[0-5])$')
PRIVATE_SUBDIR = 'private-media/visual-reference-master-20261115'
REF = {
    'identity': 'REF01_CAST_HERO_PAINTED_MASTER.jpg',
    'moodboard': 'REF02_CINEMATIC_STORY_BEATS_BOARD.jpg',
    'rear': 'REF03_TRAVEL_REAR_WIDE.jpg',
    'environment': 'REF04_JOURNEY_WIDE_ORIGINAL.jpg',
    'conversation': 'REF05_CONVERSATION_MEDIUM_COOL.jpg',
    'expression': 'REF06_CONVERSATION_MEDIUM_PAINTED.jpg',
    'alternative': 'REF07_CONVERSATION_MEDIUM_VARIANT.jpg',
}
CANON_ROLES = {
    REF['identity']: 'identity_style_anchor',
    REF['moodboard']: 'story_direction_moodboard',
    REF['rear']: 'rear_wide_composition',
    REF['environment']: 'environment_geography',
    REF['conversation']: 'medium_exchange_alternate',
    REF['expression']: 'character_expression',
    REF['alternative']: 'medium_exchange_alternate',
}


class ReferenceRoutingError(ValueError):
    pass


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True,
                                     ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()


def _assert_hash(document, key, code):
    if (not isinstance(document, dict) or not isinstance(document.get(key), str)
        or not SHA.fullmatch(document[key])
        or document[key] != _digest({k:v for k,v in document.items() if k!=key})):
        raise ReferenceRoutingError(code)


def _select(shot_type, composition, cast):
    """Purpose-driven references; never cast everyone just because a Bible lists them."""
    if shot_type not in ('extreme_wide','wide','medium','ots','reaction','insert','close_up'):
        raise ReferenceRoutingError('VISUAL_REFERENCE_UNKNOWN_SHOT_TYPE')
    names = [REF['identity']]  # style anchor even for an empty landscape
    lower = composition.lower()
    rear = any(term in lower for term in ('rear', 'behind', 'back of', 'from behind'))
    if shot_type in ('extreme_wide','wide'):
        if rear:
            names.append(REF['rear'])
        names.append(REF['environment'])
    elif shot_type == 'ots':
        if rear:
            names.append(REF['rear'])
        names.extend((REF['conversation'], REF['expression']))
    elif shot_type in ('medium','reaction','close_up'):
        names.extend((REF['expression'], REF['conversation'], REF['alternative']))
    elif shot_type == 'insert':
        if cast:  # hands of named cast, not new faces
            names.extend((REF['expression'], REF['conversation']))
        else:
            names.append(REF['environment'])
    if not names or len(names)>4 or len(names)!=len(set(names)):
        raise ReferenceRoutingError('VISUAL_REFERENCE_SELECTION_INVALID')
    return names


def _read_owner_archive(bundle_path, project_root, restore):
    root=Path(project_root).resolve()
    bundle=Path(bundle_path).resolve()
    if root == bundle or not bundle.is_file():
        raise ReferenceRoutingError('VISUAL_REFERENCE_BUNDLE_MISSING')
    blob=bundle.read_bytes()
    try:
        verified=validate_bytes(blob)  # real pinned bundle SHA + every member SHA
    except (ReferenceArchiveError, OSError) as exc:
        raise ReferenceRoutingError('VISUAL_REFERENCE_ARCHIVE_UNVERIFIED') from exc
    if verified['bundle_sha256'] != BUNDLE_SHA256 or verified['production_shots_accepted'] != 0:
        raise ReferenceRoutingError('VISUAL_REFERENCE_ARCHIVE_SCOPE_CHANGED')
    if restore:
        try:
            restore_private(bundle,root)
        except (ReferenceArchiveError,OSError) as exc:
            raise ReferenceRoutingError('VISUAL_REFERENCE_PRIVATE_RESTORE_FAILED') from exc
    private=root/PRIVATE_SUBDIR
    if (not private.is_dir() or private.is_symlink()
        or (root/'private-media').is_symlink()):
        raise ReferenceRoutingError('VISUAL_REFERENCE_NOT_RESTORED_PRIVATE')
    with zipfile.ZipFile(bundle) as z:
        manifest=json.loads(z.read(REGISTRY).decode('utf-8'))
        required={a['filename'] for a in manifest['assets']}|{REGISTRY,'READ_ME_FIRST_HE.md'}
        if {p.name for p in private.iterdir()} != required:
            raise ReferenceRoutingError('VISUAL_REFERENCE_PRIVATE_FILE_SET_CHANGED')
        if (private/REGISTRY).is_symlink() or (private/REGISTRY).read_bytes()!=z.read(REGISTRY):
            raise ReferenceRoutingError('VISUAL_REFERENCE_PRIVATE_MANIFEST_CHANGED')
        for name in required:
            p=private/name
            if p.is_symlink() or not p.is_file() or p.read_bytes()!=z.read(name):
                raise ReferenceRoutingError('VISUAL_REFERENCE_PRIVATE_BYTES_CHANGED')
    assets={a['filename']:a for a in manifest['assets']}
    if (len(assets)!=11 or set(CANON_ROLES)-set(assets)
        or any(assets[n]['role']!=role for n,role in CANON_ROLES.items())):
        raise ReferenceRoutingError('VISUAL_REFERENCE_CANON_ROLE_CHANGED')
    for name in CANON_ROLES:
        review=assets[name]['review']
        if (review.get('reference_use')!='allowed_as_direction_from_user_upload'
            or review.get('production_shot_accepted') is not False
            or review.get('owner_artistic_direction_approved_for_generation') is not False
            or review.get('rights_for_new_generated_media')!='not_evaluated'):
            raise ReferenceRoutingError('VISUAL_REFERENCE_RIGHTS_NOT_UNCHANGED')
    return assets,manifest


def build_reference_plan(packet, previews, bundle_path, project_root, *, restore=False):
    """Return offline augmented *previews*, not a live provider submission.

    Exact owner media is verified before routing. All 15 shots retain their
    independent original-image slot, lighting, cast and legacy source blockers.
    Owner refs remain annotations only: spec['references'] (provider payload) is
    unchanged, and none of the archived images becomes an accepted cache hit.
    """
    _assert_hash(packet,'packet_sha256','VISUAL_REFERENCE_PACKET_CHANGED')
    _assert_hash(previews,'preview_sha256','VISUAL_REFERENCE_CLOUD_PREVIEW_CHANGED')
    if (packet.get('status')!='SCENE_PACKET_DRAFT_NOT_AUTHORIZED'
        or packet.get('generation_gate_closed') is not True
        or packet.get('provider_dispatch_authorized') is not False
        or packet.get('inference_requests')!=0
        or previews.get('status')!='OFFLINE_PROVIDER_SHAPE_PREVIEW_NO_DISPATCH'
        or previews.get('provider_dispatch_authorized') is not False
        or previews.get('provider_calls')!=0
        or previews.get('native_legacy_engine_compatible') is not False
        or previews.get('scene_packet_sha256')!=packet['packet_sha256']
        or previews.get('scene_id')!=packet.get('scene_id')):
        raise ReferenceRoutingError('VISUAL_REFERENCE_UNSAFE_PREVIEW_SCOPE')
    jobs=packet.get('jobs');pieces=previews.get('jobs')
    if (not isinstance(jobs,list) or not isinstance(pieces,list)
        or len(jobs)!=15 or len(pieces)!=15):
        raise ReferenceRoutingError('VISUAL_REFERENCE_EXPECTED_15_SHOTS')
    assets,registry=_read_owner_archive(bundle_path,project_root,restore)
    out=copy.deepcopy(previews)
    roles_by_shot=[]
    for idx,(job,planned) in enumerate(zip(jobs,out['jobs'])):
        sid=f'EP-P{idx+1:02d}'
        if (job.get('shot_id')!=sid or planned.get('shot_id')!=sid
            or job.get('asset_key')!=planned.get('asset_key')
            or not SHOT.fullmatch(sid)
            or job.get('ready_for_model_submission') is not False
            or job.get('image_status') not in ('NEW_ORIGINAL_IMAGE_REQUIRED',
                  'EXISTING_CANDIDATE_REVIEW_ONLY','VERIFIED_ACCEPTED_CACHE','HASH_MISMATCH_BLOCKED')
            or planned.get('provider_dispatch_authorized') is not False
            or planned.get('provider_calls')!=0
            or 'HOSTED_M3_AND_GENERATION_POLICY_CLOSED' not in planned.get('blockers',[])):
            raise ReferenceRoutingError('VISUAL_REFERENCE_SHOT_OR_GATE_CHANGED:'+sid)
        visual=job.get('visual_spec') or {}
        native=visual.get('scene_native_direction') or {}
        spec=planned.get('engine_spec_preview') or {}
        director=spec.get('director') or {}
        style=spec.get('visual_direction') or {}
        cast=visual.get('cast_visible')
        if (not isinstance(cast,list) or cast!=native.get('cast_visible')
            or cast!=director.get('characters_present')
            or director.get('shot_id')!=sid
            or native.get('scene_shot_id')!=sid
            or native.get('review_status')!='DRAFT_REQUIRES_REVIEW'
            or director.get('review_status')!='DRAFT_REQUIRES_REVIEW'
            or native.get('time_of_day')!='dawn' or director.get('time_of_day')!='dawn'
            or native.get('positions')!=director.get('positions')
            or native.get('axis')!=director.get('axis')
            or native.get('screen_direction')!=director.get('screen_direction')
            or native.get('sun_direction')!=director.get('sun_direction')
            or native.get('composition')!=director.get('composition')
            or not isinstance(native.get('shot_type'),str)
            or style.get('shot_id')!=sid):
            raise ReferenceRoutingError('VISUAL_REFERENCE_DAWN_CAST_AXIS_CONFLICT:'+sid)
        selected=_select(native['shot_type'],native['composition'],cast)
        ref_data=[]
        for name in selected:
            a=assets[name]
            ref_data.append({
                'filename':name,'role':a['role'],'sha256':a['sha256'],
                'path':PRIVATE_SUBDIR+'/'+name,
                'use':'DIRECTION_ONLY_NO_PROVIDER_CONDITIONING',
                'synthesis_rights_confirmed':False,
                'production_shot_accepted':False,
            })
        # New, explicit ref-aware key for *future* generation/cache integration.
        # Existing packet asset_key remains immutable; no accepted cache promotion.
        reference_key=_digest({'scene_id':packet['scene_id'],'shot_id':sid,
                               'asset_key':job['asset_key'],
                               'reference_sha256':[a['sha256'] for a in ref_data],
                               'dawn':True,'cast_visible':cast,
                               'axis':native['axis'],'positions':native['positions']})
        review={
            'reference_key':reference_key,
            'reference_filenames':[a['filename'] for a in ref_data],
            'reference_roles':[a['role'] for a in ref_data],
            'reference_count':len(ref_data),
            'cast_visible':list(cast),
            'scene_time_of_day':'dawn',
            'moodboard_excluded_from_model_refs':True,
            'historic_opn_candidates_excluded':True,
            'owner_private_reference_bytes_verified':True,
            'owner_reference_use_only':'direction',
            'rights_for_synthesis':'NOT_EVALUATED',
            'provider_conditioning_allowed':False,
        }
        # Avoid changing actual provider references or character-specific rights:
        # passing refs to Cloudflare is still blocked by rights+M3 review.
        spec['visual_direction']['owner_private_reference_plan']=review
        planned['owner_private_reference_candidates']=ref_data
        planned['reference_aware_future_asset_key']=reference_key
        planned['blockers']=sorted(set(planned['blockers']+[
            'OWNER_REFERENCE_SYNTHESIS_RIGHTS_UNVERIFIED',
            'REFERENCE_SELECTION_REVIEW_ONLY_NO_PROVIDER_CONDITIONING']))
        roles_by_shot.append({'shot_id':sid,'references':review['reference_filenames'],
                              'cast_visible':cast,'reference_key':reference_key})
    out['visual_reference_master']={
        'registry_id':registry['registry_id'],'bundle_sha256':BUNDLE_SHA256,
        'status':'PRIVATE_ARCHIVE_RESTORED_ROUTED_NOT_PRODUCTION_APPROVED',
        'routed_shots':len(roles_by_shot),'independent_shot_images_generated':0,
        'model_inference_requests':0,'remote_writes':0,
        'rights_for_synthesis':'NOT_EVALUATED',
        'reference_routing_deterministic':True,
    }
    out['preview_sha256']=_digest({k:v for k,v in out.items() if k!='preview_sha256'})
    return out


def summarize(plan):
    return {
        'status':plan['visual_reference_master']['status'],
        'scene_id':plan['scene_id'], 'routed_shots':plan['visual_reference_master']['routed_shots'],
        'reference_counts':[j['engine_spec_preview']['visual_direction']['owner_private_reference_plan']['reference_count']
                            for j in plan['jobs']],
        'reference_names_by_shot':{j['shot_id']:[r['filename'] for r in j['owner_private_reference_candidates']]
                                   for j in plan['jobs']},
        'provider_dispatch_authorized':False,'provider_calls':0,
        'external_cost_usd':0,'new_images_generated':0,'workspace_usage':'unknown',
        'preview_sha256':plan['preview_sha256'],
    }


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bundle',required=True)
    parser.add_argument('--legacy-template',required=True)
    parser.add_argument('--root',default='.')
    parser.add_argument('--restore-private',action='store_true')
    args=parser.parse_args(argv)
    try:
        from tools.scene_factory import load, within
        from tools.scene_production_packet import build_packet
        from tools.scene_cloudflare_spec_adapter import compile_previews
        root=Path(args.root).resolve()
        scene=load(root/'episodes/berakhot-01-01/scene-prologue-v02.json')
        bible=load(within(root,scene['bible']['path']))
        packet=build_packet(scene,bible,root)
        previews=compile_previews(packet,load(Path(args.legacy_template)),root)
        out=build_reference_plan(packet,previews,Path(args.bundle),root,restore=args.restore_private)
        print(json.dumps(summarize(out),ensure_ascii=False,sort_keys=True))
        return 0
    except (ReferenceRoutingError,OSError,ValueError,TypeError,KeyError) as exc:
        print(json.dumps({'status':'BLOCKED','reason':str(exc) if isinstance(exc,ReferenceRoutingError)
                          else type(exc).__name__,
                          'provider_calls':0,'provider_dispatch_authorized':False},sort_keys=True))
        return 2


if __name__=='__main__':sys.exit(main())