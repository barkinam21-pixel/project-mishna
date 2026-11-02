"""Offline, no-spend pacing audit for the expanded Mishnah episode.

This is editorial estimation, NOT measured Hebrew speech or approved media.
"""
import argparse
import json
import re
from pathlib import Path

HEADER = re.compile(r"^### רצף (\d+) — (.+?) \(כ־(\d{1,2}:\d{2})–(\d{1,2}:\d{2})\)", re.M)
WORDS = re.compile(r"[\u0590-\u05ff]+(?:[׳״'\u05be-][\u0590-\u05ff]+)*")
QUOTE = re.compile(r'"([^"]+)"', re.S)
FPS = 24
SAMPLE_RATE = 48000


def parse_clock(value):
    minutes, seconds = map(int, value.split(":"))
    if seconds > 59:
        raise ValueError("Invalid time: " + value)
    return 60 * minutes + seconds


def review(markdown, target_wpm=125):
    if target_wpm < 80 or target_wpm > 180:
        raise ValueError("target_wpm outside supported editorial range")
    matches = list(HEADER.finditer(markdown))
    if not matches:
        raise ValueError("No time-coded sequences found")
    sequences = []
    errors = []
    previous_end = 0
    for index, match in enumerate(matches):
        number, title, start_text, end_text = match.groups()
        start, end = parse_clock(start_text), parse_clock(end_text)
        section_end = matches[index + 1].start() if index + 1 < len(matches) else len(markdown)
        body = markdown[match.end():section_end]
        # Quotes are an approximation: original dialogue and explanatory quotes are
        # included; use a real recording/forced-alignment before final locking.
        spoken = " ".join(QUOTE.findall(body))
        count = len(WORDS.findall(spoken))
        if start != previous_end:
            errors.append("Sequence %s does not start where previous ends" % number)
        if end <= start:
            errors.append("Sequence %s has invalid duration" % number)
        if count == 0:
            errors.append("Sequence %s has no quoted speech" % number)
        duration = max(1, end - start)
        estimated_voice_seconds = round(count * 60 / target_wpm, 2)
        breathing_seconds = round(duration - estimated_voice_seconds, 2)
        minimum_pause = max(3.0, duration * 0.10)
        sequences.append({
            "sequence": int(number), "title": title,
            "start_frame": start * FPS, "end_frame": end * FPS,
            "duration_frames": duration * FPS, "words_approximate": count,
            "words_per_minute_if_filled": round(count * 60 / duration, 1),
            "speech_seconds_at_target_wpm": estimated_voice_seconds,
            "remaining_seconds_for_cuts_pauses_and_actions": breathing_seconds,
            "minimum_pause_seconds_target": round(minimum_pause, 2),
            "pacing_review": "TOO_DENSE" if breathing_seconds < minimum_pause else "ROOM_FOR_DRAMA",
        })
        previous_end = end
    return {
        "audit": "EDITORIAL_ESTIMATE_NOT_VOICE_VERIFICATION",
        "episode_id": "berakhot-01-01",
        "recorded_audio_verified": False,
        "subtitle_speech_alignment_verified": False,
        "fps": FPS, "sample_rate": SAMPLE_RATE,
        "samples_per_frame": SAMPLE_RATE // FPS,
        "target_wpm": target_wpm,
        "sequence_count": len(sequences),
        "total_frames": previous_end * FPS,
        "total_seconds": previous_end,
        "spoken_words_approximate": sum(s["words_approximate"] for s in sequences),
        "needs_review": [s["sequence"] for s in sequences if s["pacing_review"] == "TOO_DENSE"],
        "errors": errors,
        "sequences": sequences,
        "blocking_conditions": [
            "Human Torah review and edition choice still outstanding",
            "No measured Hebrew voice performances or pronunciation approval",
            "No approved production keyframes or sound assets",
            "Real A/V sync is unverified until actual recorded voices are tested"
        ]
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument("script", type=Path)
    p.add_argument("--output", type=Path, default=Path("build/episode-01-pacing-audit.json"))
    p.add_argument("--target-wpm", type=int, default=125)
    args = p.parse_args()
    report = review(args.script.read_text(encoding="utf-8"), args.target_wpm)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("Pacing estimate %s sequences, %s words, %ss; tight: %s" %
          (report["sequence_count"], report["spoken_words_approximate"],
           report["total_seconds"], report["needs_review"]))
    if report["errors"]:
        print("ERRORS:", report["errors"])
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
