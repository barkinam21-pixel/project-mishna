"""Local fake ComfyUI exercises actual HTTP; no GPU/model or paid calls."""
import copy
import io
import json
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from PIL import Image
from tools.comfy_image_backend import ComfyClient
from tools.comfy_scene_images import run, sha, accept, attach, specifications, compile_klein

class SceneImagesTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.out=self.root/'private'
        Image.new('RGB',(256,144),'red').save(self.root/'reference.png')
        ref={'path':'reference.png','sha256':sha(self.root/'reference.png'),'synthesis_rights_confirmed':True}
        self.m={'schema_version':1,'size':[512,288],'style':'TEST ONLY painterly',
            'model':{'id':'black-forest-labs/FLUX.2-klein-4B','revision':'test-only','unet':'TEST','text_encoder':'TEST','vae':'TEST','component_sha256':{k:'a'*64 for k in ('unet','text_encoder','vae')}},
            'references':[ref],'characters':{'A':{'description':'older adult left','references':[ref]}},
            'shots':[{'id':'OPN02','prompt':'TEST ONLY two adults','seed':9,'characters':['A']}],
            'authorization':{'generation_approved':True,'zero_cost_compute_verified':True,'component_licenses_verified':True,'max_submissions':1,'approved_shot_ids':['OPN02','OPN03']}}
        self.posts=0
        owner=self
        class Handler(BaseHTTPRequestHandler):
            def log_message(self,*args): pass
            def do_POST(self):
                body=self.rfile.read(int(self.headers['Content-Length']))
                if self.path=='/prompt':
                    owner.posts+=1;owner.graph=json.loads(body)['prompt'];result={'prompt_id':'test-prompt-'+str(owner.posts)}
                else: result={'name':'reference.png','subfolder':''}
                self.send_response(200);self.end_headers();self.wfile.write(json.dumps(result).encode())
            def do_GET(self):
                if self.path.startswith('/view?'):
                    b=io.BytesIO();Image.new('RGB',(512,288),(0,0,owner.posts)).save(b,format='PNG');data=b.getvalue()
                elif self.path=='/object_info':
                    graph=compile_klein(specifications(owner.m,owner.root)[0]['spec'],['reference.png'])
                    info={n['class_type']:{} for n in graph.values()}
                    for nid,field in [('1','unet_name'),('2','clip_name'),('3','vae_name')]:
                        n=graph[nid];info[n['class_type']]={'input':{'required':{field:[[n['inputs'][field]]]}}}
                    data=json.dumps(info).encode()
                else:
                    pid=self.path.rsplit('/',1)[-1]
                    data=json.dumps({pid:{'outputs':{'13':{'images':[{'filename':'test.png','type':'output','subfolder':''}]}},'status':{'status_str':'success'}}}).encode()
                self.send_response(200);self.end_headers();self.wfile.write(data)
        server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
        self.addCleanup(server.server_close);self.addCleanup(server.shutdown)
        threading.Thread(target=server.serve_forever,daemon=True).start()
        self.client=ComfyClient('http://127.0.0.1:'+str(server.server_port))

    def test_http_candidate_resume_review_cache_and_renderer_bridge(self):
        first=run(self.m,self.root,self.out,self.client,True)
        self.assertEqual(self.posts,1);self.assertEqual(first['shots'][0]['status'],'CANDIDATE')
        second=run(self.m,self.root,self.out,self.client,True)
        self.assertEqual(second['candidate_reuses'],1);self.assertEqual(self.posts,1)
        cfg={'assets':{'OPN02':{}},'profile':'series-narrator-alnilam-continuous-v2','visual_approved':False}
        self.assertEqual(attach(cfg,first),cfg)
        accept(self.root,self.out,first['shots'][0]['key'],'TEST reviewer',True,True)
        third=run(self.m,self.root,self.out,self.client,True)
        self.assertEqual(third['accepted_cache_hits'],1);self.assertEqual(self.posts,1)
        bridged=attach(cfg,third)
        self.assertTrue(bridged['assets']['OPN02']['accepted']);self.assertFalse(bridged['visual_approved'])
        self.assertEqual(cfg['assets']['OPN02'],{})

    def test_missing_reference_blocks_before_post(self):
        (self.root/'reference.png').unlink()
        with self.assertRaises(ValueError):run(self.m,self.root,self.out,self.client,True)
        self.assertEqual(self.posts,0)

    def test_authorization_blocks_before_post(self):
        self.m['authorization']['zero_cost_compute_verified']=False
        with self.assertRaises(ValueError):run(self.m,self.root,self.out,self.client,True)
        self.assertEqual(self.posts,0)

    def test_dry_run_never_contacts_server(self):
        report=run(self.m,self.root,self.out,None)
        self.assertEqual(report['submissions'],0);self.assertEqual(self.posts,0)

    def test_caption_changes_do_not_invalidate_images(self):
        a=specifications(self.m,self.root)
        self.m['captions']={'text':'changed'}
        self.assertEqual(a,specifications(self.m,self.root))
        self.m['characters']['A']['description']='different costume'
        self.assertNotEqual(a[0]['key'],specifications(self.m,self.root)[0]['key'])

    def test_uncertain_post_not_retried(self):
        def fail(*a,**kw):raise TimeoutError('uncertain')
        self.client.submit=fail
        with self.assertRaises(TimeoutError):run(self.m,self.root,self.out,self.client,True)
        with self.assertRaisesRegex(ValueError,'Uncertain'):run(self.m,self.root,self.out,self.client,True)

    def test_queued_job_resumed_without_new_post(self):
        original=self.client.wait
        self.client.wait=lambda *a,**kw: (_ for _ in ()).throw(TimeoutError())
        with self.assertRaises(TimeoutError):run(self.m,self.root,self.out,self.client,True)
        self.client.wait=original
        result=run(self.m,self.root,self.out,self.client,True)
        self.assertEqual(self.posts,1);self.assertEqual(result['submissions'],0)

    def test_changed_candidate_not_silently_regenerated(self):
        result=run(self.m,self.root,self.out,self.client,True)
        (self.root/result['shots'][0]['path']).write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError,'Cached'):run(self.m,self.root,self.out,self.client,True)
        self.assertEqual(self.posts,1)

    def test_character_reference_required(self):
        self.m['characters']['A']['references']=[]
        self.assertIn('Character reference missing',specifications(self.m,self.root)[0]['missing'])

    def test_reference_outside_root_rejected(self):
        self.m['references'][0]['path']='../secret.png'
        with self.assertRaises(ValueError):specifications(self.m,self.root)

    def test_native_reference_nodes_used(self):
        row=specifications(self.m,self.root)[0]
        graph=compile_klein(row['spec'],['ref.png'])
        self.assertEqual(graph['22']['class_type'],'ReferenceLatent')
        self.assertEqual(graph['9']['inputs']['steps'],4)
        self.assertEqual(graph['6']['inputs']['batch_size'],1)

    def test_concurrent_run_blocked(self):
        self.out.mkdir();(self.out/'running.lock').touch()
        with self.assertRaisesRegex(ValueError,'lock'):run(self.m,self.root,self.out)

    def test_unverified_component_hash_blocks(self):
        self.m['model']['component_sha256']={}
        with self.assertRaises(ValueError):run(self.m,self.root,self.out,self.client,True)
        self.assertEqual(self.posts,0)

    def test_only_changed_shot_invalidated(self):
        self.m['shots'].append(dict(self.m['shots'][0],id='OPN03',seed=10))
        first=specifications(self.m,self.root)
        self.m['shots'][1]['prompt']='new pose'
        second=specifications(self.m,self.root)
        self.assertEqual(first[0]['key'],second[0]['key'])
        self.assertNotEqual(first[1]['key'],second[1]['key'])

    def test_real_cache_two_shots_and_single_replacement(self):
        self.m['shots'].append(dict(self.m['shots'][0],id='OPN03',seed=10))
        self.m['authorization']['max_submissions']=2
        first=run(self.m,self.root,self.out,self.client,True)
        for item in first['shots']:
            accept(self.root,self.out,item['key'],'TEST reviewer',True,True)
        second=run(self.m,self.root,self.out,self.client,True)
        self.assertEqual(second['accepted_cache_hits'],2)
        self.assertEqual(second['submissions'],0)
        self.m['shots'][1]['prompt']='new gesture'
        third=run(self.m,self.root,self.out,self.client,True)
        self.assertEqual(third['accepted_cache_hits'],1)
        self.assertEqual(third['submissions'],1)
        self.assertEqual(self.posts,3)

    def test_shot_authorization_separate_from_global_gate(self):
        self.m['authorization']['approved_shot_ids']=[]
        with self.assertRaisesRegex(ValueError,'Shot not authorized'):
            run(self.m,self.root,self.out,self.client,True)
        self.assertEqual(self.posts,0)
