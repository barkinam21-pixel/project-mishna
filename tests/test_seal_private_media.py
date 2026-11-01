import unittest, tempfile, importlib.util
from pathlib import Path
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization

spec=importlib.util.spec_from_file_location('seal',Path(__file__).resolve().parents[1]/'tools/seal_private_media.py')
seal=importlib.util.module_from_spec(spec);spec.loader.exec_module(seal)

class SealTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        key=rsa.generate_private_key(public_exponent=65537,key_size=3072)
        (self.root/'pub.pem').write_bytes(key.public_key().public_bytes(serialization.Encoding.PEM,serialization.PublicFormat.SubjectPublicKeyInfo))
        (self.root/'priv.pem').write_bytes(key.private_bytes(serialization.Encoding.PEM,serialization.PrivateFormat.PKCS8,serialization.NoEncryption()))
        (self.root/'input').mkdir();(self.root/'input'/'art.png').write_bytes(b'fake-png-private')
        (self.root/'input'/'ledger.json').write_text('{}')

    def test_roundtrip_and_ciphertext_private(self):
        out=self.root/'data.sealed'
        info=seal.seal(self.root/'input',self.root/'pub.pem',out)
        self.assertFalse(info['public_artifact_contains_plain_image'])
        self.assertNotIn(b'fake-png-private',out.read_bytes())
        result=seal.unseal(out,self.root/'priv.pem',self.root/'restored')
        self.assertEqual(result['file_count'],2)
        self.assertEqual((self.root/'restored'/'art.png').read_bytes(),b'fake-png-private')

    def test_refuse_overwrite(self):
        out=self.root/'data.sealed';out.write_bytes(b'existing')
        with self.assertRaises(ValueError):seal.seal(self.root/'input',self.root/'pub.pem',out)

    def test_wrong_key_rejected(self):
        out=self.root/'data.sealed';seal.seal(self.root/'input',self.root/'pub.pem',out)
        wrong=rsa.generate_private_key(public_exponent=65537,key_size=3072)
        (self.root/'wrong.pem').write_bytes(wrong.private_bytes(serialization.Encoding.PEM,serialization.PrivateFormat.PKCS8,serialization.NoEncryption()))
        with self.assertRaises(Exception):seal.unseal(out,self.root/'wrong.pem',self.root/'restored')
        self.assertFalse((self.root/'restored').exists())

    def test_tampering_rejected(self):
        out=self.root/'data.sealed';seal.seal(self.root/'input',self.root/'pub.pem',out)
        blob=bytearray(out.read_bytes());blob[-1]^=1;out.write_bytes(bytes(blob))
        with self.assertRaises(Exception):seal.unseal(out,self.root/'priv.pem',self.root/'restored')
        self.assertFalse((self.root/'restored').exists())

    def test_symlink_source_rejected(self):
        (self.root/'input'/'link.png').symlink_to(self.root/'input'/'art.png')
        with self.assertRaises(ValueError):seal.seal(self.root/'input',self.root/'pub.pem',self.root/'data.sealed')

if __name__=='__main__':unittest.main()