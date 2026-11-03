import unittest
from tools.azure_speech_check import verify_resource
class AzureTierTests(unittest.TestCase):
 def test_live_resource_gate(self):
  resource=dict(type='Microsoft.CognitiveServices/accounts',kind='SpeechServices',sku={'name':'F0'},location='eastus')
  verify_resource(resource,'eastus')
  for change in [dict(sku={'name':'S0'}),dict(location='westus'),dict(kind='Other'),dict(sku={})]:
   with self.assertRaises(ValueError):verify_resource({**resource,**change},'eastus')
