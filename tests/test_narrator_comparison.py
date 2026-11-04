import unittest
import xml.etree.ElementTree as ET
from tools.narrator_comparison import TEXT, comparison_takes
from tools.voice_take_audit import hebrew_rehearsal_ssml

class NarratorComparisonTests(unittest.TestCase):
 def test_same_text_same_voice_bounded_prosody(self):
  takes=comparison_takes()
  self.assertEqual([n for n,_ in takes],['baseline','warm_candidate'])
  self.assertEqual(takes[0][1],hebrew_rehearsal_ssml(TEXT,'narrator'))
  for name,xml in takes:
   root=ET.fromstring(xml)
   voice=root.find('{http://www.w3.org/2001/10/synthesis}voice')
   self.assertEqual(voice.get('name'),'he-IL-AvriNeural')
   prosody=voice[0]
   self.assertEqual(prosody.text,TEXT)
   self.assertEqual(prosody.get('rate'),'-3%' if name=='baseline' else '-6%')
   self.assertEqual(prosody.get('pitch'),None if name=='baseline' else '-3%')
   self.assertNotIn('express-as',xml)
 def test_original_default_stays_unpitched(self):
  self.assertNotIn('pitch=',hebrew_rehearsal_ssml('שלום','narrator'))
