"""Audit actual Hebrew voice takes against integer-frame subtitle slots.

No speech synthesis, voice cloning, payment, publication or audio processing.
Reports honest evidence levels: structural, measured waveform, human listening.
"""
import argparse
import json
from pathlib import Path
import re
import sys
import wave

FPS = 24
RATE = 48000
SAMPLES_PER_FRAME = RATE // FPS
HEBREW = re.compile(r"[\u0590-\u05ff]+(?:[׳״'-][\u0590-\u05ff]+)*")


def is_pos_int(x):
    return isinstance(x, int) and not isinstance(x, bool) and x > 0


def inspect_wav(path):
    with wave.open(str(path), "rb") as f:
        frames = f.getnframes()
        rate = f.getframerate()
        channels = f.getnchannels()
        width = f.getsampwidth()
        compression = f.getcomptype()
        raw = f.readframes(frames)
    return {"frames": frames, "sample_rate": rate, "channels": channels,
            "sample_width_bytes": width, "compression": compression,
            "is_silent": width == 2 and not any(raw)}


def validate(manifest, asset_root):
    errors = []
    warnings = []
    rows = []
    if not isinstance(manifest, dict):
        return {"status": "INVALID", "errors": ["Expected JSON object"], "warnings": []}
    if manifest.get("fps") != FPS or manifest.get("sample_rate") != RATE:
        errors.append("Exactly 24 fps and 48,000 Hz are required")
    if manifest.get("release_authorized") is not False:
        errors.append("Draft voice manifest cannot claim publication approval")
    segments = manifest.get("segments")
    if not isinstance(segments, list) or not segments:
        errors.append("Nonempty segments array required")
        segments = []
    previous_end = 0
    seen = set()
    missing = 0
    for index, item in enumerate(segments):
        prefix = f"segments[{index}]"
        if not isinstance(item, dict):
            errors.append(prefix + " must be an object")
            continue
        uid = item.get("id")
        start = item.get("start_frame")
        end = item.get("end_frame")
        if not isinstance(uid, str) or not uid or uid in seen:
            errors.append(prefix + " invalid/duplicate ID")
        seen.add(uid)
        if not isinstance(start, int) or isinstance(start, bool) or not is_pos_int(end) or start < previous_end or end <= start:
            errors.append(prefix + " invalid or overlapping integer-frame slot")
            continue
        previous_end = end
        for label in ("speaker", "spoken_text", "pronunciation_text", "source_status", "audio_path"):
            if not isinstance(item.get(label), str) or not item[label].strip():
                errors.append(prefix + " missing " + label)
        audio_path = item.get("audio_path", "")
        if not isinstance(audio_path, str):
            continue
        local = Path(audio_path)
        if local.is_absolute() or ".." in local.parts or local.suffix.lower() != ".wav":
            errors.append(prefix + " use safe relative WAV path")
            continue
        full = asset_root / local
        window_samples = (end - start) * SAMPLES_PER_FRAME
        count = len(HEBREW.findall(item.get("spoken_text", "")))
        row = {"id": uid, "speaker": item.get("speaker"), "slot_frames": end - start,
               "slot_samples": window_samples, "words": count, "audio_path": audio_path}
        if not full.exists():
            row["voice_take_status"] = "MISSING_WAV"
            missing += 1
            rows.append(row)
            continue
        try:
            data = inspect_wav(full)
        except (OSError, EOFError, wave.Error) as exc:
            errors.append(prefix + " WAV unreadable: " + type(exc).__name__)
            continue
        row.update(data)
        row["voice_take_status"] = "MEASURED_WAV_NOT_HUMAN_LISTENED"
        if data["sample_rate"] != RATE or data["channels"] not in (1, 2) or data["sample_width_bytes"] != 2 or data["compression"] != "NONE":
            errors.append(prefix + " expected 48kHz PCM16 mono/stereo WAV")
        if data["frames"] > window_samples:
            errors.append(prefix + " voice recording exceeds allotted frame slot")
        if data["frames"] == 0 or data["is_silent"]:
            errors.append(prefix + " voice WAV is silent or empty")
        duration = data["frames"] / RATE
        if duration:
            row["measured_wpm_including_pauses"] = round(count * 60 / duration, 1)
            row["remaining_slot_seconds"] = round((window_samples - data["frames"]) / RATE, 3)
            if count >= 6 and row["measured_wpm_including_pauses"] > 155:
                warnings.append(prefix + " speech may be rushed: listen to it")
            if count >= 6 and row["measured_wpm_including_pauses"] < 80:
                warnings.append(prefix + " speech may be slow: listen to it")
        rows.append(row)
    return {
        "status": "INVALID" if errors else ("MISSING_RECORDINGS" if missing else "WAV_TIMING_MEASURED_NOT_VOICE_APPROVED"),
        "errors": errors, "warnings": warnings,
        "missing_recordings": missing,
        "measured_recordings": sum(x.get("voice_take_status") == "MEASURED_WAV_NOT_HUMAN_LISTENED" for x in rows),
        "human_pronunciation_verified": False,
        "expressive_performance_verified": False,
        "lipsync_verified": False,
        "source_release_authorized": False,
        "rows": rows
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--asset-root", type=Path, default=Path("."))
    parser.add_argument("--output", type=Path, default=Path("build/voice-take-audit.json"))
    args = parser.parse_args()
    try:
        data = json.loads(args.manifest.read_text(encoding="utf-8"))
        report = validate(data, args.asset_root)
    except (ValueError, OSError) as exc:
        print("VOICE AUDIT INVALID:", str(exc), file=sys.stderr)
        return 2
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(report["status"], "missing", report["missing_recordings"], "measured", report["measured_recordings"])
    return 2 if report["status"] == "INVALID" else 0


if __name__ == "__main__":
    raise SystemExit(main())
