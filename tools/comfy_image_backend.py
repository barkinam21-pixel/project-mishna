"""ComfyUI API transport. No model install, cloud provisioning or paid fallback."""
import argparse
import hashlib
import json
import os
import urllib.parse
import time
import urllib.request
from pathlib import Path


def key(spec):
    return hashlib.sha256(json.dumps(spec, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def plan(manifest, root):
    root = Path(root).resolve()
    rows = []
    for shot in manifest['shots']:
        missing = []
        for ref in shot.get('references', []):
            path = (root / ref['path']).resolve()
            if not path.is_relative_to(root):
                raise ValueError('Reference outside asset root')
            if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != ref['sha256']:
                missing.append(ref['path'])
            if ref.get('synthesis_rights_confirmed') is not True:
                missing.append('Reference synthesis rights unconfirmed')
        rows.append({'shot_id': shot['id'], 'key': key(shot), 'missing': missing,
                     'accepted': False, 'requires_gpu': True})
    if len({x['shot_id'] for x in rows}) != len(rows):
        raise ValueError('Duplicate shot IDs')
    return {'shots': rows, 'generation_submissions': 0, 'workspace_usage': 'unknown'}


class ComfyClient:
    def __init__(self, endpoint):
        parsed = urllib.parse.urlsplit(endpoint)
        if parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ValueError('Credentials/query forbidden in endpoint URL')
        if not (parsed.scheme == 'https' or (parsed.scheme == 'http' and parsed.hostname in ('127.0.0.1', 'localhost'))):
            raise ValueError('Use loopback or an authenticated HTTPS tunnel')
        self.endpoint = endpoint.rstrip('/')
        self.headers = {}
        token = os.environ.get('COMFY_API_TOKEN')
        if token: self.headers['Authorization'] = 'Bearer '+token
        class NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, *args, **kwargs):
                raise ValueError('ComfyUI redirects forbidden')
        self.opener = urllib.request.build_opener(NoRedirect)

    def request(self, route, data=None):
        payload = None if data is None else json.dumps(data).encode()
        req = urllib.request.Request(self.endpoint + route, data=payload,
                                     headers={**self.headers, 'Content-Type': 'application/json'})
        with self.opener.open(req, timeout=30) as response:
            return json.load(response)

    def upload(self, path):
        path = Path(path)
        data = path.read_bytes()
        from PIL import Image
        with Image.open(path) as im:
            im.verify()
        boundary = 'mishnah-'+hashlib.sha256(data).hexdigest()
        name = hashlib.sha256(data).hexdigest()+path.suffix.lower()
        body = (f'--{boundary}\r\nContent-Disposition: form-data; name="image"; filename="{name}"\r\nContent-Type: application/octet-stream\r\n\r\n'.encode()
                +data+f'\r\n--{boundary}--\r\n'.encode())
        req = urllib.request.Request(self.endpoint+'/upload/image',data=body,
            headers={**self.headers,'Content-Type':'multipart/form-data; boundary='+boundary})
        with self.opener.open(req,timeout=30) as response:
            result=json.load(response)
        return '/'.join(x for x in (result.get('subfolder',''),result['name']) if x)

    def image(self, image):
        query=urllib.parse.urlencode({k:image.get(k,'') for k in ('filename','subfolder','type')})
        req=urllib.request.Request(self.endpoint+'/view?'+query,headers=self.headers)
        with self.opener.open(req,timeout=30) as response:
            data=response.read(32*1024*1024+1)
        if len(data)>32*1024*1024: raise ValueError('Image exceeds32MiB')
        return data

    engine_name = 'ComfyUI'

    def prepare(self, spec, reference_paths):
        from tools.comfy_scene_images import compile_klein
        # Verify nodes/model choices before transmitting private reference bytes.
        graph = compile_klein(spec, ['reference.png']*len(reference_paths))
        info = self.request('/object_info')
        if any(n['class_type'] not in info for n in graph.values()):
            raise ValueError('Required native ComfyUI nodes unavailable')
        for node_id, field in [('1','unet_name'),('2','clip_name'),('3','vae_name')]:
            node = graph[node_id]
            choices = info[node['class_type']].get('input',{}).get('required',{}).get(field)
            if not choices or node['inputs'][field] not in choices[0]:
                raise ValueError('Configured model component not installed')
        refs=[self.upload(path) for path in reference_paths]
        return compile_klein(spec,refs)

    def result(self, history):
        images = history.get('outputs',{}).get('13',{}).get('images',[])
        if len(images) != 1 or images[0].get('type') != 'output':
            raise ValueError('Expected exactly one saved output image')
        return {'image': images[0], 'seed': None}

    def download(self, result):
        return self.image(result['image'])

    def submit(self, workflow, *, zero_cost_verified=False, authorized=False):
        if not zero_cost_verified or not authorized:
            raise ValueError('Verified zero-cost compute and generation authorization required')
        # Never retry POST: an uncertain response may already have queued work.
        return self.request('/prompt', {'prompt': workflow})['prompt_id']

    def wait(self, prompt_id, timeout=300):
        import urllib.parse
        route = '/history/' + urllib.parse.quote(prompt_id, safe='')
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            history = self.request(route)
            if prompt_id in history:
                entry = history[prompt_id]
                if entry.get('status', {}).get('status_str') == 'error':
                    raise ValueError('ComfyUI execution failed')
                if entry.get('outputs'):
                    return entry
            time.sleep(1)
        raise TimeoutError('Generation unresolved; inspect history before resubmitting')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('manifest')
    parser.add_argument('--root', default='.')
    args = parser.parse_args()
    print(json.dumps(plan(json.loads(Path(args.manifest).read_text()), args.root), indent=2))
