"""Optional unapproved Avri audition; never changes the production voice default."""
import xml.etree.ElementTree as ET
from tools.voice_take_audit import hebrew_rehearsal_ssml

TEXT = 'ערב יורד על הכפר. בואו נתקרב, ונקשיב יחד. לפעמים, שאלה פשוטה פותחת בפנינו עולם שלם.'

def comparison_takes():
    # Age, warmth and identity require listening; SSML cannot guarantee them.
    baseline = hebrew_rehearsal_ssml(TEXT, 'narrator')
    candidate = ET.fromstring(hebrew_rehearsal_ssml(TEXT, 'narrator', -6))
    candidate.find('.//{http://www.w3.org/2001/10/synthesis}prosody').set('pitch', '-3%')
    return [('baseline', baseline), ('warm_candidate', ET.tostring(candidate, encoding='unicode'))]
