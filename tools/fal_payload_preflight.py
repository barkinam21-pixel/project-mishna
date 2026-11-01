"""Build API-schema-correct fal.ai FLUX.2 Pro request proposals OFFLINE.

NO network, NO image generation, NO payment, NO public image output.
Text-to-image endpoint only. Editing requires separate endpoint with private reference consent.
Official model schema: https://fal.ai/models/fal-ai/flux-2-pro/api
"""
from __future__ import annotations
import argparse, json, hashlib, re
from pathlib import Path

MODEL = 'fal-ai/flux-2-pro'
APPROVED_KEYS = frozenset(('prompt','image_size','output_format','seed','safety_tolerance','enable_safety_checker','sync_mode'))
PRIVATE_URL = re.compile(r'https?://|sk-[A-Za-z0-9_-]{10,}|fal_[A-Za-z0-9]{16,}|X-Amz-Signature=', re.I)

class UnsafePlan(ValueError): pass


def inspect_pack(pack: dict):
    if not isinstance(pack,dict): raise UnsafePlan('pack must be object')
    authorization=pack.get('authorization')
    if not isinstance(authorization,dict): raise UnsafePlan('authorization object missing')
    checks={
        'provider':'fal.ai', 'model_id':MODEL,
        'image_generation_in_chatgpt_allowed':False,
        'paid_request_authorized':False,
        'max_requests_this_run':0,
        'authorized_external_spend_usd':0,
        'public_release_authorized':False,
    }
    for key,expected in checks.items():
        if type(authorization.get(key)) is not type(expected) or authorization.get(key)!=expected:
            raise UnsafePlan(f'Unsafe authorization: {key}')
    if pack.get('status')!='dry_run_prompts_only': raise UnsafePlan('must be a dry-run pack')
    out=pack.get('output',{})
    if out.get('asset_visibility')!='PRIVATE' or out.get('public_github_image_upload_allowed') is not False:
        raise UnsafePlan('private media requirement missing')
    if out.get('image_size')!='landscape_16_9' or out.get('output_format')!='png':
        raise UnsafePlan('unexpected image format')
    shots=pack.get('shots')
    if not isinstance(shots,list) or len(shots)!=16:
        raise UnsafePlan('expected 16 original shots')
    for n,s in enumerate(shots,1):
        if s.get('id')!=f'SH{n:02d}' or s.get('asset_status')!='not_generated' or s.get('visual_approval') is not False:
            raise UnsafePlan('missing sequential ungenerated shot')
        if s.get('uses_chatgpt_image_generation') is not False or s.get('references') != []:
            raise UnsafePlan('forbidden ChatGPT images or exposed reference')
    return shots


def request_for_shot(pack:dict, shot_id:str) ->dict:
    shots=inspect_pack(pack)
    matches=[x for x in shots if x['id']==shot_id]
    if len(matches)!=1: raise UnsafePlan('unknown shot ID')
    shot=matches[0]
    style=pack.get('style',{})
    global_style=style.get('positive')
    negative=shot.get('negative_prompt') or style.get('negative')
    if not all(isinstance(x,str) and len(x)>30 for x in (global_style,negative,shot.get('prompt'))):
        raise UnsafePlan('incomplete prompt fragments')
    # No `negative_prompt` field in the official FLUX.2 Pro T2I API input schema.
    # Put unwanted objects in the English text prompt instead of sending unsupported fields.
    prompt= '\n\n'.join([shot['prompt'], 'Visual direction: '+global_style,
                          'Avoid these visual errors: '+negative])
    if PRIVATE_URL.search(prompt): raise UnsafePlan('secret or private URL in prompt')
    if len(prompt)>6500: raise UnsafePlan('prompt excessive length')
    payload={
        'prompt':prompt,
        'image_size':pack['output']['image_size'],
        'output_format':'png',
        'enable_safety_checker':True,
        'sync_mode':False,
    }
    if set(payload)-APPROVED_KEYS: raise UnsafePlan('undocumented payload key')
    fingerprint=hashlib.sha256(json.dumps(payload,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
    return {'endpoint': MODEL, 'shot_id':shot_id,'status':'OFFLINE_UNAUTHORIZED_PREVIEW',
            'payload':payload,'payload_sha256':fingerprint, 'image_generation_calls':0,
            'external_cost_usd_charged':0,'can_execute':False,
            'source_text_locked':False,'public_release_authorized':False,
            'privacy_note':'Never output a generated image URL in public GitHub logs; only private artifact intake',
            'edit_note':'For continuity reference use separate endpoint fal-ai/flux-2-pro/edit, image_urls, private permission; do not add image_urls to this T2I request.'}


def run(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('pack',type=Path)
    p.add_argument('--shot',default='SH01')
    p.add_argument('--output',type=Path)
    a=p.parse_args(argv)
    try:
        pack=json.loads(a.pack.read_text(encoding='utf-8'))
        result=request_for_shot(pack,a.shot)
        rc=0
    except (UnsafePlan, OSError, json.JSONDecodeError) as e:
        result={'status':'REJECTED','can_execute':False,'error':str(e)}
        rc=2
    if a.output:
        a.output.parent.mkdir(parents=True,exist_ok=True)
        a.output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(result,ensure_ascii=False,indent=2))
    return rc

if __name__=='__main__':
    raise SystemExit(run())