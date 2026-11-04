import unittest
from tools.azure_speech_check import verify_resource
class AzureTierTests(unittest.TestCase):
 def test_live_resource_gate(self):
  resource=dict(type='Microsoft.CognitiveServices/accounts',kind='SpeechServices',sku={'name':'F0'},location='eastus')
  verify_resource(resource,'eastus')
  for change in [dict(sku={'name':'S0'}),dict(location='westus'),dict(kind='Other'),dict(sku={})]:
   with self.assertRaises(ValueError):verify_resource({**resource,**change},'eastus')

class AzureExecutionTests(unittest.TestCase):
 def exercise(self, synthesize=False, sku='F0', voice=True, compare=False, new=False):
  import io,json,os,tempfile,wave
  from pathlib import Path
  from unittest.mock import patch,MagicMock
  from tools.azure_speech_check import main
  rid='/subscriptions/test/resourceGroups/test/providers/Microsoft.CognitiveServices/accounts/test'
  resource=dict(id=rid,type='Microsoft.CognitiveServices/accounts',kind='SpeechServices',sku={'name':sku},location='eastus')
  audio=io.BytesIO()
  with wave.open(audio,'wb') as f:
   f.setnchannels(1);f.setsampwidth(2);f.setframerate(48000);f.writeframes(b'\x01\x00'*4800)
  responses=[]
  from tools.new_narrator_auditions import VOICES
  catalog=([{'ShortName':n,'Gender':'Male','SecondaryLocaleList':['he-IL']} for n in VOICES] if new else [{'ShortName':'he-IL-AvriNeural'}])
  for data in [json.dumps(catalog if voice else []).encode(),audio.getvalue()] + ([audio.getvalue()] if (compare or new) else []):
   response=MagicMock();response.__enter__.return_value=io.BytesIO(data);responses.append(response)
  with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ,{'AZURE_SPEECH_KEY':'test-secret','AZURE_SPEECH_RESOURCE_ID':rid,'AZURE_SPEECH_REGION':''}), patch('sys.argv',['check']+(['--synthesize'] if synthesize else [])+(['--compare-narrator'] if compare else [])+(['--new-narrators'] if new else [])), patch('tools.azure_speech_check.subprocess.run',return_value=MagicMock(stdout=json.dumps(resource))) as arm, patch('tools.azure_speech_check.urllib.request.urlopen',side_effect=responses) as network, patch('tools.azure_speech_check.seal') as seal:
   old=os.getcwd()
   try:
    os.chdir(tmp);main()
    self.assertEqual(network.call_count,(3 if (compare or new) else 2) if synthesize else 1)
    self.assertEqual(seal.call_count,1 if synthesize else 0)
    self.assertEqual(Path('private-media/azure-audition/audition.wav').exists(),synthesize and not compare and not new)
    if new:
     self.assertNotIn(b'Avri',network.call_args.args[0].data)
     for name in VOICES:self.assertTrue(Path('private-media/azure-audition',name+'.wav').exists())
    if compare:
     self.assertTrue(Path('private-media/azure-audition/baseline.wav').exists())
     self.assertTrue(Path('private-media/azure-audition/warm_candidate.wav').exists())
    if synthesize:
     self.assertEqual(network.call_args.args[0].method,'POST')
     if not new:self.assertIn(b'he-IL-AvriNeural',network.call_args.args[0].data)
   finally:os.chdir(old)
 def test_connection_only_never_writes_audio(self):self.exercise()
 def test_mock_synthesis_decodes_wav_and_seals(self):self.exercise(True)
 def test_new_voice_mode_has_no_avri_requests(self):self.exercise(True,new=True)
 def test_two_take_comparison_is_bounded(self):self.exercise(True,compare=True)
 def test_comparison_requires_explicit_synthesis(self):
  with self.assertRaises(ValueError):self.exercise(compare=True)
 def test_paid_tier_stops_before_speech_request(self):
  with self.assertRaises(ValueError):self.exercise(True,sku='S0')
 def test_missing_voice_stops_before_synthesis(self):
  with self.assertRaises(ValueError):self.exercise(True,voice=False)
