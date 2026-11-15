"""Compose EP-P07 Cloudflare-style draft conditioning from actual owner references.

Works ONLY on an already owner-private, SHA-verified plan; never imports the
Cloudflare client, makes a provider request, grants synthesis rights or modifies
legacy OPN02/03 records. This closes the old-template-only *preview* gap.
"""
from __future__ import annotations
import copy
import hashlib
import json
import re
from pathlib import Path

SHOT = 'EP-P07'
NAMES = (
    'REF01_CAST_HERO_PAINTED_MASTER.jpg',
    'REF03_TRAVEL_REAR_WIDE.jpg',
    'REF04_JOURNEY_WIDE_ORIGINAL.jpg',
)
ROLES = ('identity_style_anchor', 'rear_wide_composition', 'environment_geography')
SHA = re.compile(r'^[a-f0-9]{64}$')
PRIVATE = 'private-media/visual-reference-master-20261115/'


class NativePreviewBlocked(ValueError):
    pass


def digest(payload):
    return hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False,
                                     separators=(',', ':')).encode()).hexdigest()


def draft_conditioning(owner_plan, root):
    """Produce a *non-executable* shape for first original dawn artwork.

    Checks real private reference file bytes; the provider-shaped spec is kept
    separate from the historical provider spec/attempt journal and never
    asserts unverified rights or accepts a prior image.
    """
    if not isinstance(owner_plan, dict):
        raise NativePreviewBlocked('OWNER_SCENE_PLAN_REQUIRED')
    value = owner_plan.get('preview_sha256')
    if not isinstance(value, str) or not SHA.fullmatch(value) or value != digest({k:v for k,v in owner_plan.items() if k!='preview_sha256'}):
        raise NativePreviewBlocked('OWNER_SCENE_PLAN_HASH_CHANGED')
    master = owner_plan.get('visual_reference_master')
    if (not isinstance(master, dict) or
        master.get('status')!='PRIVATE_ARCHIVE_RESTORED_ROUTED_NOT_PRODUCTION_APPROVED' or
        master.get('routed_shots')!=15 or master.get('model_inference_requests')!=0 or
        master.get('rights_for_synthesis')!='NOT_EVALUATED' or
        owner_plan.get('provider_dispatch_authorized') is not False or
        owner_plan.get('provider_calls')!=0):
        raise NativePreviewBlocked('OWNER_SCENE_REVIEW_ONLY_GATE_CHANGED')
    jobs = owner_plan.get('jobs')
    if not isinstance(jobs, list) or len(jobs)!=15:
        raise NativePreviewBlocked('OWNER_SCENE_FIFTEEN_SHOTS_REQUIRED')
    shot = next((j for j in jobs if j.get('shot_id') == SHOT), None)
    if not isinstance(shot, dict) or shot.get('provider_dispatch_authorized') is not False:
        raise NativePreviewBlocked('OWNER_P07_NOT_CLOSED')
    if 'HOSTED_M3_AND_GENERATION_POLICY_CLOSED' not in shot.get('blockers', []):
        raise NativePreviewBlocked('OWNER_P07_GATE_MISSING')
    spec = shot.get('engine_spec_preview')
    if not isinstance(spec, dict) or spec.get('size')!=[1024,576]:
        raise NativePreviewBlocked('OWNER_P07_SPEC_CHANGED')
    director = spec.get('director') or {}
    if (director.get('shot_id')!=SHOT or director.get('time_of_day')!='dawn' or
        director.get('review_status')!='DRAFT_REQUIRES_REVIEW' or
        director.get('characters_present')!=['elder','younger'] or
        director.get('axis')!='south side of travel line' or
        director.get('positions')!={'elder':'screen-left','younger':'screen-right'}):
        raise NativePreviewBlocked('OWNER_P07_DAWN_CAST_AXIS_CHANGED')
    candidates = shot.get('owner_private_reference_candidates')
    if (not isinstance(candidates, list) or len(candidates)!=3 or
        [a.get('filename') for a in candidates]!=list(NAMES) or
        [a.get('role') for a in candidates]!=list(ROLES)):
        raise NativePreviewBlocked('OWNER_P07_REFERENCE_ROLES_CHANGED')
    owner = Path(root).resolve()
    if not owner.is_dir():
        raise NativePreviewBlocked('OWNER_PRIVATE_ROOT_MISSING')
    new_references = []
    for item in candidates:
        name = item['filename']
        expected = item.get('sha256')
        raw_path = item.get('path')
        if (raw_path != PRIVATE + name or not isinstance(expected, str) or not SHA.fullmatch(expected) or
            item.get('synthesis_rights_confirmed') is not False or
            item.get('production_shot_accepted') is not False or
            item.get('use')!='DIRECTION_ONLY_NO_PROVIDER_CONDITIONING'):
            raise NativePreviewBlocked('OWNER_REFERENCE_PATH_RIGHTS_OR_HASH_CHANGED')
        p = owner / raw_path
        if (not p.resolve().is_relative_to(owner) or p.is_symlink() or not p.is_file() or
            hashlib.sha256(p.read_bytes()).hexdigest()!=expected or not p.read_bytes().startswith(b'\xff\xd8\xff')):
            raise NativePreviewBlocked('OWNER_REFERENCE_PRIVATE_BYTES_NOT_VERIFIED')
        new_references.append({'path':raw_path, 'sha256':expected, 'expected_sha256':expected,
                               'role':item['role'], 'synthesis_rights_confirmed':False})
    proposed = copy.deepcopy(spec)
    old_references = copy.deepcopy(spec.get('references'))
    if not isinstance(old_references, list):
        raise NativePreviewBlocked('OWNER_OLD_SPEC_REFERENCE_SHAPE_INVALID')
    proposed['references'] = new_references
    proposed['visual_direction']['owner_conditional_review_only'] = True
    # The prior seed was derived from an older asset key before owner ref selection.
    # Deterministically rekey to avoid reusing an old attempted Cloudflare request.
    new_key = shot.get('reference_aware_future_asset_key')
    if not isinstance(new_key, str) or not SHA.fullmatch(new_key):
        raise NativePreviewBlocked('OWNER_REFERENCE_CACHE_KEY_MISSING')
    proposed['seed'] = int(hashlib.sha256(('P07_DAWN_OWNER_REFS:'+new_key).encode()).hexdigest()[:16],16)
    out = {
        'status':'DRAFT_OWNER_PRIVATE_CONDITIONING_NOT_APPROVED_NOT_EXECUTABLE',
        'shot_id':SHOT,
        'scene_id':owner_plan['scene_id'],
        'future_reference_cache_key':new_key,
        'candidate_count':len(new_references),
        'candidate_reference_filenames':list(NAMES),
        'old_legacy_provider_references_preserved':old_references == spec.get('references'),
        'proposed_provider_shape':proposed,
        'rights_for_synthesis':'NOT_EVALUATED',
        'new_image_generated':False,
        'provider_dispatch_authorized':False,
        'provider_calls':0,
        'no_automatic_retry':True,
        'blockers':sorted(set(shot['blockers'] + [
            'NEW_SCOPED_OWNER_REQUEST_REQUIRED',
            'SCENE_REFERENCE_RIGHTS_AND_PARTNER_TERMS_REQUIRE_REQUEST_SCOPE',
            'HOSTED_M3_DURABLE_RESERVATION_NOT_PROVEN_LIVE',
        ])),
    }
    out['draft_sha256'] = digest(out)
    return out