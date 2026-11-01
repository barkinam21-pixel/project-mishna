"""Offline 24fps subpixel camera sampler for PRIVATE illustrated Mishnah shots.

Safety: dry-run by default; no network or paid API; refuses to overwrite.
This is one painted plate, not a substitute for a 2.5D scene pack.
Dependencies: Pillow, numpy, opencv-python-headless; ffmpeg and ffprobe in PATH.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys


def sha256(path: Path) -> str:
    d = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1048576), b""):
            d.update(chunk)
    return d.hexdigest()


def make_plan(image: Path, output: Path, expected_hash: str | None,
              fps: int, frames: int, width: int, height: int,
              mode: str, zoom_start: float, zoom_end: float,
              drift_x: float, drift_y: float) -> dict:
    image, output = image.expanduser().resolve(), output.expanduser().resolve()
    if not image.is_file():
        raise ValueError("Input PRIVATE image not found")
    if image.suffix.lower() not in (".png", ".jpg", ".jpeg", ".webp"):
        raise ValueError("Input must be PNG, JPEG or WebP")
    if output.suffix.lower() != ".mp4" or output == image:
        raise ValueError("Output must be an MP4 distinct from input")
    if output.exists():
        raise ValueError("Output already exists; refusing to overwrite")
    if fps not in (24, 25, 30) or frames < 2 or frames > 10000:
        raise ValueError("Unsupported fps or frame count")
    if width < 64 or height < 64 or width % 2 or height % 2:
        raise ValueError("Output resolution must be even and at least 64x64")
    if mode not in ("locked", "subpixel_drift"):
        raise ValueError("Unsupported motion preset")
    if not (1.0 <= zoom_start <= 1.3 and 1.0 <= zoom_end <= 1.3):
        raise ValueError("Zoom must be in [1, 1.3]")
    if abs(drift_x) > 0.15 or abs(drift_y) > 0.15:
        raise ValueError("Camera drift is unreasonably large")
    if mode == "locked":
        zoom_end = zoom_start
        drift_x, drift_y = 0.0, 0.0
    value = sha256(image)
    if expected_hash and value.lower() != expected_hash.lower():
        raise ValueError("Source SHA256 mismatch")
    return {
        "status": "plan_only", "source": str(image), "source_sha256": value,
        "output": str(output), "fps": fps, "frames": frames,
        "duration_seconds": frames / fps, "width": width, "height": height,
        "preset": mode, "zoom_start": zoom_start, "zoom_end": zoom_end,
        "drift_x": drift_x, "drift_y": drift_y,
        "technical_note": "CFR + floating-point inverse mapping / Lanczos4; still plate only",
        "audio": "intentional_silence", "external_paid_api_calls": 0,
        "workspace_usage": "unknown",
    }


def transform_at(t: float, src_w: int, src_h: int, plan: dict):
    zoom = plan["zoom_start"] + (plan["zoom_end"] - plan["zoom_start"]) * t
    cx = src_w * (0.5 + plan["drift_x"] * t)
    cy = src_h * (0.5 + plan["drift_y"] * t)
    # Fill the output aspect without using integer-rounded crop coordinates.
    scale = max(src_w / plan["width"], src_h / plan["height"]) / zoom
    cw, ch = scale * plan["width"], scale * plan["height"]
    left, top = cx - cw / 2, cy - ch / 2
    if min(left, top) < -0.001 or left + cw > src_w + 0.001 or top + ch > src_h + 0.001:
        raise ValueError("Camera motion would reveal an empty frame border")
    return [[cw / plan["width"], 0.0, left],
            [0.0, ch / plan["height"], top]]


def render(plan: dict) -> dict:
    import cv2
    import numpy as np
    from PIL import Image

    ffmpeg, ffprobe = shutil.which("ffmpeg"), shutil.which("ffprobe")
    if not ffmpeg or not ffprobe:
        raise RuntimeError("ffmpeg/ffprobe are required")
    src = np.asarray(Image.open(plan["source"]).convert("RGB"))
    src_h, src_w = src.shape[:2]
    # Validate whole path before creating any output.
    for i in range(plan["frames"]):
        transform_at(i / (plan["frames"] - 1), src_w, src_h, plan)
    target = Path(plan["output"])
    target.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        ffmpeg, "-hide_banner", "-loglevel", "error", "-n",
        "-f", "rawvideo", "-pixel_format", "rgb24", "-video_size",
        f'{plan["width"]}x{plan["height"]}', "-framerate", str(plan["fps"]),
        "-i", "-", "-an", "-c:v", "libx264", "-preset", "medium",
        "-crf", "18", "-pix_fmt", "yuv420p", "-color_primaries", "bt709",
        "-color_trc", "bt709", "-colorspace", "bt709", "-movflags",
        "+faststart", str(target),
    ]
    process = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        assert process.stdin is not None
        for i in range(plan["frames"]):
            t = i / (plan["frames"] - 1)
            m = np.array(transform_at(t, src_w, src_h, plan), dtype=np.float32)
            # Lanczos4 interpolates fractional source coordinates, unlike stepped integer crops.
            frame = cv2.warpAffine(
                src, m, (plan["width"], plan["height"]),
                flags=cv2.INTER_LANCZOS4 | cv2.WARP_INVERSE_MAP,
                borderMode=cv2.BORDER_REPLICATE,
            )
            process.stdin.write(frame.tobytes())
        process.stdin.close()
        stderr = process.stderr.read().decode("utf-8", "replace")
        if process.wait() != 0:
            raise RuntimeError("Encoding failed: " + stderr[-700:])
        data = subprocess.run(
            [ffprobe, "-v", "error", "-select_streams", "v:0", "-show_entries",
             "stream=codec_name,width,height,nb_frames,r_frame_rate,avg_frame_rate",
             "-of", "json", str(target)],
            capture_output=True, text=True, check=True,
        )
        stream = json.loads(data.stdout)["streams"][0]
        if (stream.get("codec_name") != "h264"
                or int(stream.get("nb_frames", 0)) != plan["frames"]
                or (int(stream["width"]), int(stream["height"])) != (plan["width"], plan["height"])
                or stream.get("avg_frame_rate") != f'{plan["fps"]}/1'):
            raise RuntimeError("Verification failed: frame count, codec or CFR")
        subprocess.run([ffmpeg, "-v", "error", "-i", str(target),
                        "-f", "null", "-"], check=True,
                       stdout=subprocess.DEVNULL)
        return {**plan, "status": "rendered_and_verified",
                "output_sha256": sha256(target), "output_bytes": target.stat().st_size}
    except Exception:
        if process.poll() is None:
            process.kill()
            process.wait()
        target.unlink(missing_ok=True)
        raise


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--image", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--expected-sha256")
    p.add_argument("--fps", type=int, default=24)
    p.add_argument("--frames", type=int, default=144)
    p.add_argument("--width", type=int, default=1280)
    p.add_argument("--height", type=int, default=720)
    p.add_argument("--mode", choices=("locked", "subpixel_drift"), default="subpixel_drift")
    p.add_argument("--zoom-start", type=float, default=1.062)
    p.add_argument("--zoom-end", type=float, default=1.086)
    p.add_argument("--drift-x", type=float, default=0.012)
    p.add_argument("--drift-y", type=float, default=0.002)
    p.add_argument("--render", action="store_true", help="Render offline; dry-plan otherwise")
    a = p.parse_args()
    try:
        plan = make_plan(a.image, a.output, a.expected_sha256, a.fps,
                         a.frames, a.width, a.height, a.mode, a.zoom_start,
                         a.zoom_end, a.drift_x, a.drift_y)
        result = render(plan) if a.render else plan
    except Exception as exc:
        print(json.dumps({"status": "error", "reason": str(exc)}, ensure_ascii=False))
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
