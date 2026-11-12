"""Desktop Drive file selection with PKCE; credentials go only to gh stdin."""
import argparse
import base64
import hashlib
import http.server
import json
from pathlib import Path
import secrets
import shutil
import subprocess
import time
import urllib.parse
import urllib.request
import webbrowser

IDS = ['1Enbrzl3h2iCybflc_c4y_-b6vmecgwfb', '1DGAOxZ-LdgOp02umtRp61V_iJ4_MDJeM', '1G4ZFbRnBuaVAABm4jSDid8Q7P7QAvIhX']
SCOPE = 'https://www.googleapis.com/auth/drive.file'
REPO = 'barkinam21-pixel/project-mishna'


class SetupBlocked(ValueError):
    """Fixed diagnostic code, safe to print without remote response bodies."""


def challenge(verifier):
    return base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b'=').decode()


def validate_client(data):
    c = data.get('installed', {})
    if not isinstance(c, dict) or not isinstance(c.get('client_id'), str) or not c['client_id'].endswith('.apps.googleusercontent.com') or not isinstance(c.get('client_secret'), str) or not c['client_secret']:
        raise SetupBlocked('DESKTOP_CLIENT_REQUIRED')
    return c


def load_client(path=None):
    if path is not None:
        candidates = [Path(path)]
    else:
        candidates = sorted((Path.home() / 'Downloads').glob('client_secret*.json'))
    valid = []
    for candidate in candidates:
        try:
            if candidate.stat().st_size > 65536:
                continue
            with candidate.open(encoding='utf-8-sig') as source:
                valid.append(validate_client(json.load(source)))
        except (ValueError, OSError, TypeError, AttributeError):
            continue
    if len(valid) != 1:
        raise SetupBlocked('ONE_DESKTOP_CLIENT_REQUIRED_SUPPLY_LOCAL_PATH')
    return valid[0]


def authorization_url(client, redirect, state, verifier):
    # Google's native Picker flow: no JS page, API key, or web OAuth client.
    # https://developers.google.com/workspace/drive/picker/guides/desktop-mobile-picker
    return 'https://accounts.google.com/o/oauth2/v2/auth?' + urllib.parse.urlencode(dict(
        client_id=client['client_id'], redirect_uri=redirect, response_type='code',
        scope=SCOPE, state=state, code_challenge=challenge(verifier),
        code_challenge_method='S256', access_type='offline', prompt='consent',
        include_granted_scopes='false', trigger_onepick='true',
        allow_multiple='true', file_ids=','.join(IDS)))


def parse_callback(path, state):
    if len(path) > 16384:
        raise SetupBlocked('INVALID_CALLBACK')
    parts = urllib.parse.urlsplit(path)
    q = urllib.parse.parse_qs(parts.query, keep_blank_values=True, max_num_fields=20)
    if parts.path != '/' or parts.scheme or parts.netloc or parts.fragment or any(len(v) != 1 for v in q.values()) or not secrets.compare_digest(q.get('state', [''])[0], state):
        raise SetupBlocked('INVALID_CALLBACK')
    if 'error' in q:
        return {'error': 'CONSENT_CANCELLED'}
    picked = q.get('picked_file_ids', [''])[0].split(',')
    if len(picked) != len(IDS) or set(picked) != set(IDS):
        return {'error': 'SELECT_EXACT_THREE_FILES'}
    if not q.get('code', [''])[0]:
        return {'error': 'AUTHORIZATION_CODE_MISSING'}
    return {'code': q['code'][0]}


def receive_authorization(client, timeout=300):
    state = secrets.token_urlsafe(32)
    verifier = secrets.token_urlsafe(64)
    result = {}

    class Handler(http.server.BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):
            try:
                if self.headers.get('Host') != '127.0.0.1:' + str(self.server.server_port):
                    raise SetupBlocked('INVALID_CALLBACK')
                parsed = parse_callback(self.path, state)
            except (ValueError, TypeError):
                parsed = None
            if parsed is not None:
                result.update(parsed)
            self.send_response(200 if parsed is not None else 400)
            self.send_header('Content-Type', 'text/plain; charset=utf-8')
            self.send_header('Cache-Control', 'no-store')
            self.send_header('Referrer-Policy', 'no-referrer')
            self.send_header('Content-Security-Policy', "default-src 'none'; frame-ancestors 'none'")
            self.end_headers()
            self.wfile.write(b'Return to the setup window for the result. You may close this tab.' if parsed is not None else b'Invalid callback.')

    class Server(http.server.HTTPServer):
        def get_request(self):
            sock, address = super().get_request()
            sock.settimeout(2)
            return sock, address

    with Server(('127.0.0.1', 0), Handler) as server:
        server.timeout = 1
        redirect = 'http://127.0.0.1:' + str(server.server_port) + '/'
        if not webbrowser.open(authorization_url(client, redirect, state, verifier)):
            raise SetupBlocked('BROWSER_OPEN_FAILED')
        deadline = time.monotonic() + timeout
        while not result and time.monotonic() < deadline:
            server.handle_request()
    if not result:
        raise SetupBlocked('AUTHORIZATION_TIMEOUT')
    if 'error' in result:
        raise SetupBlocked(result['error'])
    return result['code'], verifier, redirect


def request_json(url, data=None, token=None):
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *args, **kwargs):
            return None
    headers = {'Authorization': 'Bearer ' + token} if token else {}
    if data is not None:
        data = urllib.parse.urlencode(data).encode()
        headers['Content-Type'] = 'application/x-www-form-urlencoded'
    try:
        with urllib.request.build_opener(NoRedirect).open(urllib.request.Request(url, data=data, headers=headers), timeout=30) as response:
            raw = response.read(1024 * 1024 + 1)
            if len(raw) > 1024 * 1024:
                raise ValueError()
            value = json.loads(raw)
            if not isinstance(value, dict):
                raise ValueError()
            return value
    except Exception:
        raise SetupBlocked('GOOGLE_REQUEST_FAILED_NO_RETRY') from None


def validate_token(token, require_refresh=False):
    if not isinstance(token.get('access_token'), str) or not token['access_token'] or token.get('token_type', '').lower() != 'bearer':
        raise SetupBlocked('ACCESS_TOKEN_MISSING')
    if require_refresh and (not isinstance(token.get('refresh_token'), str) or not token['refresh_token']):
        raise SetupBlocked('REFRESH_TOKEN_MISSING')
    if not isinstance(token.get('scope'), str) or set(token['scope'].split()) != {SCOPE}:
        raise SetupBlocked('GRANTED_SCOPE_NOT_DRIVE_FILE')


def verify_files(access_token):
    for uid in IDS:
        url = 'https://www.googleapis.com/drive/v3/files/' + uid + '?fields=id,ownedByMe,shared,permissions(type,role),capabilities(canEdit)'
        meta = request_json(url, token=access_token)
        if meta.get('id') != uid or meta.get('ownedByMe') is not True or meta.get('shared') is not False or meta.get('permissions') != [{'type': 'user', 'role': 'owner'}] or meta.get('capabilities', {}).get('canEdit') is not True:
            raise SetupBlocked('REQUIRED_OWNER_ONLY_FILE_ACCESS_UNAVAILABLE')


def authorize(client):
    code, verifier, redirect = receive_authorization(client)
    token = request_json('https://oauth2.googleapis.com/token', dict(
        client_id=client['client_id'], client_secret=client['client_secret'],
        code=code, code_verifier=verifier, redirect_uri=redirect,
        grant_type='authorization_code'))
    validate_token(token, require_refresh=True)
    # Prove that the refresh credential intended for Actions works before storing it.
    refreshed = request_json('https://oauth2.googleapis.com/token', dict(
        client_id=client['client_id'], client_secret=client['client_secret'],
        refresh_token=token['refresh_token'], grant_type='refresh_token'))
    validate_token(refreshed)
    verify_files(refreshed['access_token'])
    payload = json.dumps(dict(client_id=client['client_id'], client_secret=client['client_secret'], refresh_token=token['refresh_token']))
    saved = subprocess.run(['gh', 'secret', 'set', 'MISHNAH_DRIVE_OAUTH_JSON', '--repo', REPO], input=payload.encode(), capture_output=True, timeout=60)
    if saved.returncode:
        raise SetupBlocked('GITHUB_SECRET_SAVE_FAILED')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('client_json', nargs='?', help='Existing Desktop JSON; default: unique client_secret*.json in Downloads')
    parser.add_argument('--existing-files', action='store_true', help='Obsolete; broad Drive access is no longer supported')
    args = parser.parse_args()
    if args.existing_files:
        raise SetupBlocked('FULL_DRIVE_DISABLED_REMOVE_EXISTING_FILES_FLAG')
    if not shutil.which('gh'):
        raise SetupBlocked('GITHUB_CLI_MISSING')
    if subprocess.run(['gh', 'auth', 'status'], capture_output=True, timeout=30).returncode:
        raise SetupBlocked('GITHUB_LOGIN_REQUIRED')
    client = load_client(args.client_json)
    authorize(client)
    print('Three private files and refresh verified; GitHub Secret saved. Actions check still required. No images created.')


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        print('Setup stopped safely: ' + (str(error) if isinstance(error, SetupBlocked) else 'LOCAL_SETUP_FAILED') + '. No tokens printed. No automatic retry.')
        raise SystemExit(2)
