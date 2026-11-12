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

    def test_package_restore_rejects_extra_or_bad_members(self):
        import zipfile,hashlib
        from tools.comfy_runtime import intake_package
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);image=root/'test.png';Image.new('RGB',(32,32),'red').save(image)
            digest=hashlib.sha256(image.read_bytes()).hexdigest()
            manifest={'references':[{'expected_sha256':digest,'expected_size':[32,32]}],
                      'characters':{'A':{'references':[]}},'direction_board':{}}
            archive=root/'references.zip'
            master='a_cinematic_detailed_illustration_in_the_same_rea.png'
            board='a_cinematic_storyboard_collage_with_four_panels_t.png'
            with zipfile.ZipFile(archive,'w') as z:
                z.writestr(master,image.read_bytes());z.writestr(board,image.read_bytes())
            bound,receipt=intake_package(archive,root,manifest,rights_uri='TEST owner permission',synthesis_rights_confirmed=True)
            self.assertEqual(len(receipt['references']),2)
            self.assertEqual(bound['references'][0]['sha256'],digest)
            with self.assertRaisesRegex(ValueError,'PACKAGE_HASH'):
                intake_package(archive,root,manifest,rights_uri='TEST',synthesis_rights_confirmed=True,expected_package_sha256='0'*64)
            with zipfile.ZipFile(archive,'a') as z:z.writestr('../bad.png',b'bad')
            with self.assertRaisesRegex(ValueError,'Unexpected ZIP'):
                intake_package(archive,root,manifest,rights_uri='TEST',synthesis_rights_confirmed=True)
