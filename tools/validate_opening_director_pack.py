#!/usr/bin/env python3
"""Offline source/continuity/spend-gate validator for the first prologue of Mishnah cinema.

This program NEVER contacts AI providers, reads private media or emits artwork.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import sys

ALLOWED_CAMERA = {"locked", "subpixel_push", "subpixel_pullback", "subpixel_pan"}
ALLOWED_SOURCE = {"symbolic_dramatization", "attributed_tradition", "modern_explanation"}
EXPECTED_IDS = [f"OPN{x:02d}" for x in range(1, 8)]
EXPECTED_FRAMES = 1080


def validate(payload: dict) -> dict:
    errors = []
    def reject(msg):
        errors.append(msg)
    if not isinstance(payload, dict):
        return {"status": "BLOCKED", "errors": ["JSON root must be an object"], "shot_count": 0}
    priv = payload.get("privacy", {})
    if not isinstance(priv, dict):
        priv = {}
    for key, expected in {
        "repository_public_text_only": True,
        "source_assets_private_only": True,
        "generation_in_chatgpt_forbidden": True,
        "fal_paid_approval_granted": False,
        "new_external_spend_authorized": False,
        "paid_calls_made_for_this_pack": 0,
        "images_generated_for_this_pack": 0,
        "production_voice_or_film_audio_generated_for_this_pack": 0,
        "synthetic_audio_previsualization_generated": 1,
        "audio_canary_contains_dialogue": False,
        "audio_canary_not_final_score": True,
        "preview_rendered_for_this_pack": False,
        "never_call_tinyfish": True,
    }.items():
        if priv.get(key) != expected or type(priv.get(key)) is not type(expected):
            reject(f"privacy.{key} must be {expected!r}")
    f = payload.get("film", {})
    if not isinstance(f, dict):
        f = {}
    if f.get("fps") != 24 or f.get("sample_rate_hz") != 48000:
        reject("render contract must be 24fps / 48000Hz")
    if f.get("target_frames_editorial_only") != EXPECTED_FRAMES or f.get("runtime_approved") is not False:
        reject("opening should be a 1080-frame unapproved editorial timeline")
    if f.get("camera_speed_factor_vs_v10_on_moving_shots") != 1.15 or f.get("camera_shake_px") != 0:
        reject("moving camera must follow V10 * 1.15 with zero shake")
    if payload.get("chronological_position") != "first_sequence_first_shot":
        reject("opening must remain the first actual sequence")
    if payload.get("next_paid_shot_candidate") != "OPN01" or payload.get("sons_return_scene_is_later") is not True:
        reject("sons story must stay later: next possible paid shot OPN01")
    src = payload.get("source_contract", {})
    if not isinstance(src, dict):
        src = {}
    if src.get("torah_review") != "not_completed" or src.get("approved_for_public_release") is not False:
        reject("source and publication gate may not be auto-approved")
    if src.get("source_layer") != "dramatization_only_until_next_sequence":
        reject("historically invented prologue must be labeled dramatization")
    if "המחזה" not in src.get("mandatory_first_caption_he", ""):
        reject("first caption must clearly identify dramatization")
    scenes = payload.get("shots", [])
    if not isinstance(scenes, list) or len(scenes) != 7:
        reject("exactly seven distinct first-prologue shot plans are required")
        scenes = scenes if isinstance(scenes, list) else []
    # A paid OPN01 was rejected (extra leg and modern details). The working
    # corrective plan must never silently reset this factual history.
    history = payload.get("production_history", {})
    if not isinstance(history, dict) or history.get("previous_opn01_paid_attempts") != 1 or history.get("previous_opn01_result") != "REJECTED_VISUAL_QA" or history.get("new_opn01_paid_authorization") is not False or history.get("existing_paid_authorization_consumed") is not True:
        reject("OPN01 prior rejected paid attempt and lack of fresh approval must be recorded")
    first = scenes[0] if scenes and isinstance(scenes[0], dict) else {}
    contract = first.get("anatomy_contract", {})
    required = {"visible_travelers": 1, "visible_legs": 2, "visible_feet": 2,
                "other_travelers_in_frame": False, "framing": "one_person_knees_down",
                "prior_paid_attempt_rejected": True}
    if not isinstance(contract, dict) or any(type(contract.get(k)) is not type(v) or contract.get(k) != v for k, v in required.items()):
        reject("OPN01 must depict exactly one visible traveler and a single coherent pair of legs/feet")
    first_prompt = first.get("prompt_subject_en", "")
    markers = ("EXACTLY ONE adult traveler", "EXACTLY TWO connected human legs",
               "EXACTLY TWO anatomically coherent feet", "NO other people", "NO buckles")
    if not isinstance(first_prompt, str) or any(x not in first_prompt for x in markers) or "TWO ANONYMOUS travelers" in first_prompt:
        reject("OPN01 prompt must be anatomically unambiguous, period-plausible and single-person")
    cursor = 0
    ids = []
    dialog_count = 0
    for i, shot in enumerate(scenes):
        if not isinstance(shot, dict):
            reject(f"shot #{i} not object")
            continue
        sid = shot.get("id", f"#{i}")
        ids.append(sid)
        if shot.get("asset_status") != "not_generated" or shot.get("original_illustration_required") is not True:
            reject(f"{sid} must be a separate, not-yet-generated original illustration")
        if shot.get("source_status") not in ALLOWED_SOURCE:
            reject(f"{sid} has invalid source status")
        start, end, duration = shot.get("start_frame"), shot.get("end_frame"), shot.get("frames")
        if not all(type(n) is int for n in (start,end,duration)) or (start,end) != (cursor,cursor+duration) or duration <= 0:
            reject(f"{sid} has missing, invalid or noncontiguous integer frame timing")
        else:
            cursor = end
        camera = shot.get("camera", {})
        if not isinstance(camera, dict) or camera.get("mode") not in ALLOWED_CAMERA:
            reject(f"{sid} camera mode invalid")
            continue
        moving = camera["mode"] != "locked"
        if camera.get("shake_px") != 0 or camera.get("motion_speed_factor") != (1.15 if moving else 1.0):
            reject(f"{sid} camera: shake/speed mismatch")
        if len(shot.get("prompt_subject_en", "")) < 130 or not shot.get("description_he"):
            reject(f"{sid} needs detailed direction, not a generic image prompt")
        for dialog in shot.get("dialogue_he", []):
            if not isinstance(dialog,dict) or dialog.get("type") != "invented_dramatization_not_a_quote":
                reject(f"{sid} unlabeled invented dialogue")
            elif not dialog.get("speaker") or not dialog.get("text"):
                reject(f"{sid} missing dialogue text/speaker")
            else:
                dialog_count += 1
        if shot.get("dialogue_he") and "מומחז" not in shot.get("source_label", ""):
            reject(f"{sid} has invented lines with no dramatization label")
        if not shot.get("cut_motivation") or not shot.get("acting") or not shot.get("sound"):
            reject(f"{sid} must have an acting, sound and motivated-cut plan")
    if ids != EXPECTED_IDS:
        reject("must preserve shot IDs OPN01..OPN07 sequentially without duplication")
    if cursor != EXPECTED_FRAMES:
        reject(f"shots must cover all {EXPECTED_FRAMES} frames, covered={cursor}")
    if dialog_count < 2:
        reject("opening must have actual dramatic dialogue not solely voice-over")
    music = payload.get("theme_motif_music", {})
    if not isinstance(music,dict):
        music = {}
    if music.get("original_music_only") is not True or music.get("do_not_use_existing_copyrighted_recordings") is not True or music.get("status") != "synthetic_private_draft_only_not_final_score" or music.get("final_music_composed_and_approved") is not False:
        reject("no final score is approved; an original synthetic scratch may exist privately")
    spots = payload.get("audio_spotting_frames", [])
    if not isinstance(spots,list) or not spots:
        reject("audio spotting sheet missing")
        spots = []
    audio_cursor = 0
    for cue in spots:
        if not isinstance(cue,dict):
            reject("invalid audio cue")
            continue
        start,end=cue.get("start_frame"),cue.get("end_frame")
        if type(start) is not int or type(end) is not int or start != audio_cursor or end <= start or cue.get("media_status") != "not_produced":
            reject(f"bad or unproduced audio cue: {cue.get('id')}")
            continue
        audio_cursor=end
    if audio_cursor != EXPECTED_FRAMES:
        reject("audio cue sheet must cover 1080 frames")
    return {
        "status": "PASS_DRY_RUN_ONLY" if not errors else "BLOCKED",
        "errors": errors,
        "shot_count": len(scenes),
        "duration_frames": cursor,
        "duration_seconds": cursor / 24,
        "dialogue_lines_proposed": dialog_count,
        "paid_requests": 0,
        "created_art": 0,
        "notes": "Editorial pictures and dialogue proposals only; one original synthetic audio scratch, zero paid provider calls, no licensed film media or rights/source approval"
    }


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument("path",type=Path)
    ap.add_argument("--output",type=Path)
    args=ap.parse_args()
    try:
        result=validate(json.loads(args.path.read_text(encoding="utf-8")))
    except (OSError, ValueError) as e:
        result={"status":"BLOCKED","errors":[str(e)]}
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(result,ensure_ascii=False,indent=2))
    return 0 if result["status"]=="PASS_DRY_RUN_ONLY" else 1

if __name__=="__main__":
    sys.exit(main())