"""Offline-only, zero-spend preflight for Mishnah Cinema external fal.ai image prompts.

This program NEVER calls fal.ai, ChatGPT image generation or any network API.
It checks a private-only unapproved proposal, not image quality or source accuracy.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys

EXPECTED_IDS = [f"SH{n:02d}" for n in range(1, 17)]
EXPECTED_SCENES = {f"S{i:02d}" for i in range(1, 6)}
ALLOWED_SOURCE = {"exact_source", "dramatization", "historical_reconstruction", "attributed_commentary"}
URL = re.compile(r"(?:https?://|fal_[a-z0-9]{16,}|sk-[A-Za-z0-9_-]{10,}|X-Amz-Signature=)", re.I)


def _is_int(value):
    return type(value) is int


def validate(pack, blueprint=None):
    errors = []

    def err(message):
        errors.append(message)

    if not isinstance(pack, dict):
        return {"valid": False, "errors": ["Pack must be a JSON object"]}
    if pack.get("schema_version") != 1 or pack.get("episode_id") != "berakhot-01-01":
        err("Unexpected schema or episode")
    if pack.get("status") != "dry_run_prompts_only":
        err("Pack must remain dry_run_prompts_only")
    auth = pack.get("authorization")
    if not isinstance(auth, dict):
        auth = {}
        err("authorization must be an object")
    mandatory = {
        "image_generation_in_chatgpt_allowed": False,
        "provider": "fal.ai",
        "model_id": "fal-ai/flux-2-pro",
        "paid_request_authorized": False,
        "authorized_external_spend_usd": 0,
        "max_requests_this_run": 0,
        "public_release_authorized": False,
        "private_reference_required_if_using_img2img": True,
    }
    for name, value in mandatory.items():
        if auth.get(name) != value or type(auth.get(name)) is not type(value):
            err(f"authorization.{name} must be {value!r}")
    out = pack.get("output")
    if not isinstance(out, dict):
        out = {}
        err("output must be an object")
    for name, value in {"image_size": "landscape_16_9", "output_format": "png", "asset_visibility": "PRIVATE", "public_github_image_upload_allowed": False}.items():
        if out.get(name) != value:
            err(f"output.{name} must be {value!r}")
    style = pack.get("style")
    if not isinstance(style, dict) or len(style.get("positive", "")) < 160 or len(style.get("negative", "")) < 60:
        err("Global style and negative instructions are required")
    source = pack.get("source_controls")
    if not isinstance(source, dict) or source.get("source_text_locked") is not False or source.get("torah_review_approved") is not False:
        err("Source/Torah review may not be silently marked approved")
    ledger = pack.get("ledger")
    if not isinstance(ledger, dict) or any(ledger.get(k) != 0 for k in (
        "accepted_originals", "generated_in_this_work_session", "external_paid_requests_in_this_work_session", "external_cash_cost_in_this_work_session_usd")):
        err("This preflight must not claim generated images or paid requests")
    if not isinstance(ledger, dict) or ledger.get("workspace_usage") != "unknown":
        err("Workspace usage must be labeled unknown")
    shots = pack.get("shots")
    if not isinstance(shots, list) or len(shots) != 16:
        err("Exactly 16 shot prompts are required")
        shots = shots if isinstance(shots, list) else []
    actual = [s.get("id") if isinstance(s, dict) else None for s in shots]
    if actual != EXPECTED_IDS:
        err("Shot IDs must be SH01..SH16 in order, exactly once")
    previous = 0
    scenes = set()
    for i, shot in enumerate(shots):
        if not isinstance(shot, dict):
            err(f"shots[{i}] must be an object")
            continue
        sid = shot.get("id", f"index{i}")
        start, end = shot.get("start_frame"), shot.get("end_frame")
        if not (_is_int(start) and _is_int(end) and start == previous and end > start):
            err(f"{sid}: invalid contiguous frame range; expected start {previous}")
        if _is_int(end):
            previous = end
        if _is_int(start) and _is_int(end) and shot.get("duration_frames") != end-start:
            err(f"{sid}: duration does not match range")
        if shot.get("scene_id") not in EXPECTED_SCENES:
            err(f"{sid}: unknown scene")
        else:
            scenes.add(shot["scene_id"])
        if shot.get("source_status") not in ALLOWED_SOURCE:
            err(f"{sid}: unknown source status")
        if shot.get("motion_preset") not in ("locked", "subpixel_drift"):
            err(f"{sid}: unsupported motion preset")
        lead = shot.get("prompt")
        negative = shot.get("negative_prompt")
        if not isinstance(lead, str) or not 200 <= len(lead) <= 2000:
            err(f"{sid}: prompt too short/long/missing")
        if not isinstance(negative, str) or len(negative) < 60:
            err(f"{sid}: negative prompt missing")
        if isinstance(negative, str) and re.search(r"\b(?:no\s+door|no\s+house|no\s+people)\b", negative, re.I):
            err(f"{sid}: negative prompt contradicts positive requirements")
        if any(URL.search(str(shot.get(key) or "")) for key in ("prompt", "negative_prompt", "references")):
            err(f"{sid}: do not embed external or private reference URLs/keys in public plan")
        if shot.get("asset_status") != "not_generated" or shot.get("visual_approval") is not False:
            err(f"{sid}: must be ungenerated and unapproved")
        if shot.get("accepted_asset_sha256") is not None:
            err(f"{sid}: accepted asset hash must be null")
        if shot.get("uses_chatgpt_image_generation") is not False:
            err(f"{sid}: ChatGPT image generation forbidden")
        if shot.get("references") != []:
            err(f"{sid}: references to private media may not appear in public planning JSON")
        if blueprint is not None:
            bs = blueprint.get("shots") if isinstance(blueprint, dict) else None
            if not isinstance(bs, list) or len(bs) != 16:
                err("Invalid canonical proof blueprint")
                blueprint = None
            else:
                match = bs[i]
                for field in ("id", "scene_id", "shot_type", "start_frame", "end_frame", "duration_frames", "source_status"):
                    if shot.get(field) != match.get(field):
                        err(f"{sid}: {field} diverges from canonical blueprint")
    if previous != 1800:
        err("Shot ranges must end exactly on frame 1800 (75 seconds @ 24fps)")
    if scenes != EXPECTED_SCENES:
        err("All five scenes must be represented")
    return {"valid": not errors, "status": "SAFE_DRY_PLAN" if not errors else "REJECTED",
            "errors": errors, "episode_id": pack.get("episode_id"), "shot_count": len(shots),
            "scene_count": len(scenes), "duration_frames": previous,
            "new_paid_requests_authorized": 0, "image_generations_in_chatgpt_allowed": False,
            "planned_original_images": 16, "currently_generated_originals_this_pack": 0,
            "external_cash_cost_usd": 0, "workspace_usage": "unknown",
            "production_gate": "WAITING_FOR_SOURCE_LOCK_PRIVATE_REFERENCE_APPROVAL_AND_SEPARATE_PAID_AUTHORIZATION"}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("pack", type=Path)
    ap.add_argument("--blueprint", type=Path)
    ap.add_argument("--output", type=Path)
    args = ap.parse_args(argv)
    try:
        pack = json.loads(args.pack.read_text(encoding="utf-8"))
        blueprint = json.loads(args.blueprint.read_text(encoding="utf-8")) if args.blueprint else None
        result = validate(pack, blueprint)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        result = {"valid": False, "status": "REJECTED", "errors": [str(exc)]}
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["valid"] else 2


if __name__ == "__main__":
    sys.exit(main())
