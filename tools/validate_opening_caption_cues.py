#!/usr/bin/env python3
"""Offline Hebrew caption/pacing gate for the chronological OPN01-OPN07 opening.

This validates editorial cues against the actual seven-shot director pack.
It does not create images, voice, music, video, paid requests, or publish media.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys
import unicodedata

ROOT = Path(__file__).resolve().parents[1]
PACK_PATH = ROOT / "episodes/berakhot-01-01/opening-45s-director-pack-v1.json"
CUES_PATH = ROOT / "episodes/berakhot-01-01/opening-45s-caption-cues-draft.json"
FORBIDDEN_BIDI = set("\u200e\u200f\u202a\u202b\u202c\u202d\u202e\u2066\u2067\u2068\u2069")
MAX_CPS = 17.0


def logical(text: str) -> str:
    return " ".join(text.split())


def validate(captions: dict, opening: dict) -> dict:
    errors = []

    def fail(message: str) -> None:
        errors.append(message)

    if not isinstance(captions, dict) or not isinstance(opening, dict):
        return {"status": "BLOCKED", "errors": ["captions and shot pack must be objects"]}

    for k, value in {
        "schema_version": 1,
        "episode": "berakhot-01-01",
        "sequence_id": "OPENING_PROLOGUE_01",
        "fps": 24,
        "sample_rate_hz": 48000,
        "total_frames": 1080,
        "next_paid_shot_candidate": "OPN01",
        "no_cloud_spend_authorized": True,
        "dialogue_audio_recorded": False,
        "caption_video_rendered": False,
        "performance_timing_measured": False,
        "editorial_status": "DRAFT_NOT_RECORDED_NOT_RENDERED_NOT_SOURCE_LOCKED",
        "source_layer": "symbolic_dramatization",
    }.items():
        if captions.get(k) != value or type(captions.get(k)) is not type(value):
            fail(f"{k} must be {value!r}")
    if captions.get("shotpack") != str(PACK_PATH.relative_to(ROOT)):
        fail("caption source must reference the canonical first-prologue director pack")
    if opening.get("next_paid_shot_candidate") != "OPN01":
        fail("opening must not switch to the sons' scenes")
    if opening.get("privacy", {}).get("fal_paid_approval_granted") is not False:
        fail("no fresh paid fal approval exists")
    if opening.get("film", {}).get("fps") != 24:
        fail("shot pack fps differs from caption timebase")

    font = captions.get("font_policy", {})
    if not isinstance(font, dict):
        font = {}
    if (font.get("family") != "Noto Sans Hebrew"
            or font.get("max_lines") != 2
            or font.get("max_visible_chars_per_line") != 42
            or font.get("phone_safe_bottom_margin_ratio", 0) < 0.1
            or font.get("ai_generated_image_contains_no_subtitles") is not True
            or font.get("soft_captions_required") is not True):
        fail("Hebrew mobile caption contract is missing or weakened")

    shots = {s.get("id"): s for s in opening.get("shots", []) if isinstance(s, dict)}
    spots = {s.get("id"): s for s in opening.get("audio_spotting_frames", []) if isinstance(s, dict)}
    cues = captions.get("cues", [])
    if not isinstance(cues, list) or not cues:
        fail("cues must be a non-empty array")
        cues = []

    expected_spoken = [
        (s["id"], d["speaker"], logical(d["text"]))
        for s in opening.get("shots", []) if isinstance(s, dict)
        for d in s.get("dialogue_he", []) if isinstance(d, dict)
    ]
    actual_spoken = []
    notice_count = 0
    seen_ids = set()
    previous_end = 0
    peak_cps = 0.0

    for index, cue in enumerate(cues):
        if not isinstance(cue, dict):
            fail(f"cue {index} must be an object")
            continue
        cid = cue.get("id")
        if not isinstance(cid, str) or cid in seen_ids:
            fail(f"cue {index} has duplicate/missing id")
        seen_ids.add(cid)
        start, end = cue.get("start_frame"), cue.get("end_frame")
        if (type(start) is not int or type(end) is not int
                or not 0 <= start < end <= 1080):
            fail(f"{cid}: invalid frame range")
            continue
        if start < previous_end:
            fail(f"{cid}: overlapping or out-of-order cue")
        previous_end = end

        shot = shots.get(cue.get("shot_id"))
        if not shot or start < shot["start_frame"] or end > shot["end_frame"]:
            fail(f"{cid}: cue escapes assigned shot or unknown shot id")
        spot = spots.get(cue.get("audio_spot_id"))
        if not spot or start < spot["start_frame"] or end > spot["end_frame"]:
            fail(f"{cid}: cue escapes its sound-spotting window")
        if cue.get("placement") != "bottom_center_phone_safe":
            fail(f"{cid}: caption outside agreed phone-safe placement")
        if cue.get("source_status") != "symbolic_dramatization":
            fail(f"{cid}: source tier cannot be silently promoted to history")

        display = cue.get("display_text_he")
        if not isinstance(display, str) or not display.strip():
            fail(f"{cid}: missing displayed Hebrew")
            continue
        if unicodedata.normalize("NFC", display) != display:
            fail(f"{cid}: not NFC-normalized")
        if any(ch in FORBIDDEN_BIDI or ch == "\ufffd" for ch in display):
            fail(f"{cid}: unsafe bidi/replacement character")
        if re.search(r"[A-Za-z]", display):
            fail(f"{cid}: unexpected Latin text in Hebrew caption")
        lines = display.split("\n")
        if len(lines) > 2 or any(not line.strip() or len(line) > 42 for line in lines):
            fail(f"{cid}: overlong, empty, or more-than-two-line caption")
        if any(unicodedata.category(ch).startswith("C") for line in lines for ch in line):
            fail(f"{cid}: hidden control character")

        seconds = (end - start) / 24.0
        visible = len("".join(display.split()))
        cps = visible / seconds
        peak_cps = max(peak_cps, cps)
        if seconds < 1.2 or seconds > 7 or cps > MAX_CPS:
            fail(f"{cid}: inaccessible estimated display time ({seconds:.2f}s, {cps:.1f} cps)")
        kind = cue.get("kind")
        if kind == "source_notice":
            notice_count += 1
            if (index != 0 or cue.get("shot_id") != "OPN01"
                    or logical(display) != logical(opening.get("source_contract", {}).get("mandatory_first_caption_he", ""))
                    or cue.get("spoken_text_he") is not None
                    or cue.get("voice_status") != "not_applicable"):
                fail(f"{cid}: first-frame symbolic dramatization disclosure missing/altered")
        elif kind == "invented_dialogue":
            spoken = cue.get("spoken_text_he")
            speaker = cue.get("speaker")
            if not isinstance(spoken, str) or logical(display) != logical(spoken):
                fail(f"{cid}: displayed and spoken dialogue differ")
            elif cue.get("voice_status") != "not_recorded":
                fail(f"{cid}: draft caption cannot claim an actual voice recording")
            else:
                actual_spoken.append((cue.get("shot_id"), speaker, logical(spoken)))
        else:
            fail(f"{cid}: unsupported caption kind")

    if notice_count != 1:
        fail("exactly one non-spoken opening source label is required")
    if actual_spoken != expected_spoken:
        fail("dialogue cue list does not exactly match director-pack words, speakers and shots")
    return {
        "status": "PASS_DRY_RUN_ONLY" if not errors else "BLOCKED",
        "errors": errors,
        "cue_count": len(cues),
        "dialogue_cues": len(actual_spoken),
        "duration_frames_editorial": captions.get("total_frames"),
        "peak_estimated_visible_chars_per_second": round(peak_cps, 2),
        "actual_voice_timing_verified": False,
        "actual_phone_render_verified": False,
        "paid_requests": 0,
        "notes": "Offline editorial QA only; no voice, artwork, video, rights, source lock or human Torah approval."
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pack", type=Path, default=PACK_PATH)
    parser.add_argument("--cues", type=Path, default=CUES_PATH)
    args = parser.parse_args()
    try:
        out = validate(
            json.loads(args.cues.read_text(encoding="utf-8")),
            json.loads(args.pack.read_text(encoding="utf-8")),
        )
    except (OSError, ValueError) as exc:
        out = {"status": "BLOCKED", "errors": [str(exc)]}
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0 if out["status"] == "PASS_DRY_RUN_ONLY" else 1


if __name__ == "__main__":
    sys.exit(main())
