"""Bounded VoxCPM2 research; no production defaults, paid API or human voice input.

Install runtime: voxcpm==2.0.3 (CPU/CUDA torch matching the environment).
--plan uses only Python's standard library and never downloads or synthesizes.
"""
from pathlib import Path
import argparse
import hashlib
import inspect
import json
import os
import random
import signal
import time

MODEL_ID = 'openbmb/VoxCPM2'
MODEL_REVISION = '32279effe8c19989596f05d353d1447f51d9e915'
PACKAGE_VERSION = '2.0.3'
EXPECTED_HASHES = {'audiovae.pth': '94b5d51e107e0507d4acc976cfdadb64edd6fd06d1f751dadbf2fd1594274bf1', 'model.safetensors': 'f7f964cfa9da23653baec6e6f7750719977ad944ed9f95fe52fe3a620506891d'}
SEED = 731
HEBREW_TEXT = (
    "מאחורי מילות המשנה עומד עולם רחוק. "
    "חכמים למדו, שאלו, והעבירו את המסורת מדור לדור. "
    "כעת נפתח במסכת ברכות, ונשאל שאלה פשוטה: "
    "מתי קוראים את קריאת שמע? "
    "רבן גמליאל אומר: עד שיעלה עמוד השחר. "
    "אבל מה משמעות הדברים? כדי להבין, נחזור אל ראשית הסיפור."
)
VARIANTS = (
    {'id': 'warm', 'description': (
        'A mature male native Israeli Hebrew speaker around 65, a kind wise scholar, '
        'warm rich natural baritone, healthy steady voice, affectionate gentle smile, '
        'patient confident storytelling, clear effortless Hebrew and nuanced emotion.')},
    {'id': 'dramatic', 'description': (
        'The same mature male native Israeli Hebrew speaker around 65, warm and kind, '
        'slightly richer natural chest resonance, quiet cinematic gravitas, thoughtful '
        'pauses, restrained emotional storytelling and clear effortless Hebrew.')},
)


def generation_options(generate_function, seed):
    """2.0.3 has no seed kwarg; newer upstream APIs do. Never request retries."""
    options = dict(cfg_value=2.0, inference_timesteps=10, max_len=1024,
                   normalize=False, denoise=False, retry_badcase=False,
                   retry_badcase_max_times=1)
    if 'seed' in inspect.signature(generate_function).parameters:
        options['seed'] = seed
    return options


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plan', action='store_true')
    parser.add_argument('--device', choices=['cpu', 'cuda', 'auto'], default='auto')
    parser.add_argument('--model-dir', type=Path)
    parser.add_argument('--output-dir', type=Path, default=Path('build/voxcpm2-research'))
    parser.add_argument('--variant', choices=['warm', 'dramatic', 'both'], default='both')
    args = parser.parse_args(argv)
    plan = dict(model=MODEL_ID, revision=MODEL_REVISION, package=PACKAGE_VERSION,
                text=HEBREW_TEXT, variants=list(VARIANTS), seed=SEED,
                generation_started=False, narrator_approved=False,
                publication_approved=False, human_voice_reference=None)
    if args.plan:
        print(json.dumps(plan, ensure_ascii=False, indent=2))
        return 0
    # Heavy dependencies remain inside explicit execution, never import/--plan.
    import importlib.metadata
    import numpy as np
    import soundfile as sf
    import torch
    from voxcpm import VoxCPM
    if importlib.metadata.version('voxcpm') != PACKAGE_VERSION:
        raise RuntimeError(f'This experiment was checked with voxcpm=={PACKAGE_VERSION}')
    torch.set_num_threads(4)
    device = ('cuda' if torch.cuda.is_available() else 'cpu') if args.device == 'auto' else args.device
    if device == 'cuda' and not torch.cuda.is_available():
        raise RuntimeError('CUDA is unavailable; no paid resource will be provisioned')
    args.output_dir.mkdir(parents=True, exist_ok=True)
    execution = dict(plan, device=device, stage='model_files', status='running',
                     backend_dtype='checkpoint default; no quantization override')
    report_path = args.output_dir / 'execution.json'
    def persist():
        report_path.write_text(json.dumps(execution, ensure_ascii=False, indent=2), encoding='utf-8')
    def interrupted(_signum, _frame):
        raise TimeoutError('External runtime bound reached; no automatic synthesis retry')
    signal.signal(signal.SIGTERM, interrupted)
    persist()
    try:
        if args.model_dir:
            model_path = args.model_dir
        else:
            from huggingface_hub import snapshot_download
            model_path = Path(snapshot_download(MODEL_ID, revision=MODEL_REVISION,
                                               allow_patterns=['*.json', '*.py', '*.safetensors', 'audiovae.pth']))
        for name, expected in EXPECTED_HASHES.items():
            with (model_path / name).open('rb') as handle:
                actual = hashlib.file_digest(handle, 'sha256').hexdigest()
            if actual != expected:
                raise ValueError(f'Pinned checkpoint hash mismatch: {name}')
        execution['stage'] = 'load_model'
        persist()
        print('Loading pinned VoxCPM2 on', device, 'without compile/warm-up', flush=True)
        model = VoxCPM.from_pretrained(str(model_path), device=device,
                                       load_denoiser=False, optimize=False)
        sr = int(model.tts_model.sample_rate)
        if sr != 48000:
            raise ValueError(f'Unexpected VoxCPM2 output rate: {sr}; refusing incorrect playback metadata')
        execution['backend_dtype'] = str(model.tts_model.config.dtype)
        options = generation_options(model._generate, SEED)
        execution['options'] = options
        execution['seed_method'] = 'native seed argument' if 'seed' in options else 'random/numpy/torch global seed before each call'
        execution['outputs'] = []
        for variant in VARIANTS:
            if args.variant != 'both' and args.variant != variant['id']:
                continue
            output = args.output_dir / (variant['id'] + '.wav')
            sidecar = output.with_suffix('.json')
            request = dict(model=MODEL_ID, revision=MODEL_REVISION, package=PACKAGE_VERSION,
                           text=HEBREW_TEXT, voice_description=variant['description'], seed=SEED,
                           options=options, device=device)
            # New design first; second conditions only on our OWN synthetic first voice.
            reference = args.output_dir / 'warm.wav' if variant['id'] == 'dramatic' else None
            if reference and not reference.exists():
                raise FileNotFoundError('Create warm first; no human/dataset fallback reference is allowed')
            request['synthetic_reference_sha256'] = hashlib.sha256(reference.read_bytes()).hexdigest() if reference else None
            if output.exists() or sidecar.exists():
                if not (output.exists() and sidecar.exists()):
                    raise ValueError('Incomplete prior result; preserve it for investigation, do not overwrite')
                prior = json.loads(sidecar.read_text())
                if prior['request'] != request or hashlib.sha256(output.read_bytes()).hexdigest() != prior['sha256']:
                    raise ValueError('Prior result differs or is corrupt; no automatic rerun')
                execution['outputs'].append(prior)
                continue
            execution['stage'] = variant['id']
            execution['generation_started'] = True
            persist()
            print('Generating', variant['id'], 'once; retries disabled', flush=True)
            random.seed(SEED)
            np.random.seed(SEED)
            torch.manual_seed(SEED)
            if torch.cuda.is_available():
                torch.cuda.manual_seed_all(SEED)
            started = time.monotonic()
            wave = np.asarray(model.generate(text=f"({variant['description']}){HEBREW_TEXT}",
                                             reference_wav_path=str(reference) if reference else None,
                                             **options), dtype=np.float32)
            if wave.ndim != 1 or wave.size < sr or not np.isfinite(wave).all():
                raise ValueError('Invalid, empty, too short or non-finite waveform')
            peak = float(np.max(np.abs(wave)))
            if peak <= 1e-5:
                raise ValueError('No audible signal generated')
            sf.write(output.with_name(variant['id'] + '-raw-float.wav'), wave, sr, subtype='FLOAT')
            gain = min(1.0, .95 / peak)
            sf.write(output, wave * gain, sr, subtype='PCM_16')
            item = dict(request=request, sample_rate=sr, samples=len(wave), seconds=len(wave)/sr,
                        raw_peak=peak, static_gain=float(gain), elapsed_seconds=time.monotonic()-started,
                        sha256=hashlib.sha256(output.read_bytes()).hexdigest(),
                        evaluated_by_human=False, narrator_approved=False, publication_approved=False,
                        processing='global gain only; raw float preserved, no Pitch/EQ/time stretch')
            sidecar.write_text(json.dumps(item, ensure_ascii=False, indent=2), encoding='utf-8')
            execution['outputs'].append(item)
            persist()
            print('Saved', output, item['seconds'], 'seconds', flush=True)
        execution.update(status='completed', stage='saved')
        persist()
        return 0
    except Exception as exc:
        execution.update(status='failed', error_type=type(exc).__name__, error=str(exc))
        persist()
        raise


if __name__ == '__main__':
    raise SystemExit(main())
