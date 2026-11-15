"""Synthetic-only CI for the permanent private master -> 15 scene-shot routing."""
import copy
import hashlib
import json
import tempfile
import unittest
from io import BytesIO
from pathlib import Path
from unittest import mock
from zipfile import ZipFile, ZIP_DEFLATED

from tools import scene_reference_archive as archive
from tools import scene_reference_routing as route
from tools.scene_factory import digest
from tools.scene_production_packet import build_packet
from tools.scene_cloudflare_spec_adapter import compile_previews

ROOT=Path(__file__).resolve().parents[1]


class VisualReferenceRoutingTests(unittest.TestCase):
    @staticmethod
    def fake_bundle():
        """Correct archive schema with deliberately tiny FAKE bytes, never owner art."""
        files={};assets=[]
        for name,role in route.CANON_ROLES.items():
            data=b'\xff\xd8\xff SYNTHETIC_'+name.encode()+b'\xff\xd9'
            files[name]=data
            assets.append({'filename':name,'role':role,'sha256':archive.sha256(data),
                           'bytes':len(data),'mime_type':'image/jpeg',
                           'review':{'reference_use':'allowed_as_direction_from_user_upload',
                             'rights_for_new_generated_media':'not_evaluated',
                             'production_shot_accepted':False,
                             'owner_artistic_direction_approved_for_generation':False}})
        for n,role in [('MOTION01_TECHNICAL_ONLY_15s.mp4','motion_diagnostic_only'),
                       ('MOTION02_PRIVATE_MOOD_STUDY_18s.mp4','motion_direction_only')]:
            data=b'\x00\x00\x00\x18ftypisom'+b'X'*40
            files[n]=data;assets.append({'filename':n,'role':role,'sha256':archive.sha256(data),
                      'bytes':len(data),'mime_type':'video/mp4','review':{
                      'production_shot_accepted':False,
                      'owner_artistic_direction_approved_for_generation':False}})
        for n in ('HISTORIC_OPN02_REJECTED_FOR_DAWN_CANDIDATE.png',
                  'HISTORIC_OPN03_REJECTED_FOR_DAWN_CANDIDATE.png'):
            data=b'\x89PNG\r\n\x1a\nSYNTHETIC IEND\xaeB`\x82'
            files[n]=data;assets.append({'filename':n,'role':'historic_cloudflare_image',
                   'sha256':archive.sha256(data),'bytes':len(data),'mime_type':'image/png',
                   'review':{'production_shot_accepted':False,
                             'owner_artistic_direction_approved_for_generation':False}})
        registry={
            'schema_version':1,'registry_id':'MIS-ART-VISUAL-REFERENCE-20261115-V1',
            'generation_gate_closed':True,'no_paid_api_allowed':True,
            'accepted_production_shots':0,'authoritative_media_count':11,
            'user_reference_unique_photos':7,'user_reference_videos':2,
            'historic_cloudflare_candidate_images':2,
            'duplicate_aliases':[{'duplicate_of':route.REF['identity']}],
            'visual_canon':{'current_scene_light':'dawn not sunset'},'assets':assets,
        }
        files[archive.REGISTRY]=json.dumps(registry).encode('utf-8')
        files[archive.README]=b'FAKE TEST ONLY'
        buff=BytesIO()
        with ZipFile(buff,'w',ZIP_DEFLATED) as z:
            for name,data in sorted(files.items()):z.writestr(name,data)
        return buff.getvalue()

    def setUp(self):
        scene=json.loads((ROOT/'episodes/berakhot-01-01/scene-prologue-v02.json').read_text())
        bible=json.loads((ROOT/scene['bible']['path']).read_text())
        self.packet=build_packet(scene,bible,ROOT)
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        old_ref=self.root/'private-media/old-engine-fixture.png'
        old_ref.parent.mkdir(parents=True)
        old_ref.write_bytes(b'FAKE_MODEL_INPUT_NOT_IMAGE')
        h=archive.sha256(old_ref.read_bytes())
        template={
            'schema_version':1,
            'model':{'id':'black-forest-labs/FLUX.2-klein-4B','revision':'UNVERIFIED'},
            'size':[1024,576],
            'style':'OLD SUNSET STYLE MUST NOT BE USED',
            'references':[{'path':'private-media/old-engine-fixture.png','sha256':h,
                           'synthesis_rights_confirmed':True,'expected_sha256':h}],
            'available_backends':{'cloudflare':{'type':'cloudflare',
                'model':'@cf/black-forest-labs/flux-2-klein-4b'}},
        }
        self.preview=compile_previews(self.packet,template,self.root)
        self.synthetic=self.fake_bundle()
        self.zip=self.root/'private-source.zip'
        self.zip.write_bytes(self.synthetic)
        fake_sha=archive.sha256(self.synthetic)
        original_validator=archive.validate_bytes
        self.patches=[
            mock.patch.object(route,'BUNDLE_SHA256',fake_sha),
            mock.patch.object(route,'validate_bytes',side_effect=lambda blob:
                original_validator(blob,expected_bundle_sha256=fake_sha)),
            mock.patch.object(archive,'validate_bytes',side_effect=lambda blob:
                original_validator(blob,expected_bundle_sha256=fake_sha)),
        ]
        for patch in self.patches:patch.start()
        self.addCleanup(lambda:[patch.stop() for patch in reversed(self.patches)])

    def test_actual_15_shot_direction_routes_correct_references_no_inference(self):
        out=route.build_reference_plan(self.packet,self.preview,self.zip,self.root,restore=True)
        self.assertEqual(out['visual_reference_master']['routed_shots'],15)
        self.assertEqual(out['provider_calls'],0)
        self.assertFalse(out['provider_dispatch_authorized'])
        self.assertEqual(route.summarize(out)['new_images_generated'],0)
        byid={j['shot_id']:j for j in out['jobs']}
        self.assertEqual([r['filename'] for r in byid['EP-P07']['owner_private_reference_candidates']],
                         [route.REF['identity'],route.REF['rear'],route.REF['environment']])
        self.assertEqual([r['filename'] for r in byid['EP-P09']['owner_private_reference_candidates']],
                         [route.REF['identity'],route.REF['expression'],
                          route.REF['conversation'],route.REF['alternative']])
        self.assertNotIn(route.REF['rear'],[r['filename'] for r in byid['EP-P01']['owner_private_reference_candidates']])
        for before,after in zip(self.preview['jobs'],out['jobs']):
            # This vital invariant prevents changing Cloudflare provider conditioning by accident.
            self.assertEqual(before['engine_spec_preview']['references'],
                             after['engine_spec_preview']['references'])
            self.assertTrue(all(not a['synthesis_rights_confirmed'] and
                                not a['production_shot_accepted']
                                for a in after['owner_private_reference_candidates']))
            self.assertNotIn(route.REF['moodboard'],[x['filename'] for x in after['owner_private_reference_candidates']])
            self.assertNotIn('HISTORIC_OPN02',[x['filename'] for x in after['owner_private_reference_candidates']])
            self.assertTrue(after['blockers'])
            self.assertEqual(after['engine_spec_preview']['director']['time_of_day'],'dawn')
            self.assertNotEqual(after['reference_aware_future_asset_key'],after['asset_key'])
        second=route.build_reference_plan(self.packet,self.preview,self.zip,self.root,restore=True)
        self.assertEqual(second['preview_sha256'],out['preview_sha256'])
        self.assertEqual(digest({k:v for k,v in out.items() if k!='preview_sha256'}),out['preview_sha256'])

    def test_changed_restored_bytes_fail_closed(self):
        route.build_reference_plan(self.packet,self.preview,self.zip,self.root,restore=True)
        f=self.root/route.PRIVATE_SUBDIR/route.REF['identity']
        f.write_bytes(b'FORGED OWNER IMAGE')
        with self.assertRaisesRegex(route.ReferenceRoutingError,'RESTORE_FAILED|PRIVATE_BYTES_CHANGED'):
            route.build_reference_plan(self.packet,self.preview,self.zip,self.root,restore=True)

    def test_forged_preview_hash_and_dawn_axis_rejected(self):
        p=copy.deepcopy(self.preview)
        p['jobs'][6]['engine_spec_preview']['director']['axis']='north side'
        with self.assertRaisesRegex(route.ReferenceRoutingError,'CLOUD_PREVIEW_CHANGED'):
            route.build_reference_plan(self.packet,p,self.zip,self.root,restore=True)
        p['preview_sha256']=digest({k:v for k,v in p.items() if k!='preview_sha256'})
        with self.assertRaisesRegex(route.ReferenceRoutingError,'DAWN_CAST_AXIS_CONFLICT'):
            route.build_reference_plan(self.packet,p,self.zip,self.root,restore=True)

    def test_missing_owner_bundle_fails_closed_not_provider(self):
        self.zip.unlink()
        with self.assertRaisesRegex(route.ReferenceRoutingError,'BUNDLE_MISSING'):
            route.build_reference_plan(self.packet,self.preview,self.zip,self.root,restore=True)

    def test_staging_no_restore_requires_private_exact_bytes(self):
        with self.assertRaisesRegex(route.ReferenceRoutingError,'NOT_RESTORED_PRIVATE'):
            route.build_reference_plan(self.packet,self.preview,self.zip,self.root,restore=False)


if __name__=='__main__':unittest.main()