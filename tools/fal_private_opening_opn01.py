#!/usr/bin/env python3
"""Generate at most one PRIVATE fal.ai OPN01 image after a fresh explicit paid gate.

Default: no network, no cost. This replaces no SH01/SH09 workflow and NEVER
implicitly spends credits. GitHub Actions MUST encrypt the result before upload.
The $0.15 budget is a conservative LOCAL reservation, NOT a provider-side limit.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
import time
from urllib import request as urllib_request
from urllib.parse import urlsplit

MODEL = 'fal-ai/flux-2-pro'
URL = 'https://fal.run/' + MODEL
LOCAL_RESERVATION_USD = 0.15
MAX_BYTES = 20_000_000
PNG_MAGIC = bytes.fromhex('89504e470d0a1a0a')

class GateBlocked(ValueError):
    pass


def prepare(manifest: dict) -> dict:
    """Build exactly one schema-correct text-to-image request with no I/O."""
    # Fail closed if the paid retake would reuse the rejected ambiguous
    # two-traveler foot prompt, or if its historic spend is erased from plan.
    from tools.validate_opening_director_pack import validate as validate_opening
    if validate_opening(manifest)["status"] != "PASS_DRY_RUN_ONLY":
        raise GateBlocked("Corrective OPN01 chronology/anatomy/source preflight failed")
    if manifest.get('episode') != 'berakhot-01-01':
        raise GateBlocked('Wrong Mishnah episode')
    if manifest.get('chronological_position') != 'first_sequence_first_shot':
        raise GateBlocked('Film chronology not locked to opening')
    if manifest.get('next_paid_shot_candidate') != 'OPN01':
        raise GateBlocked('Only chronological OPN01 is a valid next image')
    if manifest.get('sons_return_scene_is_later') is not True:
        raise GateBlocked('Sons return cannot precede the opening')
    privacy = manifest.get('privacy', {})
    for flag, expected in {
        'new_external_spend_authorized': False,
        'fal_paid_approval_granted': False,
        'generation_in_chatgpt_forbidden': True,
        'source_assets_private_only': True,
        'repository_public_text_only': True,
    }.items():
        if privacy.get(flag) is not expected:
            raise GateBlocked('Unsafe project privacy state: ' + flag)
    source = manifest.get('source_contract', {})
    if source.get('source_layer') != 'dramatization_only_until_next_sequence':
        raise GateBlocked('OPN01 must remain a symbolic dramatization')
    if source.get('approved_for_public_release') is not False:
        raise GateBlocked('Public release is not authorized')
    shots = manifest.get('shots', [])
    if not isinstance(shots, list) or len(shots) != 7:
        raise GateBlocked('Expected seven planned opening shots')
    if [s.get('id') for s in shots] != [f'OPN{i:02d}' for i in range(1, 8)]:
        raise GateBlocked('Opening shot sequence mismatch')
    shot = shots[0]
    if shot.get('asset_status') != 'not_generated' or shot.get('start_frame') != 0:
        raise GateBlocked('First shot was already generated or timeline shifted')
    if shot.get('original_illustration_required') is not True or shot.get('source_status') != 'symbolic_dramatization':
        raise GateBlocked('First shot is not a safe new illustration target')
    if shot.get('dialogue_he') != []:
        raise GateBlocked('First shot must have no historically attributed dialogue')
    if any(s.get('asset_status') != 'not_generated' for s in shots):
        raise GateBlocked('The planned-only manifest must not claim generated assets')
    prompt_body = shot.get('prompt_subject_en', '')
    if not (isinstance(prompt_body, str) and 250 < len(prompt_body) < 1900):
        raise GateBlocked('Opening visual brief absent or too long')
    # Keep this as a standalone original T2I prompt: never upload a PRIVATE
    # style candidate to the provider or put it in a public GitHub artifact.
    additional = (
        'Film artwork specification: original panoramic hand-painted cinematic '
        'illustration, 2.5D layered depth, natural weight, tactile pigment texture, '
        'muted blue-gray dawn with understated amber edge light, adult human drama, '
        'restrained epic scale, anatomically convincing sandaled feet, no extra limbs. '
        'NO legible text, no letters, no watermarks, no words, no symbols, no fake '
        'ancient inscriptions, no cartoon characters, no plastic CGI, no famous film '
        'still copying, no identifiable Sinai geography, no tablets, no religious '
        'objects. Quiet gravity, readable silhouette and spacious frame. '
        'Do not invent an accurate archaeological location. Keep camera low, '
        'people moving RIGHT to LEFT, warm key on LEFT and no lens shake.'
    )
    prompt = prompt_body + '\n\n' + additional
    if len(prompt) > 3500 or 'https://' in prompt or 'http://' in prompt:
        raise GateBlocked('External URL or oversized visual prompt rejected')
    payload = {
        'prompt': prompt,
        'image_size': 'landscape_16_9',
        'output_format': 'png',
        'enable_safety_checker': True,
        'sync_mode': False,
    }
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
    return {'model': MODEL, 'shot': 'OPN01', 'payload': payload,
            'prompt_sha256': digest, 'status': 'LOCAL_DRY_PREVIEW_ONLY',
            'external_requests': 0, 'actual_provider_charge_usd': None,
            'private_output_only': True, 'public_release_allowed': False,
            'local_reservation_usd': LOCAL_RESERVATION_USD,
            'provider_side_hard_cap': False}


def approved_result_url(raw: object) -> str:
    if not isinstance(raw, str):
        raise GateBlocked('Missing image URL')
    p = urlsplit(raw)
    host = (p.hostname or '').lower()
    if p.scheme != 'https' or p.username or p.password:
        raise GateBlocked('Insecure media delivery URL')
    if host not in ('storage.googleapis.com', 'fal.media') and not host.endswith('.fal.media'):
        raise GateBlocked('Unapproved image delivery host')
    return raw


def exclusive_json(path: Path, data: dict) -> None:
    with path.open('x', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write('\n')


def execute(manifest_file: Path, output_dir: Path, *, authorize_paid: bool = False,
            reservation_usd: float = LOCAL_RESERVATION_USD,
            provider_open=urllib_request.urlopen) -> dict:
    manifest = json.loads(manifest_file.read_text(encoding='utf-8'))
    plan = prepare(manifest)
    if not authorize_paid:
        return {key: val for key, val in plan.items() if key != 'payload'}
    if os.environ.get('CONFIRM_PAID') != 'YES':
        raise GateBlocked('Fresh explicit OPN01 consent required: CONFIRM_PAID=YES')
    if not 0 < reservation_usd <= LOCAL_RESERVATION_USD:
        raise GateBlocked('Local reserve must be at most $0.15')
    if output_dir.exists():
        raise GateBlocked('Refusing to overwrite or repeat any attempted request')
    key = os.environ.get('FAL_KEY', '').strip()
    if len(key) < 10:
        raise GateBlocked('FAL_KEY secret is missing')
    output_dir.mkdir(parents=True)
    metadata = {key: val for key, val in plan.items() if key != 'payload'}
    # This record is written BEFORE the one provider submission. Failures after
    # submission can incur a charge, so NEVER auto-retry.
    exclusive_json(output_dir / 'attempt.json', {
        **metadata, 'status': 'SUBMITTED_OR_UNKNOWN',
        'attempted_provider_requests': 1,
        'charge_may_have_occurred': True,
    })
    started = time.monotonic()
    try:
        req = urllib_request.Request(
            URL, method='POST',
            headers={'Content-Type': 'application/json',
                     'Authorization': 'Key ' + key},
            data=json.dumps(plan['payload']).encode('utf-8'),
        )
        with provider_open(req, timeout=240) as response:
            result = json.load(response)
        images = result.get('images')
        if not isinstance(images, list) or len(images) != 1:
            raise GateBlocked('Provider response has not exactly one image')
        delivery = approved_result_url(images[0].get('url'))
        with provider_open(delivery, timeout=90) as response:
            png = response.read(MAX_BYTES + 1)
        if len(png) > MAX_BYTES or not png.startswith(PNG_MAGIC):
            raise GateBlocked('Bad or oversized PNG received')
        (output_dir / 'OPN01_UNREVIEWED_PRIVATE.png').write_bytes(png)
        exclusive_json(output_dir / 'success.json', {
            **metadata, 'status': 'ONE_PRIVATE_UNREVIEWED_IMAGE',
            'attempted_provider_requests': 1,
            'image_sha256': hashlib.sha256(png).hexdigest(),
            'image_bytes': len(png),
            'provider_seed': result.get('seed'),
            'actual_provider_charge_usd': None,
            'elapsed_seconds': round(time.monotonic() - started, 2),
            'human_visual_approval': False,
            'accepted_as_movie_asset': False,
        })
        return {'status': 'ONE_PRIVATE_UNREVIEWED_IMAGE', 'shot': 'OPN01',
                'provider_requests': 1, 'actual_charge': 'unknown'}
    except Exception as exc:
        exclusive_json(output_dir / 'failure_uncertain.json', {
            **metadata, 'status': 'FAILED_OR_PROVIDER_CHARGE_UNCERTAIN',
            'error_class': type(exc).__name__, 'DO_NOT_RETRY': True,
        })
        raise


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--manifest', type=Path,
                    default=Path('episodes/berakhot-01-01/opening-45s-director-pack-v1.json'))
    ap.add_argument('--output-dir', type=Path,
                    default=Path('private-media/opn01'))
    ap.add_argument('--authorize-paid', action='store_true')
    ap.add_argument('--local-reservation-usd', type=float, default=LOCAL_RESERVATION_USD)
    args = ap.parse_args(argv)
    try:
        result = execute(args.manifest, args.output_dir, authorize_paid=args.authorize_paid,
                         reservation_usd=args.local_reservation_usd)
        print(json.dumps(result, indent=2))
        return 0
    except (ValueError, OSError, RuntimeError, json.JSONDecodeError) as exc:
        # No prompts, images or private tokens printed here.
        print(f'OPN01 blocked/failed: {type(exc).__name__}', file=sys.stderr)
        return 2

if __name__ == '__main__':
    raise SystemExit(main())