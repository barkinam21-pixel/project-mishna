import copy
import datetime as dt
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile
from PIL import Image
from tools import chat_operations as chat
from tools.opn02_recovery import recover, PREFIX, TARGET
from tools.comfy_scene_images import conditioning_inputs, conditioning_records


class ChatControlTests(unittest.TestCase):
    def setUp(self):
        self.run={'id':chat.RUN_ID,'head_sha':chat.RUN_SHA,'path':chat.WORKFLOW,'event':'workflow_dispatch','repository':{'full_name':chat.REPO},'actor':{'login':'barkinam21-pixel'},'created_at':'2026-11-13T00:30:34Z','status':'completed','conclusion':'success','run_attempt':1}
        self.jobs=[{'id':123,'run_id':chat.RUN_ID,'name':'drive-readonly','status':'completed'}]
        self.now=dt.datetime(2026,11,13,1,tzinfo=dt.timezone.utc)

    def test_natural_requests_never_turn_into_media_or_backup_writes(self):
        for text in ('תמשיך את המשנה','תמשיך את פרויקט המשנה'):
            self.assertEqual(chat.intent(text)['operation'],'check-drive')
        self.assertEqual(chat.intent('בדוק את התמונות')['operation'],'inspect-existing-assets')
        for text in ('תכין את הסרטון','תכין את הסצנה הבאה','תגבה את העבודה','run','merge','create images'):
            self.assertTrue(chat.intent(text)['status'].startswith('BLOCKED'))

    def test_plan_only_for_exact_reviewed_workflow_and_one_job(self):
        with patch.object(chat,'WORKFLOW_BLOB',hashlib.sha1(b'blob 4\0TEST').hexdigest()):
            plan=chat.replay_plan(self.run,self.jobs,'TEST',self.now)
            self.assertEqual(plan['arguments'],{'repo_full_name':chat.REPO,'job_id':123})
            self.assertEqual(plan['expected_next_attempt'],2)
            self.assertEqual(plan['remote_writes'],0)
            for changes in ({'id':12},{'head_sha':'bad'},{'path':'other.yml'},{'event':'push'},{'actor':{'login':'OTHER'}},{'repository':{'full_name':'OTHER/repo'}},{'status':'in_progress'}):
                with self.subTest(changes=changes),self.assertRaises(ValueError):chat.replay_plan(self.run|changes,self.jobs,'TEST',self.now)
            with self.assertRaises(ValueError):chat.replay_plan(self.run,self.jobs*2,'TEST',self.now)
            with self.assertRaises(ValueError):chat.replay_plan(self.run,self.jobs,'CHANGED',self.now)
            with self.assertRaisesRegex(ValueError,'EXPIRED'):chat.replay_plan(self.run,self.jobs,'TEST',self.now+dt.timedelta(days=31))

    def test_success_is_bound_to_new_attempt_and_zero_side_effects(self):
        report={'status':'DRIVE_RESTORE_AND_LOCAL_PREFLIGHT_VERIFIED','inference_requests':0,'remote_writes':0,'generation_authorized':False}
        result=chat.verify_result(self.run|{'run_attempt':2},report,2)
        self.assertFalse(result['ordinary_chat_surface_tested'])
        for changes in ({'remote_writes':1},{'inference_requests':True},{'generation_authorized':True},{'status':'SUCCESS'}):
            with self.assertRaises(ValueError):chat.verify_result(self.run|{'run_attempt':2},report|changes,2)
        with self.assertRaises(ValueError):chat.verify_result(self.run,report,2)


class RecoveryTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
        def png(color):
            b=io.BytesIO();Image.new('RGB',(8,8),color).save(b,format='PNG');return b.getvalue()
        b=io.BytesIO();Image.new('RGB',(8,8),'blue').save(b,format='JPEG');jpg=b.getvalue()
        b=io.BytesIO()
        with Image.open(io.BytesIO(jpg)) as im:im.save(b,format='PNG')
        self.raw={'OPN02_Cloudflare_20261111.jpg':jpg,'OPN02_Cloudflare_20261111.png':b.getvalue(),'layout.png':png('yellow'),'elder.png':png('red'),'younger.png':png('green')}
        digest=lambda raw:hashlib.sha256(raw).hexdigest()
        self.archive=self.root/'source.zip'
        with zipfile.ZipFile(self.archive,'w') as z:
            for name,raw in self.raw.items():z.writestr(PREFIX+name,raw)
            z.writestr(PREFIX+'spec.json',json.dumps({'seed':73003,'size':[8,8],'references':[{'sha256':digest(self.raw[n])} for n in ('layout.png','elder.png','younger.png')]}))
            z.writestr('tools/do_not_execute.py','raise RuntimeError("BUNDLED_CODE_MUST_NEVER_EXECUTE")')
        e=self.root/'docs/evidence';e.mkdir(parents=True)
        (e/'opn02-cloudflare-layout-2026-11-11.json').write_text(json.dumps({'private_bundle_sha256':digest(self.archive.read_bytes()),'png_sha256':digest(self.raw['OPN02_Cloudflare_20261111.png']),'native_sha256':digest(jpg),'layout_sha256':digest(self.raw['layout.png']),'seed':73003,'dimensions':[8,8]}))
        m=self.root/'episodes/berakhot-01-01';m.mkdir(parents=True)
        (m/'comfy-opening-images.json').write_text(json.dumps({'shots':[{'id':'OPN02','director':{'reference_preparation':{'crops':[{'sha256':digest(self.raw['elder.png'])},{'sha256':digest(self.raw['younger.png'])}]}}}]}))

    def test_exact_bundle_recovery_idempotent_and_no_execution(self):
        result=recover(self.root,self.archive)
        self.assertFalse(result['accepted']);self.assertFalse(result['bundled_code_executed'])
        self.assertEqual(result,recover(self.root,self.archive))
        self.assertFalse((self.root/'tools/do_not_execute.py').exists())
        for name,raw in self.raw.items():self.assertEqual((self.root/TARGET/name).read_bytes(),raw)

    def test_conflicting_asset_never_overwritten_and_no_other_output(self):
        target=self.root/TARGET;target.mkdir(parents=True)
        (target/'layout.png').write_bytes(b'KEEP ORIGINAL')
        with self.assertRaisesRegex(ValueError,'WOULD_OVERWRITE'):recover(self.root,self.archive)
        self.assertEqual((target/'layout.png').read_bytes(),b'KEEP ORIGINAL')
        self.assertFalse((target/'elder.png').exists())

    def test_wrong_bundle_never_writes_assets(self):
        self.archive.write_bytes(self.archive.read_bytes()+b'CHANGED')
        with self.assertRaisesRegex(ValueError,'BUNDLE_HASH'):recover(self.root,self.archive)
        self.assertFalse((self.root/TARGET).exists())

    def test_conflicting_receipt_prevents_all_asset_writes(self):
        target=self.root/TARGET;target.mkdir(parents=True);(target/'recovery.json').write_text('{}')
        with self.assertRaisesRegex(ValueError,'RECEIPT_CONFLICT'):recover(self.root,self.archive)
        self.assertFalse((target/'elder.png').exists())

    def test_matching_receipt_can_restore_missing_bytes_without_replacing_anything(self):
        recover(self.root,self.archive);(self.root/TARGET/'elder.png').unlink()
        recover(self.root,self.archive)
        self.assertEqual((self.root/TARGET/'elder.png').read_bytes(),self.raw['elder.png'])

    def test_layout_is_real_third_conditioning_input_and_hash_checked(self):
        from tools.comfy_scene_images import sha
        recover(self.root,self.archive)
        master=self.root/'master.png';master.write_bytes(self.raw['elder.png'])
        crop=self.raw['elder.png'];digest=hashlib.sha256(crop).hexdigest()
        spec={'references':[{'path':'master.png','sha256':sha(master),'synthesis_rights_confirmed':True}], 'director':{'reference_preparation':{'crops':[{'source_sha256':sha(master),'crop_box':[0,0,8,8],'size':[8,8],'sha256':digest}], 'layout_guide':{'path':TARGET+'/layout.png','sha256':hashlib.sha256(self.raw['layout.png']).hexdigest(),'size':[8,8],'role':'original_layout_guide'}}}}
        inputs=conditioning_inputs(spec,self.root)
        self.assertEqual(inputs[0][0],self.raw['layout.png']);self.assertEqual(len(inputs),2)
        self.assertEqual(conditioning_records(spec)[0]['role'],'original_layout_guide')
        (self.root/TARGET/'layout.png').write_bytes(b'CHANGED')
        with self.assertRaises(ValueError):conditioning_inputs(spec,self.root)


if __name__=='__main__':unittest.main()
