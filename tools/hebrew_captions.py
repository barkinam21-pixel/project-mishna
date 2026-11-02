"""Deterministic Hebrew subtitles from a reviewed integer-frame cue master.

No voice synthesis, assets, paid APIs, or video are generated.
The CLI refuses to export unapproved historical/religious captions.
"""
import argparse
import json
from pathlib import Path
import re
import sys
import unicodedata

FPS = 24
FORBIDDEN = set(chr(n) for n in (
    0x202A, 0x202B, 0x202C, 0x202D, 0x202E,
    0x2066, 0x2067, 0x2068, 0x2069, 0x200E, 0x200F
))
LATIN = re.compile(r"[A-Za-z]")
HEBREW = re.compile(r"[\u0590-\u05FF]")
ASS_HEADER = """[Script Info]
Title: Mishnah Hebrew captions
ScriptType: v4.00+
WrapStyle: 0
ScaledBorderAndShadow: yes
PlayResX: 1920
PlayResY: 1080

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Hebrew,Noto Sans Hebrew,52,&H00FFFFFF,&H000000FF,&H8C111111,&H7A101010,0,0,0,0,100,100,0,0,3,1,0,2,130,130,125,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""


def graphemes(text):
    """Approximate extended graphemes for Hebrew + niqqud (no 3rd-party libs)."""
    count = 0
    for char in text:
        if not unicodedata.category(char).startswith("M"):
            count += 1
    return count


def validate(master, require_approval=True):
    errors = []
    warnings = []
    if not isinstance(master, dict):
        return {"valid": False, "errors": ["Caption master must be object"], "warnings": []}
    if master.get("fps") != FPS:
        errors.append("Caption fps must be 24")
    if master.get("language") != "he":
        errors.append("Caption language must be Hebrew")
    if require_approval and (
        master.get("source_text_locked") is not True
        or master.get("human_torah_review_approved") is not True
        or master.get("caption_text_approved") is not True
    ):
        errors.append("No export before source text, human Torah review and caption approval")
    cues = master.get("cues")
    if not isinstance(cues, list) or not cues:
        errors.append("Nonempty cues array required")
        return {"valid": False, "errors": errors, "warnings": warnings}
    prev_end = 0
    ids = set()
    for i, cue in enumerate(cues):
        prefix = "cues[%s]" % i
        if not isinstance(cue, dict):
            errors.append(prefix+" must be object")
            continue
        identifier = cue.get("id")
        if not isinstance(identifier, str) or not identifier or identifier in ids:
            errors.append(prefix+" unique id required")
        ids.add(identifier)
        start, end = cue.get("start_frame"), cue.get("end_frame")
        if any(not isinstance(n, int) or isinstance(n, bool) for n in (start, end)):
            errors.append(prefix+" integer frame timings required")
            continue
        if start < 0 or end <= start or start < prev_end:
            errors.append(prefix+" invalid timing or overlap")
        prev_end = max(prev_end, end)
        display = cue.get("display_text")
        if not isinstance(display, str) or not display.strip():
            errors.append(prefix+" nonempty display_text required")
            continue
        if unicodedata.normalize("NFC", display) != display:
            errors.append(prefix+" must be NFC normalized")
        if any(ch in FORBIDDEN or ch == "\ufffd" for ch in display):
            errors.append(prefix+" contains hidden bidi controls or replacement character")
        if LATIN.search(display):
            errors.append(prefix+" contains unexpected Latin text")
        if not HEBREW.search(display):
            errors.append(prefix+" has no Hebrew characters")
        if any(ch in "{}\\" for ch in display):
            errors.append(prefix+" contains unsafe ASS markup characters")
        lines = display.split("\n")
        if len(lines) > 2 or any(not line.strip() for line in lines):
            errors.append(prefix+" may only contain one or two nonempty lines")
        if any(graphemes(line) > 42 for line in lines):
            errors.append(prefix+" line length above 42 graphemes")
        for required in ("spoken_text", "pronunciation_text", "speaker", "source", "shot_id"):
            if not isinstance(cue.get(required), str) or not cue[required]:
                errors.append(prefix+" missing "+required)
        seconds = (end-start)/FPS
        visible_chars = sum(graphemes(line.strip()) for line in lines)
        cps = visible_chars/seconds
        if cps > 17:
            warnings.append(prefix+" reading speed %.1f chars/sec exceeds 17" % cps)
        if seconds < 0.83 or seconds > 7:
            warnings.append(prefix+" duration %.2fs outside 0.83-7s" % seconds)
    return {"valid": not errors, "errors": errors, "warnings": warnings}


def timestamp(frame, kind):
    # Absolute integer frame positions; rounding never accumulated.
    # Time conversions use integer arithmetic to avoid floating point drift.
    if kind == "ass":
        centis = (frame*100 + FPS//2)//FPS
        hours, rem = divmod(centis, 360000)
        minutes, rem = divmod(rem, 6000)
        seconds, centi = divmod(rem, 100)
        return f"{hours}:{minutes:02}:{seconds:02}.{centi:02}"
    millis = (frame*1000 + FPS//2)//FPS
    hours, rem = divmod(millis, 3600000)
    minutes, rem = divmod(rem, 60000)
    seconds, milli = divmod(rem, 1000)
    delimiter = "," if kind == "srt" else "."
    return f"{hours:02}:{minutes:02}:{seconds:02}{delimiter}{milli:03}"


def emit(master):
    result = validate(master)
    if not result["valid"]:
        raise ValueError("; ".join(result["errors"]))
    srt, vtt, ass = [], ["WEBVTT", ""], [ASS_HEADER.rstrip("\n")]
    for i, cue in enumerate(master["cues"], 1):
        a, b, text = cue["start_frame"], cue["end_frame"], cue["display_text"]
        srt.extend([str(i), timestamp(a, "srt")+" --> "+timestamp(b, "srt"), text, ""])
        vtt.extend([timestamp(a,"vtt")+" --> "+timestamp(b,"vtt"), text, ""])
        ass.append("Dialogue: 0,%s,%s,Hebrew,,0,0,0,,%s" %
                   (timestamp(a,"ass"),timestamp(b,"ass"),text.replace("\n",r"\N")))
    return {"srt": "\n".join(srt).rstrip()+"\n",
            "vtt": "\n".join(vtt).rstrip()+"\n",
            "ass": "\n".join(ass).rstrip()+"\n"}, result


def main():
    p = argparse.ArgumentParser(description="Export approved Hebrew subtitles as SRT/VTT/ASS")
    p.add_argument("master", type=Path)
    p.add_argument("--out-dir", type=Path, default=Path("build/captions"))
    args = p.parse_args()
    try:
        data = json.loads(args.master.read_text(encoding="utf-8"))
        outputs, qa = emit(data)
    except (OSError, ValueError, UnicodeError) as exc:
        print("SUBTITLE EXPORT BLOCKED: "+str(exc), file=sys.stderr)
        return 2
    args.out_dir.mkdir(parents=True, exist_ok=True)
    for extension, contents in outputs.items():
        (args.out_dir/("mishnah-he."+extension)).write_text(contents,encoding="utf-8")
    (args.out_dir/"caption-qa.json").write_text(json.dumps(qa,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print("Caption files created from approved source: SRT / VTT / ASS")
    if qa["warnings"]:
        for warning in qa["warnings"]:
            print("REVIEW:",warning)
    return 0


if __name__ == "__main__":
    sys.exit(main())
