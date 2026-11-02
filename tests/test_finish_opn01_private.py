"""Security and end-to-end delivery tests with invented QA media only."""
import base64,hashlib,json,tempfile,unittest
from pathlib import Path
from tools import finish_opn01_private as f
from tools import seal_private_media
from tools import fal_private_opening_opn01
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization
ROOT=Path(__file__).resolve().parents[1]

class Delivery(unittest.TestCase):
 def test_short_file_names(self):
  with self.assertRaises(f.UnsafePipeline):
   f.finish(Path('/nonexistent'),Path('/nonexistent'),Path('/n'),Path('/n'),Path('/mnt/data/name with space'),do_finish=False)
 def test_wrong_artifact_rejected(self):
  with tempfile.TemporaryDirectory() as t:
   d=Path(t);p=d/'wrong.bin';p.write_bytes(b'no'*1000)
   with self.assertRaises(f.UnsafePipeline):f.inspect_encrypted(p)
 def test_success_requires_correct_receipts(self):
  with tempfile.TemporaryDirectory() as t:
   d=Path(t); (d/f.ALLOWED_IMAGE).write_bytes(b'fake')
   (d/'attempt.json').write_text(json.dumps({'status':'SUBMITTED_OR_UNKNOWN','attempted_provider_requests':1,'shot':'OPN01','prompt_sha256':'x'}))
   (d/'success.json').write_text(json.dumps({'status':'ONE_PRIVATE_UNREVIEWED_IMAGE','attempted_provider_requests':1,'shot':'OPN01','prompt_sha256':'x','image_sha256':'0'*64,'image_bytes':4,'accepted_as_movie_asset':False,'human_visual_approval':False,'private_output_only':True,'public_release_allowed':False}))
   with self.assertRaises(f.UnsafePipeline):f.verify_receipt(d)
 def test_two_attempts_rejected(self):
  with tempfile.TemporaryDirectory() as t:
   d=Path(t);fake=d/f.ALLOWED_IMAGE; fake.write_bytes(b'fake')
   receipt={'status':'ONE_PRIVATE_UNREVIEWED_IMAGE','attempted_provider_requests':2,'shot':'OPN01','prompt_sha256':'x','image_sha256':hashlib.sha256(b'fake').hexdigest(),'image_bytes':4,'accepted_as_movie_asset':False,'human_visual_approval':False,'private_output_only':True,'public_release_allowed':False}
   attempt={'status':'SUBMITTED_OR_UNKNOWN','attempted_provider_requests':2,'shot':'OPN01','prompt_sha256':'x'}
   (d/'attempt.json').write_text(json.dumps(attempt));(d/'success.json').write_text(json.dumps(receipt))
   with self.assertRaises(f.UnsafePipeline):f.verify_receipt(d)
 def test_wrong_frame_name_rejected(self):
  with tempfile.TemporaryDirectory() as t:
   d=Path(t);(d/'SH09.png').write_bytes(b'x')
   (d/'attempt.json').write_text('{}');(d/'success.json').write_text('{}')
   with self.assertRaises(f.UnsafePipeline):f.verify_receipt(d)
 def test_encryption_roundtrip_receipt_validation(self):
  with tempfile.TemporaryDirectory() as t:
   d=Path(t); raw=d/'raw';raw.mkdir(); png=raw/f.ALLOWED_IMAGE
   # Tiny in-memory fixture: no private image or repo-side media dependency.
   png.write_bytes(base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9Y7nuQAAAABJRU5ErkJggg=='))
   digest=hashlib.sha256(png.read_bytes()).hexdigest()
   prompt_sha=fal_private_opening_opn01.prepare(json.loads((ROOT/'episodes/berakhot-01-01/opening-45s-director-pack-v1.json').read_text()))['prompt_sha256']
   receipt={'status':'ONE_PRIVATE_UNREVIEWED_IMAGE','attempted_provider_requests':1,'shot':'OPN01','prompt_sha256':prompt_sha,'image_sha256':digest,'image_bytes':png.stat().st_size,'accepted_as_movie_asset':False,'human_visual_approval':False,'private_output_only':True,'public_release_allowed':False}
   attempt={'status':'SUBMITTED_OR_UNKNOWN','attempted_provider_requests':1,'shot':'OPN01','prompt_sha256':prompt_sha}
   (raw/'attempt.json').write_text(json.dumps(attempt));(raw/'success.json').write_text(json.dumps(receipt))
   key=rsa.generate_private_key(public_exponent=65537,key_size=3072)
   priv=d/'test_private.pem'; pub=d/'test_public.pem'
   priv.write_bytes(key.private_bytes(serialization.Encoding.PEM,serialization.PrivateFormat.PKCS8,serialization.NoEncryption()))
   pub.write_bytes(key.public_key().public_bytes(serialization.Encoding.PEM,serialization.PublicFormat.SubjectPublicKeyInfo))
   blob=d/'artifact.encrypted';seal_private_media.seal(raw,pub,blob)
   chk=f.inspect_encrypted(blob)
   self.assertTrue(chk['protected_media_not_published'])
   out=d/'unsealed';seal_private_media.unseal(blob,priv,out)
   p,s=f.verify_receipt(out)
   self.assertEqual(p.read_bytes(),png.read_bytes());self.assertEqual(s['shot'],'OPN01')
   self.assertNotIn(b'OPN01_UNREVIEWED_PRIVATE.png',blob.read_bytes())

if __name__=='__main__':unittest.main()