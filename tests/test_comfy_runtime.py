import hashlib
import tempfile
import unittest
from pathlib import Path
from PIL import Image
from tools.comfy_runtime import inspect, intake

class ComfyRuntimeTests(unittest.TestCase):
    def test_no_endpoint_fails_closed_without_generation(self):
        result=inspect()
        self.assertFalse(result['ready']);self.assertEqual(result['generation_submissions'],0)
        self.assertIn('NO_COMFY_ENDPOINT',result['errors'][0])

    def test_reference_original_preserved_without_inventing_approval(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);source=root/'original.png'
            Image.new('RGB',(32,32),'red').save(source)
            before=source.read_bytes();receipt=intake(source,root)
            self.assertEqual((root/receipt['path']).read_bytes(),before)
            self.assertEqual(receipt['sha256'],hashlib.sha256(before).hexdigest())
            self.assertFalse(receipt['synthesis_rights_confirmed'])
            self.assertFalse(receipt['visual_identity_approved'])
            self.assertEqual(intake(source,root),receipt)

    def test_rights_confirmation_needs_provenance(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);source=root/'original.png';Image.new('RGB',(32,32)).save(source)
            with self.assertRaises(ValueError):intake(source,root,synthesis_rights_confirmed=True)

    def test_existing_rights_receipt_not_overwritten(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);source=root/'original.png';Image.new('RGB',(32,32)).save(source)
            old=intake(source,root)
            result=intake(source,root,synthesis_rights_confirmed=True,rights_uri='TEST permission')
            self.assertEqual(old,result)
