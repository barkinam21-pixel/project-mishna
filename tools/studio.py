"""Offline, zero-billing preflight for the Mishnah Film Studio."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import unicodedata

FORBIDDEN_BIDI = set(chr(n) for n in [0x202A, 0x202B, 0x202C, 0x202D, 0x202E, 0x2066, 0x2067, 0x2068, 0x2069])


def preflight(data):
    errors = []
    blockers = []
    if not isinstance(data, dict):
        return {"valid": False, "status": "INVALID", "errors": ["Root must be an object"], "blockers": []}

    def obj(name):
        value = data.get(name)
        if not isinstance(value, dict):
            errors.append(f"{name}: expected object")
            return {}
        return value

    def arr(name):
        value = data.get(name)
        if not isinstance(value, list):
            errors.append(f"{name}: expected array")
            return []
        return value

    if data.get("schema_version") != 1:
        errors.append("schema_version must equal 1")
    if not isinstance(data.get("episode_id"), str) or not data.get("episode_id"):
        errors.append("episode_id required")
    unit = obj("unit")
    if not (unit.get("work") and unit.get("tractate") and isinstance(unit.get("chapter"), int) and isinstance(unit.get("mishnah"), int)):
        errors.append("unit must identify exact tractate, chapter and mishnah")
    production = obj("production")
    fps = production.get("fps")
    sample_rate = production.get("sample_rate")
    if not isinstance(fps, int) or isinstance(fps, bool) or fps <= 0:
        errors.append("production.fps must be positive integer")
    if not isinstance(sample_rate, int) or sample_rate != 48000 or not isinstance(fps, int) or fps <= 0 or sample_rate % fps:
        errors.append("audio timing requires 48kHz and integer samples per frame")
    if (production.get("width"), production.get("height")) != (1920, 1080):
        errors.append("proof must use 1920x1080")
    if production.get("status") not in ("research", "ready_for_writing", "torah_reviewed", "approved_for_production"):
        errors.append("production.status invalid")
    sources = obj("sources")
    witnesses = sources.get("independent_witnesses", [])
    if not isinstance(witnesses, list):
        errors.append("sources.independent_witnesses must be array")
        witnesses = []
    reviewed = [x for x in witnesses if isinstance(x, dict) and x.get("checked") is True and x.get("url") and x.get("edition") and x.get("license")]
    if len({x.get("name") for x in reviewed}) < 2:
        blockers.append("Two independent editions must be checked and licensed")
    if not sources.get("working_text") or sources.get("text_verified") is not True:
        blockers.append("Exact Mishnah text must be checked and locked")
    if sources.get("textual_variants_reviewed") is not True:
        blockers.append("Textual variants must be reviewed")
    if sources.get("rights_reviewed") is not True:
        blockers.append("Rights and attribution must be reviewed")
    torah = sources.get("torah_review")
    if not isinstance(torah, dict) or not (torah.get("approved") is True and torah.get("reviewer") and torah.get("date")):
        blockers.append("Human Torah review is required")
    creative = obj("creative")
    for key in ("script_approved", "visual_direction_approved", "voice_approved", "proof_approved"):
        if creative.get(key) is not True:
            blockers.append(f"creative.{key} not approved")
    shots = arr("shots")
    if not shots:
        blockers.append("Storyboard and shot manifest not prepared")
    used_ids = set()
    for i, shot in enumerate(shots):
        if not isinstance(shot, dict):
            errors.append(f"shots[{i}]: must be object")
            continue
        sid = shot.get("id")
        duration = shot.get("duration_frames")
        if not isinstance(sid, str) or not sid or sid in used_ids:
            errors.append(f"shots[{i}]: unique id required")
        used_ids.add(sid)
        if not isinstance(duration, int) or isinstance(duration, bool) or duration < 1:
            errors.append(f"shots[{i}]: positive integer duration_frames required")
        if shot.get("source_status") not in ("exact_source", "attributed_commentary", "historical_reconstruction", "dramatization"):
            errors.append(f"shots[{i}]: source_status required")
        if not shot.get("scene_id") or not shot.get("beat_id") or not shot.get("purpose") or not shot.get("image_sha256"):
            errors.append(f"shots[{i}]: scene/beat/purpose/asset sha required")
        if shot.get("motion") != "locked" and not (shot.get("motion_reason") and isinstance(shot.get("motion_parameters"), dict)):
            errors.append(f"shots[{i}]: moving shot requires parameters and reason")
    assets = arr("assets")
    for i, asset in enumerate(assets):
        if not isinstance(asset, dict) or asset.get("accepted") is not True or not isinstance(asset.get("sha256"), str) or len(asset.get("sha256", "")) != 64:
            errors.append(f"assets[{i}]: accepted asset with SHA-256 required")
    if not assets:
        blockers.append("No approved image assets")
    narration = arr("narration")
    if not narration:
        blockers.append("No checked narration or pronunciation track")
    captions = arr("captions")
    if not captions:
        blockers.append("No Hebrew subtitles")
    for i, cap in enumerate(captions):
        if not isinstance(cap, dict):
            errors.append(f"captions[{i}]: must be object")
            continue
        s = cap.get("display_text", "")
        if not isinstance(s, str) or not s or unicodedata.normalize("NFC", s) != s or any(c in FORBIDDEN_BIDI or c == "\ufffd" for c in s):
            errors.append(f"captions[{i}]: invalid Hebrew text normalization/controls")
        elif len(s.splitlines()) > 2 or any(len(line) > 42 for line in s.splitlines()):
            errors.append(f"captions[{i}]: maximum 2 lines, 42 codepoints per line")
        start, end = cap.get("start_frame"), cap.get("end_frame")
        if not isinstance(start, int) or not isinstance(end, int) or start < 0 or end <= start:
            errors.append(f"captions[{i}]: invalid integer frame timing")
        for required in ("spoken_text", "pronunciation_text", "speaker", "source", "shot_id"):
            if not isinstance(cap.get(required), str) or not cap.get(required):
                errors.append(f"captions[{i}]: {required} required")
    audio = arr("audio")
    if not audio:
        blockers.append("No approved audio clips; silent proof only if explicitly declared")
    cost = obj("cost")
    max_usd = cost.get("max_external_usd")
    if not isinstance(max_usd, (int, float)) or isinstance(max_usd, bool) or max_usd < 0:
        errors.append("cost.max_external_usd must be >= 0")
    if cost.get("workspace_usage") != "unknown":
        errors.append("Unmetered workspace usage must be recorded as unknown")
    if cost.get("external_spend_enabled") is not False:
        errors.append("External spending must remain disabled in tools stage")
    release = obj("release")
    if not all(release.get(k) is True for k in ("rights_cleared", "technical_qa_passed", "human_approval")):
        blockers.append("Release is blocked pending rights, QA and final review")
    if production.get("release_authorized") is not True:
        blockers.append("Release not authorized")
    if errors:
        status = "INVALID"
    elif blockers:
        status = "BLOCKED_AS_DESIGNED"
    else:
        status = "READY_FOR_REVIEW_ONLY"
    raw = json.dumps(data, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return {"valid": not errors, "status": status, "episode_id": data.get("episode_id"),
            "manifest_sha256": hashlib.sha256(raw).hexdigest(), "errors": errors,
            "blockers": blockers, "budget_usd_ceiling": max_usd,
            "external_generation_calls": 0, "workspace_usage": "unknown"}


def main(argv=None):
    parser = argparse.ArgumentParser(description="Validate episode plan; never calls external services")
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--output", type=Path, default=Path("build/preflight.json"))
    args = parser.parse_args(argv)
    try:
        with args.manifest.open(encoding="utf-8") as f:
            manifest = json.load(f)
    except (OSError, ValueError) as exc:
        print(f"Manifest read error: {exc}", file=sys.stderr)
        return 2
    report = preflight(manifest)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"{report['status']}: {len(report['errors'])} errors; {len(report['blockers'])} gates remaining")
    for item in report["errors"] + report["blockers"]:
        print("- " + item)
    return 2 if not report["valid"] else 0


if __name__ == "__main__":
    sys.exit(main())
