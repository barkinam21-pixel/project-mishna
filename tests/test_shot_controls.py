import copy
import json
import tempfile
import unittest
from pathlib import Path
from PIL import Image
from tools.shot_controls import validate,apply_override,visual_qa
from tools.cloudflare_image_backend import CloudflareClient,CloudflareBlocked

class ControlsTests(unittest.TestCase):
    def setUp(self):
        self.m=json.loads(Path('episodes/berakhot-01-01/comfy-opening-images.json').read_text());self.s=self.m['shots'][1]
    def test_all_shots_valid(self):
        for s in self.m['shots']: self.assertEqual(validate(s['director'],s,self.m),[])
    def test_missing_and_conflicting_fields(self):
        for field,value in [('time_of_day','dawn'),('style_lock','wrong'),('preserve_costumes',False),('review_status','ACCEPTED')]:
            d=copy.deepcopy(self.s['director']);d[field]=value;self.assertTrue(validate(d,self.s,self.m))
    def test_override_scoped(self):
        with self.assertRaises(ValueError):apply_override(self.m,'OPN02',{'review_status':'ACCEPTED'})
        changed=apply_override(self.m,'OPN02',{'composition_notes':'Wider landscape'})
        self.assertNotEqual(changed,self.m);self.assertEqual(changed['characters'],self.m['characters'])
    def test_similarity_and_unknown_semantics(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'im.png';Image.new('RGB',(128,72),'orange').save(p)
            qa=visual_qa(p,[p]);self.assertTrue(qa['flags']);self.assertTrue(all(v=='NOT_EVALUATED' for v in qa['semantic'].values()))
    def test_no_charge_gate_before_any_network(self):
        client=CloudflareClient(self.m['available_backends']['cloudflare'],request=lambda *a: self.fail('Network must not be called'))
        with self.assertRaisesRegex(CloudflareBlocked,'HARD_CAP'):client.readiness({'size':[1024,576],'references':[{}]})
    def test_partner_privacy_gate_blocks_before_network_even_when_free_cap_attested(self):
        import datetime as dt
        cfg=copy.deepcopy(self.m['available_backends']['cloudflare'])
        cfg['safety'].update(
            free_hard_cap_verified=True,
            partner_private_reference_terms_verified=False,
            verified_at=dt.datetime.now(dt.timezone.utc).isoformat())
        c=CloudflareClient(cfg,request=lambda *args: self.fail('Private reference network forbidden'))
        with self.assertRaisesRegex(CloudflareBlocked,'PARTNER_PRIVATE_REFERENCE_TERMS_UNVERIFIED'):
            c.readiness({'size':[1024,576],'references':[{}]})

    def test_no_unapproved_submit(self):
        with self.assertRaises(CloudflareBlocked):CloudflareClient({}).submit({})
    def test_invalid_or_empty_provider_response(self):
        for response in [{},{'result':{'image':''}},{'result':{'image':'!!!'}}]:
            c=CloudflareClient({},request=lambda *a:response);c.images=[];c.receipt={'started_at':'test'};c._prepared_spec={};c.readiness=lambda spec: None
            with self.assertRaises(CloudflareBlocked):c.submit({},zero_cost_verified=True,authorized=True)
    def test_timeout_never_retried(self):
        calls=[]
        def fail(*a):calls.append(a);raise TimeoutError()
        c=CloudflareClient({},request=fail);c.images=[];c.receipt={'started_at':'test'};c._prepared_spec={};c.readiness=lambda spec: None
        with self.assertRaises(TimeoutError):c.submit({},zero_cost_verified=True,authorized=True)
        self.assertEqual(len(calls),1)
    def test_readiness_fresh_success_and_usage_failure(self):
        import datetime as dt
        cfg=copy.deepcopy(self.m['available_backends']['cloudflare'])
        cfg['safety'].update(free_hard_cap_verified=True,
                             partner_private_reference_terms_verified=True,
                             verified_at=dt.datetime.now(dt.timezone.utc).isoformat())
        for used,ok in [(0,True),(9999,False),(float('nan'),False)]:
            def request(method,path,*args):
                if method=='GET': return {'result':[{'name':'@cf/black-forest-labs/flux-2-klein-4b'}]}
                return {'data':{'viewer':{'accounts':[{'aiInferenceAdaptiveGroups':[{'sum':{'totalNeurons':used}}]}]}},'errors':None}
            c=CloudflareClient(cfg,request=request)
            if ok:self.assertGreater(c.readiness({'size':[1024,576],'references':[{}]})['estimated_neurons'],0)
            else:
                with self.assertRaises(CloudflareBlocked):c.readiness({'size':[1024,576],'references':[{}]})

    def test_jpeg_integration_and_second_run_cache(self):
        import base64,io,hashlib
        from tools.comfy_scene_images import run,sha
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);ref=root/'reference.png';Image.new('RGB',(1672,941),'orange').save(ref)
            m=copy.deepcopy(self.m);m['shots']=[m['shots'][1]];m['backend']=m['available_backends']['cloudflare']
            r=dict(m['references'][0],path='reference.png',sha256=sha(ref),expected_sha256=sha(ref))
            m['references']=[r]
            for c in m['characters'].values():c['references']=[r]
            d=m['shots'][0]['director'];d.pop('reference_preparation',None);d['reference_images']=[r['sha256']]
            d['style_lock']=hashlib.sha256(json.dumps({k:m[k] for k in ['style','characters','references']},sort_keys=True,ensure_ascii=False).encode()).hexdigest()
            # Synthetic in-memory fake client only: the real manifest remains closed.
            m['authorization'].update(zero_cost_compute_verified=True,
                                       component_licenses_verified=True,
                                       generation_approved=True)
            b=io.BytesIO();Image.new('RGB',(1024,576),'blue').save(b,format='JPEG');native=b.getvalue()
            class Fake(CloudflareClient):
                calls=0
                def readiness(self,spec):self.receipt={'test_only':True};return self.receipt
                def submit(self,*args,**kwargs):
                    self.calls+=1;return {'raw_base64':base64.b64encode(native).decode(),'receipt':{'test_only':True}}
            c=Fake(m['backend']);a=run(m,root,root/'private',c,True);second=run(m,root,root/'private',c,True)
            self.assertEqual(c.calls,1);self.assertEqual(second['candidate_reuses'],1)
            e=a['shots'][0];self.assertFalse(e['accepted']);self.assertEqual(e['native_format'],'JPEG')
            self.assertEqual((root/e['native_path']).read_bytes(),native)
            with Image.open(io.BytesIO(native)) as n,Image.open(root/e['path']) as png:self.assertEqual(n.tobytes(),png.tobytes())
            # The image must never be serialized as a queue ID or usage log;
            # prior synchronous behavior wrote full base64 into both files.
            private_state=(root/'private/state.json').read_text()
            usage=(root/'private/usage.jsonl').read_text()
            report=(root/'private/report.json').read_text()
            image_base64=base64.b64encode(native).decode()
            self.assertNotIn(image_base64,private_state)
            self.assertNotIn(image_base64,usage)
            self.assertNotIn(image_base64,report)
            self.assertIn('synchronous-response:',private_state)
            self.assertIn('received_unpersisted',usage)
            self.assertEqual(len(json.loads((root/'private/state.json').read_text())['attempts']),1)
