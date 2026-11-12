import contextlib
import io
import json
import subprocess
import tempfile
import threading
import unittest
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from tools import authorize_private_drive as auth

CLIENT = {'client_id': 'test.apps.googleusercontent.com', 'client_secret': 'TEST_CLIENT_SECRET'}
TOKEN = {'access_token': 'TEST_ACCESS', 'refresh_token': 'TEST_REFRESH', 'token_type': 'Bearer', 'scope': auth.SCOPE}


def metadata(uid):
    return dict(id=uid, ownedByMe=True, shared=False, permissions=[{'type': 'user', 'role': 'owner'}], capabilities={'canEdit': True})


class DesktopOAuthTests(unittest.TestCase):
    def test_pkce_rfc7636(self):
        self.assertEqual(auth.challenge('dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk'), 'E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM')

    def test_web_client_rejected(self):
        for value in ({'web': CLIENT}, {'installed': []}, {'installed': {'client_id': 'test'}}, {'installed': {'client_id': CLIENT['client_id'], 'client_secret': 12}}):
            with self.subTest(value=value), self.assertRaises(ValueError):
                auth.validate_client(value)

    def test_existing_download_autodetection_no_guessing(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(auth.Path, 'home', return_value=Path(tmp)):
            downloads = Path(tmp) / 'Downloads'
            downloads.mkdir()
            with self.assertRaises(ValueError):
                auth.load_client()
            first = downloads / 'client_secret_existing.json'
            first.write_text(json.dumps({'installed': CLIENT}), encoding='utf-8-sig')
            self.assertEqual(auth.load_client(), CLIENT)
            second = downloads / 'client_secret_other.json'
            second.write_text(json.dumps({'installed': CLIENT}))
            with self.assertRaises(ValueError):
                auth.load_client()
            self.assertEqual(auth.load_client(first), CLIENT)

    def test_invalid_or_web_download_is_not_selected(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(auth.Path, 'home', return_value=Path(tmp)):
            downloads = Path(tmp) / 'Downloads'
            downloads.mkdir()
            (downloads / 'client_secret_web.json').write_text(json.dumps({'web': CLIENT}))
            (downloads / 'client_secret_bad.json').write_text('invalid')
            with self.assertRaises(ValueError):
                auth.load_client()

    def test_native_picker_exact_scope_and_files(self):
        q = urllib.parse.parse_qs(urllib.parse.urlsplit(auth.authorization_url(CLIENT, 'http://127.0.0.1:1234/', 'STATE', 'VERIFIER')).query)
        self.assertEqual(q['scope'], [auth.SCOPE])
        self.assertEqual(q['trigger_onepick'], ['true'])
        self.assertEqual(q['allow_multiple'], ['true'])
        self.assertEqual(q['file_ids'], [','.join(auth.IDS)])
        self.assertEqual(q['include_granted_scopes'], ['false'])
        self.assertEqual(q['code_challenge_method'], ['S256'])
        self.assertEqual(q['access_type'], ['offline'])
        self.assertNotIn('client_secret', q)

    def callback(self, **kwargs):
        return '/?' + urllib.parse.urlencode(dict(state='STATE', code='CODE', picked_file_ids=','.join(reversed(auth.IDS))) | kwargs)

    def test_selection_order_irrelevant(self):
        self.assertEqual(auth.parse_callback(self.callback(), 'STATE'), {'code': 'CODE'})

    def test_invalid_callback_state_path_duplicates(self):
        for value in (self.callback(state='OTHER'), '/favicon.ico?state=STATE', self.callback() + '&code=OTHER', 'http://evil/' + self.callback()[1:], '/?' + 'x' * 16384):
            with self.subTest(value=value[:40]), self.assertRaises(ValueError):
                auth.parse_callback(value, 'STATE')

    def test_missing_wrong_extra_or_duplicate_ids(self):
        for ids in ('', ','.join(auth.IDS[:2]), ','.join(auth.IDS + ['OTHER']), ','.join([auth.IDS[0]] * 3)):
            self.assertEqual(auth.parse_callback(self.callback(picked_file_ids=ids), 'STATE')['error'], 'SELECT_EXACT_THREE_FILES')

    def test_cancelled_and_missing_code(self):
        self.assertEqual(auth.parse_callback(self.callback(error='access_denied'), 'STATE'), {'error': 'CONSENT_CANCELLED'})
        self.assertEqual(auth.parse_callback(self.callback(code=''), 'STATE')['error'], 'AUTHORIZATION_CODE_MISSING')

    def test_real_loopback_callback_and_no_http_logging(self):
        errors = []
        threads = []
        def browser(url):
            q = urllib.parse.parse_qs(urllib.parse.urlsplit(url).query)
            redirect = q['redirect_uri'][0]
            self.assertTrue(redirect.startswith('http://127.0.0.1:'))
            def send():
                try:
                    # Wrong state must not end the legitimate flow.
                    with self.assertRaises(urllib.error.HTTPError):
                        urllib.request.urlopen(redirect + '?state=WRONG', timeout=3)
                    callback = redirect + '?' + urllib.parse.urlencode(dict(state=q['state'][0], code='CODE', picked_file_ids=','.join(auth.IDS)))
                    with urllib.request.urlopen(callback, timeout=3) as response:
                        self.assertEqual(response.headers['Cache-Control'], 'no-store')
                        self.assertNotIn(b'CODE', response.read())
                except Exception as error:
                    errors.append(error)
            thread = threading.Thread(target=send)
            threads.append(thread)
            thread.start()
            return True
        with patch.object(auth.webbrowser, 'open', browser), contextlib.redirect_stderr(io.StringIO()) as err:
            code, verifier, redirect = auth.receive_authorization(CLIENT, timeout=4)
        for thread in threads:
            thread.join(4)
        self.assertFalse(errors)
        self.assertEqual(code, 'CODE')
        self.assertGreaterEqual(len(verifier), 43)
        self.assertEqual(err.getvalue(), '')

    def test_timeout_and_browser_failure(self):
        with patch.object(auth.webbrowser, 'open', return_value=True), self.assertRaisesRegex(ValueError, 'AUTHORIZATION_TIMEOUT'):
            auth.receive_authorization(CLIENT, timeout=0)
        with patch.object(auth.webbrowser, 'open', return_value=False), self.assertRaisesRegex(ValueError, 'BROWSER_OPEN_FAILED'):
            auth.receive_authorization(CLIENT)

    def test_tokens_fail_closed(self):
        for token in (TOKEN | {'scope': auth.SCOPE + ' https://www.googleapis.com/auth/drive'}, TOKEN | {'scope': ''}, TOKEN | {'access_token': ''}, TOKEN | {'refresh_token': ''}, TOKEN | {'token_type': 'wrong'}):
            with self.subTest(token=token), self.assertRaises(ValueError):
                auth.validate_token(token, require_refresh=True)

    def test_wrong_account_shared_readonly_missing_evidence(self):
        for changes in ({'ownedByMe': False}, {'shared': True}, {'permissions': []}, {'permissions': [{'type': 'user', 'role': 'owner'}, {'type': 'anyone', 'role': 'reader'}]}, {'capabilities': {'canEdit': False}}, {'id': 'OTHER'}):
            with patch.object(auth, 'request_json', return_value=metadata(auth.IDS[0]) | changes), self.assertRaisesRegex(ValueError, 'OWNER_ONLY'):
                auth.verify_files('TEST')

    def flow_request(self, url, data=None, token=None):
        if url == 'https://oauth2.googleapis.com/token':
            if data['grant_type'] == 'authorization_code':
                self.assertEqual(data['code_verifier'], 'VERIFIER')
            else:
                self.assertEqual(data['refresh_token'], TOKEN['refresh_token'])
            return TOKEN.copy()
        self.assertEqual(token, TOKEN['access_token'])
        uid = urllib.parse.urlsplit(url).path.rsplit('/', 1)[1]
        return metadata(uid)

    def test_full_flow_refresh_before_secret_stdin_only(self):
        with patch.object(auth, 'receive_authorization', return_value=('CODE', 'VERIFIER', 'http://127.0.0.1:1234/')), patch.object(auth, 'request_json', side_effect=self.flow_request) as request, patch.object(auth.subprocess, 'run', return_value=SimpleNamespace(returncode=0)) as run, contextlib.redirect_stdout(io.StringIO()) as out:
            auth.authorize(CLIENT)
        self.assertEqual(request.call_count, 5)
        args, kwargs = run.call_args
        self.assertEqual(args[0], ['gh', 'secret', 'set', 'MISHNAH_DRIVE_OAUTH_JSON', '--repo', auth.REPO])
        self.assertEqual(json.loads(kwargs['input'])['refresh_token'], TOKEN['refresh_token'])
        self.assertNotIn(TOKEN['refresh_token'], str(args))
        self.assertEqual(out.getvalue(), '')

    def test_failure_never_saves_secret(self):
        failures = [auth.SetupBlocked('SELECT_EXACT_THREE_FILES'), auth.SetupBlocked('CONSENT_CANCELLED')]
        for failure in failures:
            with patch.object(auth, 'receive_authorization', side_effect=failure), patch.object(auth, 'request_json') as request, patch.object(auth.subprocess, 'run') as run, self.assertRaises(ValueError):
                auth.authorize(CLIENT)
            request.assert_not_called()
            run.assert_not_called()
        for bad in (TOKEN | {'refresh_token': ''}, TOKEN | {'scope': 'https://www.googleapis.com/auth/drive'}):
            with patch.object(auth, 'receive_authorization', return_value=('CODE', 'VERIFIER', 'http://127.0.0.1:1/')), patch.object(auth, 'request_json', return_value=bad), patch.object(auth.subprocess, 'run') as run, self.assertRaises(ValueError):
                auth.authorize(CLIENT)
            run.assert_not_called()
        for failure in (auth.SetupBlocked('NO_ACCESS'), TimeoutError()):
            with patch.object(auth, 'receive_authorization', return_value=('CODE', 'VERIFIER', 'http://127.0.0.1:1/')), patch.object(auth, 'request_json', side_effect=[TOKEN, TOKEN, failure]), patch.object(auth.subprocess, 'run') as run, self.assertRaises(Exception):
                auth.authorize(CLIENT)
            run.assert_not_called()

    def test_gh_failure_or_timeout_does_not_report_success(self):
        for result in (SimpleNamespace(returncode=1), subprocess.TimeoutExpired('gh', 60)):
            with patch.object(auth, 'receive_authorization', return_value=('CODE', 'VERIFIER', 'http://127.0.0.1:1/')), patch.object(auth, 'request_json', side_effect=self.flow_request), patch.object(auth.subprocess, 'run', **({'side_effect': result} if isinstance(result, Exception) else {'return_value': result})), contextlib.redirect_stdout(io.StringIO()) as out, self.assertRaises(Exception):
                auth.authorize(CLIENT)
            self.assertEqual(out.getvalue(), '')

    def test_full_drive_flag_rejected_before_browser_network_or_gh(self):
        with patch('sys.argv', ['authorize_private_drive.py', 'unused.json', '--existing-files']), patch.object(auth, 'authorize') as authorize, patch.object(auth.subprocess, 'run') as run, self.assertRaisesRegex(ValueError, 'FULL_DRIVE_DISABLED'):
            auth.main()
        authorize.assert_not_called()
        run.assert_not_called()

    def test_http_failure_redacted_no_retry(self):
        opener = SimpleNamespace(open=unittest.mock.Mock(side_effect=RuntimeError('PRIVATE_RESPONSE_BODY')))
        with patch.object(auth.urllib.request, 'build_opener', return_value=opener), self.assertRaisesRegex(ValueError, '^GOOGLE_REQUEST_FAILED_NO_RETRY$'):
            auth.request_json('https://oauth2.googleapis.com/token', {'client_secret': 'TEST'})
        self.assertEqual(opener.open.call_count, 1)

    def test_redirect_handler_rejects_credential_forwarding(self):
        with patch.object(auth.urllib.request, 'build_opener') as build:
            build.return_value.open.side_effect = RuntimeError()
            with self.assertRaises(ValueError):
                auth.request_json('https://oauth2.googleapis.com/token')
        handler = build.call_args.args[0]
        self.assertIsNone(handler().redirect_request(None, None, None, None, None, None))


if __name__ == '__main__':
    unittest.main()
