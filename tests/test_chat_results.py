import copy
import json
import unittest
from tools.chat_results import verify, next_task, EvidenceBlocked
from tools.chat_issue_bridge import REPO, OWNER, RUNTIME_SHA

class ChatResultsTests(unittest.TestCase):
    def setUp(self):
        self.expected={'request_id':'a'*32,'operation':'check-drive','conditioning_sha256':['b'*64,'c'*64,'d'*64],'candidate_sha256':'e'*64}
        self.result={'status':'DRIVE_RESTORE_AND_LOCAL_PREFLIGHT_VERIFIED','generation_authorized':False,'remote_writes':0,'inference_requests':0,'conditioning_inputs':3,'conditioning_sha256':self.expected['conditioning_sha256'],'latest_recorded_candidate_available':True,'latest_recorded_candidate_sha256':'e'*64,'latest_trial_layout_in_current_inputs':True,'latest_trial_layout_sha256':'b'*64,'journal_continuity_verified':True,'historical_attempts':4,'restored_candidates':[{'sha256':'e'*64,'native_original_verified':True,'approval_granted_by_preparation':False}]}
        self.receipt={'status':'VALIDATED_READ_ONLY','request_id':'a'*32,'operation':'check-drive','runtime_sha':RUNTIME_SHA,'generation_authorized':False,'remote_writes':0}
        self.bundle={'run':{'id':1,'event':'issues','repository':{'full_name':REPO},'actor':{'login':OWNER},'head_branch':'main','path':'.github/workflows/chat-readonly-command.yml','status':'completed','conclusion':'success'},'jobs':[{'name':'validate-request','run_id':1,'status':'completed','conclusion':'success'},{'name':'drive-readonly','run_id':1,'status':'completed','conclusion':'success'}]}
        self.logs()
    def logs(self):
        self.bundle['validator_log']='2026-11-13T13:16:23Z '+json.dumps(self.receipt)
        self.bundle['runtime_log']='2026-11-13T13:16:39Z '+json.dumps(self.result)
    def test_verified_is_technical_only_and_charge_unknown(self):
        r=verify(self.bundle,self.expected)
        self.assertEqual(r['status'],'VERIFIED');self.assertFalse(r['artistic_approval']);self.assertIsNone(r['actual_external_charge_usd'])
    def test_wrong_nonce_or_runtime_blocks_green_unrelated_run(self):
        for field,value in [('request_id','f'*32),('runtime_sha','f'*40),('operation','prepare-opn02')]:
            with self.subTest(field=field):
                b=copy.deepcopy(self.bundle);b['validator_log']=b['validator_log'].replace(str(self.receipt[field]),value)
                with self.assertRaises(EvidenceBlocked): verify(b,self.expected)
    def test_wrong_origin_and_job_binding_block(self):
        for field,value in [('event','pull_request'),('head_branch','foreign'),('path','other.yml')]:
            b=copy.deepcopy(self.bundle);b['run'][field]=value
            with self.assertRaises(EvidenceBlocked):verify(b,self.expected)
        self.bundle['jobs'][1]['run_id']=2
        self.assertEqual(verify(self.bundle,self.expected)['status'],'FAILED')
    def test_paid_generation_writes_missing_assets_history_rejected(self):
        for field,value in [('inference_requests',1),('remote_writes',1),('generation_authorized',True),('conditioning_inputs',2),('historical_attempts',0),('latest_recorded_candidate_available',False),('latest_trial_layout_in_current_inputs',False),('conditioning_sha256',[])]:
            with self.subTest(field=field):
                previous=self.result[field];self.result[field]=value;self.logs()
                with self.assertRaises(EvidenceBlocked):verify(self.bundle,self.expected)
                self.result[field]=previous
    def test_duplicate_or_truncated_result_is_not_success(self):
        for log in ['',self.bundle['runtime_log']+'\n'+self.bundle['runtime_log']]:
            self.bundle['runtime_log']=log
            with self.assertRaises(EvidenceBlocked):verify(self.bundle,self.expected)
    def test_running_and_failure_never_redispatch(self):
        self.bundle['run']['status']='in_progress'
        self.assertEqual(verify(self.bundle,self.expected)['next'],'READ_SAME_RUN_NO_REDISPATCH')
        self.bundle['run']['status']='completed';self.bundle['run']['conclusion']='failure'
        self.assertEqual(verify(self.bundle,self.expected)['next'],'DIAGNOSE_NO_REDISPATCH')
    def test_preparation_operation_supported_without_authorizing(self):
        self.expected['operation']='prepare-opn02';self.receipt['operation']='prepare-opn02';self.result['status']='OPN02_PREPARATION_VERIFIED_NOT_AUTHORIZED';self.logs()
        self.assertFalse(verify(self.bundle,self.expected)['generation_authorized'])
    def test_task_dependencies_attempt_limits_and_approval(self):
        tasks=[{'id':'check','status':'completed'},{'id':'prepare','status':'pending','depends_on':['check'],'risk':'read_only','required_approval':'none','attempts':0,'max_attempts':1},{'id':'generate','status':'pending','depends_on':['prepare'],'risk':'paid_or_generative','required_approval':'fresh_owner'}]
        self.assertEqual(next_task(tasks),'prepare');tasks[1]['status']='running';self.assertEqual(next_task(tasks),'READ_ACTIVE_RESULT')
        tasks[1]['status']='failed';tasks[1]['attempts']=1;self.assertEqual(next_task(tasks),'REVIEW_APPROVAL_BLOCKERS_NO_AUTOMATIC_GENERATION')
        tasks[1]['status']='completed';self.assertEqual(next_task(tasks),'REVIEW_APPROVAL_BLOCKERS_NO_AUTOMATIC_GENERATION')
        tasks.append({'id':'check','status':'completed'})
        with self.assertRaises(EvidenceBlocked):next_task(tasks)
