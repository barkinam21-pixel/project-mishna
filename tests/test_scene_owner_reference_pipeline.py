"""Offline scene integration: fake owner Drive + real 15-shot manifest, never network."""
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase, mock

from tools import scene_reference_archive as archive
from tools import scene_reference_routing as route
from tools import scene_owner_archive_fetch as fetcher
from tools import scene_owner_reference_pipeline as pipeline
from tests.test_scene_reference_routing import VisualReferenceRoutingTests
from tests.test_scene_owner_archive_fetch import FakeDrive, fake_locator

ROOT = Path(__file__).resolve().parents[1]


class OwnerPrivateSceneIntegrationTests(TestCase):
    def setUp(self):
        # Synthetic FakeDrive only: emulate an owner host without weakening
        # the production public-Actions guard. The explicit true test overrides.
        self.owner_host_fixture = mock.patch.dict(os.environ, {'GITHUB_ACTIONS': 'false'})
        self.owner_host_fixture.start()
        self.addCleanup(self.owner_host_fixture.stop)
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = json.loads((ROOT / 'episodes/berakhot-01-01/scene-prologue-v02.json').read_text())
        paths = [Path('episodes/berakhot-01-01/scene-prologue-v02.json'),
                 Path(self.source['bible']['path']),
                 Path(self.source['script']['path'])]
        for rel in paths:
            p = self.root / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes((ROOT / rel).read_bytes())
        old_ref = self.root / 'private-media/legacy-fixture.png'
        old_ref.parent.mkdir(parents=True, exist_ok=True)
        old_ref.write_bytes(b'FAKE_OLD_REFERENCE_NOT_IMAGE')
        h=archive.sha256(old_ref.read_bytes())
        self.template=self.root/'pinned-old-template.json'
        self.template.write_text(json.dumps({
            'schema_version':1,
            'model':{'id':'black-forest-labs/FLUX.2-klein-4B'},
            'size':[1024,576],
            'references':[{'path':'private-media/legacy-fixture.png',
                           'sha256':h,'expected_sha256':h,
                           'synthesis_rights_confirmed':True}],
            'available_backends':{'cloudflare':{'type':'cloudflare',
                    'model':'@cf/black-forest-labs/flux-2-klein-4b'}},
        }))
        data=VisualReferenceRoutingTests.fake_bundle()
        self.locator=fake_locator(data)
        self.drive=FakeDrive(data)
        sha=archive.sha256(data)
        original=archive.validate_bytes
        patches=[
            mock.patch.object(fetcher,'BUNDLE_SHA256',sha),
            mock.patch.object(fetcher,'validate_bytes',side_effect=lambda raw:
                              original(raw,expected_bundle_sha256=sha)),
            mock.patch.object(route,'BUNDLE_SHA256',sha),
            mock.patch.object(route,'validate_bytes',side_effect=lambda raw:
                              original(raw,expected_bundle_sha256=sha)),
            mock.patch.object(archive,'validate_bytes',side_effect=lambda raw:
                              original(raw,expected_bundle_sha256=sha)),
        ]
        for p in patches:
            p.start();self.addCleanup(p.stop)

    def run_private(self):
        return pipeline.prepare_owner_private_scene(locator=self.locator, drive=self.drive,
                        project_root=self.root,legacy_template=self.template)

    def test_actual_15_shots_fetched_once_privately_then_cached_without_inference(self):
        result=self.run_private()
        report=result['safe_summary']
        self.assertEqual(report['routed_shots'],15)
        self.assertFalse(report['provider_dispatch_authorized'])
        self.assertEqual(report['provider_calls'],0)
        self.assertEqual(report['new_images_generated'],0)
        self.assertEqual(report['archive_fetch']['remote_reads'],1)
        self.assertNotIn('drive_file_id',str(report))
        self.assertNotIn('archive_path',str(report))
        self.assertEqual(len(result['private_review_plan']['jobs']),15)
        second=self.run_private()
        self.assertTrue(second['safe_summary']['archive_fetch']['cache_hit'])
        self.assertEqual(second['safe_summary']['archive_fetch']['remote_reads'],0)
        self.assertEqual(len(self.drive.download_calls),1)
        self.assertEqual(result['private_review_plan']['preview_sha256'],
                         second['private_review_plan']['preview_sha256'])

    def test_public_actions_rejected_before_drive_auth_or_read(self):
        with mock.patch.dict(os.environ,{'GITHUB_ACTIONS':'true'}):
            with self.assertRaisesRegex(pipeline.OwnerPrivateSceneBlocked,'PUBLIC_GITHUB_ACTIONS'):
                self.run_private()
        self.assertEqual(self.drive.metadata_calls,[])
        self.assertEqual(self.drive.download_calls,[])

    def test_shared_owner_folder_and_corrupt_source_rejected_before_routing(self):
        self.drive.shared=True
        with self.assertRaisesRegex(fetcher.OwnerArchiveFetchBlocked,'NOT_PRIVATE'):
            self.run_private()
        self.assertEqual(self.drive.download_calls,[])
        self.drive.shared=False
        self.drive.data=b'CORRUPTED_REFERENCE'
        with self.assertRaisesRegex(fetcher.OwnerArchiveFetchBlocked,'PINNED_VERIFICATION'):
            self.run_private()
        self.assertEqual(len(self.drive.download_calls),1)
        self.assertFalse((self.root/'private-media/visual-reference-master-20261115').exists())

    def test_corrupted_cached_owner_media_never_repaired_silently(self):
        self.run_private()
        target=self.root/'private-media/visual-reference-master-20261115'/route.REF['identity']
        target.write_bytes(b'TAMPERED')
        with self.assertRaisesRegex(route.ReferenceRoutingError,'PRIVATE_RESTORE_FAILED'):
            self.run_private()
        self.assertEqual(len(self.drive.download_calls),1)

class PrivateProcessBoundaryTests(TestCase):
    def test_public_actions_cli_refuses_before_access_to_locator(self):
        with mock.patch.dict(os.environ,{'GITHUB_ACTIONS':'true'}):
            self.assertEqual(pipeline.main(['--root','/not-existing',
                 '--legacy-runtime','/not-existing','--legacy-template','/not-existing',
                 '--private-locator','/not-existing']),2)

    def test_private_plan_local_cache_exact_bytes_and_tamper_block(self):
        with TemporaryDirectory() as tmp:
            root=Path(tmp)
            (root/'private-media').mkdir()
            plan={'shot_count':15,'provider_dispatch_authorized':False,
                  'jobs':[{'shot_id':f'EP-P{i:02d}'} for i in range(1,16)]}
            a=pipeline.persist_private_plan(plan,root)
            b=pipeline.persist_private_plan(plan,root)
            self.assertFalse(a['cache_hit'])
            self.assertTrue(b['cache_hit'])
            self.assertEqual(a['plan_sha256'],b['plan_sha256'])
            target=root/'private-media'/('owner-scene-reference-plan-'+a['plan_sha256']+'.json')
            target.write_bytes(b'CORRUPTED')
            with self.assertRaisesRegex(pipeline.OwnerPrivateSceneBlocked,'CACHE_CHANGED'):
                pipeline.persist_private_plan(plan,root)

    def test_immutable_legacy_source_hash_checker(self):
        raw=b'fake historical code'
        import hashlib
        want=hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest()
        self.assertEqual(pipeline._git_blob_sha(raw),want)
        self.assertNotEqual(pipeline._git_blob_sha(raw+b'changed'),want)