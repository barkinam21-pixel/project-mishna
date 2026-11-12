import unittest
from tools.authorize_private_drive import challenge,validate_client
class DesktopOAuthTests(unittest.TestCase):
 def test_pkce_rfc7636(self):self.assertEqual(challenge('dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk'),'E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM')
 def test_web_client_rejected(self):
  with self.assertRaises(ValueError):validate_client({'web':{'client_id':'test'}})
