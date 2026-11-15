"""Real contract tests over synthetic in-memory bundles; no private photos in CI."""
from io import BytesIO
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock
from zipfile import ZipFile, ZIP_DEFLATED

from tools import scene_reference_archive as ref


class ReferenceArchiveTests(unittest.TestCase):
    def fake_bundle(self, corrupt=None):
        mime_samples={'jpg':b'\xff\xd8\xffA camera photo\xff\xd9',
                      'png':b'\x89PNG\r\n\x1a\nxxxxIEND\xaeB`\x82',
                      'mp4':b'\x00\x00\x00\x18ftypisom\x00\x00\x00\x00' + b'0'*40}
        entries=[];files={}
        for i in range(1,8):
            name=f'REF{i:02d}_TEST.jpg';data=mime_samples['jpg']+bytes([i])  # fixture only
            # JPEG terminal marker required
            data=b'\xff\xd8\xffA fake '+bytes([i])+b'\xff\xd9'
            files[name]=data;entries.append({'filename':name,'sha256':ref.sha256(data),'bytes':len(data),
                  'mime_type':'image/jpeg','role':'cast' if i==1 else 'direction',
                  'review':{'production_shot_accepted':False,'owner_artistic_direction_approved_for_generation':False}})
        for i,role in enumerate(('motion_diagnostic_only','motion_direction_only'),1):
            name=f'MOTION{i:02d}_TEST.mp4';data=mime_samples['mp4']+bytes([i]);files[name]=data
            entries.append({'filename':name,'sha256':ref.sha256(data),'bytes':len(data),
                'mime_type':'video/mp4','role':role,
                'review':{'production_shot_accepted':False,'owner_artistic_direction_approved_for_generation':False}})
        for i in (2,3):
            name=f'HISTORIC_OPN0{i}_TEST.png';data=mime_samples['png'];files[name]=data
            entries.append({'filename':name,'sha256':ref.sha256(data),'bytes':len(data),
                'mime_type':'image/png','role':'historic_cloudflare_image',
                'review':{'production_shot_accepted':False,'owner_artistic_direction_approved_for_generation':False}})
        master={'schema_version':1,'registry_id':'MIS-ART-VISUAL-REFERENCE-20261115-V1',
                'generation_gate_closed':True,'no_paid_api_allowed':True,'accepted_production_shots':0,
                'authoritative_media_count':11,'user_reference_unique_photos':7,'user_reference_videos':2,
                'historic_cloudflare_candidate_images':2,
                'duplicate_aliases':[{'upload_name':'duplicate','duplicate_of':'REF01'}],
                'visual_canon':{'current_scene_light':'dawn not sunset'},'assets':entries}
        if corrupt: corrupt(master,files)
        files[ref.REGISTRY]=json.dumps(master).encode();files[ref.README]=b'Private only'
        result=BytesIO()
        with ZipFile(result,'w',ZIP_DEFLATED) as z:
            for n,data in sorted(files.items()):z.writestr(n,data)
        return result.getvalue()

    def test_bundle_verified_and_offline_restore_idempotent(self):
        data=self.fake_bundle()
        report=ref.validate_bytes(data,expected_bundle_sha256=ref.sha256(data))
        self.assertEqual(report['reference_photos'],7)
        self.assertEqual(report['production_shots_accepted'],0)
        with tempfile.TemporaryDirectory() as d:
            source=Path(d)/'source.zip';source.write_bytes(data)
            original_validator = ref.validate_bytes
            with mock.patch.object(ref,'validate_bytes',side_effect=lambda blob:original_validator(blob, expected_bundle_sha256=ref.sha256(data))):
                self.assertFalse(ref.restore_private(source,Path(d))['cache_hit'])
                self.assertTrue(ref.restore_private(source,Path(d))['cache_hit'])
                bad=Path(d)/'private-media/visual-reference-master-20261115/REF01_TEST.jpg'
                bad.write_bytes(b'corrupt')
                with self.assertRaisesRegex(ref.ReferenceArchiveError,'CACHED_BYTES_CHANGED'):
                    ref.restore_private(source,Path(d))

    def test_reject_disallowed_status_and_tampered_asset(self):
        for mut in (lambda m,f: m['assets'][0]['review'].update(production_shot_accepted=True),
                    lambda m,f: f.__setitem__('REF01_TEST.jpg',b'fake changed'),
                    lambda m,f: m.update(generation_gate_closed=False),
                    lambda m,f: m['assets'][0].update(filename='../escape.jpg'),
                    lambda m,f: m.update(accepted_production_shots=1)):
            data=self.fake_bundle(mut)
            with self.assertRaises(ref.ReferenceArchiveError):
                ref.validate_bytes(data,expected_bundle_sha256=ref.sha256(data))

    def test_wrong_bundle_hash_rejected_before_unzip(self):
        with self.assertRaisesRegex(ref.ReferenceArchiveError,'BUNDLE_HASH_MISMATCH'):
            ref.validate_bytes(self.fake_bundle())

    def test_private_path_required(self):
        data=self.fake_bundle()
        with tempfile.TemporaryDirectory() as d:
            source=Path(d)/'source.zip';source.write_bytes(data)
            for target in ('../leak','public/visuals','/tmp/visuals','private-media/../../leak'):
                with self.assertRaisesRegex(ref.ReferenceArchiveError,'PRIVATE_DESTINATION_REQUIRED'):
                    ref.restore_private(source,Path(d),target)


if __name__=='__main__': unittest.main()