import copy,hashlib,io,json,tempfile,unittest,zipfile
from pathlib import Path
from unittest.mock import patch
from PIL import Image
from tools.comfy_scene_images import conditioning_inputs,sha
from tools.shot_controls import assess_composition
from tools.studio_runtime import Studio

class ImageHardening(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
        self.source=self.root/'source.png';Image.new('RGB',(256,144),'green').save(self.source)
        self.ref={'path':'source.png','sha256':sha(self.source),'synthesis_rights_confirmed':True}
        with Image.open(self.source) as im:
            b=io.BytesIO();im.crop((10,10,90,130)).convert('RGB').save(b,format='PNG')
        self.crop={'source_sha256':sha(self.source),'crop_box':[10,10,90,130],'size':[80,120],'sha256':hashlib.sha256(b.getvalue()).hexdigest()}
        self.spec={'references':[self.ref],'director':{'reference_preparation':{'crops':[self.crop]}}}
    def test_crops_reproducible_no_new_reference(self):
        a=conditioning_inputs(self.spec,self.root);self.assertEqual(len(a),1)
        self.assertEqual(hashlib.sha256(a[0][0]).hexdigest(),self.crop['sha256'])
    def test_invalid_crop_or_changed_source_blocked(self):
        for field,value in [('source_sha256','0'*64),('crop_box',[-1,0,10,20]),('sha256','0'*64),('size',[1,1])]:
            s=copy.deepcopy(self.spec);s['director']['reference_preparation']['crops'][0][field]=value
            with self.assertRaises(ValueError):conditioning_inputs(s,self.root)
        self.source.write_bytes(b'changed')
        with self.assertRaises(ValueError):conditioning_inputs(self.spec,self.root)
    def test_measurements_bound_to_image_and_not_approval(self):
        m={'image_sha256':sha(self.source),'reviewer':'TEST','method':'human_bounding_boxes','boxes':[{'character':'A','xyxy':[10,10,30,53]},{'character':'B','xyxy':[70,10,90,53]}]}
        self.assertFalse(assess_composition(self.source,m)['approval_granted'])
        m['boxes'][0]['xyxy']=[10,0,30,140];self.assertEqual(assess_composition(self.source,m)['status'],'FLAG')
        m['image_sha256']='0'*64
        with self.assertRaises(ValueError):assess_composition(self.source,m)
    def test_backup_checks_file_mutation_and_symlink(self):
        s=Studio(self.root);f=s.work/'private.txt';f.write_text('good')
        original=Path.read_bytes
        calls=[]
        def racing(p):
            raw=original(p)
            if p==f:
                calls.append(1)
                if len(calls)==1:p.write_text('changed')
            return raw
        with patch.object(Path,'read_bytes',racing):
            with self.assertRaisesRegex(ValueError,'CHANGED'):s.backup('private-media/race.zip')
        self.assertFalse((self.root/'private-media/race.zip').exists())
    def test_restore_references_existing_rights_without_manifest_changes(self):
        m={'references':[{'synthesis_rights_confirmed':False}]}
        path=self.root/'episodes/berakhot-01-01/comfy-opening-images.json';path.parent.mkdir(parents=True);path.write_text(json.dumps(m))
        with self.assertRaisesRegex(ValueError,'RIGHTS'):Studio(self.root).restore_references('private-media/input.zip')
    def test_cloudflare_sends_two_derivatives_without_generation(self):
        from tools.cloudflare_image_backend import CloudflareClient
        spec=copy.deepcopy(self.spec);spec.update(size=[1024,576],seed=7,style='TEST',prompt='TEST',characters={})
        spec['director']['reference_preparation']['crops']*=2
        paths=[]
        for i,(raw,digest) in enumerate(conditioning_inputs(spec,self.root)):
            p=self.root/f'crop{i}.png';p.write_bytes(raw);paths.append(p)
        c=CloudflareClient({});c.readiness=lambda spec:{}
        prepared=c.prepare(spec,paths)
        self.assertEqual(len(c.images),2);self.assertEqual(len(c.receipt['references']),2)
        self.assertIn('TEST',prepared['prompt'])
    def test_comfy_checks_models_before_private_upload(self):
        from tools.comfy_image_backend import ComfyClient
        c=ComfyClient('http://127.0.0.1:8188')
        spec=dict(self.spec,size=[1024,576],seed=7,style='TEST',prompt='TEST',characters={},model={'unet':'TEST','text_encoder':'TEST','vae':'TEST'})
        with patch.object(c,'request',return_value={}),patch.object(c,'upload') as upload:
            with self.assertRaises(ValueError):c.prepare(spec,[self.source])
            upload.assert_not_called()
    def test_restore_known_private_package_independent_of_chat(self):
        from tools.comfy_scene_images import atomic
        source=self.source.read_bytes();digest=sha(self.source)
        master='a_cinematic_detailed_illustration_in_the_same_rea.png';board='a_cinematic_storyboard_collage_with_four_panels_t.png'
        ref={'expected_sha256':digest,'expected_size':[256,144],'sha256':digest,'synthesis_rights_confirmed':True,'rights_uri':'TEST OWNER','role':'approved_style_and_character_master'}
        m={'references':[ref],'characters':{'A':{'references':[ref]},'B':{'references':[ref]}},'direction_board':{'sha256':digest,'dimensions':[256,144]}}
        atomic(self.root/'episodes/berakhot-01-01/comfy-opening-images.json',m)
        p=self.root/'private-media/refs.zip';p.parent.mkdir(exist_ok=True)
        with zipfile.ZipFile(p,'w') as z:z.writestr(master,source);z.writestr(board,source)
        s=Studio(self.root);r=s.restore_references('private-media/refs.zip');self.assertEqual(r['status'],'REFERENCES_RESTORED')
        self.assertEqual(json.loads(s.manifest.read_text()),m)
        self.assertTrue((self.root/f'private-media/introduction/references/{digest}.png').exists())
