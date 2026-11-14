"""Lossless, fail-closed cinematic scene blocker triage (OFFLINE/READ-ONLY).

Never infer approvals from counts; classify every M1 finding, preserve full IDs,
and make the next safe phase clear. Unknown findings remain critical rather
than disappearing from a report. No images, voices, media, provider or Drive IO.
"""
import argparse
import json
import sys
from pathlib import Path
from tools.scene_factory import SceneBlocked, load, validate, within

ORDER = (
    "SCRIPT_AND_EDITORIAL",
    "SOURCES_AND_CHRONOLOGY",
    "VISUAL_CONTINUITY",
    "SHOT_LANGUAGE_AND_TIMING",
    "VISUAL_ASSETS",
    "VOICE_AUDIO_AND_RIGHTS",
    "HEBREW_CAPTIONS",
    "UNCLASSIFIED_CRITICAL",
)

CATEGORY_PREFIXES = (
    ("SCRIPT_AND_EDITORIAL", (
        "SCRIPT_", "BIBLE_HASH_", "EDITORIAL_DECISION_", "CAPTION_NOT_IN_LOCKED_SCRIPT",
    )),
    ("SOURCES_AND_CHRONOLOGY", (
        "SOURCE_", "INVENTED_SOURCE_", "CHRONOLOGY_", "SYMBOLIC_EVENT_",
    )),
    ("VISUAL_CONTINUITY", (
        "ASSET_CONTINUITY_", "CONTINUITY_", "WITHIN_SHOT_",
        "CHARACTER_LOCK_", "CHARACTER_BIBLE_",
    )),
    ("SHOT_LANGUAGE_AND_TIMING", (
        "SHOT_", "FRAME_", "CAMERA_", "SCRIPT_SPAN_",
    )),
    ("VISUAL_ASSETS", (
        "ASSET_", "IMAGE_", "VISUAL_",
    )),
    ("VOICE_AUDIO_AND_RIGHTS", (
        "SOUND_", "VOICE_", "MUSIC_", "AUDIO_", "LICENSE_",
    )),
    ("HEBREW_CAPTIONS", (
        "CAPTION_", "SUBTITLE_",
    )),
)

ACTIONS_HEBREW = {
    "SCRIPT_AND_EDITORIAL": "להכריע ולנעול תסריט, כניסת קריינות ומיפוי הסצנות",
    "SOURCES_AND_CHRONOLOGY": "לבדוק מקורות, ייחוס היסטורי וסימון המחזה",
    "VISUAL_CONTINUITY": "ליישב שחר/שקיעה, דמויות, אביזרים ותנועת צילום",
    "SHOT_LANGUAGE_AND_TIMING": "לתקן סדר שוטים, תפקיד דרמטי ותזמון פריימים",
    "VISUAL_ASSETS": "להשלים רק נכסים מקוריים נדרשים לאחר אישורי הבטיחות",
    "VOICE_AUDIO_AND_RIGHTS": "לאשר ולהשלים קריינות, סאונד, זכויות ומיקס",
    "HEBREW_CAPTIONS": "לאמת כתוביות עבריות וסנכרון מול הנוסח המאושר",
    "UNCLASSIFIED_CRITICAL": "להוסיף בדיקת אבחון ייעודית; לא להתעלם מחסם לא מוכר",
}


def classify(issue):
    if not isinstance(issue, str) or not issue.strip():
        return "UNCLASSIFIED_CRITICAL"
    # More specific prefixes (e.g. ASSET_CONTINUITY) are ordered before ASSET.
    for category, prefixes in CATEGORY_PREFIXES:
        if issue.startswith(prefixes):
            return category
    return "UNCLASSIFIED_CRITICAL"


def summarize(issues, *, scene_id="UNKNOWN"):
    if not isinstance(issues, list) or not all(isinstance(x, str) for x in issues):
        raise SceneBlocked("SCENE_REPORT_INVALID_ISSUES")
    unique = sorted(set(issues))
    if len(unique) != len(issues):
        raise SceneBlocked("SCENE_REPORT_DUPLICATED_ISSUES")
    groups = {cat: [] for cat in ORDER}
    for issue in issues:
        groups[classify(issue)].append(issue)
    if sum(map(len, groups.values())) != len(issues):
        raise SceneBlocked("SCENE_REPORT_LOST_ISSUE")
    sections = [{
        "category": cat,
        "count": len(groups[cat]),
        "action_he": ACTIONS_HEBREW[cat],
        "issues": groups[cat],
    } for cat in ORDER if groups[cat]]
    counts = {s["category"]: s["count"] for s in sections}
    blockers = [
        "SCRIPT_AND_EDITORIAL", "SOURCES_AND_CHRONOLOGY",
        "VISUAL_CONTINUITY", "UNCLASSIFIED_CRITICAL",
    ]
    return {
        "status": "BLOCKED" if issues else "PREFLIGHT_NO_DECLARED_BLOCKERS_NOT_ART_APPROVAL",
        "scene_id": scene_id,
        "total_blockers": len(issues),
        "category_counts": counts,
        "critical_preproduction_blockers": sum(counts.get(k, 0) for k in blockers),
        "unclassified_critical_count": counts.get("UNCLASSIFIED_CRITICAL", 0),
        "next_actions_he": [x["action_he"] for x in sections],
        "sections": sections,
        "all_issue_ids": list(issues),
        "has_lost_findings": False,
        "live_generation_authorized": False,
        "media_art_approved": False,
        "external_inference_requests": 0,
    }


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--root", default=".")
    p.add_argument("--manifest", default="episodes/berakhot-01-01/scene-prologue-v02.json")
    args = p.parse_args(argv)
    try:
        root = Path(args.root).resolve()
        scene = load(within(root, args.manifest))
        bible = load(within(root, scene["bible"]["path"]))
        report = summarize(validate(scene, bible, root), scene_id=scene["id"])
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 2 if report["status"] == "BLOCKED" else 0
    except (OSError, TypeError, ValueError, KeyError) as exc:
        print(json.dumps({
            "status": "BLOCKED",
            "reason": str(exc) if isinstance(exc, SceneBlocked) else type(exc).__name__,
            "external_inference_requests": 0, "live_generation_authorized": False,
        }))
        return 2


if __name__ == "__main__":
    sys.exit(main())
