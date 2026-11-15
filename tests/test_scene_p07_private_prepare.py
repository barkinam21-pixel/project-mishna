"""No-network tests for one-command owner-private P07 staging."""
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from tools import scene_p07_private_prepare as p07


class P07PrivatePrepareTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / 'private-media').mkdir()
        self.plan = {'private': 'test-only'}
        self.draft = {
            'shot_id': 'EP-P07',
            'provider_dispatch_authorized': False,
            'provider_calls': 0,
            'rights_for_synthesis': 'NOT_EVALUATED',
            'candidate_count': 3,
            'draft_sha256': 'a' * 64,
        }

    def _prepare(self):
        with patch.object(p07, 'prepare_owner_private_scene', return_value={
            'private_review_plan': self.plan}), patch.object(
            p07, 'draft_conditioning', return_value=self.draft
        ):
            return p07.prepare_p07(locator={}, drive=object(),
                                  project_root=self.root, legacy_template='unused')

    def test_draft_persists_privately_and_second_call_is_idempotent(self):
        first = self._prepare()
        self.assertEqual(first['status'], 'P07_OWNER_PRIVATE_DRAFT_PREPARED_NO_INFERENCE')
        self.assertFalse(first['private_draft_cache_hit'])
        self.assertEqual(first['provider_calls'], 0)
        self.assertFalse(first['generation_authorized'])
        self.assertTrue(self._prepare()['private_draft_cache_hit'])
        target = self.root / 'private-media' / ('p07-native-conditioning-' + 'a'*64 + '.json')
        self.assertEqual(json.loads(target.read_text()), self.draft)

    def test_mutated_private_cache_rejected_without_overwrite(self):
        self._prepare()
        target = self.root / 'private-media' / ('p07-native-conditioning-' + 'a'*64 + '.json')
        target.write_text('tampered')
        with self.assertRaisesRegex(p07.OwnerPrivateSceneBlocked, 'CACHE_CHANGED'):
            self._prepare()
        self.assertEqual(target.read_text(), 'tampered')

    def test_public_actions_forbidden_before_any_drive(self):
        with patch.dict(os.environ, {'GITHUB_ACTIONS':'true'}), patch.object(
            p07, 'prepare_owner_private_scene'
        ) as drive:
            with self.assertRaisesRegex(p07.OwnerPrivateSceneBlocked, 'PUBLIC_ACTIONS'):
                self._prepare()
            drive.assert_not_called()

    def test_draft_cannot_be_promoted_by_mocked_pipeline(self):
        self.draft['provider_dispatch_authorized'] = True
        with self.assertRaisesRegex(p07.NativePreviewBlocked, 'UNEXPECTEDLY_EXECUTABLE'):
            self._prepare()
        self.assertFalse(list((self.root/'private-media').glob('p07-native-conditioning-*')))

    def test_private_draft_symlink_rejected(self):
        target = self.root / 'private-media' / ('p07-native-conditioning-' + 'a'*64 + '.json')
        target.symlink_to(self.root / 'outside')
        with self.assertRaisesRegex(p07.OwnerPrivateSceneBlocked, 'SYMLINK_FORBIDDEN'):
            self._prepare()


if __name__ == '__main__':
    unittest.main()
