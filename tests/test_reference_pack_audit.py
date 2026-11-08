"""Offline fixtures for missing/changed/mislabeled reference-archive members."""
import hashlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED
from PIL import Image
from tools.reference_pack_audit import ROLES, ACTIVE, audit


def archives(root, tamper=None):
    originals=[]
    for cat,count in ROLES.items():
        for index in range(count):
            fmt='PNG' if cat=='00_PRIMARY_REFERENCE' else 'JPEG'
            stream=io.BytesIO()
            Image.new('RGB',(96,64),(index*20%255,80,120)).save(stream,format=fmt)
            old=f'{cat}/image-{index:02d}.png'
            new=old if fmt=='PNG' else old[:-4]+'.jpg'
            raw=stream.getvalue()
            originals.append((old,new,raw,cat))
    records=[{'archive_path':old,'category':cat,'sha256':hashlib.sha256(raw).hexdigest(),
              'provider_upload_allowed':False,'release_approved':False}
             for old,new,raw,cat in originals]
    master={'records':records}
    full=root/'full.zip';oldsubset=root/'old.zip';newsubset=root/'new.zip'
    with ZipFile(full,'w',ZIP_DEFLATED) as z:
        for old,new,raw,cat in originals:z.writestr(old,raw)
        z.writestr('manifest.json',json.dumps(master))
    with ZipFile(oldsubset,'w',ZIP_DEFLATED) as z:
        for old,new,raw,cat in originals:
            if cat in ACTIVE:z.writestr(old,raw)
        z.writestr('manifest.json',json.dumps(master))
    full_hash=hashlib.sha256(full.read_bytes()).hexdigest()
    old_hash=hashlib.sha256(oldsubset.read_bytes()).hexdigest()
    corrected_records=[]
    with ZipFile(newsubset,'w',ZIP_DEFLATED) as z:
        for old,new,raw,cat in originals:
            if cat not in ACTIVE:continue
            if tamper=='changed_bytes' and old.endswith('01_ACTIVE_GUIDES/image-00.png'):
                raw=b'changed'
            z.writestr(new,raw)
            corrected_records.append({'source_archive_path':old,'archive_path':new,
                 'sha256':hashlib.sha256(raw).hexdigest(),
                 'provider_upload_allowed':True if tamper=='rights' else False,
                 'release_approved':False})
        if tamper=='missing_member':
            # The manifest still lists eight; the ZIP member list lacks one.
            pass
        manifest={'status':'PRIVATE_REFERENCE_ONLY_NOT_APPROVED_FOR_PROVIDER_UPLOAD',
                  'source_full_archive_sha256':full_hash,
                  'source_curated_archive_sha256':old_hash,
                  'records':corrected_records}
        z.writestr('manifest.json',json.dumps(manifest))
    return full,oldsubset,newsubset


class ReferenceAuditTests(unittest.TestCase):
    def test_source_27_and_corrected_8_verified(self):
        with tempfile.TemporaryDirectory() as d:
            r=audit(*archives(Path(d)))
            self.assertEqual((r['full_reference_count'],r['curated_reference_count']),(27,8))
            self.assertEqual((r['original_extension_mismatches'],r['corrected_file_extensions']),(25,6))
            self.assertEqual(r['retained_context_and_hold'],19)
            self.assertFalse(r['rights_or_publication_approved'])

    def test_changed_corrected_bytes_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaisesRegex(ValueError,'original bytes do not match'):
                audit(*archives(Path(d),'changed_bytes'))

    def test_rights_flag_must_remain_false(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaisesRegex(ValueError,'rights gate mismatch'):
                audit(*archives(Path(d),'rights'))

    def test_malformed_duplicate_full_archive_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            full,subset,corrected=archives(Path(d))
            with ZipFile(full,'a',ZIP_DEFLATED) as z:z.writestr('manifest.json','{}')
            with self.assertRaisesRegex(ValueError,'Unsafe reference ZIP contents'):
                audit(full,subset,corrected)


if __name__=='__main__':unittest.main()