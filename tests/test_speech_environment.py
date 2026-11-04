import copy,json,unittest
from pathlib import Path
from tools.verify_speech_environment import validate_environment

class SpeechEnvironmentTests(unittest.TestCase):
 def setUp(self):
  self.environment={'protection_rules':[{'type':'required_reviewers','prevent_self_review':False,'reviewers':[{'reviewer':{'login':'barkinam21-pixel'}}]}],'deployment_branch_policy':{'custom_branch_policies':True,'protected_branches':False},'can_admins_bypass':False}
  self.policy={'branch_policies':[{'name':'main','type':'branch'}]}
 def test_owner_and_main_are_required(self):
  validate_environment(self.environment,self.policy)
  for changed in [{},{'branch_policies':[{'name':'*'}]},{'branch_policies':[{'name':'main','type':'tag'}]}]:
   with self.assertRaises(ValueError):validate_environment(self.environment,changed)
 def test_no_reviewer_or_bypass_or_self_review_deadlock(self):
  for change in [{'can_admins_bypass':True},{'deployment_branch_policy':None}]:
   with self.assertRaises(ValueError):validate_environment({**self.environment,**change},self.policy)
  changed=copy.deepcopy(self.environment);changed['protection_rules'][0]['prevent_self_review']=True
  with self.assertRaises(ValueError):validate_environment(changed,self.policy)
 def test_main_only_without_manual_review_is_allowed(self):
  validate_environment({**self.environment,'protection_rules':[]},self.policy)
 def test_template_grants_only_reader_on_existing_speech(self):
  root=Path(__file__).resolve().parents[1]
  template=json.loads((root/'infrastructure/azure-speech-identity.json').read_text())
  resources=template['resources']
  self.assertEqual(len(resources),3)
  self.assertNotIn('Microsoft.CognitiveServices/accounts',[r['type'] for r in resources])
  role=next(r for r in resources if r['type']=='Microsoft.Authorization/roleAssignments')
  self.assertEqual(role['scope'],"[variables('speechId')]")
  self.assertIn('acdd72a7-3385-48ef-bd42-f606fba81ae7',template['variables']['readerRole'])
  fed=next(r for r in resources if r['type'].endswith('federatedIdentityCredentials'))
  self.assertEqual(fed['properties']['subject'],'repo:barkinam21-pixel@312509860/project-mishna@1342201292:environment:azure-speech')
  self.assertEqual(template['parameters']['speechResourceName']['defaultValue'],'bar-universal-speech-2026')
 def test_no_pr_execution_or_repository_secret_exposure(self):
  root=Path(__file__).resolve().parents[1]
  workflow=(root/'.github/workflows/azure-speech-check.yml').read_text()
  self.assertNotIn('pull_request',workflow)
  self.assertIn('needs: verify_environment',workflow)
  self.assertIn("github.ref == 'refs/heads/main'",workflow)
  self.assertIn('environment: azure-speech',workflow)
  self.assertEqual(workflow.count("github.actor == github.repository_owner"),2)
  self.assertEqual(workflow.count("github.event_name == 'workflow_dispatch'"),2)
  self.assertIn('if-no-files-found: error',workflow)
  self.assertIn('cancel-in-progress: false',workflow)
