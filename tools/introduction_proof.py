"""Offline opening-scene validator and resumable assembly planner. No provider calls."""
import argparse
import hashlib
import json
from pathlib import Path
from tools.private_proof_assembler import ffmpeg_args, file_under

PROFILE = 'series-narrator-alnilam-continuous-v2'
SHOTS = [f'OPN{i:02}' for i in range(1, 8)]
CUES = ['INTRO-A1-S01-N01', 'INTRO-A1-S01-N02']

def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def plan(config, root, previous=None):
    errors, missing, assets, changed = [], [], {}, []
    if config.get('scene') != 'INTRO-A1-S01' or config.get('profile') != PROFILE:
        errors.append('Wrong scene or approved narrator profile')
    if config.get('release_authorized') is not False or config.get('external_spend_usd') != 0:
        errors.append('Publication and spending must remain disabled')
    expected = SHOTS + CUES + ['captions']
    entries = config.get('assets', {})
    if not isinstance(entries, dict):
        return {'status': 'INVALID', 'errors': ['assets must be an object']}
    if set(entries) - set(expected):
        errors.append('Unknown asset IDs')
    index = json.loads((root/'docs/evidence/introduction-script-audit-2026-11-06.json').read_text())
    hashes = {x['id']: x['display_text_sha256'] for x in index['cues']}
    rejected = {x.get('sha256') for x in json.loads((root/'episodes/berakhot-01-01/trials.json').read_text())['voice_trials'] if x.get('status') in ('rejected_by_user', 'not_applied_approved_baseline_retained')}
    import wave
    for uid in expected:
        item = entries.get(uid)
        if not isinstance(item, dict):
            missing.append(uid); continue
        path = file_under(root, item.get('path'))
        if path is None:
            errors.append(uid+': unsafe path'); continue
        if not path.is_file():
            missing.append(uid); continue
        actual = digest(path)
        if actual != item.get('sha256') or actual in rejected:
            errors.append(uid+': mismatched/rejected hash')
        if item.get('accepted') is not True or item.get('rights_verified') is not True or not item.get('license') or not item.get('provenance'):
            missing.append(uid+': review/rights')
        if uid in CUES:
            if item.get('text_sha256') != hashes[uid] or item.get('profile') != PROFILE:
                errors.append(uid+': wrong spoken text/profile (audition is not scene narration)')
            try:
                with wave.open(str(path)) as wav:
                    if wav.getframerate()!=48000 or wav.getsampwidth()!=2 or wav.getnchannels()!=1 or wav.getcomptype()!='NONE':
                        errors.append(uid+': require mono48kPCM16')
                    if not any(wav.readframes(wav.getnframes())): errors.append(uid+': silent audio')
            except (wave.Error, EOFError): errors.append(uid+': invalid WAV')
        if uid in SHOTS:
            from PIL import Image
            try:
                with Image.open(path) as im: im.verify()
            except Exception: errors.append(uid+': invalid image')
        assets[uid]=actual
        if (previous or {}).get('assets', {}).get(uid)!=actual: changed.append(uid)
    image_hashes=[assets[x] for x in SHOTS if x in assets]
    if len(set(image_hashes))!=len(image_hashes): errors.append('Seven distinct originals required')
    timing=config.get('shots', [])
    if not timing: missing.append('Measured shot/voice/caption timing')
    elif [x.get('id') for x in timing]!=SHOTS or any(type(x.get('duration_frames')) is not int or x['duration_frames']<=0 for x in timing): errors.append('Invalid ordered integer shot timing')
    # READY is deliberately not asserted before caption/voice-slot integration is validated.
    status='INVALID' if errors else 'BLOCKED_MISSING_REAL_MEDIA'
    fingerprint=hashlib.sha256(json.dumps({'config':config,'assets':assets},sort_keys=True).encode()).hexdigest()
    return {'status':status,'errors':errors,'missing':missing,'assets':assets,'changed_assets':changed,'build_key':fingerprint,'cache_hit':False,'assembly_adapter':'tools.private_proof_assembler.ffmpeg_args','render_enabled':False,'remaining_gate':'caption/voice-slot QA and real-media review before render','release_authorized':False}

def assembly_command(config, root, temp):
    """Reuse existing assembly graph, without calling it or changing the75s contract."""
    shots=config['shots']
    blueprint={'shots':shots,'target_duration_frames':sum(s['duration_frames'] for s in shots)}
    media={'images':[dict(config['assets'][uid],shot_id=uid) for uid in SHOTS],
           'voice_takes':config['voice_takes']}
    return ffmpeg_args(media,blueprint,root,temp)

def main():
    p=argparse.ArgumentParser();p.add_argument('--config',default='episodes/berakhot-01-01/introduction-proof.json');p.add_argument('--state',default='build/introduction-proof-state.json');a=p.parse_args()
    root=Path(__file__).resolve().parents[1];config=json.loads((root/a.config).read_text());state=root/a.state
    previous=json.loads(state.read_text()) if state.exists() else None
    report=plan(config,root,previous);state.parent.mkdir(parents=True,exist_ok=True)
    temp=state.with_suffix('.tmp');temp.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n');temp.replace(state)
    print(json.dumps(report,ensure_ascii=False));return 1 if report['errors'] else 0

if __name__=='__main__': raise SystemExit(main())
