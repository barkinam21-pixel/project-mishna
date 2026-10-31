"""Pure offline review of an UNAPPROVED Mishnah proof storyboard.

This validation is structural, not Torah review, source verification, art generation,
technical video QA, or release authorization. No network, paid API, GPU, or render.
"""
import argparse
import json
from pathlib import Path
import sys

ALLOWED_STATUSES = {
    "exact_source", "attributed_commentary",
    "historical_reconstruction", "dramatization"
}
REQUIRED_FALSE = (
    "selected_source_text_locked", "human_torah_review_approved",
    "script_approved", "visual_direction_approved", "voice_approved",
    "proof_approved", "external_spend_enabled", "image_generation_enabled",
    "video_generation_enabled", "release_authorized"
)


def valid_positive_int(x):
    return isinstance(x, int) and not isinstance(x, bool) and x > 0


def validate(data):
    errors = []
    if not isinstance(data, dict):
        return {"valid": False, "status": "INVALID", "errors": ["Expected root object"],
                "blockers": ["Human text, Torah, visual and voice review not approved"]}
    def error(message):
        errors.append(message)

    if data.get("schema_version") != 1 or data.get("episode_id") != "berakhot-01-01":
        error("Expected schema v1 and episode berakhot-01-01")
    if data.get("status") != "editorial_draft_only" or data.get("purpose") != "private_editorial_plan_only":
        error("Blueprint must remain a private editorial draft")
    for key in REQUIRED_FALSE:
        if data.get(key) is not False:
            error(key + " must explicitly be false in draft")
    if data.get("max_external_usd") != 0 or data.get("workspace_usage") != "unknown":
        error("Zero authorized external budget and unknown workspace usage required")
    if any(data.get(k) != "none" for k in ("images_status", "audio_status")):
        error("No actual media may be claimed by editorial draft")
    if data.get("narration_status") != "unrecorded":
        error("Draft narration must be unrecorded")
    fps = data.get("fps")
    rate = data.get("sample_rate")
    total = data.get("target_duration_frames")
    if not valid_positive_int(fps) or rate != 48000 or not valid_positive_int(total):
        error("fps, 48000 sample rate and integer total frames required")
        fps, total = 24, 1800
    if rate % fps != 0 or data.get("frame_to_audio_samples") != rate // fps:
        error("Must use exact samples per frame")
    if total != 1800 or fps != 24:
        error("Pilot is fixed at 1,800 frames / 24fps / 75s")
    scenes = data.get("scenes")
    shots = data.get("shots")
    if not isinstance(scenes, list) or not isinstance(shots, list):
        error("Scenes and shots must be arrays")
        scenes = scenes if isinstance(scenes, list) else []
        shots = shots if isinstance(shots, list) else []
    if not scenes or not shots:
        error("Missing scene/shot plan")
    scene_by_id = {}
    previous = 0
    for n, scene in enumerate(scenes):
        if not isinstance(scene, dict):
            error(f"scenes[{n}] must be object")
            continue
        sid = scene.get("id")
        if not isinstance(sid, str) or not sid or sid in scene_by_id:
            error(f"scenes[{n}] requires unique id")
        else:
            scene_by_id[sid] = scene
        begin, end = scene.get("start_frame"), scene.get("end_frame")
        if not isinstance(begin, int) or not isinstance(end, int) or begin != previous or end <= begin:
            error(f"scenes[{n}] invalid continuity, expected start {previous}")
        if isinstance(end, int):
            previous = end
        for field in ("source_facts", "dramatization", "dramatization_label",
                      "dramatic_change", "continuity_lock", "axis"):
            if not isinstance(scene.get(field), str) or not scene.get(field):
                error(f"scenes[{n}].{field} missing")
        if not isinstance(scene.get("unknowns"), list) or not scene["unknowns"]:
            error(f"scenes[{n}].unknowns missing")
        if not isinstance(scene.get("attributed_interpretations"), list):
            error(f"scenes[{n}].attributed_interpretations must be array")
        links = scene.get("source_links")
        if not isinstance(links, list) or not links or not all(isinstance(u, str) and u.startswith("https://") for u in links):
            error(f"scenes[{n}].source_links missing HTTPS evidence")
    if previous != total:
        error(f"Scene plan ends at frame {previous} instead of {total}")
    previous = 0
    ids = set()
    per_scene = {sid: [] for sid in scene_by_id}
    for n, shot in enumerate(shots):
        if not isinstance(shot, dict):
            error(f"shots[{n}] must be object")
            continue
        shot_id = shot.get("id")
        if not isinstance(shot_id, str) or not shot_id or shot_id in ids:
            error(f"shots[{n}] requires unique id")
        ids.add(shot_id)
        begin, end, duration = shot.get("start_frame"), shot.get("end_frame"), shot.get("duration_frames")
        if not isinstance(begin, int) or not isinstance(end, int) or begin != previous or end <= begin:
            error(f"shots[{n}] invalid continuity, expected start {previous}")
        if not valid_positive_int(duration) or (isinstance(begin, int) and isinstance(end, int) and end-begin != duration):
            error(f"shots[{n}] invalid duration_frames")
        if isinstance(end, int):
            previous = end
        sid = shot.get("scene_id")
        if sid not in scene_by_id:
            error(f"shots[{n}] references absent scene {sid}")
        else:
            scene = scene_by_id[sid]
            if isinstance(begin, int) and isinstance(end, int):
                if begin < scene["start_frame"] or end > scene["end_frame"]:
                    error(f"shots[{n}] crosses scene boundary")
            per_scene[sid].append(shot)
        if shot.get("source_status") not in ALLOWED_STATUSES:
            error(f"shots[{n}] lacks source-status label")
        if not isinstance(shot.get("dramatic_purpose"), str) or not shot["dramatic_purpose"]:
            error(f"shots[{n}] lacks purpose")
        if not isinstance(shot.get("camera_axis"), str) or not shot["camera_axis"]:
            error(f"shots[{n}] lacks camera-axis lock")
        if shot.get("original_illustration_required") is not True or shot.get("asset_ready") is not False:
            error(f"shots[{n}]: original planned illustration is NOT an actual asset")
        if shot.get("motion") != "locked":
            error(f"shots[{n}]: draft must not animate without approved reasons")
    if previous != total:
        error(f"Shot plan ends at frame {previous} instead of {total}")
    for sid, group in per_scene.items():
        if not group:
            error("No shots for scene "+sid)
        if group and group[0].get("start_frame") != scene_by_id[sid]["start_frame"]:
            error("Scene shot pack starts late: "+sid)
        if group and group[-1].get("end_frame") != scene_by_id[sid]["end_frame"]:
            error("Scene shot pack ends early: "+sid)
    # The only enacted historical conversation in this proof uses a true scene pack,
    # never five crops from one illustration.
    if not (4 <= len(per_scene.get("S04", [])) <= 7):
        error("S04 Rabban Gamliel sons' dramatic scene needs 4–7 planned ORIGINAL images")
    if len(shots) != 16 or len(scenes) != 5:
        error("Pilot version 1 expects five scenes and sixteen independent shot plans")
    blockers = [
        "Exact Mishnah edition not locked or approved by human Torah reviewer",
        "No approved original illustration, voice, pronunciation, caption or audio",
        "Production budget and publication authorization not granted",
    ]
    return {"valid": not errors,
            "status": "EDITORIAL_PLAN_VALID_BUT_BLOCKED" if not errors else "INVALID",
            "errors": errors, "blockers": blockers,
            "duration_frames": total, "duration_seconds": total/fps,
            "scene_count": len(scenes), "shot_count": len(shots),
            "planned_original_images": sum(s.get("original_illustration_required") is True for s in shots if isinstance(s, dict)),
            "actual_generated_images": 0,
            "actual_rendered_videos": 0, "external_generation_calls": 0,
            "external_spend_authorized_usd": 0, "workspace_usage": "unknown"}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("blueprint", type=Path)
    parser.add_argument("--output", type=Path, default=Path("build/editorial-plan-review.json"))
    args = parser.parse_args()
    try:
        data = json.loads(args.blueprint.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        print("Cannot open blueprint:", type(exc).__name__, file=sys.stderr)
        return 2
    report = validate(data)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    print(f"{report['status']}: {report['scene_count']} scenes, {report['shot_count']} shots; {len(report['errors'])} errors")
    for problem in report["errors"] + report["blockers"]:
        print("- "+problem)
    return 0 if report["valid"] else 2


if __name__ == "__main__":
    sys.exit(main())
