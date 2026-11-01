"""Strict, offline assembler for a PRIVATE illustrated Mishnah proof.

Default action is read-only. No image/voice generation, network, cloud API or
publication. A real MP4 may be rendered only with verified, previously supplied
original illustrations, spoken Hebrew WAV takes, caption review and an explicit
private-preview authorization. Never accept the rejected SH01 GPU trial.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import wave

from tools import hebrew_captions

ROOT = Path(__file__).resolve().parents[1]
BLUEPRINT = ROOT / "episodes/berakhot-01-01/proof-blueprint.json"
EXAMPLE = ROOT / "episodes/berakhot-01-01/private-proof-assets.example.json"
BAD_RIGHTS = {"", "unknown", "none", "all rights reserved", "unverified"}
HASH = re.compile(r"^[a-f0-9]{64}$")
IMAGE_EXT = {".png", ".jpg", ".jpeg", ".webp"}


def file_under(root, name):
    """Reject absolute paths, traversal and symlink escapes before touching files."""
    if not isinstance(name, str) or not name or "\x00" in name:
        return None
    path = Path(name)
    if path.is_absolute() or ".." in path.parts:
        return None
    target = (root / path).resolve()
    if not target.is_relative_to(root.resolve()):
        return None
    return target


def image_signature_ok(path):
    """Cheap rejection of mislabeled file extensions (not a full decode test)."""
    with path.open("rb") as item:
        head = item.read(16)
    extension = path.suffix.lower()
    if extension == ".png":
        return head.startswith(b"\x89PNG\r\n\x1a\n")
    if extension in (".jpg", ".jpeg"):
        return head.startswith(b"\xff\xd8\xff")
    if extension == ".webp":
        return head.startswith(b"RIFF") and head[8:12] == b"WEBP"
    return False


def digest(path):
    h = hashlib.sha256()
    with path.open("rb") as src:
        for part in iter(lambda: src.read(1024 * 1024), b""):
            h.update(part)
    return h.hexdigest()


def inspect_wav(path):
    try:
        with wave.open(str(path), "rb") as wav:
            rate, channels, width = wav.getframerate(), wav.getnchannels(), wav.getsampwidth()
            frames, compression = wav.getnframes(), wav.getcomptype()
            raw = wav.readframes(frames)
    except (OSError, EOFError, wave.Error) as exc:
        return None, type(exc).__name__
    if rate != 48000 or channels not in (1, 2) or width != 2 or compression != "NONE":
        return None, "WAV must be 48kHz PCM16 mono/stereo"
    if frames <= 0 or not any(raw):
        return None, "Empty or silent voice WAV"
    return frames, None


def audit(config, blueprint, root=ROOT):
    errors, missing = [], []
    if not isinstance(config, dict) or not isinstance(blueprint, dict):
        return {"status": "INVALID", "errors": ["Expected JSON objects"], "missing": []}
    root = Path(root).resolve()
    shots = blueprint.get("shots")
    total = blueprint.get("target_duration_frames")
    if (blueprint.get("episode_id") != "berakhot-01-01"
            or blueprint.get("fps") != 24 or blueprint.get("sample_rate") != 48000
            or total != 1800 or not isinstance(shots, list) or len(shots) != 16):
        errors.append("Expected original 75-second, 16-shot 24fps/48kHz proof blueprint")
        shots = shots if isinstance(shots, list) else []
    if config.get("episode_id") != "berakhot-01-01":
        errors.append("Incorrect episode_id")
    if config.get("external_spend_enabled") is not False or config.get("release_authorized") is not False:
        errors.append("No external spending or release may be enabled")
    by_id = {}
    timeline = 0
    for shot in shots:
        if not isinstance(shot, dict) or shot.get("start_frame") != timeline:
            errors.append("Noncontiguous or malformed shot timeline")
            break
        if (not isinstance(shot.get("end_frame"), int) or
                shot["end_frame"] - timeline != shot.get("duration_frames")):
            errors.append("Shot duration mismatches frame boundaries")
            break
        timeline = shot["end_frame"]
        by_id[shot["id"]] = shot
    if timeline != total or len(by_id) != len(shots):
        errors.append("Shot list must cover every frame exactly once")

    images = config.get("images", [])
    voices = config.get("voice_takes", [])
    if not isinstance(images, list) or not isinstance(voices, list):
        errors.append("images and voice_takes must be arrays")
        images, voices = [], []
    image_by_shot, seen_hashes = {}, set()
    rejected = set()
    rejected_ledger = root / "episodes/berakhot-01-01/trials.json"
    if rejected_ledger.is_file():
        try:
            trials = json.loads(rejected_ledger.read_text(encoding="utf-8")).get("trials", [])
            rejected = {t.get("image_sha256") for t in trials
                        if not t.get("production_asset_accepted")}
        except (ValueError, OSError, TypeError):
            errors.append("Unable to read rejected SH01 trial ledger")

    for image in images:
        if not isinstance(image, dict) or image.get("shot_id") not in by_id:
            errors.append("Image has unknown shot_id")
            continue
        sid = image["shot_id"]
        if sid in image_by_shot:
            errors.append("Duplicate image for " + sid)
            continue
        image_by_shot[sid] = image
        if image.get("accepted_for_private_preview") is not True or image.get("original_illustration") is not True:
            errors.append(sid + ": unaccepted image or a crop substituted for original art")
        if (image.get("rights_verified_for_private_preview") is not True
                or str(image.get("license", "")).strip().casefold() in BAD_RIGHTS
                or not image.get("provenance")):
            errors.append(sid + ": missing asset-specific rights/license/provenance")
        sha = image.get("sha256")
        if not isinstance(sha, str) or not HASH.fullmatch(sha):
            errors.append(sid + ": valid SHA256 required")
        elif sha in seen_hashes or sha in rejected:
            errors.append(sid + ": duplicate asset or unapproved SH01 trial")
        else:
            seen_hashes.add(sha)
        target = file_under(root, image.get("path"))
        if target is None or target.suffix.lower() not in IMAGE_EXT:
            errors.append(sid + ": unsafe image path or type")
        elif not target.is_file():
            missing.append(sid + ": original illustration missing")
        elif not image_signature_ok(target):
            errors.append(sid + ": image signature does not match extension")
        elif HASH.fullmatch(str(sha)) and digest(target) != sha:
            errors.append(sid + ": image SHA256 mismatch")
    for sid in by_id:
        if sid not in image_by_shot:
            missing.append(sid + ": no accepted original illustration")

    if not voices:
        missing.append("No real Hebrew spoken WAV takes")
    seen_voice = set()
    for item in voices:
        if not isinstance(item, dict):
            errors.append("Invalid voice take")
            continue
        name = item.get("id")
        if not isinstance(name, str) or not name or name in seen_voice:
            errors.append("Voice IDs must be nonempty and unique")
            continue
        seen_voice.add(name)
        start, end = item.get("start_frame"), item.get("end_frame")
        if (not isinstance(start, int) or isinstance(start, bool)
                or not isinstance(end, int) or isinstance(end, bool)
                or not (0 <= start < end <= total)):
            errors.append(name + ": invalid frame slot")
            continue
        if (item.get("real_hebrew_speech_confirmed") is not True
                or item.get("rights_verified_for_private_preview") is not True
                or str(item.get("license", "")).strip().casefold() in BAD_RIGHTS
                or not item.get("speaker") or not item.get("provenance")):
            errors.append(name + ": real speech, speaker, rights and provenance required")
        sha = item.get("sha256")
        if not isinstance(sha, str) or not HASH.fullmatch(sha):
            errors.append(name + ": valid SHA256 required")
        target = file_under(root, item.get("path"))
        if target is None or target.suffix.lower() != ".wav":
            errors.append(name + ": unsafe WAV path")
        elif not target.is_file():
            missing.append(name + ": real recorded WAV missing")
        else:
            length, problem = inspect_wav(target)
            if problem:
                errors.append(name + ": " + problem)
            elif length > (end - start) * 2000:
                errors.append(name + ": WAV exceeds assigned frame slot")
            if isinstance(sha, str) and HASH.fullmatch(sha) and digest(target) != sha:
                errors.append(name + ": WAV SHA256 mismatch")

    caption = file_under(root, config.get("caption_master"))
    if caption is None:
        errors.append("Unsafe or missing caption master path")
    elif not caption.is_file():
        missing.append("Hebrew caption master missing")
    else:
        try:
            master = json.loads(caption.read_text(encoding="utf-8"))
            qa = hebrew_captions.validate(master, require_approval=False)
            if not qa["valid"]:
                missing.append("Private Hebrew captions incomplete: " + "; ".join(qa["errors"]))
            if any(cue.get("end_frame", 0) > total for cue in master.get("cues", [])):
                errors.append("Caption extends beyond 75-second film")
        except (ValueError, OSError, TypeError, AttributeError) as exc:
            errors.append("Malformed caption master: " + type(exc).__name__)
    if config.get("private_caption_text_checked") is not True:
        missing.append("Private caption wording not checked")
    if errors:
        status = "INVALID"
    elif missing:
        status = "BLOCKED_MISSING_REAL_MEDIA"
    elif config.get("private_preview_authorized") is not True:
        status = "AWAITING_PRIVATE_PREVIEW_AUTHORIZATION"
    else:
        status = "READY_PRIVATE_RENDER_ONLY"
    return {"status": status, "errors": errors, "missing": missing,
            "expected_shots": len(by_id), "supplied_images": len(image_by_shot),
            "real_voice_takes": len(voices), "total_frames": total,
            "release_authorized": False, "workspace_usage": "unknown"}


def ffmpeg_args(config, blueprint, root, temp):
    """Only called after a READY audit. Paths become argv, never shell fragments."""
    images = {item["shot_id"]: item for item in config["images"]}
    voices = config["voice_takes"]
    cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y"]
    for shot in blueprint["shots"]:
        img = file_under(root, images[shot["id"]]["path"])
        duration = format(shot["duration_frames"] / 24, ".8f")
        cmd += ["-loop", "1", "-framerate", "24", "-t", duration, "-i", str(img)]
    count = len(blueprint["shots"])
    for item in voices:
        cmd += ["-i", str(file_under(root, item["path"]))]
    cmd += ["-i", "private-captions.srt"]
    graph = []
    for index, shot in enumerate(blueprint["shots"]):
        graph.append(f"[{index}:v]scale=1920:1080:force_original_aspect_ratio=increase,"
                     f"crop=1920:1080,setsar=1,fps=24,"
                     f"trim=end_frame={shot['duration_frames']},setpts=PTS-STARTPTS[v{index}]")
    graph.append("".join(f"[v{i}]" for i in range(count)) +
                 f"concat=n={count}:v=1:a=0[video]")
    graph.append("[video]ass=filename=private-captions.ass,format=yuv420p,"
                 "setparams=range=limited:color_primaries=bt709:"
                 "color_trc=bt709:colorspace=bt709[vout]")
    for i, take in enumerate(voices):
        delay = take["start_frame"] * 2000
        graph.append(f"[{count+i}:a]aresample=48000,aformat=channel_layouts=stereo,"
                     f"adelay=delays={delay}S:all=1[a{i}]")
    if len(voices) == 1:
        mix = "[a0]"
    else:
        mix = "".join(f"[a{i}]" for i in range(len(voices)))
        mix += f"amix=inputs={len(voices)}:duration=longest:normalize=0,"
    samples = blueprint["target_duration_frames"] * 2000
    graph.append(mix + f"atrim=end_sample={samples},apad=whole_len={samples}[aout]")
    cmd += ["-filter_complex", ";".join(graph),
            "-map", "[vout]", "-map", "[aout]", "-map", f"{count+len(voices)}:s:0",
            "-frames:v", str(blueprint["target_duration_frames"]), "-r", "24",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
            "-pix_fmt", "yuv420p", "-profile:v", "high",
            "-color_primaries", "bt709", "-color_trc", "bt709",
            "-colorspace", "bt709", "-color_range", "tv",
            "-c:a", "aac", "-ar", "48000", "-ac", "2", "-b:a", "160k",
            "-c:s", "mov_text", "-metadata:s:a:0", "language=heb",
            "-metadata:s:s:0", "language=heb",
            "-metadata", "title=Mishnah Private Unapproved Proof",
            "-movflags", "+faststart", "private-review.mp4"]
    return cmd


def verify_video(path, total_frames=1800):
    result = subprocess.run(["ffprobe", "-v", "error", "-count_frames",
                             "-show_entries", "stream=codec_type,codec_name,pix_fmt,width,height,nb_read_frames,"
                             "avg_frame_rate,sample_rate,channels,color_primaries,color_transfer,color_space:"
                             "stream_tags=language", "-of", "json", str(path)],
                            check=True, capture_output=True, text=True)
    streams = json.loads(result.stdout)["streams"]
    v = [s for s in streams if s["codec_type"] == "video"]
    a = [s for s in streams if s["codec_type"] == "audio"]
    sub = [s for s in streams if s["codec_type"] == "subtitle"]
    return bool(len(v) == len(a) == len(sub) == 1
                and v[0].get("codec_name") == "h264"
                and v[0].get("pix_fmt") == "yuv420p"
                and v[0].get("nb_read_frames") == str(total_frames)
                and v[0].get("avg_frame_rate") == "24/1"
                and v[0].get("width") == 1920 and v[0].get("height") == 1080
                and v[0].get("color_primaries") == "bt709"
                and v[0].get("color_transfer") == "bt709"
                and v[0].get("color_space") == "bt709"
                and a[0].get("codec_name") == "aac"
                and a[0].get("sample_rate") == "48000"
                and a[0].get("channels") == 2
                and sub[0].get("codec_name") == "mov_text"
                and sub[0].get("tags", {}).get("language") in ("he", "heb"))


def render_private(config, blueprint, root, out):
    report = audit(config, blueprint, root)
    if report["status"] != "READY_PRIVATE_RENDER_ONLY":
        raise ValueError("PRIVATE RENDER BLOCKED: " + report["status"])
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        raise RuntimeError("FFmpeg and FFprobe required; no paid service substituted")
    out = Path(out).resolve()
    out.mkdir(parents=True, exist_ok=True)
    master = json.loads(file_under(root, config["caption_master"]).read_text(encoding="utf-8"))
    # Preserve all publication approval flags; private draft captions are not released.
    qa = hebrew_captions.validate(master, require_approval=False)
    if not qa["valid"]:
        raise ValueError("Private captions invalid")
    # Private draft formatting does NOT manufacture Torah/caption approval flags,
    # even transiently. The public caption exporter remains strictly gated.
    srt, vtt, ass = [], ["WEBVTT", ""], [hebrew_captions.ASS_HEADER.rstrip("\n")]
    for number, cue in enumerate(master["cues"], 1):
        start, end, displayed = cue["start_frame"], cue["end_frame"], cue["display_text"]
        srt.extend([str(number),
                    hebrew_captions.timestamp(start, "srt") + " --> " +
                    hebrew_captions.timestamp(end, "srt"),
                    displayed, ""])
        vtt.extend([hebrew_captions.timestamp(start, "vtt") + " --> " +
                    hebrew_captions.timestamp(end, "vtt"), displayed, ""])
        ass.append("Dialogue: 0,%s,%s,Hebrew,,0,0,0,,%s" %
                   (hebrew_captions.timestamp(start, "ass"),
                    hebrew_captions.timestamp(end, "ass"),
                    displayed.replace("\n", r"\N")))
    caption_files = {"srt": "\n".join(srt).rstrip() + "\n",
                     "vtt": "\n".join(vtt).rstrip() + "\n",
                     "ass": "\n".join(ass).rstrip() + "\n"}
    with tempfile.TemporaryDirectory(prefix="private-proof-", dir=out) as folder:
        temp = Path(folder)
        for ext, contents in caption_files.items():
            (temp / ("private-captions." + ext)).write_text(contents, encoding="utf-8")
        subprocess.run(ffmpeg_args(config, blueprint, root, temp), cwd=temp,
                       check=True, capture_output=True, text=True)
        video = temp / "private-review.mp4"
        if not video.is_file() or not verify_video(video):
            raise RuntimeError("Private film failed codec/frame/stream verification")
        for ext in ("mp4", "srt", "vtt", "ass"):
            name = "private-review.mp4" if ext == "mp4" else "private-captions." + ext
            shutil.copy2(temp / name, out / name)
    return {"status": "PRIVATE_PREVIEW_RENDERED_NOT_RELEASED",
            "video": str(out / "private-review.mp4"),
            "sha256": digest(out / "private-review.mp4"),
            "total_frames": 1800, "human_torah_review": "not_substituted",
            "external_spend_usd": 0, "workspace_usage": "unknown"}


def main():
    parser = argparse.ArgumentParser(description="Private illustrated proof: offline audit or explicit render")
    parser.add_argument("--assets", type=Path, default=EXAMPLE)
    parser.add_argument("--blueprint", type=Path, default=BLUEPRINT)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--out", type=Path, default=ROOT / "build/private-proof")
    parser.add_argument("--render-private", action="store_true",
                        help="Only with verified real media and explicit private-preview authorization")
    args = parser.parse_args()
    try:
        config = json.loads(args.assets.read_text(encoding="utf-8"))
        blueprint = json.loads(args.blueprint.read_text(encoding="utf-8"))
        report = (render_private(config, blueprint, args.root, args.out)
                  if args.render_private else audit(config, blueprint, args.root))
    except (OSError, ValueError, RuntimeError, subprocess.CalledProcessError) as exc:
        print(json.dumps({"status": "ERROR", "detail": str(exc)[:350]},
                         ensure_ascii=False))
        return 2
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["status"] not in ("INVALID", "ERROR") else 2


if __name__ == "__main__":
    sys.exit(main())
