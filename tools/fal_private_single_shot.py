"""At most ONE paid private fal.ai SH01 style candidate, NO retries.

DRY RUN by default. This script writes media to local PRIVATE working directory
only; the GitHub Action MUST encrypt it before uploading artifacts.
Requires separate manual `confirm_paid=YES` per run; a credit balance is NOT consent.
The local reservation is NOT a provider-side hard billing cap.
"""
from __future__ import annotations
import argparse, hashlib, json, os, re, sys, time
from pathlib import Path
from urllib import request as urllib_request
from urllib.parse import urlsplit
from .fal_payload_preflight import request_for_shot, UnsafePlan

MODEL='fal-ai/flux-2-pro'
URL='https://fal.run/'+MODEL
CONSERVATIVE_RESERVATION_USD=0.15
PNG_SIGNATURE=bytes.fromhex('89504e470d0a1a0a')


def write_receipt(path:Path, receipt:dict):
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('x',encoding='utf-8') as f:
        json.dump(receipt,f,indent=2,ensure_ascii=False)
        f.write('\n')


def validate_result_url(raw):
    if not isinstance(raw,str):raise ValueError('Missing provider image URL')
    parsed=urlsplit(raw)
    host=(parsed.hostname or '').lower()
    if parsed.scheme!='https' or not host or parsed.username or parsed.password:
        raise ValueError('Unsafe provider image URL')
    if host!='storage.googleapis.com' and host!='fal.media' and not host.endswith('.fal.media'):
        raise ValueError('Output host not in the approved fal delivery list')
    return raw


def candidate(pack_path:Path,shot_id:str,output_dir:Path,authorize_paid:bool,max_budget_usd:float):
    pack=json.loads(pack_path.read_text(encoding='utf-8'))
    dry=request_for_shot(pack,shot_id)
    # Only the anonymous establishing plate is authorized as a *candidate* workflow.
    # No historical characters, speech, exact source variants or other 15 shots yet.
    if shot_id!='SH01':raise ValueError('This protected single-shot workflow supports SH01 only')
    result={'shot_id':shot_id,'provider':MODEL,'prompt_hash':dry['payload_sha256'],
            'authorization':'separate_manual_paid_gate_required','estimated_local_reservation_usd':CONSERVATIVE_RESERVATION_USD,
            'provider_hard_budget_cap':False,'private_media_only':True,'public_release_authorized':False}
    if not authorize_paid:
        return {**result,'status':'SAFE_DRY_PLAN','external_paid_requests':0}
    if os.getenv('CONFIRM_PAID','')!='YES':
        raise ValueError('Manual CONFIRM_PAID=YES is mandatory for one paid request')
    if not (0<max_budget_usd<=0.15 and CONSERVATIVE_RESERVATION_USD<=max_budget_usd):
        raise ValueError('Only a single explicitly budgeted <= 0.15 USD local reservation is allowed')
    key=os.getenv('FAL_KEY','').strip()
    if len(key)<10:raise ValueError('FAL_KEY secret missing')
    if output_dir.exists():raise ValueError('Existing run output folder: no repeat/no overwrite')
    output_dir.mkdir(parents=True)
    ledger=output_dir/'attempt.json'
    # Write only safe metadata BEFORE any network request, with no retry after uncertainty.
    write_receipt(ledger,{**result,'status':'submitted_or_unknown','requests_attempted':1,'provider_charge_usd':None})
    req=urllib_request.Request(URL,method='POST',
        headers={'Content-Type':'application/json','Authorization':'Key '+key},
        data=json.dumps(dry['payload']).encode('utf-8'))
    started=time.monotonic()
    try:
        with urllib_request.urlopen(req,timeout=240) as resp:
            body=json.load(resp)
        images=body.get('images')
        if not isinstance(images,list) or len(images)!=1:
            raise ValueError('Provider did not return exactly one image')
        image_url=validate_result_url(images[0].get('url'))
        with urllib_request.urlopen(image_url,timeout=90) as response:
            blob=response.read(20_000_001)
        if not blob.startswith(PNG_SIGNATURE) or len(blob)>20_000_000:
            raise ValueError('Invalid or oversized PNG result')
        (output_dir/'SH01_unreviewed.png').write_bytes(blob)
        # Do not log the response image URL or prompt, and do not overwrite ledger.
        write_receipt(output_dir/'receipt_final.json',{**result,
              'status':'one_unreviewed_candidate_received',
              'requests_attempted':1,
              'provider_charge_usd':None,
              'png_sha256':hashlib.sha256(blob).hexdigest(),
              'provider_seed':body.get('seed'),
              'duration_seconds':round(time.monotonic()-started,3),
              'approval':'NOT_APPROVED_HISTORICALLY_OR_VISUALLY',
              'storage':'ENCRYPT_BEFORE_ANY_GITHUB_ARTIFACT_UPLOAD'})
        return {**result,'status':'ONE_UNREVIEWED_PRIVATE_CANDIDATE','external_paid_requests':1,
                'actual_provider_charge_usd':'unknown'}
    except Exception as exc:
        # Failing after submission may still have incurred a charge. Never retry.
        write_receipt(output_dir/'failure_uncertain.json',{
              **result,'status':'FAILED_OR_CHARGE_UNCERTAIN','error_class':type(exc).__name__,
              'provider_charge_usd':None,'do_not_retry':True})
        raise


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('pack',type=Path)
    p.add_argument('--shot',default='SH01')
    p.add_argument('--out-dir',type=Path,default=Path('private-media/fal-single-sh01'))
    p.add_argument('--authorize-paid',action='store_true')
    p.add_argument('--max-budget-usd',type=float,default=0.15)
    a=p.parse_args(argv)
    try:
        result=candidate(a.pack,a.shot,a.out_dir,a.authorize_paid,a.max_budget_usd)
        print(json.dumps(result,ensure_ascii=False,indent=2))
        return 0
    except (UnsafePlan,ValueError,RuntimeError,OSError,json.JSONDecodeError) as exc:
        print({'status':'BLOCKED_OR_FAILED','reason':type(exc).__name__+': '+str(exc)},file=sys.stderr)
        return 2

if __name__=='__main__':raise SystemExit(main())