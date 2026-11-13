"""Validate an owner-edited Issue 54 read-only request. No network or credentials."""
import argparse
import datetime as dt
import json
import os
from pathlib import Path
import re

REPO='barkinam21-pixel/project-mishna'
OWNER='barkinam21-pixel'
ISSUE=54
RUNTIME_SHA='80ba1559b785855a1f9f4cbd90083fd0228eec96'
OPERATIONS=frozenset(('check-drive','prepare-opn02'))
BLOCK=re.compile(r'^```mishnah-readonly-request\n([^`]{1,2048})\n```[ \t]*$',re.M)


class RequestBlocked(ValueError):pass


def unique_pairs(pairs):
    result={}
    for k,v in pairs:
        if k in result:raise RequestBlocked('DUPLICATE_REQUEST_FIELD')
        result[k]=v
    return result


def extract(body):
    if not isinstance(body,str) or len(body)>65536:raise RequestBlocked('INVALID_ISSUE_BODY')
    blocks=BLOCK.findall(body)
    if not blocks:return None
    if len(blocks)!=1:raise RequestBlocked('MULTIPLE_REQUEST_BLOCKS')
    try:value=json.loads(blocks[0],object_pairs_hook=unique_pairs)
    except (ValueError,TypeError):raise RequestBlocked('INVALID_REQUEST_JSON') from None
    if not isinstance(value,dict) or set(value)!={'version','request_id','operation','issued_at'}:
        raise RequestBlocked('UNEXPECTED_REQUEST_FIELDS')
    if type(value['version']) is not int or value['version']!=1:raise RequestBlocked('UNSUPPORTED_REQUEST_VERSION')
    if not isinstance(value['request_id'],str) or not re.fullmatch('[a-f0-9]{32}',value['request_id']):raise RequestBlocked('INVALID_REQUEST_ID')
    if not isinstance(value['operation'],str) or value['operation'] not in OPERATIONS:raise RequestBlocked('OPERATION_NOT_ALLOWLISTED')
    return value


def validate_event(event,now=None):
    now=now or dt.datetime.now(dt.timezone.utc)
    if event.get('action')!='edited' or event.get('repository',{}).get('full_name')!=REPO or event.get('repository',{}).get('owner',{}).get('login')!=OWNER or event.get('sender',{}).get('login')!=OWNER:
        raise RequestBlocked('UNEXPECTED_EVENT_REPOSITORY_OR_ACTOR')
    issue=event.get('issue',{})
    if type(issue.get('number')) is not int or issue['number']!=ISSUE or 'pull_request' in issue or issue.get('state')!='open':
        raise RequestBlocked('UNEXPECTED_ISSUE')
    current=extract(issue.get('body'))
    if current is None:return {'status':'IGNORED_NO_REQUEST','operation':''}
    old_body=event.get('changes',{}).get('body',{}).get('from')
    if not isinstance(old_body,str):return {'status':'IGNORED_NO_BODY_EDIT','operation':''}
    try:previous=extract(old_body)
    except RequestBlocked:previous=None
    if previous and current['request_id']==previous['request_id']:
        return {'status':'IGNORED_UNCHANGED_REQUEST_ID','operation':''}
    try:
        issued=dt.datetime.fromisoformat(current['issued_at'].replace('Z','+00:00'))
        if issued.tzinfo is None or not -60<=(now-issued).total_seconds()<=900:raise ValueError()
    except (ValueError,TypeError,AttributeError):raise RequestBlocked('REQUEST_TIME_INVALID_OR_EXPIRED') from None
    return {'status':'VALIDATED_READ_ONLY','operation':current['operation'],'request_id':current['request_id'],
            'runtime_sha':RUNTIME_SHA,'generation_authorized':False,'remote_writes':0}


def make_request(body,operation,request_id,issued_at):
    """Preserve the existing issue and replace only this bounded command block."""
    if not isinstance(body,str):raise RequestBlocked('INVALID_ISSUE_BODY')
    value={'version':1,'request_id':request_id,'operation':operation,'issued_at':issued_at}
    block='```mishnah-readonly-request\n'+json.dumps(value,separators=(',',':'))+'\n```'
    extract(block)
    new=block+'\n\n'+BLOCK.sub('',body).lstrip('\n')
    if len(new)>65536:raise RequestBlocked('ISSUE_BODY_LIMIT_REQUIRES_REVIEW')
    return new


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--event',default=os.environ.get('GITHUB_EVENT_PATH'));p.add_argument('--outputs',default=os.environ.get('GITHUB_OUTPUT'))
    a=p.parse_args()
    try:
        event=json.loads(Path(a.event).read_text(encoding='utf-8'))
        result=validate_event(event)
        if a.outputs:
            with Path(a.outputs).open('a',encoding='utf-8') as f:
                for key in ('operation','request_id'):
                    f.write(key+'='+result.get(key,'')+'\n')
        print(json.dumps(result))
        return 0
    except Exception as error:
        print(json.dumps({'status':'BLOCKED','code':str(error) if isinstance(error,RequestBlocked) else 'INVALID_EVENT','operation':''}))
        return 2


if __name__=='__main__':raise SystemExit(main())

# Generation is a distinct envelope; never add it to read-only OPERATIONS.
GENERATION_BLOCK=re.compile(r'^```mishnah-generation-request\n([^`]{1,4096})\n```[ \t]*$',re.M)

def validate_generation_event(event,policy,history,now=None):
    """Validate a future one-shot ticket; no dispatch, approval promotion or I/O."""
    now=now or dt.datetime.now(dt.timezone.utc)
    if event.get('action')!='edited' or event.get('sender',{}).get('login')!=OWNER or event.get('repository',{}).get('full_name')!=REPO or event.get('repository',{}).get('owner',{}).get('login')!=OWNER:
        raise RequestBlocked('GENERATION_OWNER_EVENT_REQUIRED')
    issue=event.get('issue',{})
    if issue.get('number')!=ISSUE or issue.get('state')!='open' or 'pull_request' in issue:raise RequestBlocked('GENERATION_ISSUE_REQUIRED')
    blocks=GENERATION_BLOCK.findall(issue.get('body',''))
    if len(blocks)!=1:raise RequestBlocked('ONE_GENERATION_ENVELOPE_REQUIRED')
    try:ticket=json.loads(blocks[0],object_pairs_hook=unique_pairs)
    except (ValueError,TypeError):raise RequestBlocked('INVALID_GENERATION_JSON') from None
    legacy_fields={'version','request_id','operation','issued_at','approval','spec_sha256','history_sha256','historical_attempts','total_attempt_limit','max_charge_usd'}
    fields=legacy_fields|{'shot_id'}
    if not isinstance(ticket,dict) or set(ticket) not in (legacy_fields,fields):raise RequestBlocked('GENERATION_FIELDS_INVALID')
    # Old OPN02 envelopes remain valid; new shots must name the exact target.
    shot_id=ticket.get('shot_id','OPN02')
    operations={
        'OPN02':('generate-opn02-once','APPROVE_ONE_OPN02_FREE_ATTEMPT'),
        'OPN03':('generate-opn03-once','APPROVE_ONE_OPN03_FREE_ATTEMPT'),
    }
    if (set(ticket)==legacy_fields and shot_id!='OPN02') or shot_id not in operations or type(ticket['version']) is not int or ticket['version']!=1 or (ticket['operation'],ticket['approval'])!=operations[shot_id]:
        raise RequestBlocked('EXPLICIT_ONE_SHOT_APPROVAL_REQUIRED')
    if not isinstance(ticket['request_id'],str) or not re.fullmatch('[a-f0-9]{32}',ticket['request_id']):raise RequestBlocked('INVALID_GENERATION_ID')
    if type(ticket['max_charge_usd']) not in (int,float) or ticket['max_charge_usd']!=0:raise RequestBlocked('ZERO_CHARGE_ONLY')
    try:
        issued=dt.datetime.fromisoformat(ticket['issued_at'].replace('Z','+00:00'))
        verified=dt.datetime.fromisoformat(policy['verified_at'].replace('Z','+00:00'))
        if issued.tzinfo is None or verified.tzinfo is None or not -60<=(now-issued).total_seconds()<=900 or not 0<=(now-verified).total_seconds()<=86400:raise ValueError()
    except (ValueError,KeyError,TypeError,AttributeError):raise RequestBlocked('GENERATION_EVIDENCE_EXPIRED') from None
    if not all(policy.get(k) is True for k in ('privacy_verified','free_hard_cap_verified','quota_verified')):raise RequestBlocked('GENERATION_SAFETY_UNVERIFIED')
    if not isinstance(policy.get('spec_sha256'),str) or not re.fullmatch('[a-f0-9]{64}',policy['spec_sha256']) or ticket['spec_sha256']!=policy['spec_sha256']:raise RequestBlocked('GENERATION_SPEC_CHANGED')
    import hashlib
    history_digest=hashlib.sha256(json.dumps(history,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    attempts=history.get('attempts')
    if not isinstance(attempts,list) or ticket['history_sha256']!=history_digest:raise RequestBlocked('GENERATION_HISTORY_CHANGED')
    if type(ticket['historical_attempts']) is not int or ticket['historical_attempts']!=len(attempts) or len(attempts)<4:raise RequestBlocked('HISTORICAL_ATTEMPTS_MUST_BE_PRESERVED')
    if type(ticket['total_attempt_limit']) is not int or ticket['total_attempt_limit']!=len(attempts)+1:raise RequestBlocked('EXACTLY_ONE_ADDITIONAL_ATTEMPT_REQUIRED')
    if any(a.get('request_id')==ticket['request_id'] for a in attempts):raise RequestBlocked('GENERATION_ALREADY_RESERVED_NO_RETRY')
    previous=event.get('changes',{}).get('body',{}).get('from')
    if not isinstance(previous,str) or ticket['request_id'] in previous:raise RequestBlocked('GENERATION_NOT_A_NEW_OWNER_REQUEST')
    normalized=dict(ticket);normalized['shot_id']=shot_id
    return dict(normalized,status='ONE_SHOT_TICKET_VALIDATED_NOT_SUBMITTED')


def reserve_generation(ticket,history,persist):
    """Persist through the existing private journal transport BEFORE any submit.

    Caller must serialize producers and use freshly validated history. This does
    not implement a distributed lock or silently retry a failed persist.
    """
    import copy,hashlib
    digest=hashlib.sha256(json.dumps(history,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    if ticket.get('status')!='ONE_SHOT_TICKET_VALIDATED_NOT_SUBMITTED' or ticket.get('history_sha256')!=digest:raise RequestBlocked('GENERATION_RESERVATION_INVALID')
    updated=copy.deepcopy(history)
    updated['attempts'].append({'key':ticket['spec_sha256'],'request_id':ticket['request_id'],'spec_sha256':ticket['spec_sha256'],'status':'RESERVED_SUBMISSION_UNCERTAIN_NO_RETRY'})
    persist(updated)  # exception means stop, never submit or reset the reservation
    return updated
