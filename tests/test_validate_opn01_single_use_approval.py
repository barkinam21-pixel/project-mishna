import unittest
from datetime import datetime,timezone,timedelta
from tools.validate_opn01_single_use_approval import validate,ApprovalDenied,APPROVAL_FILE,MESSAGE

NOW=datetime(2026,11,1,14,0,0,tzinfo=timezone.utc)

def approved():
 return {'project':'kolnoa-hamishnah','episode':'berakhot-01-01','shot':'OPN01',
  'approval':MESSAGE,'created_at_utc':'2026-11-01T13:59:00Z',
  'expires_at_utc':'2026-11-01T14:20:00Z','approved_external_requests':1,
  'local_reservation_usd':0.15,'provider_hard_cap_exists':False,
  'new_user_authorization':True,'authorized_prompt_sha256':'a'*64}

class ApprovalSecurity(unittest.TestCase):
 def test_only_expected_new_file(self):
  r=validate(approved(),'A\t'+APPROVAL_FILE,1,now=NOW)
  self.assertEqual(r['provider_calls_allowed'],1)
 def test_replay_history(self):
  with self.assertRaises(ApprovalDenied):validate(approved(),'A\t'+APPROVAL_FILE,2,now=NOW)
 def test_prompt_digest_required(self):
  d=approved();d['authorized_prompt_sha256']='unknown'
  with self.assertRaises(ApprovalDenied):validate(d,'A\t'+APPROVAL_FILE,1,now=NOW)
 def test_legacy_used_path_never_authorizes_retake(self):
  with self.assertRaises(ApprovalDenied):
   validate(approved(),'A\tproduction_authorizations/OPN01_APPROVED_ONCE.json',1,now=NOW)
 def test_wrong_shot(self):
  d=approved();d['shot']='SH09'
  with self.assertRaises(ApprovalDenied):validate(d,'A\t'+APPROVAL_FILE,1,now=NOW)
 def test_modified_file(self):
  with self.assertRaises(ApprovalDenied):validate(approved(),'M\t'+APPROVAL_FILE,1,now=NOW)
 def test_extra_files_in_commit(self):
  with self.assertRaises(ApprovalDenied):validate(approved(),'A\t'+APPROVAL_FILE+'\nM\ttools/fal_private_opening_opn01.py',1,now=NOW)
 def test_expired(self):
  with self.assertRaises(ApprovalDenied):validate(approved(),'A\t'+APPROVAL_FILE,1,now=NOW+timedelta(minutes=22))
 def test_bad_approval_phrase(self):
  d=approved();d['approval']='YES'
  with self.assertRaises(ApprovalDenied):validate(d,'A\t'+APPROVAL_FILE,1,now=NOW)
 def test_no_pretend_provider_hard_cap(self):
  d=approved();d['provider_hard_cap_exists']=True
  with self.assertRaises(ApprovalDenied):validate(d,'A\t'+APPROVAL_FILE,1,now=NOW)
 def test_more_than_one_request(self):
  d=approved();d['approved_external_requests']=2
  with self.assertRaises(ApprovalDenied):validate(d,'A\t'+APPROVAL_FILE,1,now=NOW)
 def test_stale_time(self):
  d=approved();d['created_at_utc']='2026-10-30T14:00:00Z'
  with self.assertRaises(ApprovalDenied):validate(d,'A\t'+APPROVAL_FILE,1,now=NOW)
 def test_unknown_receipt_key_rejected(self):
  d=approved();d['user']='someone'
  with self.assertRaises(ApprovalDenied):validate(d,'A\t'+APPROVAL_FILE,1,now=NOW)

if __name__=='__main__':unittest.main()