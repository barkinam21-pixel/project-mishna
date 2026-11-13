import copy
import datetime as dt
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from tools.chat_issue_bridge import validate_event,make_request,extract,RequestBlocked,RUNTIME_SHA


class ChatIssueBridgeTests(unittest.TestCase):
    def setUp(self):
        self.now=dt.datetime(2026,11,13,2,tzinfo=dt.timezone.utc)
        self.body=make_request('Existing issue history remains here.','prepare-opn02','a'*32,self.now.isoformat())
        self.event={'action':'edited','repository':{'full_name':'barkinam21-pixel/project-mishna','owner':{'login':'barkinam21-pixel'}},'sender':{'login':'barkinam21-pixel'},'issue':{'number':54,'state':'open','body':self.body},'changes':{'body':{'from':'Existing issue history remains here.'}}}

    def test_owner_event_outputs_fixed_runtime_and_readonly_operation(self):
        result=validate_event(self.event,self.now)
        self.assertEqual(result['operation'],'prepare-opn02')
        self.assertEqual(result['runtime_sha'],RUNTIME_SHA)
        self.assertEqual(result['remote_writes'],0)
        self.assertFalse(result['generation_authorized'])

    def test_real_cli_event_round_trip_without_network_or_secret(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp);e=copy.deepcopy(self.event)
            e['issue']['body']=make_request('HISTORY','check-drive','b'*32,dt.datetime.now(dt.timezone.utc).isoformat())
            (p/'event.json').write_text(json.dumps(e));(p/'outputs').write_text('')
            proc=subprocess.run([sys.executable,'-m','tools.chat_issue_bridge','--event',str(p/'event.json'),'--outputs',str(p/'outputs')],capture_output=True,text=True,timeout=5,env={'PATH':str(Path(sys.executable).parent)})
            self.assertEqual(proc.returncode,0,proc.stdout)
            self.assertEqual(json.loads(proc.stdout)['status'],'VALIDATED_READ_ONLY')
            self.assertEqual((p/'outputs').read_text(),'operation=check-drive\nrequest_id='+('b'*32)+'\n')
            self.assertNotIn('HISTORY',proc.stdout)

    def test_foreign_actor_repo_issue_pr_or_action_blocked(self):
        for modify in ('actor','repo','owner','issue','pr','closed','action'):
            e=copy.deepcopy(self.event)
            if modify=='actor':e['sender']['login']='OTHER'
            elif modify=='repo':e['repository']['full_name']='OTHER/repo'
            elif modify=='owner':e['repository']['owner']['login']='OTHER'
            elif modify=='issue':e['issue']['number']=55
            elif modify=='pr':e['issue']['pull_request']={}
            elif modify=='closed':e['issue']['state']='closed'
            else:e['action']='opened'
            with self.subTest(modify=modify),self.assertRaises(RequestBlocked):validate_event(e,self.now)

    def test_arbitrary_commands_target_shas_and_extra_fields_rejected(self):
        value=extract(self.body)
        for change in ({'operation':'run'},{'operation':'check-drive; echo SECRET'},{'operation':'backup'},{'runtime_sha':'unreviewed'},{'url':'https://evil.invalid'},{'version':True}):
            body='```mishnah-readonly-request\n'+json.dumps(value|change)+'\n```'
            with self.subTest(change=change),self.assertRaises(RequestBlocked):extract(body)

    def test_duplicate_json_fields_blocks(self):
        body=self.body.replace('"operation":"prepare-opn02"','"operation":"check-drive","operation":"prepare-opn02"')
        with self.assertRaises(RequestBlocked):extract(body)

    def test_repeated_metadata_edit_does_not_relaunch(self):
        e=copy.deepcopy(self.event);e['changes']['body']['from']=self.body
        self.assertEqual(validate_event(e,self.now)['status'],'IGNORED_UNCHANGED_REQUEST_ID')
        e['changes']={}
        self.assertEqual(validate_event(e,self.now)['status'],'IGNORED_NO_BODY_EDIT')
        e['issue']['body']='No request block.'
        self.assertEqual(validate_event(e,self.now)['status'],'IGNORED_NO_REQUEST')

    def test_expired_future_or_naive_request_blocked(self):
        for at in (self.now-dt.timedelta(seconds=901),self.now+dt.timedelta(seconds=61),self.now.replace(tzinfo=None)):
            e=copy.deepcopy(self.event);e['issue']['body']=make_request('HISTORY','check-drive','c'*32,at.isoformat())
            with self.assertRaisesRegex(RequestBlocked,'TIME'):validate_event(e,self.now)

    def test_new_request_preserves_history_and_replaces_only_command(self):
        new=make_request(self.body,'check-drive','d'*32,self.now.isoformat())
        self.assertEqual(new.count('```mishnah-readonly-request'),1)
        self.assertIn('Existing issue history remains here.',new)
        self.assertEqual(extract(new)['request_id'],'d'*32)
        e=copy.deepcopy(self.event);e['issue']['body']=new;e['changes']['body']['from']=self.body
        self.assertEqual(validate_event(e,self.now)['status'],'VALIDATED_READ_ONLY')

    def test_multiple_blocks_block_and_body_length_bound(self):
        with self.assertRaises(RequestBlocked):extract(self.body+'\n'+self.body)
        with self.assertRaises(RequestBlocked):extract('x'*65537)

    def test_workflow_keeps_secrets_behind_validation_and_pinned_code(self):
        text=Path('.github/workflows/chat-readonly-command.yml').read_text()
        self.assertIn('ref: '+RUNTIME_SHA,text)
        self.assertIn("github.actor == github.repository_owner",text)
        self.assertIn('needs: validate-request',text)
        self.assertNotIn('pull_request_target',text)
        self.assertNotIn('contents: write',text)
        self.assertNotIn('issues: write',text)
        self.assertNotIn('CLOUDFLARE_API_TOKEN',text)
        self.assertNotIn('upload-artifact',text)
        self.assertNotIn('private_drive_runtime run',text)
        self.assertNotIn('github.event.issue.body',text)
        self.assertEqual(text.count('secrets.'),1)


if __name__=='__main__':unittest.main()
