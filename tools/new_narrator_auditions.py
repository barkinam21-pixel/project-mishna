"""Unapproved Hebrew casting probes; no Avri and no custom-voice claims."""
import xml.etree.ElementTree as ET

VOICES = ('en-US-AndrewMultilingualNeural', 'en-US-BrianMultilingualNeural')
TEXT = 'ערב יורד על הכפר. בואו נתקרב, ונקשיב יחד. לפעמים, שאלה פשוטה פותחת בפנינו עולם שלם.'

def audition_takes(catalog):
    # Fail closed unless the live catalog explicitly advertises Hebrew support.
    available = {v.get('ShortName'): v for v in catalog}
    for name in VOICES:
        item = available.get(name, {})
        if item.get('Gender') != 'Male' or 'he-IL' not in item.get('SecondaryLocaleList', []):
            raise ValueError('Alternative Hebrew male voice not verified in live catalog')
    takes = []
    for name in VOICES:
        root = ET.Element('speak', {'version': '1.0', 'xmlns': 'http://www.w3.org/2001/10/synthesis', 'xml:lang': 'he-IL'})
        voice = ET.SubElement(root, 'voice', {'name': name})
        lang = ET.SubElement(voice, 'lang', {'xml:lang': 'he-IL'})
        ET.SubElement(lang, 'prosody', {'rate': '-3%'}).text = TEXT
        takes.append((name, ET.tostring(root, encoding='unicode')))
    return takes
