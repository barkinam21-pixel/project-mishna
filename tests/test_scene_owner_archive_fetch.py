"""Synthetic Drive reads only; no credentials, OAuth or private files in CI."""
import hashlib
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest import mock

from tests.test_scene_reference_archive import ReferenceArchiveTests
from tools import scene_owner_archive_fetch as stage
from tools import scene_reference_archive as ra


class FakeDrive:
    def __init__(self, data):
        self.data = data
        self.metadata_calls = []
        self.download_calls = []
        self.shared = False
    def metadata(self, fid):
        self.metadata_calls.append(fid)
        mime = ('application/vnd.google-apps.folder' if fid == 'ownerFolder0123456'
                else 'application/zip')
        return {'id':fid,'mimeType':mime,'shared':self.shared,
                'permissions':[{'type':'user','role':'owner'}]}
    def download(self, fid):
        self.download_calls.append(fid)
        return self.data


def fake_locator(data):
    sha=hashlib.sha256(data).hexdigest()
    names=[ra.BUNDLE_FILENAME]+[f'other{i:02d}.jpg' for i in range(13)]
    return {'schema_version':1,'privacy':'OWNER_PRIVATE_ONLY_NO_PUBLICATION',
            'project':'barkinam21-pixel/project-mishna',
            'folder_name':'00-PRIVATE-VISUAL-REFERENCE-MASTER-20261115',
            'folder_id':'ownerFolder0123456','bundle_filename':ra.BUNDLE_FILENAME,
            'bundle_sha256':sha,
            'lookup_mode':'use exact Drive file IDs; verify bytes SHA; no fuzzy search and no live inference',
            'files':[{'filename':name,'sha256':sha,
                      'drive_file_id':f'ownerAssetFile{i:02d}12345'}
                     for i,name in enumerate(names)]}


class OwnerArchiveFetchTests(unittest.TestCase):
    def setUp(self):
        self.data=ReferenceArchiveTests().fake_bundle()
        self.sha=hashlib.sha256(self.data).hexdigest()
        self.locator=fake_locator(self.data)
        self.drive=FakeDrive(self.data)
        original=ra.validate_bytes
        self.patchers=[
            mock.patch.object(stage,'BUNDLE_SHA256',self.sha),
            mock.patch.object(stage,'validate_bytes',side_effect=lambda blob:
                             original(blob,expected_bundle_sha256=self.sha)),
        ]
        for p in self.patchers:
            p.start();self.addCleanup(p.stop)
        self.tmp=TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)/'private-media'

    def test_real_shape_synthetic_drive_read_atomic_private_cache_and_resume(self):
        report=stage.fetch_archive(self.locator,self.drive,self.root)
        self.assertEqual(report['status'],'OWNER_PRIVATE_REFERENCE_ARCHIVE_VERIFIED')
        self.assertEqual(report['bundle_sha256'],self.sha)
        self.assertEqual(report['remote_reads'],1)
        self.assertFalse(report['cache_hit'])
        self.assertFalse(report['generation_authorized'])
        self.assertEqual(report['model_calls'],0)
        self.assertEqual(report['remote_writes'],0)
        self.assertEqual(Path(report['archive_path']).read_bytes(),self.data)
        self.assertEqual(self.drive.download_calls,['ownerAssetFile0012345'])
        self.assertEqual(self.drive.metadata_calls,['ownerFolder0123456','ownerAssetFile0012345'])
        status=stage.safe_status(report)
        self.assertNotIn('archive_path',status)
        self.assertNotIn('drive_file_id',str(status))
        cached=stage.fetch_archive(self.locator,self.drive,self.root)
        self.assertTrue(cached['cache_hit'])
        self.assertEqual(cached['remote_reads'],0)
        self.assertEqual(len(self.drive.download_calls),1)

    def test_shared_folder_blocks_before_download_and_write(self):
        self.drive.shared=True
        with self.assertRaisesRegex(stage.OwnerArchiveFetchBlocked,'DRIVE_NOT_PRIVATE'):
            stage.fetch_archive(self.locator,self.drive,self.root)
        self.assertEqual(self.drive.download_calls,[])
        self.assertFalse(self.root.exists())

    def test_corrupt_download_blocks_without_cache(self):
        self.drive.data=b'corrupt zip'
        with self.assertRaisesRegex(stage.OwnerArchiveFetchBlocked,'PINNED_VERIFICATION'):
            stage.fetch_archive(self.locator,self.drive,self.root)
        self.assertFalse(self.root.exists())

    def test_cache_tampering_blocks_without_overwrite_or_redownload(self):
        result=stage.fetch_archive(self.locator,self.drive,self.root)
        Path(result['archive_path']).write_bytes(b'corrupted cache')
        with self.assertRaisesRegex(stage.OwnerArchiveFetchBlocked,'CACHE_TAMPERED'):
            stage.fetch_archive(self.locator,self.drive,self.root)
        self.assertEqual(len(self.drive.download_calls),1)
        self.assertEqual(Path(result['archive_path']).read_bytes(),b'corrupted cache')

    def test_locator_forgeries_fail_before_remote_access(self):
        from copy import deepcopy
        variants=[]
        for mutator in (
            lambda x: x.update(privacy='PUBLIC'),
            lambda x: x['files'].append(x['files'][0]),
            lambda x: x['files'][0].update(sha256='0'*64),
            lambda x: x['files'][0].update(drive_file_id='../escape'),
            lambda x: x.update(folder_id=''),
            lambda x: x.update(bundle_filename='another.zip'),
        ):
            v=deepcopy(self.locator);mutator(v);variants.append(v)
        for variant in variants:
            with self.subTest(variant=variant.get('privacy')):
                with self.assertRaises(stage.OwnerArchiveFetchBlocked):
                    stage.fetch_archive(variant,self.drive,self.root)
        self.assertFalse(self.drive.metadata_calls)
        self.assertFalse(self.drive.download_calls)

    def test_symlinked_private_destination_fails_closed(self):
        with TemporaryDirectory() as other:
            self.root.symlink_to(Path(other),target_is_directory=True)
            with self.assertRaisesRegex(stage.OwnerArchiveFetchBlocked,'DESTINATION_NOT_PRIVATE'):
                stage.fetch_archive(self.locator,self.drive,self.root)
            self.assertFalse(self.drive.metadata_calls)


if __name__=='__main__':unittest.main()
