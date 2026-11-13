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
