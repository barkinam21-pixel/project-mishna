"""Prepare exact, UNTIMED Hebrew caption cards from the existing opening script.

No TTS, model calls, fabricated timestamps, production manifest edits or approvals.
Output is a text-only rehearsal/editing plan, NOT a renderable captions.json.
"""
import argparse
import hashlib
import json
import re
import unicodedata
from pathlib import Path

SCENE = "INTRO-A1-S01"
VOICE = ("INTRO-A1-S01-N01", "INTRO-A1-S01-N02")
PROFILE = "series-narrator-alnilam-continuous-v2"
MAX_LINE = 42
MAX_CARD_VISIBLE = 60  # ~4.6s at 13 chars/s; still requires actual audio alignment
WORD_RE = re.compile(r"\S+", flags=re.UNICODE)


def sha(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def extract(script, uid):
    """Use the same > quote extraction as the authoritative renderer."""
    pieces = re.split(r"(?=^\*\*[^\n]*INTRO-A\d-S\d+-[NQ]\d+)", script, flags=re.M)
    matching = [part for part in pieces[1:]
                if re.search(r"INTRO-A\d-S\d+-[NQ]\d+", part).group() == uid]
    if len(matching) != 1:
        raise ValueError("Expected exactly one narration block for " + uid)
    paragraphs = []
    current = []
    for line in matching[0].splitlines():
        if line.startswith("> "):
            current.append(line[2:])
        elif line == ">" and current:
            paragraphs.append(" ".join(current))
            current = []
    if current:
        paragraphs.append(" ".join(current))
    # The archived cue digest preserves paragraph boundaries as two newlines.
    # The renderer later normalizes whitespace to compare spoken captions.
    body = "\n\n".join(paragraphs)
    if not body or unicodedata.normalize("NFC", body) != body:
        raise ValueError("Empty or non-NFC source for " + uid)
    return body


def caption_lines(text):
    """Break exact spoken tokens into <=42-character lines without rewriting."""
    words = WORD_RE.findall(text)
    if not words:
        raise ValueError("Empty spoken caption")
    lines = []
    line = ""
    for word in words:
        if len(word) > MAX_LINE:
            raise ValueError("A spoken word exceeds the caption line limit")
        attempt = word if not line else line + " " + word
        if len(attempt) > MAX_LINE:
            lines.append(line)
            line = word
        else:
            line = attempt
    if line:
        lines.append(line)
    return lines


def split_long_sentence(sentence):
    """Prefer natural punctuation breaks to keep draft cards readable.

    Exact words and punctuation remain unchanged, and no frame timing is inferred.
    """
    remaining = sentence.strip()
    chunks = []
    while len(remaining) > MAX_CARD_VISIBLE:
        punct = [m.end() for m in re.finditer(r"(?<=[,:;!?])\s+", remaining)
                 if 12 <= m.end() <= MAX_CARD_VISIBLE
                 and len(remaining[m.end():].strip()) >= 10]
        choices = punct or [m.end() for m in re.finditer(r"\s+", remaining)
                            if 12 <= m.end() <= MAX_CARD_VISIBLE]
        if not choices:
            raise ValueError("Unbreakable sentence exceeds card length")
        boundary = min(choices, key=lambda pos: abs(pos - len(remaining) / 2))
        chunks.append(remaining[:boundary].rstrip())
        remaining = remaining[boundary:].lstrip()
    if remaining:
        chunks.append(remaining)
    if " ".join(chunks) != " ".join(sentence.split()):
        raise ValueError("Clause splitting altered source words")
    return chunks


def cue_cards(text, uid):
    cards = []
    # Sentence boundary is only a presentation hint, never a text change.
    # Preserve punctuation and logical RTL text; NEVER reverse letters.
    sentences = re.split(r"(?<=[.!?])\s+", text)
    for sentence in sentences:
        if not sentence.strip():
            continue
        for chunk in split_long_sentence(sentence):
            lines = caption_lines(chunk)
            if len(lines) > 2 or len(chunk) > MAX_CARD_VISIBLE:
                raise ValueError("Untimed caption card exceeds safe reading limit")
            cards.append({
                "card_id": uid + "-C" + f"{len(cards) + 1:02d}",
                "voice_id": uid,
                "spoken_text": " ".join(lines),
                "display_text": "\n".join(lines),
                "start_frame": None,
                "end_frame": None,
                "timing_status": "UNALIGNED_WITH_REAL_WAV",
                "approved": False,
            })
    if " ".join(c["spoken_text"] for c in cards) != " ".join(text.split()):
        raise ValueError("Caption transcription changed the source")
    return cards


def build(root):
    root = Path(root)
    script = (root / "scripts/introduction-working-draft.md").read_text(encoding="utf-8")
    index = json.loads((root / "docs/evidence/introduction-script-audit-2026-11-06.json")
                       .read_text(encoding="utf-8"))
    if sha(script) != index["master_sha256"]:
        raise ValueError("Script master modified since reference audit")
    rows = {r["id"]: r for r in index["cues"]}
    segments = []
    for uid in VOICE:
        source = extract(script, uid)
        if sha(source) != rows[uid]["display_text_sha256"]:
            raise ValueError("Source narration hash mismatch: " + uid)
        if rows[uid]["matching_recording"] != "MISSING":
            raise ValueError("Existing recording inventory has changed: review manually")
        cards = cue_cards(source, uid)
        segments.append({
            "id": uid,
            "speaker": "narrator",
            "voice_profile": PROFILE,
            "source_ids": rows[uid]["source_ids"],
            "source_text": source,
            "source_text_sha256": sha(source),
            "cards": cards,
            "word_count": len(source.split()),
            "recording_status": "NOT_RECORDED",
            "pronunciation_review": "PENDING",
            "source_text_approved": False,
        })
    return {
        "schema_version": 1,
        "purpose": "UNALIGNED_CAPTION_SOURCE_PREPARATION_ONLY",
        "scene": SCENE,
        "profile": PROFILE,
        "script_master_sha256": index["master_sha256"],
        "segments": segments,
        "card_count": sum(len(s["cards"]) for s in segments),
        "fps_for_future_alignment": 24,
        "audio_sample_rate_for_future_alignment": 48000,
        "timing_measured": False,
        "narration_generated": False,
        "scene_assets_approved": False,
        "release_authorized": False,
        "provider_calls": 0,
        "next_step": "Record exact N01 and N02 with locked Alnilam voice; align by real WAV samples, validate and human-review Hebrew captions before copying into production manifest.",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=".")
    parser.add_argument("--out", default="build/opening-caption-draft.json")
    args = parser.parse_args()
    root = Path(args.root).resolve()
    report = build(root)
    out = (root / args.out).resolve()
    if not out.is_relative_to(root) or out == root / "private-media/introduction/captions.json":
        raise ValueError("Refusing unsafe/production caption output")
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(".tmp")
    tmp.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(out)
    print(json.dumps({"status": report["purpose"], "cards": report["card_count"],
                      "narration_segments": len(report["segments"]),
                      "timing_measured": False, "provider_calls": 0,
                      "out": str(out.relative_to(root))}, ensure_ascii=False))


if __name__ == "__main__":
    main()
