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
 def test_default_production_gates_closed(self):
  from pathlib import Path
  p=json.loads(Path('episodes/berakhot-01-01/generation-safety.json').read_text())
  self.assertFalse(any(p[k] for k in ('privacy_verified','free_hard_cap_verified','quota_verified')))
