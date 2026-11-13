import copy,json,unittest
from tools.generation_issue_runtime import checkpoint_once
from tools.chat_issue_bridge import RequestBlocked
from tests import test_generation_ticket as ticket_fixture
class RuntimeCheckpointTests(unittest.TestCase):
 def test_engine_attempt_is_reserved_once_not_twice(self):
  f=ticket_fixture.GenerationTicketTests();f.setUp()
  from tools.chat_issue_bridge import validate_generation_event
  ticket=validate_generation_event(f.event(),f.policy,f.history,f.now)
  proposed=copy.deepcopy(f.history);proposed['attempts'].append({'key':ticket['spec_sha256']})
  stored=[];checkpoint_once(ticket,f.history,proposed,stored.append)
  self.assertEqual(len(stored[0]['attempts']),5);self.assertEqual(stored[0]['attempts'][-1]['request_id'],ticket['request_id']);self.assertEqual(len(f.history['attempts']),4)
 def test_persistence_failure_or_wrong_key_blocks(self):
  f=ticket_fixture.GenerationTicketTests();f.setUp()
  from tools.chat_issue_bridge import validate_generation_event
  t=validate_generation_event(f.event(),f.policy,f.history,f.now);p=copy.deepcopy(f.history);p['attempts'].append({'key':t['spec_sha256']})
  with self.assertRaises(OSError):checkpoint_once(t,f.history,p,lambda v:(_ for _ in ()).throw(OSError()))
  p['attempts'][-1]['key']='changed'
  with self.assertRaises(RequestBlocked):checkpoint_once(t,f.history,p,lambda v:self.fail('WRITE'))
 def test_generation_gates_require_all_evidence_or_stay_closed(self):
  from pathlib import Path
  p=json.loads(Path('episodes/berakhot-01-01/generation-safety.json').read_text())
  flags=[p[k] for k in ('privacy_verified','free_hard_cap_verified','quota_verified')]
  self.assertTrue(all(x is True for x in flags) or all(x is False for x in flags))
  if all(flags):
   self.assertRegex(p['spec_sha256'],r'^[a-f0-9]{64}$')
   self.assertIsInstance(p['verified_at'],str)
   self.assertIn('Free',p['reason'])
   self.assertIn('NO RETRY',p['reason'])
  else:
   self.assertIsNone(p['verified_at'])


class ProviderDiagnosticsTests(unittest.TestCase):
 def test_only_fixed_provider_codes_are_reported(self):
  from tools.generation_issue_runtime import safe_failure_code
  CloudflareBlocked=type('CloudflareBlocked',(ValueError,),{})
  for code in ('CREDENTIALS_UNAVAILABLE','USAGE_UNKNOWN','MODEL_UNAVAILABLE','TRANSPORT_FAILED_NO_AUTOMATIC_RETRY'):
   self.assertEqual(safe_failure_code(CloudflareBlocked(code)),code)
  self.assertEqual(safe_failure_code(CloudflareBlocked('secret-token-or-provider-body')),'CloudflareBlocked')
 def test_unrelated_exception_text_is_never_printed(self):
  from tools.generation_issue_runtime import safe_failure_code
  self.assertEqual(safe_failure_code(OSError('secret-token-or-private-url')),'OSError')
