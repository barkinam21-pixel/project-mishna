import copy
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from tools.studio_runtime import Studio
from tools.comfy_scene_images import atomic
from tests import test_comfy_scene_images as fixture_http

REPO=Path(__file__).resolve().parents[1]

class RuntimeTests(unittest.TestCase):
    def setUp(self):
        self.h=fixture_http.SceneImagesTests();self.h.setUp();self.addCleanup(self.h.doCleanups)
        self.root=self.h.root;m=self.h.m;m['scene']='INTRO-A1-S01'
        shot=m['shots'][0];m['shots']=[dict(shot,id=f'OPN{i:02d}',seed=i) for i in range(1,8)]
        m['authorization']['approved_shot_ids']=['OPN02']
        atomic(self.root/'episodes/berakhot-01-01/comfy-opening-images.json',m)
        atomic(self.root/'episodes/berakhot-01-01/introduction-proof.json',{'assets':{}})
        self.studio=Studio(self.root)
    def enable(self):
        self.studio.endpoint=self.h.client.endpoint
        self.studio.runtime={'private_endpoint_verified':True,'zero_cost_verified':True}
    def test_offline_cpu_subprocess(self):
        code='import socket,sys; socket.create_connection=lambda *a,**k: (_ for _ in ()).throw(AssertionError("NETWORK")); from tools.studio_runtime import main;sys.exit(main())'
        for command in ['doctor','plan','review','run','resume','proof']:
            p=subprocess.run([sys.executable,'-c',code,command,'--root',str(self.root)],cwd=REPO,capture_output=True,text=True)
            r=json.loads(p.stdout);self.assertIn('cost',r);self.assertEqual(r['cost']['provider_requests'],0)
        self.assertEqual(self.h.posts,0)
    def test_resume_queued_http_without_duplicate(self):
        self.enable()
        with patch('tools.comfy_runtime.inspect',return_value={'ready':True}),patch('tools.comfy_image_backend.ComfyClient.wait',side_effect=TimeoutError):
            with self.assertRaises(TimeoutError): self.studio.run()
        self.assertEqual(self.h.posts,1)
        with patch('tools.comfy_runtime.inspect',return_value={'ready':True}): result=self.studio.run(resume=True)
        self.assertEqual(self.h.posts,1)
        self.assertEqual(result['status'],'REVIEW_READY')
        result=self.studio.run(resume=True);self.assertEqual(self.h.posts,1)
        state=json.loads((self.studio.work/'images/state.json').read_text());self.assertTrue(all(e['accepted'] is False for e in state['entries'].values()))
    def test_uncertain_never_retries(self):
        atomic(self.studio.work/'images/state.json',{'entries':{'unknown':{'status':'SUBMISSION_UNCERTAIN'}}})
        self.assertEqual(self.studio.run(True)['blocked_reason'],['UNCERTAIN_SUBMISSION_NO_RETRY']);self.assertEqual(self.h.posts,0)
    def test_endpoint_switch_rejects_foreign_queue(self):
        self.enable()
        from tools.comfy_scene_images import specifications
        row=specifications(self.h.m,self.root)[1]
        atomic(self.studio.work/'images/state.json',{'entries':{row['key']:{'status':'QUEUED','prompt_id':'old-server'}}})
        atomic(self.studio.work/'execution-endpoint.json',{'sha256':'another-server'})
        with patch('tools.comfy_runtime.inspect',return_value={'ready':True}):r=self.studio.run(True)
        self.assertIn('QUEUED_JOB_BELONGS_TO_DIFFERENT_ENDPOINT',r['blocked_reason']);self.assertEqual(self.h.posts,0)
    def test_backup_restore_and_no_overwrite(self):
        self.studio.review();result=self.studio.backup('private-media/backup.zip')
        import shutil
        with tempfile.TemporaryDirectory() as tmp:
            fresh=Path(tmp);(fresh/'private-media').mkdir();shutil.copy(self.root/result['outputs']['archive'],fresh/'private-media/backup.zip')
            restored=Studio(fresh);r=restored.restore('private-media/backup.zip');self.assertGreater(r['outputs']['files'],0)
            old=json.loads((self.studio.work/'queue.json').read_text());new=json.loads((restored.work/'queue.json').read_text());self.assertEqual(old,new)
            (restored.work/'queue.json').write_text('corrupt')
            with self.assertRaisesRegex(ValueError,'OVERWRITE'):restored.restore('private-media/backup.zip')
    def test_corrupt_backup_and_path_escape(self):
        import zipfile,hashlib
        p=self.root/'private-media/bad.zip'
        with zipfile.ZipFile(p,'w') as z:
            z.writestr('snapshot.json',json.dumps({'../escape':'x'}));z.writestr('../escape','bad')
        with self.assertRaises(ValueError):self.studio.restore('private-media/bad.zip')
    def test_private_workspace_only(self):
        with self.assertRaises(ValueError):Studio(self.root,'public-output')
    def test_dead_runtime_lock_recovery(self):
        (self.studio.work/'images').mkdir();(self.studio.work/'images/running.lock').write_text('')
        atomic(self.studio.work/'process-owner.json',{'pid':12345})
        with patch('tools.studio_runtime.os.kill',side_effect=ProcessLookupError):self.studio.run(True)
        self.assertFalse((self.studio.work/'images/running.lock').exists());self.assertEqual(self.h.posts,0)

    def test_hash_corruption_restores_nothing(self):
        import zipfile
        p=self.root/'private-media/corrupt.zip'
        with zipfile.ZipFile(p,'w') as z:
            z.writestr('snapshot.json',json.dumps({'private-media/first.txt':'0'*64}))
            z.writestr('private-media/first.txt','wrong')
        with self.assertRaisesRegex(ValueError,'HASH'):self.studio.restore('private-media/corrupt.zip')
        self.assertFalse((self.root/'private-media/first.txt').exists())
