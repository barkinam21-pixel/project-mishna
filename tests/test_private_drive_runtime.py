import io,json,os,tempfile,unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch
from tools.private_drive_runtime import Drive,DriveBlocked,main

class PrivateDriveTests(unittest.TestCase):
    def test_public_file_rejected_before_download(self):
        calls=[]
        def request(method,url,*args,**kwargs):
            calls.append(url);return json.dumps({'shared':True,'permissions':[{'type':'anyone','role':'reader'}]}).encode()
        d=Drive(request);d.token='TEST'
        with self.assertRaisesRegex(DriveBlocked,'OWNER_ONLY'):d.download('TEST_FILE')
        self.assertEqual(len(calls),1);self.assertNotIn('alt=media',calls[0])
    def test_owner_only_replace_readback_and_no_permission_changes(self):
        calls=[]
        def request(method,url,*args,**kwargs):
            calls.append((method,url))
            if 'fields=' in url:return json.dumps({'shared':False,'permissions':[{'type':'user','role':'owner'}]}).encode()
            return b'test'
        d=Drive(request);d.token='TEST';d.replace('TEST_FILE',b'test','application/zip')
        self.assertEqual(sum(m=='PATCH' for m,u in calls),1)
        self.assertFalse(any('/permissions' in u for m,u in calls))
    def test_corrupt_save_readback_stops(self):
        def request(method,url,*args,**kwargs):
            if 'fields=' in url:return b'{"shared":false,"permissions":[{"type":"user","role":"owner"}]}'
            return b'wrong'
        d=Drive(request);d.token='TEST'
        with self.assertRaisesRegex(DriveBlocked,'READBACK'):d.replace('TEST_FILE',b'expected','application/json')
    def test_missing_secret_safe_without_network(self):
        with patch.dict(os.environ,{},clear=True),patch('sys.argv',['private_drive_runtime','check']),patch.object(Drive,'login',side_effect=AssertionError('NETWORK')),redirect_stdout(io.StringIO()) as out:
            self.assertEqual(main(),2)
        self.assertEqual(json.loads(out.getvalue())['status'],'BLOCKED')
    def test_checkpoint_failure_prevents_generation_and_retry(self):
        from tools.studio_runtime import Studio
        from tools import comfy_scene_images
        env={k:'TEST' for k in ['CLOUDFLARE_ACCOUNT_ID','CLOUDFLARE_API_TOKEN','MISHNAH_DRIVE_OAUTH_JSON']}
        env.update(MISHNAH_REFERENCE_FILE_ID='REF',MISHNAH_STATE_FILE_ID='STATE',MISHNAH_SNAPSHOT_FILE_ID='SNAP')
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);private=root/'private-media/studio';private.mkdir(parents=True)
            def download(_,uid):return b'{"entries":{}}' if uid=='STATE' else b'TEST'
            posts=[]
            def run(studio):
                comfy_scene_images.atomic(studio.work/'images/state.json',{'entries':{'test':{'status':'SUBMISSION_UNCERTAIN'}}})
                posts.append('MODEL_REQUEST')
            with patch.dict(os.environ,env,clear=True),patch('pathlib.Path.cwd',return_value=root),patch.object(Drive,'login'),patch.object(Drive,'metadata'),patch.object(Drive,'download',download),patch.object(Drive,'replace',side_effect=DriveBlocked('WRITE_FAILED')),patch.object(Studio,'inputs',return_value=({'authorization':{k:True for k in ['generation_approved','zero_cost_compute_verified','component_licenses_verified']}},[],{})),patch.object(Studio,'restore_references'),patch.object(Studio,'restore'),patch.object(Studio,'run',run),patch('sys.argv',['private_drive_runtime','run']),redirect_stdout(io.StringIO()):
                self.assertEqual(main(),2)
            self.assertEqual(posts,[])
            state=json.loads((private/'images/state.json').read_text());self.assertEqual(state['entries']['test']['status'],'SUBMISSION_UNCERTAIN')
