"""No-network first-dawn-shot conditioning tests using synthetic private art."""
import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tools import scene_native_conditioning_preview as native
from tools import scene_reference_archive as archive
from tools import scene_reference_routing as routing
from tools.scene_factory import digest
from tools.scene_production_packet import build_packet
from tools.scene_cloudflare_spec_adapter import compile_previews
from tests.test_scene_reference_routing import VisualReferenceRoutingTests

ROOT = Path(__file__).resolve().parents[1]


class OwnerNativeConditioningTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        scene=json.loads((ROOT/'episodes/berakhot-01-01/scene-prologue-v02.json').read_text())
        bible=json.loads((ROOT/scene['bible']['path']).read_text())
        packet=build_packet(scene,bible,ROOT)
        old=self.root/'private-media/old-engine.png'
        old.parent.mkdir(parents=True)
        old.write_bytes(b'FAKE_LEGACY_REF_NOT_ART')
        h=hashlib.sha256(old.read_bytes()).hexdigest()
        template={'schema_version':1, 'model':{'id':'black-forest-labs/FLUX.2-klein-4B'},
                  'size':[1024,576], 'references':[{'path':'private-media/old-engine.png',
                  'sha256':h,'synthesis_rights_confirmed':True}],
                  'available_backends':{'cloudflare':{'type':'cloudflare',
                  'model':'@cf/black-forest-labs/flux-2-klein-4b'}}}
        base=compile_previews(packet,template,self.root)
        blob=VisualReferenceRoutingTests.fake_bundle()
        bundle=self.root/'source.zip';bundle.write_bytes(blob)
        original_validator=archive.validate_bytes
        p=[mock.patch.object(routing,'BUNDLE_SHA256',archive.sha256(blob)),
           mock.patch.object(routing,'validate_bytes',side_effect=lambda raw:
               original_validator(raw,expected_bundle_sha256=archive.sha256(blob))),
           mock.patch.object(archive,'validate_bytes',side_effect=lambda raw:
               original_validator(raw,expected_bundle_sha256=archive.sha256(blob)))]
        for patch in p:patch.start()
        self.addCleanup(lambda:[patch.stop() for patch in reversed(p)])
        self.plan=routing.build_reference_plan(packet,base,bundle,self.root,restore=True)

    def test_p07_preview_uses_real_owner_role_mapping_not_legacy_template(self):
        old=self.plan['jobs'][6]['engine_spec_preview']['references']
        result=native.draft_conditioning(self.plan,self.root)
        refs=result['proposed_provider_shape']['references']
        self.assertEqual([r['path'].split('/')[-1] for r in refs],list(native.NAMES))
        self.assertEqual([r['role'] for r in refs],list(native.ROLES))
        self.assertEqual(len(refs),3)
        self.assertNotEqual(refs,old)
        self.assertEqual(self.plan['jobs'][6]['engine_spec_preview']['references'],old)
        self.assertTrue(all(r['synthesis_rights_confirmed'] is False for r in refs))
        self.assertFalse(result['provider_dispatch_authorized'])
        self.assertEqual(result['provider_calls'],0)
        self.assertEqual(result['proposed_provider_shape']['director']['time_of_day'],'dawn')
        self.assertTrue(result['no_automatic_retry'])
        self.assertEqual(result['draft_sha256'],native.digest({k:v for k,v in result.items() if k!='draft_sha256'}))

    def test_unchanged_preview_is_deterministic_and_rekeyed(self):
        first=native.draft_conditioning(self.plan,self.root)
        second=native.draft_conditioning(self.plan,self.root)
        self.assertEqual(first['draft_sha256'],second['draft_sha256'])
        self.assertNotEqual(first['proposed_provider_shape']['seed'],self.plan['jobs'][6]['engine_spec_preview']['seed'])

    def test_private_ref_mutation_and_symlink_rejected(self):
        a=self.root/routing.PRIVATE_SUBDIR/native.NAMES[0]
        original=a.read_bytes();a.write_bytes(b'MUTATED')
        with self.assertRaisesRegex(native.NativePreviewBlocked,'PRIVATE_BYTES_NOT_VERIFIED'):
            native.draft_conditioning(self.plan,self.root)
        a.unlink();a.symlink_to(self.root/'private-media/old-engine.png')
        with self.assertRaisesRegex(native.NativePreviewBlocked,'PRIVATE_BYTES_NOT_VERIFIED'):
            native.draft_conditioning(self.plan,self.root)

    def test_cannot_promote_rights_or_change_dawn_under_rehashed_plan(self):
        changed=copy.deepcopy(self.plan)
        changed['jobs'][6]['owner_private_reference_candidates'][0]['synthesis_rights_confirmed']=True
        changed['preview_sha256']=digest({k:v for k,v in changed.items() if k!='preview_sha256'})
        with self.assertRaisesRegex(native.NativePreviewBlocked,'RIGHTS_OR_HASH_CHANGED'):
            native.draft_conditioning(changed,self.root)
        changed=copy.deepcopy(self.plan)
        changed['jobs'][6]['engine_spec_preview']['director']['time_of_day']='sunset'
        changed['preview_sha256']=digest({k:v for k,v in changed.items() if k!='preview_sha256'})
        with self.assertRaisesRegex(native.NativePreviewBlocked,'DAWN_CAST_AXIS_CHANGED'):
            native.draft_conditioning(changed,self.root)

    def test_unverified_digest_and_removed_closed_gate_rejected(self):
        changed=copy.deepcopy(self.plan)
        changed['jobs'][6]['engine_spec_preview']['prompt']='CHANGED'
        with self.assertRaisesRegex(native.NativePreviewBlocked,'PLAN_HASH_CHANGED'):
            native.draft_conditioning(changed,self.root)
        changed=copy.deepcopy(self.plan)
        changed['jobs'][6]['blockers'].remove('HOSTED_M3_AND_GENERATION_POLICY_CLOSED')
        changed['preview_sha256']=digest({k:v for k,v in changed.items() if k!='preview_sha256'})
        with self.assertRaisesRegex(native.NativePreviewBlocked,'GATE_MISSING'):
            native.draft_conditioning(changed,self.root)


if __name__=='__main__':unittest.main()