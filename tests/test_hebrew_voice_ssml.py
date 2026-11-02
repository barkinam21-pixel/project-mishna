import unittest
import xml.etree.ElementTree as ET
from tools.voice_take_audit import hebrew_rehearsal_ssml

class HebrewSsmlTests(unittest.TestCase):
    def test_hebrew_voices_escape_text_and_preserve_niqqud(self):
        text='רַבָּן גַּמְלִיאֵל <בדיקה> & קול'
        xml=hebrew_rehearsal_ssml(text,'narrator')
        doc=ET.fromstring(xml)
        self.assertEqual(doc.attrib['{http://www.w3.org/XML/1998/namespace}lang'],'he-IL')
        self.assertEqual(''.join(doc.itertext()),text)
        self.assertIn('he-IL-AvriNeural',xml)
        self.assertNotIn('express-as',xml)
        self.assertNotIn('en-US',xml)
        self.assertIn('he-IL-HilaNeural',hebrew_rehearsal_ssml(text,'explainer'))

    def test_no_invented_cast_or_injected_markup(self):
        for role,text in [('unknown','שלום'),('narrator',''),('narrator','שלום\u202e')]:
            with self.assertRaises(ValueError):hebrew_rehearsal_ssml(text,role)
