"""One offline proof attempt using the existing strict assembler; never generates media.

Exit 3 means a truthful blocked attempt, 2 invalid/error, 0 a completed audit or
verified private render. Reports are public-safe metadata; raw media stays local.
"""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess

from tools import private_proof_assembler as assembler


def run(assets, blueprint, root, out, render=False):
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    hashes = {}
    try:
        config = json.loads(Path(assets).read_text(encoding='utf-8'))
        plan = json.loads(Path(blueprint).read_text(encoding='utf-8'))
        report = assembler.audit(config, plan, root)
        inputs = {'assets': Path(assets), 'blueprint': Path(blueprint),
                  'renderer': Path(assembler.__file__)}
        if isinstance(config, dict):
            caption = assembler.file_under(Path(root), config.get('caption_master'))
            if caption and caption.is_file():
                inputs['captions'] = caption
        hashes = {key: assembler.digest(path) for key, path in inputs.items()}
        report['movie_created'] = False
        if render and report['status'] == 'READY_PRIVATE_RENDER_ONLY':
            rendered = assembler.render_private(config, plan, root, out)
            # Full decode in addition to existing codec/frame/stream verification.
            subprocess.run(['ffmpeg', '-v', 'error', '-i', rendered['video'],
                            '-f', 'null', '-'], check=True, capture_output=True)
            report.update(rendered)
            report['movie_created'] = True
    except (OSError, ValueError, TypeError, RuntimeError, subprocess.CalledProcessError) as exc:
        report = {'status': 'INVALID', 'movie_created': False,
                  'errors': [type(exc).__name__], 'missing': []}
    report.update(input_hashes=hashes, release_authorized=False,
                  external_spend_usd=0, workspace_usage='unknown',
                  generated_images=0, generated_voice_takes=0,
                  voice_backend='NONE_CONFIGURED_BY_THIS_OFFLINE_RUNNER')
    (out/'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    heading = 'PRIVATE TECHNICAL PROOF — NOT RELEASED' if report['movie_created'] else 'NOT A FILM'
    lines = [f'# {heading}', '', f"Status: `{report['status']}`", '',
             'Uses existing assembler, blueprint and asset registry. No TTS/API/GPU calls.',
             'ChatGPT Library originals are not accessible through this runner.',
             'Existing rejected image trials do not satisfy the production asset gate.',
             'No source, rights, voice or creative approval is changed.', '']
    lines += ['- '+item for item in report.get('errors', [])+report.get('missing', [])]
    (out/'report.md').write_text('\n'.join(lines)+'\n', encoding='utf-8')
    with (out/'usage-ledger.jsonl').open('a', encoding='utf-8') as ledger:
        ledger.write(json.dumps({'at_utc': datetime.now(timezone.utc).isoformat(),
                                 'operation': 'offline_proof_attempt',
                                 'status': report['status'], 'input_hashes': hashes,
                                 'movie_created': report['movie_created'],
                                 'external_spend_usd': 0, 'workspace_usage': 'unknown'})+'\n')
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--assets', type=Path, default=assembler.EXAMPLE)
    parser.add_argument('--blueprint', type=Path, default=assembler.BLUEPRINT)
    parser.add_argument('--root', type=Path, default=assembler.ROOT)
    parser.add_argument('--out', type=Path, default=assembler.ROOT/'build/cloud-proof')
    parser.add_argument('--render-private', action='store_true')
    args = parser.parse_args()
    report = run(args.assets, args.blueprint, args.root, args.out, args.render_private)
    print(report['status'])
    if report['status'] == 'INVALID':
        return 2
    return 3 if report['status'].startswith(('BLOCKED', 'AWAITING')) else 0


if __name__ == '__main__':
    raise SystemExit(main())
