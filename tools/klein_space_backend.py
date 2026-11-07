"""Official Klein ZeroGPU Gradio adapter. Shares scene state/cache; not a ComfyUI API."""
import hashlib
import json
import re
import time
import urllib.parse
import urllib.request

SPACE = 'black-forest-labs/FLUX.2-klein-4B'
HOST = 'https://black-forest-labs-flux-2-klein-4b.hf.space'


class ProviderBlocked(ValueError):
    """Safe fixed-code error: do not log provider response bodies or private paths."""


class KleinSpaceClient:
    engine_name = 'HF ZeroGPU / Diffusers'

    def __init__(self, config):
        if config.get('space') != SPACE:
            raise ProviderBlocked('UNAPPROVED_SPACE')
        self.config = config
        # Anonymous only: no HF_TOKEN, paid credits, inference routers or credentials.
        class NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self,*args,**kwargs):
                raise ProviderBlocked('UNEXPECTED_REDIRECT')
        self.opener = urllib.request.build_opener(NoRedirect)

    def open(self, url, data=None, content_type='application/json'):
        return self.opener.open(urllib.request.Request(url,data=data,
            headers={'Content-Type':content_type}),timeout=30)

    def get_json(self, url):
        with self.open(url) as response: return json.load(response)

    def readiness(self):
        metadata=self.get_json('https://huggingface.co/api/spaces/'+SPACE)
        if metadata.get('sha')!=self.config['revision']:
            raise ProviderBlocked('SPACE_REVISION_CHANGED')
        if metadata.get('runtime',{}).get('stage')!='RUNNING':
            raise ProviderBlocked('GPU_SPACE_NOT_RUNNING')
        if not str(metadata.get('runtime',{}).get('hardware',{}).get('current','')).startswith('zero'):
            raise ProviderBlocked('ZERO_GPU_HARDWARE_UNVERIFIED')
        with self.open('https://huggingface.co/spaces/'+SPACE+'/raw/'+self.config['revision']+'/app.py') as response:
            code=response.read()
        if hashlib.sha256(code).hexdigest()!=self.config['app_sha256']:
            raise ProviderBlocked('APP_SOURCE_CHANGED')
        api=self.get_json(HOST+'/gradio_api/info')
        endpoint=api.get('named_endpoints',{}).get('/infer',{})
        expected=['prompt','input_images','mode_choice','seed','randomize_seed','width','height','num_inference_steps','guidance_scale','prompt_upsampling']
        if [p.get('parameter_name') for p in endpoint.get('parameters',[])]!=expected:
            raise ProviderBlocked('INFERENCE_SCHEMA_CHANGED')
        config=self.get_json(HOST+'/config')
        images=[c for c in config.get('components',[]) if c.get('type')=='image' and c.get('props',{}).get('label')=='Result']
        if len(images)!=1 or images[0]['props'].get('format') not in ('png','webp'):
            raise ProviderBlocked('UNSUPPORTED_OUTPUT_FORMAT')
        return {'endpoint_reachable':True,'gpu_allocation':'NOT_TESTED','anonymous':True}

    def prepare(self, spec, reference_paths):
        self.readiness()  # before uploading references or consuming GPU quota
        if spec['seed']>2**31-1:raise ProviderBlocked('SEED_OUTSIDE_SPACE_RANGE')
        gallery=[]
        for path in reference_paths:
            raw=path.read_bytes();boundary='mishnah-'+hashlib.sha256(raw).hexdigest()
            name=hashlib.sha256(raw).hexdigest()+path.suffix.lower()
            body=(f'--{boundary}\r\nContent-Disposition: form-data; name="files"; filename="{name}"\r\nContent-Type: application/octet-stream\r\n\r\n'.encode()+raw+f'\r\n--{boundary}--\r\n'.encode())
            with self.open(HOST+'/gradio_api/upload',body,'multipart/form-data; boundary='+boundary) as response:
                paths=json.load(response)
            if len(paths)!=1:raise ProviderBlocked('UPLOAD_RESPONSE_INVALID')
            gallery.append({'image':{'path':paths[0],'meta':{'_type':'gradio.FileData'}},'caption':None})
        from tools.comfy_scene_images import prompt_text
        prompt=prompt_text(spec)
        width,height=spec['size']
        return {'data':[prompt,gallery,'Distilled (4 steps)',spec['seed'],False,width,height,4,1.0,False]}

    def submit(self, payload, *, zero_cost_verified=False, authorized=False):
        if zero_cost_verified is not True or authorized is not True:
            raise ProviderBlocked('ZERO_COST_AUTHORIZATION_REQUIRED')
        with self.open(HOST+'/gradio_api/call/infer',json.dumps(payload).encode()) as response:
            event=json.load(response)['event_id']
        if not re.fullmatch(r'[a-zA-Z0-9_-]+',event):raise ProviderBlocked('INVALID_EVENT_ID')
        return event

    def wait(self, event, timeout=300):
        if not re.fullmatch(r'[a-zA-Z0-9_-]+',event):raise ProviderBlocked('INVALID_EVENT_ID')
        deadline=time.monotonic()+timeout;event_type='';parts=[]
        with self.open(HOST+'/gradio_api/call/infer/'+event) as response:
            for raw in response:
                if time.monotonic()>deadline:raise TimeoutError('Existing Gradio event unresolved; no resubmit')
                line=raw.decode().rstrip('\r\n')
                if line.startswith('event:'):event_type=line[6:].strip()
                elif line.startswith('data:'):parts.append(line[5:].strip())
                elif not line:
                    data='\n'.join(parts);parts=[]
                    if event_type=='complete': return json.loads(data)
                    if event_type=='error':
                        reason='GPU_QUOTA_OR_QUEUE_BLOCKED' if any(s in data.lower() for s in ('quota','gpu','queue')) else 'GPU_INFERENCE_FAILED'
                        raise ProviderBlocked(reason)
        raise TimeoutError('Existing Gradio event expired/unresolved; no resubmit')

    def result(self, result):
        if not isinstance(result,list) or len(result)!=2 or not isinstance(result[0],dict):
            raise ProviderBlocked('OUTPUT_SCHEMA_CHANGED')
        return {'image':result[0],'seed':result[1]}

    def download(self, result):
        image=result['image'];url=image.get('url')
        if not url:
            url=HOST+'/gradio_api/file='+urllib.parse.quote(image['path'],safe='/')
        parsed=urllib.parse.urlsplit(url)
        if parsed.scheme!='https' or parsed.netloc!=urllib.parse.urlsplit(HOST).netloc or not parsed.path.startswith(('/gradio_api/file=','/file=')):
            raise ProviderBlocked('UNAPPROVED_DOWNLOAD_HOST')
        with self.open(url) as response: raw=response.read(32*1024*1024+1)
        if len(raw)>32*1024*1024:raise ProviderBlocked('OUTPUT_TOO_LARGE')
        return raw


if __name__=='__main__':
    import argparse
    from pathlib import Path
    p=argparse.ArgumentParser(description='Read-only hosted readiness; never submits inference')
    p.add_argument('manifest');a=p.parse_args()
    manifest=json.loads(Path(a.manifest).read_text())
    config=manifest.get('available_backends',{}).get('hf-zero',manifest.get('backend',{}))
    try:
        print(json.dumps(KleinSpaceClient(config).readiness()))
    except ProviderBlocked as error:
        print(json.dumps({'status':'BLOCKED','code':str(error),'generation_submissions':0}))
        raise SystemExit(2)
