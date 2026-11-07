import copy
import hashlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from tools.klein_space_backend import KleinSpaceClient,ProviderBlocked,SPACE,HOST
from tools.comfy_scene_images import specifications
from tools.comfy_runtime import intake
from PIL import Image

class SpaceTests(unittest.TestCase):
    def setUp(self):
        self.source=b'TEST official source snapshot'
        self.config={'type':'hf-zero','space':SPACE,'revision':'a'*40,'app_sha256':hashlib.sha256(self.source).hexdigest()}
        self.client=KleinSpaceClient(self.config)
        self.documents={
            'https://huggingface.co/api/spaces/'+SPACE:{'sha':'a'*40,'runtime':{'stage':'RUNNING','hardware':{'current':'zero-a10g'}}},
            HOST+'/gradio_api/info':{'named_endpoints':{'/infer':{'parameters':[{'parameter_name':p} for p in ['prompt','input_images','mode_choice','seed','randomize_seed','width','height','num_inference_steps','guidance_scale','prompt_upsampling']]}}},
            HOST+'/config':{'components':[{'type':'image','props':{'label':'Result','format':'png'}}]}}
        self.client.get_json=lambda u:self.documents[u]
        self.client.open=lambda *a,**k:io.BytesIO(self.source)

    def test_readiness_not_gpu_allocation(self):
        self.assertEqual(self.client.readiness()['gpu_allocation'],'NOT_TESTED')

    def test_actual_demo_webp_blocks_before_upload_or_inference(self):
        self.documents[HOST+'/config']['components'][0]['props']['format']='webp'
        with self.assertRaisesRegex(ProviderBlocked,'ORIGINAL_PNG_UNAVAILABLE'):
            self.client.prepare({},[Path('must-not-be-opened.png')])

    def test_revision_change_blocks(self):
        self.documents['https://huggingface.co/api/spaces/'+SPACE]['sha']='b'*40
        with self.assertRaisesRegex(ProviderBlocked,'REVISION'):self.client.readiness()

    def test_wrong_hardware_blocks(self):
        self.documents['https://huggingface.co/api/spaces/'+SPACE]['runtime']['hardware']['current']='cpu-basic'
        with self.assertRaisesRegex(ProviderBlocked,'HARDWARE'):self.client.readiness()

    def test_changed_source_blocks(self):
        self.client.open=lambda *a,**kw:io.BytesIO(b'changed')
        with self.assertRaisesRegex(ProviderBlocked,'APP_SOURCE'):self.client.readiness()

    def test_foreign_output_host_rejected(self):
        with self.assertRaisesRegex(ProviderBlocked,'DOWNLOAD_HOST'):
            self.client.download({'image':{'url':'https://other.example/output.png'}})

    def test_requires_authorization_before_post(self):
        with self.assertRaisesRegex(ProviderBlocked,'AUTHORIZATION'):self.client.submit({})

    def test_sse_success_and_quota_failure(self):
        self.client.open=lambda *a:io.BytesIO(b'event: heartbeat\ndata: null\n\nevent: complete\ndata: [{"url":"TEST"},7]\n\n')
        result=self.client.result(self.client.wait('abc123'))
        self.assertEqual(result['seed'],7)
        self.client.open=lambda *a:io.BytesIO(b'event: error\ndata: "GPU quota exceeded"\n\n')
        with self.assertRaisesRegex(ProviderBlocked,'QUOTA'):self.client.wait('abc123')

    def test_reference_mismatch_never_saved(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);p=root/'ref.png';Image.new('RGB',(32,32)).save(p)
            with self.assertRaisesRegex(ValueError,'HASH_MISMATCH'):
                intake(p,root,expected_sha256='0'*64)
            with self.assertRaisesRegex(ValueError,'DIMENSIONS_MISMATCH'):
                intake(p,root,expected_size=[1672,941])
            self.assertFalse((root/'private-media').exists())

    def test_verified_reference_has_separate_role(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);p=root/'ref.png';Image.new('RGB',(32,32)).save(p)
            result=intake(p,root,expected_sha256=hashlib.sha256(p.read_bytes()).hexdigest(),
                          expected_size=[32,32],role='direction_board')
            self.assertEqual(result['role'],'direction_board')
            self.assertFalse(result['visual_identity_approved'])

    def test_manifest_binding_never_promotes_film_approval(self):
        from tools.comfy_runtime import bind_reference
        manifest={'references':[{'expected_sha256':'a'*64,'expected_size':[1672,941]}],
                  'characters':{'A':{'references':[]},'B':{'references':[]}},
                  'direction_board':{},'visual_approved':False,'release_authorized':False}
        receipt={'role':'approved_style_and_character_master','sha256':'a'*64,
                 'dimensions':[1672,941],'path':'private-media/ref.png','rights_uri':'TEST owner instruction',
                 'original_bytes_preserved':True,'synthesis_rights_confirmed':True}
        bound=bind_reference(manifest,receipt)
        self.assertEqual(bound['characters']['A']['references'],bound['characters']['B']['references'])
        self.assertFalse(bound['visual_approved']);self.assertFalse(bound['release_authorized'])
        self.assertEqual(manifest['characters']['A']['references'],[])
        receipt['sha256']='b'*64
        with self.assertRaises(ValueError):bind_reference(manifest,receipt)

    def test_director_board_is_not_a_generation_input(self):
        from tools.comfy_runtime import bind_reference
        m={'references':[],'characters':{},'direction_board':{}}
        r={'role':'direction_board','path':'private-media/board.png','sha256':'b'*64,'dimensions':[1280,720],
           'rights_uri':'TEST','original_bytes_preserved':True,'synthesis_rights_confirmed':True}
        bound=bind_reference(m,r)
        self.assertEqual(bound['references'],[])
        self.assertEqual(bound['direction_board']['sha256'],'b'*64)

    def test_shared_cache_works_with_non_comfy_results(self):
        from tools.comfy_scene_images import run, accept, attach
        from tools.comfy_scene_images import sha
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);p=root/'ref.png';Image.new('RGB',(32,32)).save(p)
            ref={'path':'ref.png','sha256':sha(p),'synthesis_rights_confirmed':True}
            m={'schema_version':1,'model':{'id':'black-forest-labs/FLUX.2-klein-4B','revision':None},
               'backend':self.config,'size':[512,288],'style':'TEST ONLY',
               'references':[ref],'characters':{'A':{'description':'adult','references':[ref]}},
               'shots':[{'id':'OPN02','prompt':'TEST ONLY','seed':7,'characters':['A']}],
               'authorization':{'approved_shot_ids':['OPN02'],'generation_approved':True,
                  'zero_cost_compute_verified':True,'component_licenses_verified':True,
                  'max_submissions':1,'total_submissions_limit':1}}
            output=io.BytesIO();Image.new('RGB',(512,288),'red').save(output,format='PNG')
            class Adapter:
                engine_name='TEST hosted Diffusers'
                count=0
                def prepare(s,spec,paths):return {'prompt':spec['prompt']}
                def submit(s,*a,**k):s.count+=1;return 'one'
                def wait(s,event):return [{'path':'TEST'},7]
                def result(s,result):return {'image':result[0],'seed':result[1]}
                def download(s,result):return output.getvalue()
            client=Adapter();out=root/'private'
            first=run(m,root,out,client,True)
            accept(root,out,first['shots'][0]['key'],'TEST',True,True)
            second=run(m,root,out,client,True)
            self.assertEqual(client.count,1);self.assertEqual(second['accepted_cache_hits'],1)
            result=attach({'assets':{'OPN02':{}},'release_authorized':False},second)
            self.assertEqual(result['assets']['OPN02']['provenance']['engine'],'TEST hosted Diffusers')
            m['shots'][0]['prompt']='changed'
            with self.assertRaisesRegex(ValueError,'Total authorized'):run(m,root,out,client,True)
            self.assertEqual(client.count,1)
