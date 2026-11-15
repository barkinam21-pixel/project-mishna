"""Scene-native 15-shot private rough cut through the existing M2 FFmpeg assembler.

OFFLINE ONLY: no provider, no Drive client, no upload, no publishing. A drawing
of a missing shot is a labeled slate, never an "AI illustration". Existing media
is used only after per-shot private-preview rights and SHA verification.
A playable output is always DRAFT, not creative/source/voice approval.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import shutil
import subprocess
import sys
import tempfile
import wave
from pathlib import Path

from tools import hebrew_captions, private_proof_assembler
from tools.scene_factory import SceneBlocked, digest, file_sha, load, within
from tools.scene_production_packet import build_packet

HERE = Path(__file__).resolve().parents[1]
SCENE = "episodes/berakhot-01-01/scene-prologue-v02.json"
SAMPLES_PER_FRAME = 2000
FPS = 24

TRIAL_LEDGER = "episodes/berakhot-01-01/trials.json"


def _reject_previously_rejected_media(root, sha, kind):
    """A metadata checkbox cannot re-accept bytes rejected in the real trial ledger."""
    ledger = load(within(root, TRIAL_LEDGER))
    if ledger.get("episode_id") != "berakhot-01-01":
        raise SceneBlocked("PREVIEW_TRIAL_HISTORY_INVALID")
    if kind == "image":
        records = ledger.get("trials")
        if not isinstance(records, list):
            raise SceneBlocked("PREVIEW_TRIAL_HISTORY_INVALID")
        rejected = any(isinstance(x, dict) and x.get("image_sha256") == sha
                       and x.get("production_asset_accepted") is not True for x in records)
    elif kind == "voice":
        records = ledger.get("voice_trials")
        if not isinstance(records, list):
            raise SceneBlocked("PREVIEW_TRIAL_HISTORY_INVALID")
        rejected = any(isinstance(x, dict) and x.get("sha256") == sha
                       and x.get("status") == "rejected_by_user" for x in records)
    else:
        raise SceneBlocked("PREVIEW_TRIAL_MEDIA_KIND_INVALID")
    if rejected:
        raise SceneBlocked("PREVIEW_KNOWN_REJECTED_" + kind.upper())



def _private_path(root: Path, filename: str) -> Path:
    if not isinstance(filename, str) or not filename.startswith("private-media/"):
        raise SceneBlocked("PREVIEW_PRIVATE_MEDIA_PATH_REQUIRED")
    path = within(root, filename)
    if "private-media" not in path.relative_to(root).parts:
        raise SceneBlocked("PREVIEW_PRIVATE_MEDIA_PATH_REQUIRED")
    return path


def _checked_image(root, shot_id, asset_key, value):
    if not isinstance(value, dict):
        raise SceneBlocked("PREVIEW_IMAGE_BINDING_INVALID")
    if (value.get("shot_id") != shot_id or value.get("asset_key") != asset_key
            or value.get("source_asset_id") != shot_id
            or value.get("time_of_day") != "dawn"
            or value.get("accepted_for_private_preview") is not True
            or value.get("rights_verified_for_private_preview") is not True
            or not value.get("rights_evidence")):
        raise SceneBlocked("PREVIEW_IMAGE_SCOPE_OR_RIGHTS_NOT_VERIFIED:" + shot_id)
    path = _private_path(root, value.get("path"))
    sha = value.get("sha256")
    if (path.suffix.lower() not in (".png", ".jpg", ".jpeg", ".webp")
            or not isinstance(sha, str) or len(sha) != 64
            or not path.is_file() or file_sha(path) != sha):
        raise SceneBlocked("PREVIEW_IMAGE_BYTES_NOT_VERIFIED:" + shot_id)
    if not private_proof_assembler.image_signature_ok(path):
        raise SceneBlocked("PREVIEW_IMAGE_FORMAT_INVALID:" + shot_id)
    _reject_previously_rejected_media(root, sha, "image")
    return path, sha


def _checked_voice(root, scene, item, total):
    if not isinstance(item, dict):
        raise SceneBlocked("PREVIEW_VOICE_BINDING_INVALID")
    if (item.get("script_sha256") != scene["script"]["sha256"]
            or item.get("private_preview_rights_verified") is not True
            or item.get("hebrew_speech_confirmed") is not True
            or not item.get("rights_evidence") or not item.get("speaker")):
        raise SceneBlocked("PREVIEW_VOICE_SCRIPT_OR_RIGHTS_MISSING")
    start, end = item.get("start_frame"), item.get("end_frame")
    if (type(start) is not int or type(end) is not int or
            not 0 <= start < end <= total):
        raise SceneBlocked("PREVIEW_VOICE_FRAME_RANGE_INVALID")
    path = _private_path(root, item.get("path"))
    sha = item.get("sha256")
    if (path.suffix.lower() != ".wav" or not isinstance(sha, str) or len(sha) != 64
            or not path.is_file() or file_sha(path) != sha):
        raise SceneBlocked("PREVIEW_VOICE_BYTES_NOT_VERIFIED")
    length, problem = private_proof_assembler.inspect_wav(path)
    if problem or length > (end-start) * SAMPLES_PER_FRAME:
        raise SceneBlocked("PREVIEW_VOICE_PCM_OR_TIMING_INVALID")
    _reject_previously_rejected_media(root, sha, "voice")
    return {"start_frame": start, "end_frame": end, "path": item["path"], "sha256": sha}


def _checked_sound(root, item, spotting):
    """Bind one licensed PRIVATE sound file to an authored EP-P spotting window.

    A sound spot is editorial direction, not a recording or rights permission.
    Its byte identity, sample timing, role and private review scope are checked.
    """
    if not isinstance(item, dict):
        raise SceneBlocked("PREVIEW_SOUND_BINDING_INVALID")
    spot = spotting.get(item.get("spot_id"))
    if spot is None or item.get("shot_id") != spot["shot_id"]:
        raise SceneBlocked("PREVIEW_SOUND_SPOT_NOT_IN_SCENE")
    if (item.get("kind") not in ("ambience", "foley", "sfx", "music")
            or item.get("private_preview_rights_verified") is not True
            or item.get("reviewed_for_private_preview") is not True
            or not isinstance(item.get("rights_evidence"), str)
            or not item["rights_evidence"].strip()
            or not isinstance(item.get("license"), str)
            or item["license"].strip().casefold() in ("", "unknown", "none", "all rights reserved")):
        raise SceneBlocked("PREVIEW_SOUND_RIGHTS_OR_REVIEW_MISSING")
    start, end = item.get("start_sample"), item.get("end_sample")
    if (type(start) is not int or type(end) is not int
            or start != spot["start_sample"] or not start < end <= spot["end_sample"]
            or start % SAMPLES_PER_FRAME or end % SAMPLES_PER_FRAME):
        raise SceneBlocked("PREVIEW_SOUND_SPOTTING_TIMING_INVALID")
    gain = item.get("gain_db", -18)
    if type(gain) not in (int, float) or not math.isfinite(gain) or not -30 <= gain <= -12:
        raise SceneBlocked("PREVIEW_SOUND_GAIN_INVALID")
    path = _private_path(root, item.get("path"))
    sha = item.get("sha256")
    if (path.suffix.lower() != ".wav" or not isinstance(sha, str)
            or len(sha) != 64 or not path.is_file() or file_sha(path) != sha):
        raise SceneBlocked("PREVIEW_SOUND_BYTES_NOT_VERIFIED")
    length, problem = private_proof_assembler.inspect_wav(path)
    if problem or length > end-start:
        raise SceneBlocked("PREVIEW_SOUND_PCM_OR_TIMING_INVALID")
    return {"shot_id": spot["shot_id"], "spot_id": item["spot_id"],
            "kind": item["kind"], "path": item["path"], "sha256": sha,
            "start_frame": start // SAMPLES_PER_FRAME,
            "end_frame": end // SAMPLES_PER_FRAME, "gain_db": gain}


def _render_cache_key(plan):
    """An output cache is valid only for the exact renderer, font and encoders."""
    from tools.private_storyreel import font_path
    dependencies = (
        Path(__file__), Path(private_proof_assembler.__file__),
        Path(hebrew_captions.__file__), HERE / "tools/private_storyreel.py",
    )
    version_lines = []
    for executable in ("ffmpeg", "ffprobe"):
        version = subprocess.run([executable, "-version"], check=True,
                                 capture_output=True, text=True, timeout=15).stdout.splitlines()
        if not version:
            raise SceneBlocked("PREVIEW_ENCODER_VERSION_UNKNOWN")
        version_lines.append(version[0])
    return digest({
        "plan_key": plan["preview_key"],
        "renderer_source_sha256": [file_sha(p) for p in dependencies],
        "font_sha256": file_sha(Path(font_path())),
        "encoder_versions": version_lines,
    })


def build_plan(root: Path, media: dict | None = None):
    """Exact v02 shot times; source/creative review never inferred from media."""
    root = Path(root).resolve()
    scene = load(within(root, SCENE))
    bible = load(within(root, scene["bible"]["path"]))
    packet = build_packet(scene, bible, root)
    if (scene["id"] != "ACT1-PROLOGUE" or len(packet["jobs"]) != 15
            or packet["duration_frames"] != 2184
            or packet["generation_gate_closed"] is not True
            or packet["provider_dispatch_authorized"] is not False):
        raise SceneBlocked("PREVIEW_NOT_THE_LOCKED_DRAFT_SCENE")
    media = {} if media is None else media
    if not isinstance(media, dict):
        raise SceneBlocked("PREVIEW_MEDIA_BINDINGS_INVALID")
    if set(media) - {"images", "voices", "sounds"}:
        raise SceneBlocked("PREVIEW_UNSUPPORTED_MEDIA_BINDING")
    images, voices = media.get("images", []), media.get("voices", [])
    sounds = media.get("sounds", [])
    if not all(isinstance(items, list) for items in (images, voices, sounds)):
        raise SceneBlocked("PREVIEW_MEDIA_BINDINGS_INVALID")
    ids = [j["shot_id"] for j in packet["jobs"]]
    mapping, hashes = {}, set()
    for entry in images:
        if not isinstance(entry, dict) or entry.get("shot_id") not in ids:
            raise SceneBlocked("PREVIEW_UNKNOWN_SHOT_BINDING")
        sid = entry["shot_id"]
        if sid in mapping:
            raise SceneBlocked("PREVIEW_DUPLICATE_SHOT_BINDING")
        job = packet["jobs"][ids.index(sid)]
        path, sha = _checked_image(root, sid, job["asset_key"], entry)
        if sha in hashes:
            raise SceneBlocked("PREVIEW_DUPLICATED_ORIGINAL_IMAGE")
        hashes.add(sha)
        mapping[sid] = {"path": entry["path"], "sha256": sha}
    voice_entries = [_checked_voice(root, scene, x, packet["duration_frames"]) for x in voices]
    if len({(x["path"], x["start_frame"]) for x in voice_entries}) != len(voice_entries):
        raise SceneBlocked("PREVIEW_DUPLICATE_VOICE_BINDING")
    spots = {spot["id"]: dict(spot, shot_id=job["shot_id"])
             for job in packet["jobs"] for spot in job["sound_spotting"]}
    sound_entries = [_checked_sound(root, item, spots) for item in sounds]
    if (len({x["spot_id"] for x in sound_entries}) != len(sound_entries)
            or len({(x["path"], x["start_frame"]) for x in sound_entries}) != len(sound_entries)):
        raise SceneBlocked("PREVIEW_DUPLICATE_SOUND_BINDING")
    sound_entries.sort(key=lambda x: (x["start_frame"], x["spot_id"]))
    slots = []
    cursor = 0
    for job in packet["jobs"]:
        if job["start_frame"] != cursor or job["end_frame"] <= cursor:
            raise SceneBlocked("PREVIEW_NONCONTIGUOUS_SHOTS")
        slots.append({
            "shot_id": job["shot_id"], "start_frame": cursor,
            "end_frame": job["end_frame"], "duration_frames": job["duration_frames"],
            "purpose": job["visual_spec"]["purpose"],
            "source_layer": job["source_label"],
            "image": mapping.get(job["shot_id"]),
            "media_status": "VERIFIED_PRIVATE_PREVIEW_ONLY" if job["shot_id"] in mapping
                            else "MISSING_OR_UNAPPROVED_SLATE",
        })
        cursor = job["end_frame"]
    key = digest({"packet": packet["packet_sha256"], "bound_images": mapping,
                  "voices": voice_entries, "sounds": sound_entries,
                  "renderer": "SCENE_V02_M2_DRAFT_V2_SOUND_STEMS"})
    return {
        "status": "PRIVATE_DRAFT_ASSEMBLY_PLAN_NOT_FILM", "scene_id": scene["id"],
        "packet_sha256": packet["packet_sha256"], "preview_key": key,
        "total_frames": cursor, "fps": 24, "shots": slots,
        "verified_private_preview_images": len(mapping),
        "missing_or_unapproved_images": len(slots)-len(mapping),
        "verified_hebrew_voice_clips": len(voice_entries),
        "verified_private_sound_stems": len(sound_entries),
        "voices": voice_entries, "sounds": sound_entries,
        "editorial_source_rights_approval": False,
        "original_image_inference_requests": 0,
        "external_cost_usd": 0, "workspace_usage": "unknown",
    }


def _stamp(frame):
    milliseconds = round(frame * 1000 / FPS)
    h, rem = divmod(milliseconds, 3600000)
    m, rem = divmod(rem, 60000)
    s, ms = divmod(rem, 1000)
    return f"{h:02d}:{m:02d}:{s:02d}.{ms:03d}"


def _write_slate(shot, image_path, destination):
    from PIL import Image, ImageDraw, ImageFont
    from tools.private_storyreel import font_path, rtl

    f = ImageFont.truetype(font_path(), 35)
    small = ImageFont.truetype(font_path(), 25)
    if image_path is None:
        im = Image.new("RGB", (1280, 720), (23, 30, 45))
    else:
        with Image.open(image_path) as source:
            if source.width < 32 or source.height < 32:
                raise SceneBlocked("PREVIEW_IMAGE_DIMENSIONS_INVALID")
            im = source.convert("RGB").resize((1280, 720), Image.Resampling.LANCZOS)
    draw = ImageDraw.Draw(im)
    draw.rectangle((0, 0, 1280, 100), fill=(11, 16, 27))
    rtl(draw, (1240, 38), "טיוטת בימוי פרטית — לא סרט מאושר", f, (255, 219, 165))
    draw.text((45, 52), shot["shot_id"], font=small, fill=(236, 235, 227))
    if image_path is None:
        draw.rectangle((90, 152, 1190, 570), outline=(111, 124, 140), width=4)
        rtl(draw, (1130, 285), "חסר איור מקורי מאושר", f, (239, 237, 226))
        rtl(draw, (1130, 360), shot["purpose"][:70], small, (205, 212, 220))
    draw.rectangle((0, 638, 1280, 720), fill=(13, 20, 33))
    rtl(draw, (1240, 683), "סקיצה בלבד • " + shot["source_layer"][:45],
        small, (240, 221, 200))
    im.save(destination, format="PNG")


def _silence_wav(path, frames):
    with wave.open(str(path), "wb") as sound:
        sound.setnchannels(2)
        sound.setsampwidth(2)
        sound.setframerate(48000)
        chunk = b"\0" * (SAMPLES_PER_FRAME * 4)
        for _ in range(frames):
            sound.writeframesraw(chunk)
        sound.writeframes(b"")


def render_private_draft(root: Path, out: str, media: dict | None = None):
    root = Path(root).resolve()
    target = _private_path(root, out)
    if target.suffix.lower() != ".mp4" or not target.parent.is_dir():
        raise SceneBlocked("PREVIEW_OUTPUT_PRIVATE_MP4_DIRECTORY_REQUIRED")
    if not all(shutil.which(tool) for tool in ("ffmpeg", "ffprobe")):
        raise SceneBlocked("PREVIEW_FFMPEG_MISSING")
    plan = build_plan(root, media)
    render_key = _render_cache_key(plan)
    report_path = target.with_suffix(".qa.json")
    srt_path, ass_path = target.with_suffix(".srt"), target.with_suffix(".ass")
    output_files = (target, report_path, srt_path, ass_path)
    if any(p.exists() for p in output_files):
        if not all(p.is_file() for p in output_files):
            raise SceneBlocked("PREVIEW_PARTIAL_OUTPUT_EXISTS")
        prior = json.loads(report_path.read_text(encoding="utf-8"))
        if (prior.get("status") != "PRIVATE_DRAFT_TECH_PASS_NOT_ART_OR_SOURCE_APPROVAL"
                or prior.get("release_authorized") is not False
                or prior.get("preview_key") != render_key
                or prior.get("video_sha256") != file_sha(target)
                or prior.get("caption_srt_sha256") != file_sha(srt_path)
                or prior.get("caption_ass_sha256") != file_sha(ass_path)):
            raise SceneBlocked("PREVIEW_CACHED_OUTPUT_CHANGED")
        return dict(prior, cache_hit=True)
    with tempfile.TemporaryDirectory(prefix="scene-draft-", dir=target.parent) as directory:
        work = Path(directory)
        images = []
        for shot in plan["shots"]:
            name = shot["shot_id"] + ".png"
            original = (_private_path(root, shot["image"]["path"])
                        if shot["image"] else None)
            _write_slate(shot, original, work / name)
            images.append({"shot_id": shot["shot_id"],
                           "path": str((work / name).relative_to(root))})
        voices = [{"start_frame": v["start_frame"], "path": v["path"]}
                  for v in plan["voices"]]
        sound_takes = [{"start_frame": v["start_frame"], "path": v["path"],
                        "gain_db": v["gain_db"]} for v in plan["sounds"]]
        if not voices and not sound_takes:
            wav = work / "INTENTIONAL_SILENCE_NOT_NARRATION.wav"
            _silence_wav(wav, plan["total_frames"])
            voices.append({"start_frame": 0, "path": str(wav.relative_to(root))})
        srt, ass = [], [hebrew_captions.ASS_HEADER]
        for i, shot in enumerate(plan["shots"], 1):
            caption = "סקיצת בימוי בלבד — " + shot["shot_id"]
            start, end = _stamp(shot["start_frame"]), _stamp(shot["end_frame"])
            srt.extend([str(i), start.replace(".", ",") + " --> " + end.replace(".", ","),
                        caption, ""])
            ass.append(f"Dialogue: 0,{start[:-1]},{end[:-1]},Hebrew,,0,0,0,,{caption}\n")
        (work / "private-captions.srt").write_text("\n".join(srt), encoding="utf-8")
        (work / "private-captions.ass").write_text("".join(ass), encoding="utf-8")
        blueprint = {
            "target_duration_frames": plan["total_frames"],
            "shots": [{"id": x["shot_id"], "duration_frames": x["duration_frames"]}
                      for x in plan["shots"]],
        }
        cfg = {"images": images, "voice_takes": voices, "sound_takes": sound_takes}
        command = private_proof_assembler.ffmpeg_args(cfg, blueprint, root, work)
        subprocess.run(command, cwd=work, check=True,
                       capture_output=True, text=True, timeout=900)
        video = work / "private-review.mp4"
        if not private_proof_assembler.verify_video(video, plan["total_frames"]):
            raise SceneBlocked("PREVIEW_FFMPEG_QA_FAILED")
        report = {
            "status": "PRIVATE_DRAFT_TECH_PASS_NOT_ART_OR_SOURCE_APPROVAL",
            "scene_id": plan["scene_id"], "preview_key": render_key,
            "plan_key": plan["preview_key"], "video_sha256": file_sha(video),
            "caption_srt_sha256": file_sha(work / "private-captions.srt"),
            "caption_ass_sha256": file_sha(work / "private-captions.ass"),
            "frames": plan["total_frames"],
            "fps": 24, "verified_images": plan["verified_private_preview_images"],
            "slates_for_missing_images": plan["missing_or_unapproved_images"],
            "verified_hebrew_voice_clips": plan["verified_hebrew_voice_clips"],
            "verified_private_sound_stems": plan["verified_private_sound_stems"],
            "voice_missing": not bool(plan["voices"]),
            "placeholder_silence": not bool(plan["voices"] or plan["sounds"]),
            "generated_original_images": 0, "provider_calls": 0,
            "external_cost_usd": 0, "release_authorized": False,
            "copyright_review_complete": False, "owner_scene_review_complete": False,
        }
        # Render is private and local; never upload or publish from this module.
        shutil.copy2(video, target)
        shutil.copy2(work / "private-captions.srt", srt_path)
        shutil.copy2(work / "private-captions.ass", ass_path)
        # QA JSON is the last commit marker. A crash before it is PARTIAL,
        # never a recoverable cache hit and never silently cleaned/deleted.
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        return dict(report, cache_hit=False)


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--root", default=".")
    p.add_argument("--media", help="Local PRIVATE per-shot image and voice binding JSON")
    p.add_argument("--out", default="private-media/scene-prologue-draft.mp4")
    p.add_argument("--render", action="store_true")
    args = p.parse_args(argv)
    try:
        root = Path(args.root).resolve()
        media = load(_private_path(root, args.media)) if args.media else {}
        result = (render_private_draft(root, args.out, media)
                  if args.render else build_plan(root, media))
        print(json.dumps(result if args.render else {
            k: v for k, v in result.items() if k != "shots"
        }, ensure_ascii=False, indent=2))
        return 0
    except (OSError, ValueError, TypeError, KeyError, subprocess.SubprocessError) as exc:
        print(json.dumps({"status": "BLOCKED",
                          "reason": str(exc) if isinstance(exc, SceneBlocked)
                          else type(exc).__name__,
                          "inference_requests": 0}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    sys.exit(main())
