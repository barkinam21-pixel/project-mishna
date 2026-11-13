"""Offline verification of connector-fetched Actions evidence. Never dispatches or retries."""
import argparse
import json
from pathlib import Path
from tools.chat_issue_bridge import REPO, OWNER, RUNTIME_SHA, OPERATIONS

class EvidenceBlocked(ValueError):
    pass

def records(log):
    if not isinstance(log, str) or len(log)>2_000_000:
        raise EvidenceBlocked('LOG_INVALID_OR_TOO_LARGE')
    result=[]
    for line in log.splitlines():
        # GitHub job logs prefix each actual output line with an ISO timestamp.
        parts=line.lstrip('\ufeff').split(' ',1)
        if len(parts)!=2 or not parts[0].endswith('Z') or not parts[1].startswith('{'):
            continue
        try: value=json.loads(parts[1])
        except ValueError: continue
        if isinstance(value,dict): result.append(value)
    return result

def exactly(rows,status):
    found=[x for x in rows if x.get('status')==status]
    if len(found)!=1: raise EvidenceBlocked('MISSING_OR_AMBIGUOUS_'+status)
    return found[0]

def verify(bundle,expected):
    """Consume fetched metadata+logs, correlate request, fail closed, emit safe summary."""
    run=bundle['run']; jobs=bundle['jobs']
    if type(run.get('id')) is not int or run['id']<=0:raise EvidenceBlocked('INVALID_RUN_ID')
    if not isinstance(jobs,list) or any(not isinstance(j,dict) for j in jobs):raise EvidenceBlocked('INVALID_JOBS')
    for name in ('validate-request','drive-readonly'):
        selected=[j for j in jobs if j.get('name')==name]
        if len(selected)>1:raise EvidenceBlocked('AMBIGUOUS_JOB_'+name)
        if selected and 'run_attempt' in run and selected[0].get('run_attempt')!=run['run_attempt']:raise EvidenceBlocked('JOB_ATTEMPT_MISMATCH')
    if (run.get('event')!='issues' or run.get('repository',{}).get('full_name')!=REPO
        or run.get('actor',{}).get('login')!=OWNER or run.get('head_branch')!='main'
        or run.get('path')!='.github/workflows/chat-readonly-command.yml'):
        raise EvidenceBlocked('WRONG_RUN_ORIGIN')
    if expected.get('operation') not in OPERATIONS: raise EvidenceBlocked('WRONG_OPERATION')
    validator=next((j for j in jobs if j.get('name')=='validate-request'),None)
    if not validator or validator.get('run_id')!=run['id']: raise EvidenceBlocked('MISSING_VALIDATOR')
    if validator.get('status')!='completed': return {'status':'RUNNING','run_id':run['id'],'next':'READ_SAME_RUN_NO_REDISPATCH'}
    if validator.get('conclusion')!='success': return {'status':'FAILED','run_id':run['id'],'next':'DIAGNOSE_NO_REDISPATCH'}
    receipt=exactly(records(bundle['validator_log']),'VALIDATED_READ_ONLY')
    if (receipt.get('request_id')!=expected['request_id'] or receipt.get('operation')!=expected['operation']
        or receipt.get('runtime_sha')!=RUNTIME_SHA): raise EvidenceBlocked('REQUEST_CORRELATION_FAILED')
    runtime=next((j for j in jobs if j.get('name')=='drive-readonly'),None)
    if run.get('status')!='completed': return {'status':'RUNNING','run_id':run['id'],'next':'READ_SAME_RUN_NO_REDISPATCH'}
    if not runtime or runtime.get('run_id')!=run['id'] or run.get('conclusion')!='success' or runtime.get('conclusion')!='success' or runtime.get('status')!='completed':
        return {'status':'FAILED','run_id':run['id'],'next':'DIAGNOSE_NO_REDISPATCH'}
    status='DRIVE_RESTORE_AND_LOCAL_PREFLIGHT_VERIFIED' if expected['operation']=='check-drive' else 'OPN02_PREPARATION_VERIFIED_NOT_AUTHORIZED'
    result=exactly(records(bundle['runtime_log']),status)
    for row in (receipt,result):
        if row.get('generation_authorized') is not False or type(row.get('remote_writes')) is not int or row['remote_writes']!=0:
            raise EvidenceBlocked('SAFETY_RESULT_FAILED')
    if type(result.get('inference_requests')) is not int or result['inference_requests']!=0:
        raise EvidenceBlocked('INFERENCE_NOT_ZERO')
    if (result.get('conditioning_inputs')!=3 or result.get('conditioning_sha256')!=expected['conditioning_sha256']
        or result.get('latest_recorded_candidate_available') is not True
        or result.get('latest_recorded_candidate_sha256')!=expected['candidate_sha256']
        or result.get('latest_trial_layout_in_current_inputs') is not True
        or result.get('latest_trial_layout_sha256')!=expected['conditioning_sha256'][0]
        or result.get('journal_continuity_verified') is not True or result.get('historical_attempts')!=4):
        raise EvidenceBlocked('ASSET_OR_HISTORY_MISMATCH')
    if not any(x.get('sha256')==expected['candidate_sha256'] and x.get('native_original_verified') is True
               and x.get('approval_granted_by_preparation') is False for x in result.get('restored_candidates',[])):
        raise EvidenceBlocked('NATIVE_CANDIDATE_NOT_VERIFIED')
    return {'status':'VERIFIED','request_id':receipt['request_id'],'operation':receipt['operation'],
            'run_id':run['id'],'runtime_sha':RUNTIME_SHA,'conditioning_inputs':3,'historical_attempts':4,
            'inference_requests':0,'remote_writes':0,'generation_authorized':False,
            'artistic_approval':False,'generation_blockers':result.get('generation_blockers',[]),
            'actual_external_charge_usd':None,'billing_note':'No inference or paid service invoked; billing account not inspected'}

def next_task(tasks):
    """A recommendation only; never executes tasks or infers approval."""
    for t in tasks:
        if not isinstance(t,dict) or not isinstance(t.get('id'),str) or not t['id']:raise EvidenceBlocked('INVALID_TASK')
        if any(type(t.get(k,default)) is not int or t.get(k,default)<0 for k,default in (('attempts',0),('max_attempts',1))):raise EvidenceBlocked('INVALID_ATTEMPT_LIMIT')
    by_id={t['id']:t for t in tasks}
    if len(by_id)!=len(tasks): raise EvidenceBlocked('DUPLICATE_TASK_ID')
    if any(t.get('status')=='running' for t in tasks): return 'READ_ACTIVE_RESULT'
    for t in tasks:
        if t.get('status') not in ('pending','failed'): continue
        if any(x not in by_id for x in t.get('depends_on',[])): raise EvidenceBlocked('UNKNOWN_DEPENDENCY')
        if not all(by_id[x].get('status')=='completed' for x in t.get('depends_on',[])): continue
        if (t.get('risk')!='read_only' or t.get('required_approval')!='none'
            or t.get('attempts',0)>=t.get('max_attempts',1)):
            continue
        return t['id']
    return 'REVIEW_APPROVAL_BLOCKERS_NO_AUTOMATIC_GENERATION'

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('bundle');p.add_argument('expected');a=p.parse_args()
    try:
        print(json.dumps(verify(json.loads(Path(a.bundle).read_text()),json.loads(Path(a.expected).read_text()))))
        return 0
    except (ValueError,KeyError,TypeError,OSError):
        print(json.dumps({'status':'BLOCKED','next':'READ_OR_DIAGNOSE_SAME_RUN_NO_REDISPATCH'}));return 2

if __name__=='__main__': raise SystemExit(main())
