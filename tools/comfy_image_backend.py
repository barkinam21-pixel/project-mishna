"""ComfyUI API transport. No model install, cloud provisioning or paid fallback."""
import argparse
import hashlib
import json
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
        if not endpoint.startswith(('http://127.0.0.1:', 'http://localhost:', 'https://')):
            raise ValueError('Use loopback or an authenticated HTTPS tunnel')
        self.endpoint = endpoint.rstrip('/')

    def request(self, route, data=None):
        payload = None if data is None else json.dumps(data).encode()
        req = urllib.request.Request(self.endpoint + route, data=payload,
                                     headers={'Content-Type': 'application/json'})
        with urllib.request.urlopen(req, timeout=30) as response:
            return json.load(response)

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
