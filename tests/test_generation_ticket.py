import copy,datetime as dt,hashlib,json,unittest
from tools.chat_issue_bridge import validate_generation_event,reserve_generation,validate_event,OWNER,REPO,RequestBlocked
class GenerationTicketTests(unittest.TestCase):
 def setUp(self):
  self.now=dt.datetime.now(dt.timezone.utc);self.history={'attempts':[{'key':str(i)} for i in range(4)]}
  self.policy=dict(verified_at=self.now.isoformat(),privacy_verified=True,free_hard_cap_verified=True,quota_verified=True,spec_sha256='b'*64)
  self.ticket=dict(version=1,request_id='a'*32,operation='generate-opn02-once',issued_at=self.now.isoformat(),approval='APPROVE_ONE_OPN02_FREE_ATTEMPT',spec_sha256='b'*64,history_sha256=hashlib.sha256(json.dumps(self.history,sort_keys=True,separators=(',',':')).encode()).hexdigest(),historical_attempts=4,total_attempt_limit=5,max_charge_usd=0)
 def event(self):return {'action':'edited','sender':{'login':OWNER},'repository':{'full_name':REPO,'owner':{'login':OWNER}},'issue':{'number':54,'state':'open','body':'```mishnah-generation-request\n'+json.dumps(self.ticket)+'\n```'},'changes':{'body':{'from':'Prior status'}}}
 def test_explicit_ticket_and_durable_reservation(self):
  t=validate_generation_event(self.event(),self.policy,self.history,self.now);saved=[];h=reserve_generation(t,self.history,saved.append)
  self.assertEqual(len(h['attempts']),5);self.assertEqual(len(self.history['attempts']),4);self.assertEqual(saved,[h])
  with self.assertRaises(RequestBlocked):validate_generation_event(self.event(),self.policy,h,self.now)
 def test_readonly_cannot_execute_generation(self):self.assertEqual(validate_event(self.event(),self.now)['status'],'IGNORED_NO_REQUEST')
 def test_privacy_quota_or_free_unknown_blocks(self):
  for k in ('privacy_verified','free_hard_cap_verified','quota_verified'):
   p=dict(self.policy);p[k]=False
   with self.assertRaises(RequestBlocked):validate_generation_event(self.event(),p,self.history,self.now)
 def test_changed_history_spec_or_budget_blocks(self):
  for k,v in [('history_sha256','f'*64),('spec_sha256','f'*64),('max_charge_usd',1),('total_attempt_limit',6),('historical_attempts',0)]:
   old=self.ticket[k];self.ticket[k]=v
   with self.assertRaises(RequestBlocked):validate_generation_event(self.event(),self.policy,self.history,self.now)
   self.ticket[k]=old
 def test_storage_failure_not_retried(self):
  calls=[];t=validate_generation_event(self.event(),self.policy,self.history,self.now)
  def fail(h):calls.append(h);raise OSError('TEST')
  with self.assertRaises(OSError):reserve_generation(t,self.history,fail)
  self.assertEqual(len(calls),1)
 def test_wrong_actor_and_stale_ticket_block(self):
  e=self.event();e['sender']['login']='foreign'
  with self.assertRaises(RequestBlocked):validate_generation_event(e,self.policy,self.history,self.now)
  self.ticket['issued_at']=(self.now-dt.timedelta(hours=1)).isoformat()
  with self.assertRaises(RequestBlocked):validate_generation_event(self.event(),self.policy,self.history,self.now)
