"""One-time Desktop OAuth PKCE -> GitHub Secret. No token file or token output."""
import argparse,base64,hashlib,http.server,json,secrets,shutil,subprocess,time,urllib.parse,urllib.request,webbrowser

IDS=['1Enbrzl3h2iCybflc_c4y_-b6vmecgwfb','1DGAOxZ-LdgOp02umtRp61V_iJ4_MDJeM','1G4ZFbRnBuaVAABm4jSDid8Q7P7QAvIhX']
def challenge(verifier):return base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b'=').decode()
def validate_client(data):
    c=data.get('installed',{})
    if not c.get('client_id','').endswith('.apps.googleusercontent.com') or not c.get('client_secret'):raise ValueError('Desktop client JSON required')
    return c

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('client_json');p.add_argument('--existing-files',action='store_true',help='Explicit full Drive scope for existing files not selected with Picker');a=p.parse_args()
    if not shutil.which('gh'):raise ValueError('Install GitHub CLI from https://cli.github.com/ first')
    if subprocess.run(['gh','auth','status'],capture_output=True).returncode:raise ValueError('Run gh auth login first')
    with open(a.client_json,encoding='utf-8') as f:c=validate_client(json.load(f))
    scope='https://www.googleapis.com/auth/drive'+('' if a.existing_files else '.file')
    if a.existing_files:
        print('Existing-file mode requests full Drive access: Google does not offer a scope limited to three pre-existing file IDs.')
    state=secrets.token_urlsafe(32);verifier=secrets.token_urlsafe(64);result={}
    class Handler(http.server.BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def do_GET(self):
            q=urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query)
            valid=urllib.parse.urlsplit(self.path).path=='/' and secrets.compare_digest(q.get('state',[''])[0],state)
            if valid and q.get('code'):result['code']=q['code'][0]
            self.send_response(200 if valid else 400);self.send_header('Content-Type','text/plain');self.send_header('Cache-Control','no-store');self.end_headers();self.wfile.write(b'You may close this window.' if valid else b'Invalid callback.')
    with http.server.HTTPServer(('127.0.0.1',0),Handler) as server:
        server.timeout=1;redirect='http://127.0.0.1:'+str(server.server_port)+'/'
        url='https://accounts.google.com/o/oauth2/v2/auth?'+urllib.parse.urlencode(dict(client_id=c['client_id'],redirect_uri=redirect,response_type='code',scope=scope,state=state,code_challenge=challenge(verifier),code_challenge_method='S256',access_type='offline',prompt='consent'))
        webbrowser.open(url);deadline=time.monotonic()+300
        while 'code' not in result and time.monotonic()<deadline:server.handle_request()
    if 'code' not in result:raise ValueError('Authorization timed out; no secret saved')
    body=urllib.parse.urlencode(dict(client_id=c['client_id'],client_secret=c['client_secret'],code=result['code'],code_verifier=verifier,redirect_uri=redirect,grant_type='authorization_code')).encode()
    token=json.load(urllib.request.urlopen(urllib.request.Request('https://oauth2.googleapis.com/token',data=body),timeout=30))
    if not token.get('refresh_token'):raise ValueError('No refresh token returned; no secret saved')
    # Check same owner-only predicate as private_drive_runtime; do not modify media.
    for uid in IDS:
        url='https://www.googleapis.com/drive/v3/files/'+uid+'?fields=shared,permissions(type,role),capabilities(canEdit)'
        m=json.load(urllib.request.urlopen(urllib.request.Request(url,headers={'Authorization':'Bearer '+token['access_token']}),timeout=30))
        if m.get('shared') is not False or m.get('permissions')!=[{'type':'user','role':'owner'}] or not m.get('capabilities',{}).get('canEdit'):raise ValueError('Required owner-only file access unavailable; no secret saved')
    payload=json.dumps({k:(token['refresh_token'] if k=='refresh_token' else c[k]) for k in ('client_id','client_secret','refresh_token')})
    saved=subprocess.run(['gh','secret','set','MISHNAH_DRIVE_OAUTH_JSON','--repo','barkinam21-pixel/project-mishna'],input=payload.encode(),capture_output=True)
    if saved.returncode:raise ValueError('GitHub secret save failed; no local token file was created')
    print('Drive access verified. GitHub Secret saved. No images created.')

if __name__=='__main__':
    try:main()
    except Exception:
        print('Setup stopped safely. Check Desktop client, consent, Drive permissions and GitHub CLI access. No tokens printed.');raise SystemExit(2)
