"""Offline, reproducible SH09-style camera-move preview from an existing PRIVATE still.

This does not create a scene pack, voice, subtitles, or a published film.
No network, generative model, or external paid API is used. Default: plan only.
Never commit a private input PNG or the rendered output to the public repository.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys

FPS = 24
FRAME_COUNT = 144
TARGET_SIZE = (1280, 720)
END_ZOOM = 1.03


def file_hash(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open('rb') as f:
        for piece in iter(lambda: f.read(1024 * 1024), b''):
            hasher.update(piece)
    return hasher.hexdigest()


def make_plan(image: Path, output: Path, expected_sha256: str | None) -> dict:
    image = image.expanduser().resolve()
    output = output.expanduser().resolve()
    if not image.is_file():
        raise ValueError('Private input image does not exist')
    if image.suffix.lower() not in ('.png', '.jpg', '.jpeg', '.webp'):
        raise ValueError('Only PNG/JPEG/WebP input is supported')
    if output.suffix.lower() != '.mp4' or output == image:
        raise ValueError('Output must be a distinct MP4 path')
    if output.is_file():
        raise ValueError('Output already exists; refusing to overwrite a reviewed file')
    sha = file_hash(image)
    if expected_sha256 and sha.lower() != expected_sha256.lower():
        raise ValueError('Input SHA256 does not match expected source')
    return {
        'status': 'plan_only', 'source_sha256': sha, 'source_path': str(image),
        'output_path': str(output), 'fps': FPS, 'frames': FRAME_COUNT,
        'duration_seconds': FRAME_COUNT / FPS, 'resolution': '1280x720',
        'camera': 'locked_center, 3 percent push-in across six seconds',
        'sound': 'none', 'scope': 'technical motion preview only; one illustration',
        'external_cash_cost_usd': 0, 'plan_usage': 'unknown',
    }


def render(plan: dict) -> dict:
    ffmpeg, ffprobe = shutil.which('ffmpeg'), shutil.which('ffprobe')
    if not ffmpeg or not ffprobe:
        raise RuntimeError('ffmpeg and ffprobe are required locally')
    out = Path(plan['output_path'])
    out.parent.mkdir(parents=True, exist_ok=True)
    vf = (
        "scale=1600:900:flags=lanczos,"
        "zoompan=z='min(1.0+on*0.00021,1.03)':"
        "x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':"
        "d=1:s=1280x720:fps=24,format=yuv420p"
    )
    cmd = [ffmpeg, '-hide_banner', '-loglevel', 'error', '-n', '-loop', '1',
           '-framerate', str(FPS), '-i', plan['source_path'], '-vf', vf,
           '-frames:v', str(FRAME_COUNT), '-an', '-c:v', 'libx264',
           '-preset', 'medium', '-crf', '19', '-pix_fmt', 'yuv420p',
           '-r', str(FPS), '-color_primaries', 'bt709', '-color_trc', 'bt709',
           '-colorspace', 'bt709', '-movflags', '+faststart', str(out)]
    subprocess.run(cmd, check=True, timeout=120)
    probe = subprocess.run([ffprobe, '-v', 'error', '-select_streams', 'v:0',
                            '-show_entries', 'stream=codec_name,nb_frames,width,height,r_frame_rate',
                            '-show_entries', 'format=duration', '-of', 'json', str(out)],
                           capture_output=True, text=True, check=True, timeout=30)
    info = json.loads(probe.stdout)
    stream = info['streams'][0]
    if (stream['codec_name'] != 'h264' or int(stream['nb_frames']) != FRAME_COUNT
            or (int(stream['width']), int(stream['height'])) != TARGET_SIZE
            or stream['r_frame_rate'] != '24/1'
            or abs(float(info['format']['duration']) - 6.0) > 0.01):
        raise RuntimeError('Rendered file failed technical verification')
    subprocess.run([ffmpeg, '-v', 'error', '-i', str(out), '-f', 'null', '-'],
                   check=True, timeout=120)
    return {**plan, 'status': 'rendered_and_fully_decoded',
            'output_sha256': file_hash(out), 'output_bytes': out.stat().st_size}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--image', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--expected-sha256')
    parser.add_argument('--render', action='store_true', help='Encode six seconds offline (default: plan only)')
    args = parser.parse_args()
    try:
        plan = make_plan(args.image, args.output, args.expected_sha256)
        result = render(plan) if args.render else plan
    except (ValueError, RuntimeError, subprocess.SubprocessError, OSError, KeyError, IndexError) as error:
        print(json.dumps({'status': 'error', 'reason': str(error)}, ensure_ascii=False))
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    sys.exit(main())
