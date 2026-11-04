import unittest
import xml.etree.ElementTree as ET
from tools.new_narrator_auditions import VOICES, TEXT, audition_takes

class NewNarratorTests(unittest.TestCase):
 def catalog(self):return [{'ShortName':n,'Gender':'Male','SecondaryLocaleList':['he-IL']} for n in VOICES]
 def test_two_distinct_non_avri_voices_same_text_and_settings(self):
  takes=audition_takes(self.catalog())
  self.assertEqual(len(takes),2)
  self.assertNotEqual(takes[0][0],takes[1][0])
  for name,ssml in takes:
   self.assertNotIn('Avri',ssml)
   root=ET.fromstring(ssml)
   self.assertEqual(root.get('{http://www.w3.org/XML/1998/namespace}lang'),'he-IL')
   self.assertEqual(''.join(root.itertext()),TEXT)
   self.assertIn('rate="-3%"',ssml)
 def test_no_unadvertised_hebrew_or_unknown_gender(self):
  for changes in [{'SecondaryLocaleList':[]},{'Gender':'Female'},{'Gender':None}]:
   catalog=self.catalog();catalog[0].update(changes)
   with self.assertRaises(ValueError):audition_takes(catalog)
  with self.assertRaises(ValueError):audition_takes([])
