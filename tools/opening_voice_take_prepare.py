"""Produce an offline, source-locked single-take Alnilam opening recording brief.

This does NOT call TTS, copy private media, approve the script, schedule cuts,
invent timestamps, certify a no-charge service or enable generation.
"""
import argparse
import hashlib
import json
from pathlib import Path
from tools.opening_caption_prepare import build as caption_source

PROFILE = "series-narrator-alnilam-continuous-v2"
VOICE = "Alnilam"
MODEL = "gemini-2.5-flash-preview-tts"
APPROVED_REFERENCE_SHA = "f6648459ead4913e960eda94204af0c9e9e820f855a6d854b4ac3847aa7ac45d"
SEGMENTS = ("INTRO-A1-S01-N01", "INTRO-A1-S01-N02")

# Semantic edit points, not fabricated timestamps. Each phrase must be a
# literal substring of its original, source-hashed narration.
BEATS = (
    ("OPN01", SEGMENTS[0], "אדם יוצא לדרך.",
     "צעד ראשון בדרך", "Locked detail; a grown traveler's foot and ground"),
    ("OPN02", SEGMENTS[0], "הוא יודע מה לקח בידיו:",
     "הדרך נפתחת למרחב", "Wide two-adult rear view; figures <=35% frame height"),
    ("OPN03", SEGMENTS[0], "ויש דברים שהוא נושא בלי שיוכל להניח אותם",
     "משא לא נראה; הצעיר נעצר", "Adult younger traveler pauses, stays screen-right; metaphor, not a source fact"),
    ("OPN04", SEGMENTS[0], "דרך שלמד להבחין בה בין טוב לרע.",
     "הקשב מתעורר בין הדורות", "Elder notices the younger traveler; original OTS, fixed 180-degree axis"),
    ("OPN05", SEGMENTS[0], "מה מן הדברים יוכל לעבור אליו?",
     "שאלה שמבקשת תשובה", "Intimate reaction close-up; mature restrained emotion"),
    ("OPN06", SEGMENTS[1], "זה המסע שנצא אליו:",
     "מחווה אנושית קטנה", "Original insert: hand near travel satchel, no invented scroll"),
    ("OPN07", SEGMENTS[1], "בדרך נפגוש עולם גדול",
     "שני האנשים ממשיכים", "Distinct wide shot; never re-crop or copy OPN02"),
)


def sha(s):
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def build(root):
    root = Path(root)
    captions = caption_source(root)
    if captions["scene"] != "INTRO-A1-S01" or captions["profile"] != PROFILE:
        raise ValueError("Caption source identity mismatch")
    registry = json.loads((root / "episodes/berakhot-01-01/voice-rehearsal-draft.json")
                          .read_text(encoding="utf-8"))
    baseline = registry["speakers"]["narrator"]["production_baseline_profile"]
    if (baseline.get("profile_id") != PROFILE or baseline.get("voice_name") != VOICE or
            baseline.get("model_declared_by_host") != MODEL or
            baseline.get("status") != "owner_approved_reference_for_continuing_production" or
            baseline.get("source_trial_id") != "alnilam-one-continuous-correction-2026-11-06"):
        raise ValueError("Selected narrator baseline changed")
    settings = baseline.get("synthesis_settings", {})
    if (settings.get("speed_factor") != 1 or settings.get("temperature") != 1 or
            settings.get("pitch_override") is not None or
            settings.get("reference_audio") is not None or
            settings.get("seed") != "not exposed"):
        raise ValueError("Unexpected approved narrator synthesis settings")
    legacy_scene_instruction = (
        'במילים "ואז הגיע החורבן" נשאר בדיוק אותו אדם: רצינות וכאב מאופק '
        'באמצעות משקל למילים והפסקה קצרה, לא קול דרמטי חדש.')
    opening_instruction = (
        "בשאלות על מסירת הלימוד לדור הבא, הדגש בעדינות את האחריות ואת "
        "הסקרנות, בלי לשנות גוון קול ובלי להוסיף דרמה מלאכותית.")
    if baseline.get("exact_direction", "").count(legacy_scene_instruction) != 1:
        raise ValueError("Approved voice direction template changed; review before adapting")
    # Retain the exact approved source while making an explicitly UNAPPROVED
    # scene-specific direction that cannot accidentally request past narration.
    scene_direction_draft = baseline["exact_direction"].replace(
        legacy_scene_instruction, opening_instruction)
    if "ואז הגיע החורבן" in scene_direction_draft:
        raise ValueError("Unrelated previous audition instruction still present")
    original = baseline["approved_wav"]
    if original.get("sha256") != APPROVED_REFERENCE_SHA or not original.get("must_not_overwrite"):
        raise ValueError("Original owner-approved Alnilam recording is not locked")
    if not baseline.get("exact_direction") or not baseline.get("commercial_free_production_access"):
        raise ValueError("Approved performance instructions or cost gate missing")
    if baseline.get("scope", {}).get("full_intro_spoken_text_approved") is not False:
        raise ValueError("Scene text approval may have changed; review before preparing")
    segments = captions["segments"]
    if [s["id"] for s in segments] != list(SEGMENTS):
        raise ValueError("Unexpected intro scene cue identifiers")
    if any(s["source_text_approved"] is not False or s["recording_status"] != "NOT_RECORDED"
           for s in segments):
        raise ValueError("Scene recording/approval state may have changed")
    script = "\n\n".join(s["source_text"] for s in segments)
    if sum(s["word_count"] for s in segments) != 109:
        raise ValueError("Unexpected number of exact source words")
    positions = {}
    beats = []
    for shot_id, voice_id, phrase, editorial_intent, shot_direction in BEATS:
        source = next(s["source_text"] for s in segments if s["id"] == voice_id)
        pos = source.find(phrase)
        if pos < 0 or source.find(phrase, pos + 1) >= 0:
            raise ValueError("Missing or ambiguous beat phrase for " + shot_id)
        if pos <= positions.get(voice_id, -1):
            raise ValueError("The proposed shot beats are out of narration order")
        positions[voice_id] = pos
        beats.append({
            "shot_id": shot_id, "voice_id": voice_id,
            "spoken_phrase_anchor": phrase, "editorial_intent": editorial_intent,
            "shot_direction_for_review_only": shot_direction,
            "source_layer": "symbolic_dramatization",
            "exact_cut_frame": None, "estimated_seconds": None,
            "shot_approved": False, "needs_measured_alignment": True,
        })
    # Editor bridge: link the semantic shot starts to exact caption-card
    # boundaries. No timestamps or frame lengths are inferred from words.
    flat_cards = [card for segment in segments for card in segment["cards"]]
    boundaries = []
    for beat in beats:
        hits = [i for i, card in enumerate(flat_cards)
                if card["voice_id"] == beat["voice_id"]
                and card["spoken_text"].startswith(beat["spoken_phrase_anchor"])]
        if len(hits) != 1:
            raise ValueError("Shot/untimed-caption boundary mismatch: " + beat["shot_id"])
        boundaries.append(hits[0])
    if not boundaries or boundaries[0] != 0 or any(
            boundaries[i] >= boundaries[i + 1] for i in range(len(boundaries) - 1)):
        raise ValueError("Storyboard/caption sequence incomplete or reordered")
    for i, beat in enumerate(beats):
        start = boundaries[i]
        end = boundaries[i + 1] if i + 1 < len(beats) else len(flat_cards)
        beat["first_caption_card_id"] = flat_cards[start]["card_id"]
        beat["caption_card_ids_until_next_shot"] = [
            x["card_id"] for x in flat_cards[start:end]]
        if not beat["caption_card_ids_until_next_shot"]:
            raise ValueError("Shot would have no narration caption coverage")
        beat["provisional_spoken_words_in_shot"] = sum(
            len(card["spoken_text"].split()) for card in flat_cards[start:end])
        beat["pacing_status"] = "UNMEASURED_REVIEW_AFTER_WAV"
    return {
        "schema_version": 1,
        "type": "PRIVATE_VOICE_PREPARATION_NOT_A_PROVIDER_REQUEST",
        "scene": "INTRO-A1-S01",
        "narrator_profile": PROFILE,
        "voice_name": VOICE,
        "model_declared_by_approved_baseline": MODEL,
        "host_revision_from_approved_audition": baseline["host_revision"],
        "approved_voice_trial_id": baseline["source_trial_id"],
        "baseline_settings_unchanged": settings,
        "approved_performance_direction_unchanged": baseline["exact_direction"],
        "scene_specific_direction_draft": scene_direction_draft,
        "scene_specific_direction_approved": False,
        "performance_context_note": (
            "Original direction refers to an old audition passage about the destruction; "
            "that passage is NOT in this scene. Keep one warm, serious Israeli narrator "
            "throughout, no invented speech and no childlike or advertisement delivery. "
            "This scene-specific performance direction requires review before TTS."),
        "approved_sample_sha256": APPROVED_REFERENCE_SHA,
        "approved_sample_location": original["url"],
        "approved_sample_is_only_a_voice_reference": True,
        "approved_sample_is_not_target_scene_audio": True,
        "single_continuous_take": True,
        "one_speaker": True,
        "single_take_spoken_text": script,
        "segment_boundaries": [{
            "id": s["id"], "spoken_text": s["source_text"],
            "text_sha256": s["source_text_sha256"],
            "word_count": s["word_count"],
            "source_start_sample": None, "source_end_sample": None,
            "approved": False
        } for s in segments],
        "beat_anchors_provisional": beats,
        "caption_card_count": len(flat_cards),
        "all_untimed_caption_cards_assigned_to_shots": True,
        "caption_alignment_is_semantic_not_measured": True,
        "script_master_sha256": captions["script_master_sha256"],
        "expected_total_words": 109,
        "expected_segment_ids": list(SEGMENTS),
        "source_text_approved": False,
        "real_scene_recording_exists": False,
        "all_shot_images_approved": False,
        "visual_scene_status": "UNAPPROVED",
        "verify_free_hard_cap_before_submission": True,
        "verified_no_charge_tts_route_available": False,
        "tts_submission_permitted": False,
        "generation_requests_made": 0,
        "external_spend_initiated_usd": 0,
        "workspace_usage": "unknown",
        "post_recording_steps": [
            "Capture one uninterrupted WAV without changing approved narrator identity",
            "Verify spoken N01 then N02 against exact text, not just ASR similarity",
            "Measure 48kHz WAV and section split at real pauses with listening review",
            "Align the 14 provisional caption cards from real word timing; never invent timecodes",
            "Use only explicitly reviewed accepted images and human Torah/rights approvals",
        ],
        "release_authorized": False,
    }


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--root", default=".")
    p.add_argument("--out", default="build/opening-voice-preparation.json")
    args = p.parse_args()
    root = Path(args.root).resolve()
    result = build(root)
    destination = (root / args.out).resolve()
    safe_build = (root / "build").resolve()
    if (not safe_build.is_relative_to(root) or not destination.is_relative_to(safe_build)
            or destination.suffix != ".json"):
        raise ValueError("Voice preparation reports may only be written as JSON inside build/")
    destination.parent.mkdir(parents=True, exist_ok=True)
    tmp = destination.with_suffix(".tmp")
    tmp.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(destination)
    print(json.dumps({"status": result["type"],
                      "words": result["expected_total_words"],
                      "segments": len(result["segment_boundaries"]),
                      "shot_anchors": len(result["beat_anchors_provisional"]),
                      "provider_calls": 0, "tts_submission_permitted": False,
                      "out": str(destination.relative_to(root))}, ensure_ascii=False))


if __name__ == "__main__":
    main()
