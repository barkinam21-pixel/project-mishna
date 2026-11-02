"""Make a zero-cost A/V synchronization test: tones + Hebrew test cards.

NOT a film, a voice performance, an approved religious quote or visual proof.
Run with FFmpeg on CPU. Every frame/audio sample time is integer-based.
"""
import argparse
from array import array
import json
import math
from pathlib import Path
import subprocess
import sys
import wave

FPS = 24
RATE = 48000
SAMPLES_PER_FRAME = RATE // FPS
DURATION_FRAMES = 288
START_FRAMES = (0, 96, 192, 264)
TEXTS = (
    "בדיקה טכנית ראשונה\nללא קריינות",
    "בדיקה טכנית שנייה\nקול סימון בלבד",
    "בדיקה טכנית שלישית\nאין כאן סרט מוגמר",
    "בדיקה טכנית רביעית",
)


def time_srt(frame):
    millis = (frame * 1000 + FPS // 2) // FPS
    hour, rem = divmod(millis, 3600000)
    minute, rem = divmod(rem, 60000)
    second, ms = divmod(rem, 1000)
    return f"{hour:02}:{minute:02}:{second:02},{ms:03}"


def make_srt():
    boundaries = (*START_FRAMES, DURATION_FRAMES)
    return "".join(
        f"{i+1}\n{time_srt(boundaries[i])} --> {time_srt(boundaries[i+1])}\n{TEXTS[i]}\n\n"
        for i in range(len(START_FRAMES))
    )


def write_audio(path):
    total = DURATION_FRAMES * SAMPLES_PER_FRAME
    result = array("h", [0]) * total
    pulse_samples = int(RATE * 0.16)
    fade = int(RATE * 0.01)
    for start_frame in START_FRAMES:
        start = start_frame * SAMPLES_PER_FRAME
        for i in range(pulse_samples):
            envelope = min(1.0, i / max(1, fade), (pulse_samples - i - 1) / max(1, fade))
            result[start + i] = int(17000 * envelope * math.sin(2 * math.pi * 880 * i / RATE))
    with wave.open(str(path), "wb") as writer:
        writer.setnchannels(1)
        writer.setsampwidth(2)
        writer.setframerate(RATE)
        writer.writeframes(result.tobytes())
    return {"samples": total, "rate": RATE, "channels": 1, "pulse_start_samples": [f * SAMPLES_PER_FRAME for f in START_FRAMES]}


def command(probe_dir):
    return [
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-f", "lavfi", "-i", "color=c=0x172630:s=960x540:r=24:d=12",
        "-i", str(probe_dir / "sync-test.wav"),
        "-i", str(probe_dir / "sync-test.srt"),
        "-map", "0:v:0", "-map", "1:a:0", "-map", "2:s:0",
        "-vf", "subtitles=" + str(probe_dir / "sync-test.srt") + ",setparams=range=limited:color_primaries=bt709:color_trc=bt709:colorspace=bt709",
        "-frames:v", str(DURATION_FRAMES),
        "-r", str(FPS),
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "24",
        "-pix_fmt", "yuv420p", "-profile:v", "high",
        "-color_primaries", "bt709", "-color_trc", "bt709",
        "-colorspace", "bt709", "-color_range", "tv",
        "-c:a", "aac", "-ar", str(RATE), "-ac", "2", "-b:a", "112k",
        "-c:s", "mov_text",
        "-metadata:s:a:0", "language=heb",
        "-metadata:s:s:0", "language=heb",
        "-metadata", "title=Mishnah Sync Test - Not an Episode",
        "-movflags", "+faststart",
        str(probe_dir / "sync-test.mp4")
    ]


def run(cmd):
    return subprocess.run(cmd, check=True, stdout=subprocess.PIPE,
                          stderr=subprocess.PIPE)


def verify_mp4(path):
    info = json.loads(run([
        "ffprobe", "-v", "error", "-count_frames",
        "-show_entries",
        "stream=codec_type,codec_name,width,height,avg_frame_rate,nb_read_frames,sample_rate,channels,color_primaries,color_transfer,color_space:stream_tags=language",
        "-of", "json", str(path)]).stdout)
    streams = info["streams"]
    videos = [s for s in streams if s["codec_type"] == "video"]
    audios = [s for s in streams if s["codec_type"] == "audio"]
    subs = [s for s in streams if s["codec_type"] == "subtitle"]
    failures = []
    if len(videos) != 1 or videos[0].get("nb_read_frames") != "288" or videos[0].get("avg_frame_rate") != "24/1":
        failures.append("Video frame count / frame rate wrong")
    if len(audios) != 1 or audios[0].get("sample_rate") != "48000" or audios[0].get("channels") != 2:
        failures.append("Audio format wrong")
    if not subs or subs[0].get("codec_name") != "mov_text":
        failures.append("Missing embedded soft subtitles")
    if audios and audios[0].get("tags", {}).get("language") not in ("heb", "he"):
        failures.append("Missing Hebrew audio tag")
    if subs and subs[0].get("tags", {}).get("language") not in ("heb", "he"):
        failures.append("Missing Hebrew subtitle tag")
    if videos and (videos[0].get("color_primaries") != "bt709" or videos[0].get("color_transfer") != "bt709" or videos[0].get("color_space") != "bt709"):
        failures.append("BT.709 metadata missing")
    raw = run([
        "ffmpeg", "-v", "error", "-i", str(path),
        "-map", "0:a:0", "-ac", "1", "-ar", str(RATE),
        "-f", "s16le", "pipe:1"
    ]).stdout
    samples = array("h")
    samples.frombytes(raw)
    for frame in START_FRAMES:
        expected = frame * SAMPLES_PER_FRAME
        left = max(0, expected - SAMPLES_PER_FRAME)
        right = min(len(samples), expected + SAMPLES_PER_FRAME)
        if not any(abs(n) >= 1600 for n in samples[left:right]):
            failures.append("Missing synchronized audio onset near frame " + str(frame))
    if abs(len(samples) - DURATION_FRAMES * SAMPLES_PER_FRAME) > 2048:
        failures.append("Decoded sample length differs by more than one AAC frame")
    run(["ffmpeg", "-v", "error", "-xerror", "-i", str(path), "-f", "null", "-"])
    return {
        "video_codec": videos[0].get("codec_name") if videos else None,
        "video_frames": videos[0].get("nb_read_frames") if videos else None,
        "audio_rate": audios[0].get("sample_rate") if audios else None,
        "audio_channels": audios[0].get("channels") if audios else None,
        "soft_hebrew_subtitles_present": bool(subs),
        "decoded_audio_samples": len(samples),
        "pulses_expected_at_frames": list(START_FRAMES),
        "errors": failures,
    }


def build(output_dir):
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "sync-test.srt").write_text(make_srt(), encoding="utf-8")
    generated = write_audio(output_dir / "sync-test.wav")
    run(command(output_dir))
    checked = verify_mp4(output_dir / "sync-test.mp4")
    report = {
        "status": "TECHNICAL_TIMING_PASS_NOT_REAL_VOICE" if not checked["errors"] else "FAIL",
        "media_is_only_diagnostic": True,
        "human_voice_test_performed": False,
        "hebrew_pronunciation_verified": False,
        "real_episode_sync_verified": False,
        "source_release_authorized": False,
        "paid_services_called": 0,
        "workspace_usage": "unknown",
        "fps": FPS, "sample_rate": RATE, "samples_per_frame": SAMPLES_PER_FRAME,
        "duration_frames": DURATION_FRAMES,
        "duration_seconds": DURATION_FRAMES // FPS,
        "synthetic_audio": generated,
        "post_encode_validation": checked,
    }
    (output_dir / "sync-qa.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out-dir", type=Path, default=Path("build/sync-probe"))
    args = parser.parse_args()
    try:
        report = build(args.out_dir)
    except (OSError, subprocess.CalledProcessError, ValueError) as exc:
        print("SYNCHRONIZATION PROBE FAILED:", str(exc), file=sys.stderr)
        return 2
    print(report["status"], report["post_encode_validation"])
    return 0 if report["status"] == "TECHNICAL_TIMING_PASS_NOT_REAL_VOICE" else 2


if __name__ == "__main__":
    raise SystemExit(main())
