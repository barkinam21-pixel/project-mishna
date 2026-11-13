"""Allowlisted connector plans. No credentials, shell execution, network or model calls."""
import argparse
import datetime as dt
import hashlib
import json
import re
from pathlib import Path

REPO='barkinam21-pixel/project-mishna'
RUN_ID=43337618166
RUN_SHA='4b14becd05c5ce6690800a545a3e620850fe45e4'
CODE_SHA='2a7544d7d63a4e90e0872ba31df9736cd3103a21'
WORKFLOW='.github/workflows/verify-private-drive-readonly.yml'
WORKFLOW_BLOB='162d2698e20b296ee23c0e3cc2a2eddfdd65fa07'
READONLY={'תמשיך את המשנה','תמשיך את פרויקט המשנה','בדוק את המערכת','בדיקת חיבור','continue','check'}


def intent(text):
    clean=re.sub(r'[״״"?!.,]','',text.strip()).strip()
    if clean in READONLY:
        return {'operation':'check-drive','status':'READ_ONLY_ONLY','run_id':RUN_ID,
                'next':'Read allowlisted run metadata, workflow at its immutable SHA, and latest jobs; validate before replay',
                'generation_authorized':False,'remote_writes':0}
    if clean=='בדוק את התמונות':
        return {'operation':'inspect-existing-assets','status':'REQUIRES_EXISTING_ASSET_ACCESS_AND_VISUAL_REVIEW',
                'generation_authorized':False,'remote_writes':0,
                'next':'Use the existing verified recovery record and privately inspect image bytes. A Drive connection check is not visual QA.'}
    return {'status':'BLOCKED_UNIMPLEMENTED_OR_REQUIRES_SPECIFIC_APPROVAL',
            'generation_authorized':False,'remote_writes':0,
            'next':'Inspect project state; never map scene, repair, voice, video or backup requests to unrestricted workflow execution'}


def replay_plan(run,jobs,workflow_text,now=None):
    now=now or dt.datetime.now(dt.timezone.utc)
    if run.get('id')!=RUN_ID or run.get('head_sha')!=RUN_SHA or run.get('path')!=WORKFLOW or run.get('event')!='workflow_dispatch':
        raise ValueError('UNREVIEWED_WORKFLOW_RUN')
    if run.get('repository',{}).get('full_name')!=REPO or run.get('actor',{}).get('login')!=REPO.split('/')[0]:
        raise ValueError('UNEXPECTED_REPOSITORY_OR_OWNER')
    created=dt.datetime.fromisoformat(run['created_at'].replace('Z','+00:00'))
    if not 0<=(now-created).total_seconds()<30*86400:raise ValueError('REPLAY_WINDOW_EXPIRED_NEEDS_NEW_REVIEWED_READONLY_RUN')
    raw=workflow_text.encode()
    if hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest()!=WORKFLOW_BLOB:
        raise ValueError('WORKFLOW_CONTENT_NOT_REVIEWED')
    if run.get('status')!='completed':raise ValueError('RUN_ALREADY_ACTIVE_NO_DUPLICATE_START')
    if len(jobs)!=1 or jobs[0].get('name')!='drive-readonly' or jobs[0].get('run_id')!=RUN_ID or jobs[0].get('status')!='completed' or type(jobs[0].get('id')) is not int:
        raise ValueError('UNEXPECTED_JOB_GRAPH')
    return {'tool':'mcp__codex_apps__github_rerun_workflow_job',
            'arguments':{'repo_full_name':REPO,'job_id':jobs[0]['id']},
            'run_id':RUN_ID,'expected_next_attempt':run['run_attempt']+1,
            'reviewed_runtime_code':CODE_SHA,'operation':'check-drive',
            'inference_requests':0,'remote_writes':0,'status':'SAFE_REPLAY_PLAN_NOT_EXECUTED'}


def verify_result(run,report,expected_attempt):
    if run.get('id')!=RUN_ID or run.get('head_sha')!=RUN_SHA or run.get('run_attempt')!=expected_attempt or run.get('status')!='completed' or run.get('conclusion')!='success':
        raise ValueError('RUN_NOT_VERIFIED_SUCCESS')
    if report.get('status')!='DRIVE_RESTORE_AND_LOCAL_PREFLIGHT_VERIFIED' or type(report.get('inference_requests')) is not int or report['inference_requests']!=0 or type(report.get('remote_writes')) is not int or report['remote_writes']!=0 or report.get('generation_authorized') is not False:
        raise ValueError('READONLY_RESULT_NOT_VERIFIED')
    return {'status':'CONNECTED_TOOL_READONLY_EXECUTION_VERIFIED','run_id':RUN_ID,
            'attempt':expected_attempt,'runtime_code_sha':CODE_SHA,'inference_requests':0,'remote_writes':0,
            'ordinary_chat_surface_tested':False,'note':'Connector operation verified here; an ordinary chat must expose the same GitHub tools. No browser or local CLI is needed by that operation.'}


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('request');a=p.parse_args()
    print(json.dumps(intent(a.request),ensure_ascii=False,indent=2))


if __name__=='__main__':main()
