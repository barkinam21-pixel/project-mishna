"""Offline audit regressions. No external credentials, media synthesis or provider calls."""
import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, Mock
from tools.private_drive_runtime import Drive, validate_journal, DriveBlocked, prepare_opn02, verify_restored_candidates
from tools.comfy_scene_images import visual_request_key, ensure_visual_request_new


class JournalSafetyTests(unittest.TestCase):
    def test_oversized_snapshot_blocked_before_any_remote_call(self):
        request=Mock();drive=Drive(request);drive.max_file_bytes=4
        with self.assertRaisesRegex(DriveBlocked,'WRITE_EXCEEDS_READBACK_LIMIT'):
            drive.replace('EXISTING_SNAPSHOT',b'12345','application/zip')
        request.assert_not_called()
    def state(self):
        return {'entries':{'key':{'status':'SUBMISSION_UNCERTAIN','spec':{'seed':1}}},
                'attempts':[{'key':'key','native_sha256':'a'*64}]}

    def test_initial_and_snapshot_continuity(self):
        previous=self.state();new=copy.deepcopy(previous)
        new['attempts'].append({'key':'next'})
        new['entries']['key'].update(status='CANDIDATE',sha256='b'*64,path='private-media/a.png')
        self.assertIs(validate_journal(new,previous,['a'*64]),new)

    def test_historical_floor_cannot_be_reset_in_fresh_runner(self):
        with self.assertRaisesRegex(DriveBlocked,'HISTORICAL_ATTEMPTS_MISSING'):
            validate_journal({'entries':{},'attempts':[]},baseline=['a'*64])

    def test_wrong_history_order_or_deleted_entry_blocks(self):
        old=self.state()
        for change in ({'attempts':[]},{'entries':{}}):
            with self.subTest(change=change),self.assertRaises(DriveBlocked):
                validate_journal(old|change,old)

    def test_candidate_bytes_or_direction_cannot_be_rewritten(self):
        old=self.state();old['entries']['key'].update(status='CANDIDATE',sha256='b'*64,path='private-media/a.png')
        for change in ({'sha256':'c'*64},{'spec':{'seed':2}},{'status':'SUBMISSION_UNCERTAIN'}):
            new=copy.deepcopy(old);new['entries']['key'].update(change)
            with self.subTest(change=change),self.assertRaises(DriveBlocked):
                validate_journal(new,old)

    def test_accepted_never_demoted_by_checkpoint(self):
        old=self.state();old['entries']['key']['status']='ACCEPTED'
        new=copy.deepcopy(old);new['entries']['key']['status']='CANDIDATE'
        with self.assertRaisesRegex(DriveBlocked,'STATUS_ROLLBACK'):
            validate_journal(new,old)

    def test_invalid_schema_blocks(self):
        for invalid in ([],{}, {'entries':[]},{'entries':{},'attempts':{}}, {'entries':{'key':'bad'}}, {'entries':{},'attempts':[None]}, {'entries':{'key':{'status':'MADE_UP'}}}):
            with self.subTest(invalid=invalid),self.assertRaises(DriveBlocked):
                validate_journal(invalid)

    def test_safety_refresh_never_changes_visual_identity(self):
        old={'seed':1,'prompt':'TEST','backend':{'type':'cloudflare','model':'TEST','safety':{'verified_at':'old','free_hard_cap_verified':False}}}
        new=copy.deepcopy(old);new['backend']['safety']={'verified_at':'new','free_hard_cap_verified':True}
        self.assertEqual(visual_request_key(old),visual_request_key(new))
        with self.assertRaisesRegex(ValueError,'NO_RESUBMISSION'):
            ensure_visual_request_new(new,{'previous':{'status':'SUBMISSION_UNCERTAIN','spec':old}},'new-key')
        self.assertNotEqual(visual_request_key(old),visual_request_key(new|{'seed':2}))
        ensure_visual_request_new(new|{'seed':2},{'previous':{'spec':old}},'new-key')

    def test_preparation_rejects_journal_before_reading_any_input(self):
        with tempfile.TemporaryDirectory() as tmp,patch('tools.cloudflare_image_backend.CloudflareClient') as provider:
            with self.assertRaisesRegex(DriveBlocked,'INVALID_PRIVATE_JOURNAL'):
                prepare_opn02(Path(tmp),Path(tmp),{})
            provider.assert_not_called()

    def test_changed_cache_key_still_blocks_duplicate_before_client_prepare(self):
        from tools.comfy_scene_images import _run
        old={'seed':1,'prompt':'TEST','backend':{'type':'cloudflare','safety':{'verified_at':'old'}}}
        new=copy.deepcopy(old);new['backend']['safety']['verified_at']='new'
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);out=root/'private-media';out.mkdir()
            (out/'state.json').write_text(json.dumps({'entries':{'old-key':{'status':'SUBMISSION_UNCERTAIN','spec':old}}}))
            row={'id':'OPN02','key':'new-key','spec':new,'missing':[]}
            manifest={'backend':{'type':'cloudflare'},'authorization':{'generation_approved':True,'zero_cost_compute_verified':True,'component_licenses_verified':True,'approved_shot_ids':['OPN02'],'max_submissions':1}}
            client=Mock()
            with patch('tools.comfy_scene_images.specifications',return_value=[row]),self.assertRaisesRegex(ValueError,'NO_RESUBMISSION'):
                _run(manifest,root,out,client,True)
            client.prepare.assert_not_called();client.submit.assert_not_called()

    def test_snapshot_candidate_registry_must_match_restored_bytes(self):
        import hashlib
        from PIL import Image
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);work=root/'private-media/studio';work.mkdir(parents=True)
            p=work/'existing.png';Image.new('RGB',(16,16),'red').save(p)
            entry={'status':'CANDIDATE','path':'private-media/studio/existing.png','sha256':hashlib.sha256(p.read_bytes()).hexdigest()}
            (work/'candidates.json').write_text(json.dumps({'OPN02':entry}))
            report=verify_restored_candidates(root,{'entries':{}})
            self.assertEqual(report[0]['status'],'CANDIDATE_NEEDS_HUMAN_REVIEW')
            self.assertFalse(report[0]['native_original_verified'])
            self.assertFalse(report[0]['approval_granted_by_preparation'])
            p.write_bytes(b'CHANGED')
            with self.assertRaisesRegex(DriveBlocked,'CANDIDATE_INTEGRITY_FAILED'):
                verify_restored_candidates(root,{'entries':{}})


if __name__=='__main__':unittest.main()
