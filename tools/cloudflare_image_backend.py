"""Private synchronous Cloudflare adapter. No public upload or uncertain POST retry."""
import base64
import datetime as dt
import hashlib
import io
import json
import math
import os
import urllib.request
from PIL import Image

MODEL = '@cf/black-forest-labs/flux-2-klein-4b'


class CloudflareBlocked(ValueError):
    pass


class CloudflareClient:
    engine_name = 'Cloudflare Workers AI'

    def __init__(self, config, request=None):
        self.config = config
        self.account = os.environ.get('CLOUDFLARE_ACCOUNT_ID', '')
        self.token = os.environ.get('CLOUDFLARE_API_TOKEN', '')
        self.transport = request or self._request
        self.receipt = {}

    def _request(self, method, path, body=None, content_type='application/json'):
        if not self.account or not self.token:
            raise CloudflareBlocked('CREDENTIALS_UNAVAILABLE')
        class NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, *args, **kwargs):
                return None
        data = json.dumps(body).encode() if isinstance(body, dict) else body
        req = urllib.request.Request('https://api.cloudflare.com/client/v4'+path, data=data,
            method=method, headers={'Authorization':'Bearer '+self.token,'Content-Type':content_type})
        try:
            with urllib.request.build_opener(NoRedirect).open(req, timeout=120) as response:
                result = json.load(response)
        except Exception:
            # Never retain headers, bearer tokens, private content or signed URLs.
            raise CloudflareBlocked('TRANSPORT_FAILED_NO_AUTOMATIC_RETRY') from None
        if result.get('success') is False or result.get('errors'):
            raise CloudflareBlocked('PROVIDER_REJECTED')
        return result

    def readiness(self, spec):
        now = dt.datetime.now(dt.timezone.utc)
        policy = self.config.get('safety', {})
        if policy.get('private_direct_api_verified') is not True or policy.get('licenses_verified') is not True:
            raise CloudflareBlocked('PRIVACY_OR_LICENSE_UNVERIFIED')
        # Historic or delayed analytics alone cannot guarantee no billable overage.
        if policy.get('free_hard_cap_verified') is not True:
            raise CloudflareBlocked('NO_CHARGE_HARD_CAP_UNVERIFIED')
        # A provider's "zero data retention" label does not settle the
        # upstream partner license governing private image references.
        # This is a separate, fail-closed approval gate, not a claim that
        # any particular terms automatically override the provider policy.
        if policy.get('partner_private_reference_terms_verified') is not True:
            raise CloudflareBlocked('PARTNER_PRIVATE_REFERENCE_TERMS_UNVERIFIED')
        checked = dt.datetime.fromisoformat(policy.get('verified_at','').replace('Z','+00:00'))
        if checked.tzinfo is None or not 0 <= (now-checked).total_seconds() <= 86400:
            raise CloudflareBlocked('SAFETY_EVIDENCE_EXPIRED')
        models = self.transport('GET',f'/accounts/{self.account}/ai/models/search?search=flux-2-klein-4b')
        if not any(m.get('name') == MODEL for m in models.get('result', [])):
            raise CloudflareBlocked('MODEL_UNAVAILABLE')
        start = now.date().isoformat()+'T00:00:00Z'
        query = 'query { viewer { accounts(filter:{accountTag:'+json.dumps(self.account)+'}) { aiInferenceAdaptiveGroups(limit:1,filter:{datetime_geq:'+json.dumps(start)+',datetime_leq:'+json.dumps(now.isoformat())+'}) { sum { totalNeurons } } } } }'
        usage = self.transport('POST','/graphql',{'query':query})
        try:
            accounts = usage['data']['viewer']['accounts']
            assert len(accounts)==1 and not usage.get('errors')
            used = sum(g['sum']['totalNeurons'] for g in accounts[0]['aiInferenceAdaptiveGroups'])
            assert math.isfinite(used) and used >= 0
        except (KeyError, TypeError, AssertionError):
            raise CloudflareBlocked('USAGE_UNKNOWN') from None
        w,h = spec['size']
        estimate = math.ceil(w/512)*math.ceil(h/512)*26.05 + len(spec.get('director',{}).get('reference_preparation',{}).get('crops') or spec['references'])*5.37
        if used + estimate + 1000 > 10000:
            raise CloudflareBlocked('FREE_ALLOWANCE_HEADROOM_INSUFFICIENT')
        self.receipt = {'started_at':now.isoformat(),'model':MODEL,'neurons_before':used,
                        'estimated_neurons':estimate,'charged_usd':None,'private_direct_api':True}
        return self.receipt

    def prepare(self, spec, reference_paths):
        from tools.comfy_scene_images import prompt_text
        self.readiness(spec)
        if not 1 <= len(reference_paths) <= 4:
            raise CloudflareBlocked('REFERENCE_COUNT_INVALID')
        images=[]
        actual_refs=spec.get('director',{}).get('reference_preparation',{}).get('crops') or spec['references']
        if len(actual_refs)!=len(reference_paths):raise CloudflareBlocked('REFERENCE_COUNT_MISMATCH')
        for path,ref in zip(reference_paths,actual_refs):
            raw=path.read_bytes()
            if hashlib.sha256(raw).hexdigest()!=ref['sha256']:
                raise CloudflareBlocked('REFERENCE_CHANGED')
            with Image.open(io.BytesIO(raw)) as im:
                im.load(); im=im.convert('RGB'); im.thumbnail((511,511),Image.Resampling.LANCZOS)
                b=io.BytesIO(); im.save(b,format='PNG'); images.append(b.getvalue())
        self.receipt['references']=[{'sha256':r['sha256'],'role':r.get('role')} for r in actual_refs]
        self.images=images
        return {'prompt':prompt_text(spec),'width':spec['size'][0],'height':spec['size'][1],
                'seed':spec['seed'],'guidance':spec.get('director',{}).get('generation_parameters',{}).get('guidance',1.0)}

    def submit(self, payload, *, zero_cost_verified=False, authorized=False):
        if not authorized or not zero_cost_verified or not self.receipt:
            raise CloudflareBlocked('SUBMISSION_NOT_AUTHORIZED')
        boundary='mishnah-'+os.urandom(16).hex(); parts=[]
        for k,v in payload.items():
            parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode())
        for i,raw in enumerate(self.images):
            parts.extend([f'--{boundary}\r\nContent-Disposition: form-data; name="input_image_{i}"; filename="reference.png"\r\nContent-Type: image/png\r\n\r\n'.encode(),raw,b'\r\n'])
        parts.append(f'--{boundary}--\r\n'.encode())
        result=self.transport('POST',f'/accounts/{self.account}/ai/run/{MODEL}',b''.join(parts),'multipart/form-data; boundary='+boundary)
        try:
            raw=base64.b64decode(result['result']['image'],validate=True)
            if not raw: raise ValueError()
        except (KeyError,TypeError,ValueError):
            raise CloudflareBlocked('INVALID_OR_EMPTY_IMAGE_RESPONSE') from None
        self.receipt.update(finished_at=dt.datetime.now(dt.timezone.utc).isoformat(),parameters=payload,
                            provider_result='IMAGE_RETURNED',native_sha256=hashlib.sha256(raw).hexdigest())
        return {'raw_base64':base64.b64encode(raw).decode(),'receipt':self.receipt}

    def wait(self, event, timeout=300): return event
    def result(self, history): return history
    def download(self, result): return base64.b64decode(result['raw_base64'],validate=True)
