"""Create a reusable scene-wide cinematic shot planning packet, entirely offline.

No AI/provider/Drive import. Turns the existing authored scene + continuity bible
into deterministic image specifications and audio slots in ONE call. It is not a
production permit, prompt-based source verification, nor a finished storyboard.
"""
import argparse
import json
import sys
from pathlib import Path

from tools.scene_factory import SceneBlocked, digest, file_sha, keys, load, validate, within

FPS = 24
SAMPLES_PER_FRAME = 2000  # 48kHz / 24fps
REQUIRED_VISUAL_KEYS = (
    "characters", "location", "era", "time_of_day", "sun_direction", "weather",
    "palette", "style", "axis", "screen_direction", "eyelines", "props",
)
NEGATIVE = (
    "No written words, subtitles, logos, watermark, pseudo-Hebrew, modern objects, "
    "extra fingers or limbs, plastic skin, invented props, accidental camera-axis "
    "reversal, arbitrary wardrobe or face changes, or misplaced sun. "
    "Do not depict unknown ancient people as documented portraits."
)


def _visual_spec(scene, shot, state):
    """A text brief, not a provider payload. Reuses authoritative shot data."""
    characters = {
        name: {
            "face_lock": char["face_lock"],
            "reference_sha256": char["reference_sha256"],
            "age": char["age"], "proportions": char["proportions"],
            "costume": char["costume"],
        }
        for name, char in sorted(state["characters"].items())
    }
    locks = {name: state[name] for name in REQUIRED_VISUAL_KEYS if name != "characters"}
    # Producer-authored language is compiled once for all shots, not typed 15
    # times by the owner. These are descriptive prompts only; not executable.
    character_notes = "; ".join(
        name + ": " + char["face_lock"] + ", " + char["costume"]
        for name, char in characters.items()
    )
    prompt = (
        "Mature hand-painted cinematic illustration, 16:9; "
        + "visual action: " + shot["description"]
        + "; narrative reason: " + shot["why"]
        + "; camera: " + shot["camera"]["intent"]
        + "; location: " + state["location"]
        + "; era: " + state["era"]
        + "; time of day: " + state["time_of_day"]
        + "; sun: " + state["sun_direction"]
        + "; weather: " + state["weather"]
        + "; palette: " + state["palette"]
        + "; art style: " + state["style"]
        + "; camera axis: " + state["axis"]
        + "; screen direction: " + state["screen_direction"]
        + "; eyelines: " + str(state["eyelines"])
        + "; continuity character locks ONLY IF visible: " + character_notes
        + "; props: " + json.dumps(state["props"], ensure_ascii=False, sort_keys=True)
        + ". Respect the scene's symbolic/draft source status; never add captions inside an image."
    )
    return {
        "scene_id": scene["id"], "shot_id": shot["id"],
        "positive_prompt": prompt,
        "purpose": shot["why"], "shot_description": shot["description"],
        "camera": shot["camera"], "visual_locks": locks,
        "character_locks_if_visible": characters,
        "negative_prompt": NEGATIVE,
        "aspect_ratio": "16:9", "width": 1024, "height": 576,
        "no_text_in_art": True,
    }


def build_packet(scene, bible, root):
    """Construct planning and batching inputs, but NEVER authorize execution.

    Deliberately revalidates all shots and source hashes on each call.
    Only exact existing accepted assets with a matching hash are reusable.
    Unapproved OPN candidates are never silently promoted to cache hits.
    """
    root = Path(root).resolve()
    issues = validate(scene, bible, root)
    if digest(bible) != scene["bible"]["sha256"]:
        raise SceneBlocked("PACKET_BIBLE_CHANGED")
    script = within(root, scene["script"]["path"])
    if not script.is_file() or file_sha(script) != scene["script"]["sha256"]:
        raise SceneBlocked("PACKET_SCRIPT_CHANGED")
    if scene["authorization"].get("generation_approved") is not False or scene["authorization"].get("budget_usd") != 0:
        raise SceneBlocked("PACKET_LIVE_AUTHORIZATION_FORBIDDEN")
    image_index = keys(scene, bible)
    image_keys = image_index["asset_keys"]
    # Count actual candidate FILE identities, not just timeline slots. OPN02 is
    # currently mapped to both EP-P07 and EP-P14: these are NOT two originals.
    candidate_uses = {}
    for shot in scene["shots"]:
        a = shot["asset"]
        if a["origin"] == "original" and a["accepted"] is False and a["id"]:
            candidate_uses.setdefault(a["id"], []).append(shot["id"])
    duplicate_candidates = {aid: ids for aid, ids in candidate_uses.items() if len(ids) > 1}
    jobs = []
    for shot in scene["shots"]:
        state = bible["states"][shot["pre_state"]]
        visual = _visual_spec(scene, shot, state)
        asset = shot["asset"]
        if asset["accepted"] is True and asset["path"] and asset["origin"] not in ("mock", "missing"):
            candidate = within(root, asset["path"])
            reuse = candidate.is_file() and file_sha(candidate) == asset["sha256"]
            image_status = "VERIFIED_ACCEPTED_CACHE" if reuse else "HASH_MISMATCH_BLOCKED"
        elif asset["id"] and asset["accepted"] is False and asset["origin"] == "original":
            image_status = "EXISTING_CANDIDATE_REVIEW_ONLY"
        else:
            image_status = "NEW_ORIGINAL_IMAGE_REQUIRED"
        start, end = shot["start_frame"], shot["end_frame"]
        if type(start) is not int or type(end) is not int or end <= start:
            raise SceneBlocked("PACKET_FRAMES_INVALID")
        # Same M1 visual asset key; sound/caption edits must not re-generate art.
        jobs.append({
            "shot_id": shot["id"], "image_status": image_status,
            "candidate_asset_id": asset["id"] if image_status == "EXISTING_CANDIDATE_REVIEW_ONLY" else None,
            "candidate_repeated_in_scene": bool(asset["id"] in duplicate_candidates and image_status == "EXISTING_CANDIDATE_REVIEW_ONLY"),
            "asset_key": image_keys[shot["id"]],
            "source_label": shot["source"]["layer"],
            "source_verified": shot["source"]["verified"] is True,
            "script_anchor": {"sha256": scene["script"]["sha256"], "lines": shot["script_span"]},
            "start_frame": start, "end_frame": end, "duration_frames": end-start,
            "audio_samples": [start*SAMPLES_PER_FRAME, end*SAMPLES_PER_FRAME],
            "beat": shot["beat"], "visual_spec": visual,
            "sound_spotting": [
                {"id": s["id"], "kind": s["kind"], "start_sample": s["start_sample"],
                 "end_sample": s["end_sample"], "licensed": bool(s["license"] and s["path"])}
                for s in shot["sound"]
            ],
            "ambience_continuity": state["sound_state"],
            "voice_approved": scene["script"]["approved"] is True and bool(scene["script"]["reviewer"]),
            "ready_for_model_submission": False,
        })
    packet = {
        "schema_version": 1, "status": "SCENE_PACKET_DRAFT_NOT_AUTHORIZED",
        "scene_id": scene["id"], "scene_approval_scope": "NONE",
        "scene_build_key": image_index["build_key"],
        "fps": FPS, "audio_sample_rate": 48000, "aspect_ratio": "16:9",
        "duration_frames": jobs[-1]["end_frame"], "shot_count": len(jobs),
        "candidate_review_only_count": sum(j["image_status"] == "EXISTING_CANDIDATE_REVIEW_ONLY" for j in jobs),
        "new_original_image_slots": sum(j["image_status"] == "NEW_ORIGINAL_IMAGE_REQUIRED" for j in jobs),
        "verified_accepted_cache_hits": sum(j["image_status"] == "VERIFIED_ACCEPTED_CACHE" for j in jobs),
        "unique_candidate_asset_count": len(candidate_uses),
        "duplicate_unapproved_candidate_usage": duplicate_candidates,
        "source_and_editorial_blockers": issues,
        "generation_gate_closed": True, "inference_requests": 0,
        "provider_dispatch_authorized": False,
        "external_cost_usd": 0, "workspace_usage": "unknown",
        "jobs": jobs,
    }
    # Specification/plan identity, not authorization to generate.
    packet["packet_sha256"] = digest(packet)
    return packet


def summary(packet):
    return {k: packet[k] for k in (
        "status", "scene_id", "shot_count", "duration_frames", "candidate_review_only_count",
        "new_original_image_slots", "verified_accepted_cache_hits", "unique_candidate_asset_count",
        "duplicate_unapproved_candidate_usage", "packet_sha256",
        "generation_gate_closed", "inference_requests", "provider_dispatch_authorized",
    )} | {"blocker_count": len(packet["source_and_editorial_blockers"])}


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--root", default=".")
    p.add_argument("--manifest", default="episodes/berakhot-01-01/scene-prologue-v02.json")
    p.add_argument("--summary", action="store_true")
    a = p.parse_args(argv)
    try:
        root = Path(a.root).resolve()
        scene = load(within(root, a.manifest))
        bible = load(within(root, scene["bible"]["path"]))
        packet = build_packet(scene, bible, root)
        print(json.dumps(summary(packet) if a.summary else packet, ensure_ascii=False, sort_keys=True))
        return 0  # Plan built; production remains closed.
    except (OSError, ValueError, KeyError, TypeError) as e:
        print(json.dumps({"status":"BLOCKED","reason":str(e) if isinstance(e, SceneBlocked) else type(e).__name__,
                          "provider_dispatch_authorized":False,"inference_requests":0}))
        return 2


if __name__ == "__main__":
    sys.exit(main())
