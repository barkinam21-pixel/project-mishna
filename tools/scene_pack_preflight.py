"""Offline, no-charge scene-pack preflight for the Mishnah introduction.

A single command summarises all seven shots and the film gate without calling
Cloudflare, ComfyUI, Google Drive or an image model. Never grants approvals.
"""
import argparse
import json
from pathlib import Path

from tools.comfy_scene_images import specifications, under, sha

EXPECTED_IDS = [f"OPN{i:02d}" for i in range(1, 8)]
CANDIDATE = "CANDIDATE_NEEDS_HUMAN_REVIEW"
ACCEPTED = "VERIFIED_LOCAL_ACCEPTED"
REMOTE = "REMOTE_CANDIDATE_NOT_LOCALLY_VERIFIED"
BLOCKED = "BLOCKED_MISSING_PRIVATE_INPUT"
UNAUTHORIZED = "NOT_AUTHORIZED_FOR_GENERATION"


def verified_entry(entry, root):
    """Return (status, reason); never trust a status flag without actual bytes."""
    if not isinstance(entry, dict):
        return None, None
    status = entry.get("status")
    if status not in ("ACCEPTED", "CANDIDATE"):
        return None, None
    try:
        path = under(root, entry["path"])
        valid = path.is_file() and sha(path) == entry["sha256"]
        if entry.get("png_is_converted"):
            native = under(root, entry["native_path"])
            valid = valid and native.is_file() and sha(native) == entry["native_sha256"]
    except (KeyError, ValueError, OSError, TypeError):
        valid = False
    if not valid:
        return "LOCAL_STATE_ASSET_MISMATCH", "Saved status cannot be trusted until private bytes match"
    if status == "ACCEPTED" and entry.get("accepted") is True and entry.get("rights_verified") is True and entry.get("continuity_review"):
        return ACCEPTED, "Local bytes and explicit review fields verified"
    return CANDIDATE, "Candidate is not approved for the film"


def report_scene(manifest, rows, state, proof, evidence, root):
    """Pure reporting and file-hash checks. Never generates, edits, or accepts."""
    shots = manifest.get("shots", [])
    ids = [s.get("id") for s in shots]
    if ids != EXPECTED_IDS or [r.get("id") for r in rows] != EXPECTED_IDS:
        raise ValueError("Opening scene must contain OPN01..OPN07 in order")
    auth = manifest.get("authorization", {})
    entries = state.get("entries", {}) if isinstance(state, dict) else {}
    evidence_ok = bool(
        isinstance(evidence, dict)
        and evidence.get("local_task_id", "").startswith("OPN02-")
        and evidence.get("accepted") is False
        and evidence.get("png_sha256")
        and evidence.get("private_png")
    )
    outputs = []
    for shot, row in zip(shots, rows):
        director = shot.get("director", {})
        notes = []
        if not director or director.get("shot_id") != row["id"]:
            notes.append("Director record missing or mismatched")
        if not director.get("cut_motivation") or not director.get("new_relative_to_previous"):
            notes.append("Missing distinct camera/cut intention")
        if shot.get("source_layer") != "symbolic_dramatization":
            notes.append("Source layer must be reviewed independently")
        entry_state, entry_reason = verified_entry(entries.get(row["key"]), root)
        if entry_state:
            status = entry_state
            notes.append(entry_reason)
        elif row["id"] == "OPN02" and evidence_ok:
            status = REMOTE
            notes.append("Real provider receipt exists; private image bytes not present in this runtime; remains unapproved")
        elif row.get("missing"):
            status = BLOCKED
        else:
            status = UNAUTHORIZED
        allowed_id = row["id"] in auth.get("approved_shot_ids", [])
        if not allowed_id:
            notes.append("Shot has no generation authorization")
        if not all(auth.get(x) is True for x in (
                "zero_cost_compute_verified", "generation_approved", "component_licenses_verified")):
            notes.append("Generation gates are not all verified")
        outputs.append({
            "shot_id": row["id"], "status": status,
            "key": row["key"],
            "shot_purpose": director.get("purpose", shot.get("story_emotion", "")),
            "camera": director.get("camera_distance", ""),
            "cut_reason": director.get("cut_motivation", ""),
            "missing_inputs": row.get("missing", []),
            "notes": notes,
            "generation_requested": False, "auto_accepted": False,
        })
    assets = proof.get("assets", {}) if isinstance(proof, dict) else {}
    media = list(EXPECTED_IDS) + ["INTRO-A1-S01-N01", "INTRO-A1-S01-N02", "captions"]
    missing_media = [name for name in media if not (
        isinstance(assets.get(name), dict)
        and assets[name].get("accepted") is True
        and assets[name].get("rights_verified") is True
        and assets[name].get("sha256")
    )]
    if any(s["status"] == REMOTE for s in outputs):
        next_action = "Review existing private OPN02 candidate; do not re-generate blindly"
    elif any(s["status"] == "LOCAL_STATE_ASSET_MISMATCH" for s in outputs):
        next_action = "Restore/verify private bytes; do not trust stored state"
    elif any(s["status"] == CANDIDATE for s in outputs):
        next_action = "Present one scene-level review board; no individual prompt editing"
    elif any(s["status"] == BLOCKED for s in outputs):
        next_action = "Restore approved private references in authorized runtime"
    else:
        next_action = "Review remaining approvals and shot coverage before any new generation"
    return {
        "schema_version": 1,
        "scene_id": manifest.get("scene"),
        "mode": "OFFLINE_READ_ONLY_NO_PROVIDER_CALLS",
        "scene_status": "NOT_READY_FOR_PRIVATE_RENDER" if missing_media else "REVIEW_RENDER_GATES",
        "next_action": next_action,
        "shots": outputs,
        "ready_local_accepted_shots": sum(s["status"] == ACCEPTED for s in outputs),
        "known_remote_candidates": sum(s["status"] == REMOTE for s in outputs),
        "missing_or_unapproved_proof_assets": missing_media,
        "proof_approval_flags": {
            "script_approved": proof.get("script_approved") is True,
            "visual_approved": proof.get("visual_approved") is True,
            "release_authorized": False,
        },
        "provider_submissions": 0,
        "external_charge_usd": "NOT_MEASURED_NO_REQUEST",
        "workspace_usage": "unknown",
        "notes": [
            "A passing preflight never authorizes generation or publication",
            "Remote evidence is a candidate, not proof that private bytes are present",
            "Age, faces, clothing, pose and historical accuracy require visual/source review",
            "This offline planner cannot supply unattended Cloudflare credentials",
        ],
    }


def load_optional(path):
    if not path.is_file():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def build(root):
    root = Path(root).resolve()
    manifest = load_optional(root / "episodes/berakhot-01-01/comfy-opening-images.json")
    if not manifest:
        raise ValueError("Missing image manifest")
    manifest["backend"] = manifest["available_backends"]["cloudflare"]
    rows = specifications(manifest, root)
    proof = load_optional(root / "episodes/berakhot-01-01/introduction-proof.json")
    state = load_optional(root / "private-media/director-images/state.json")
    evidence = load_optional(root / "docs/evidence/opn02-rear-wide-2026-11-08.json")
    return report_scene(manifest, rows, state, proof, evidence, root)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=".")
    parser.add_argument("--out", default="build/scene-pack-preflight.json")
    args = parser.parse_args()
    root = Path(args.root).resolve()
    report = build(root)
    out = under(root, args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    temp = out.with_suffix(".tmp")
    temp.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temp.replace(out)
    print(json.dumps({
        "scene": report["scene_id"], "status": report["scene_status"],
        "accepted_shots": report["ready_local_accepted_shots"],
        "remote_candidates": report["known_remote_candidates"],
        "remaining_assets": len(report["missing_or_unapproved_proof_assets"]),
        "next": report["next_action"], "provider_submissions": 0,
        "report": str(out.relative_to(root)),
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
