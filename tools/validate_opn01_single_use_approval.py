#!/usr/bin/env python3
"""Fail-closed, single-use GitHub push gate for ONE paid OPN01 illustration.

The authorization JSON is NOT present in repo before an explicit new approval.
No API network or image generation. A non-approval push must never charge.
Only a new addition of a fixed path in a dedicated single-file commit qualifies.
"""
from __future__ import annotations
import argparse
from datetime import datetime,timezone,timedelta
import json
from pathlib import Path
import re
import subprocess
import sys

APPROVAL_FILE='production_authorizations/OPN01_RETAKE_01_APPROVED_ONCE.json'
MESSAGE='YES_ONE_OPN01_RETAKE_CREDIT_CHARGE'

class ApprovalDenied(ValueError):pass

def iso_time(value):
    if not isinstance(value,str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z',value):
        raise ApprovalDenied('Timestamp must be exact UTC ISO Z')
    try: return datetime.strptime(value,'%Y-%m-%dT%H:%M:%SZ').replace(tzinfo=timezone.utc)
    except ValueError as e:raise ApprovalDenied('Bad UTC timestamp') from e


def validate(payload:dict,diff_status:str,history_entries:int,*,now=None):
    """Pure strict gate: no network, no writes and no secrets ever logged."""
    now=now or datetime.now(timezone.utc)
    expected={'project','episode','shot','approval','created_at_utc','expires_at_utc',
              'approved_external_requests','local_reservation_usd','provider_hard_cap_exists',
              'new_user_authorization','authorized_prompt_sha256'}
    if set(payload)!=expected:raise ApprovalDenied('Approval receipt schema does not match')
    if payload['project']!='kolnoa-hamishnah' or payload['episode']!='berakhot-01-01' or payload['shot']!='OPN01':
        raise ApprovalDenied('Wrong project, episode or chronological shot')
    if payload['approval']!=MESSAGE or payload['new_user_authorization'] is not True:
        raise ApprovalDenied('One-shot authorization is absent')
    if type(payload['approved_external_requests']) is not int or payload['approved_external_requests']!=1:
        raise ApprovalDenied('Approval must allow exactly one provider request')
    if type(payload['local_reservation_usd']) not in (float,int) or abs(payload['local_reservation_usd']-0.15)>1e-9:
        raise ApprovalDenied('Unexpected local reservation')
    if not isinstance(payload['authorized_prompt_sha256'], str) or not re.fullmatch(r'[0-9a-f]{64}', payload['authorized_prompt_sha256']):
        raise ApprovalDenied('Retake approval must pin the exact corrective prompt digest')
    if payload['provider_hard_cap_exists'] is not False:
        raise ApprovalDenied('Price reservation must not masquerade as provider cap')
    created=iso_time(payload['created_at_utc']);expires=iso_time(payload['expires_at_utc'])
    if created>now+timedelta(seconds=30) or now>expires or expires-created>timedelta(minutes=25) or expires<=created:
        raise ApprovalDenied('Authorization expired or has unsafe time window')
    if now-created>timedelta(minutes=25):raise ApprovalDenied('Authorization no longer fresh')
    if diff_status.strip()!=f'A\t{APPROVAL_FILE}':
        raise ApprovalDenied('Only an isolated new approval file can authorize payment')
    if history_entries!=1:raise ApprovalDenied('Re-added or modified approval file is not single-use')
    return {'status':'FRESH_ONE_SHOT_APPROVAL_VERIFIED','shot':'OPN01','provider_calls_allowed':1,
            'public_release_allowed':False,'authorization_does_not_guarantee_price_cap':True}


def run_git(args:list[str])->str:
    r=subprocess.run(args,capture_output=True,text=True,check=True,timeout=25)
    return r.stdout.strip()


def gate(repo:Path,approval_path:Path,before:str,sha:str,run_attempt:int,now=None):
    if run_attempt!=1:raise ApprovalDenied('Rerun attempts blocked to prevent double charge')
    if not re.fullmatch(r'[0-9a-f]{40}',before) or not re.fullmatch(r'[0-9a-f]{40}',sha):
        raise ApprovalDenied('Invalid push commits')
    if before=='0'*40:raise ApprovalDenied('Only an existing branch can authorize')
    if approval_path.resolve()!=(repo/APPROVAL_FILE).resolve():
        raise ApprovalDenied('Must use fixed single-use approval file')
    if approval_path.is_symlink() or not approval_path.is_file():
        raise ApprovalDenied('Approval file missing or symlink')
    status=run_git(['git','-C',str(repo),'diff','--name-status',before,sha])
    commits=run_git(['git','-C',str(repo),'log','--format=%H','--all','--',APPROVAL_FILE]).splitlines()
    if run_git(['git','-C',str(repo),'rev-parse','HEAD'])!=sha:
        raise ApprovalDenied('Untrusted checkout commit')
    payload=json.loads(approval_path.read_text(encoding='utf-8'))
    result=validate(payload,status,len(commits),now=now)
    # The previous OPN01 authorization is irrevocably consumed. A retake
    # requires a NEW path and a user-approved hash of the corrective payload.
    old_path='production_authorizations/OPN01_APPROVED_ONCE.json'
    if not run_git(['git','-C',str(repo),'log','--format=%H','--all','--',old_path]):
        raise ApprovalDenied('Historical paid OPN01 approval is not verifiable')
    from tools.fal_private_opening_opn01 import prepare
    manifest=json.loads((repo/'episodes/berakhot-01-01/opening-45s-director-pack-v1.json').read_text(encoding='utf-8'))
    expected_digest=prepare(manifest)['prompt_sha256']
    if payload['authorized_prompt_sha256']!=expected_digest:
        raise ApprovalDenied('Authorized prompt differs from corrective OPN01 payload')
    return result


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--repo',type=Path,default=Path.cwd());p.add_argument('--file',type=Path,default=Path(APPROVAL_FILE))
    p.add_argument('--before',required=True);p.add_argument('--sha',required=True);p.add_argument('--run-attempt',type=int,required=True)
    args=p.parse_args(argv)
    try:
        r=gate(args.repo,args.file,args.before,args.sha,args.run_attempt)
        print(json.dumps(r,ensure_ascii=False,sort_keys=True));return 0
    except (ValueError,OSError,subprocess.SubprocessError,json.JSONDecodeError) as e:
        print('PAID_REQUEST_BLOCKED: '+type(e).__name__+': '+str(e),file=sys.stderr);return 2

if __name__=='__main__':raise SystemExit(main())