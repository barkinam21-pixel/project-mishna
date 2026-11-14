"""Read-only creative crosswalk audit: literary script vs editorial shotmap vs M1 scene manifest.

Does NOT approve the scene or modify authoritative script. Any disagreement
remains a human editorial gate. This auditor is deterministic and offline.
"""
import argparse
import json
import re
import sys
from pathlib import Path

from tools.scene_factory import SceneBlocked, load, within

SCENE_MANIFEST = "episodes/berakhot-01-01/scene-prologue-v02.json"
LITERARY = "scripts/episode-01-before-dawn.md"
SHOTMAP = "docs/epic-intro-prologue-shotmap-v02.md"
CHRONOLOGY = "docs/epic-intro-directing-contract.md"

_ROW = re.compile(
    r"^\|\s*(EP-P\d{2})\s*\|\s*(\d+)\s*[–-]\s*(\d+)\s*ש[׳']\s*\|",
    re.M,
)
_SEQUENCE = re.compile(r"^### רצף 1\b", re.M)
_SEQUENCE_END = re.compile(r"^### רצף 2\b", re.M)


def _read(root, path):
    return within(root, path).read_text(encoding="utf-8")


def analyze(root):
    root = Path(root).resolve()
    scene = load(within(root, SCENE_MANIFEST))
    if scene["id"] != "ACT1-PROLOGUE":
        raise SceneBlocked("CROSSWALK_SCENE_CHANGED")
    literary = _read(root, LITERARY)
    shotmap = _read(root, SHOTMAP)
    contract = _read(root, CHRONOLOGY)
    m = list(_ROW.finditer(shotmap))
    if len(m) != 15 or len({x.group(1) for x in m}) != 15:
        raise SceneBlocked("CROSSWALK_EXPECTED_15_UNIQUE_SHOTS")
    rows = [
        {"id": x.group(1), "start_sec": int(x.group(2)),
         "end_sec": int(x.group(3))}
        for x in m
    ]
    issues = []
    shots = scene["shots"]
    if len(shots) != len(rows):
        issues.append("SHOT_COUNT_DIFFERS_FROM_SHOTMAP")
    for i, row in enumerate(rows):
        if i >= len(shots):
            issues.append("SHOT_MISSING_IN_MANIFEST:" + row["id"])
            continue
        shot = shots[i]
        if shot["id"] != row["id"]:
            issues.append("SHOT_ID_ORDER_MISMATCH:" + row["id"])
        if shot["start_frame"] != row["start_sec"] * 24:
            issues.append("SHOT_START_FRAME_MISMATCH:" + row["id"])
        if shot["end_frame"] != row["end_sec"] * 24:
            issues.append("SHOT_END_FRAME_MISMATCH:" + row["id"])
        if (i and row["start_sec"] != rows[i-1]["end_sec"]):
            issues.append("SHOTMAP_TIME_GAP:" + row["id"])
    begin = _SEQUENCE.search(literary)
    end = _SEQUENCE_END.search(literary)
    if not begin or not end or end.start() <= begin.end():
        raise SceneBlocked("CROSSWALK_LITERARY_SEQUENCE_MISSING")
    seq = literary[begin.end():end.start()]
    script_early_narrator = bool(re.search(r"\[קריין[,\]]", seq))
    scene_voice = str(scene["script"].get("voice_entry", ""))
    shotmap_delayed_narrator = (
        "קריין יכול להיכנס **רק כאן**" in shotmap
        and "EP-P15" in shotmap
    )
    if script_early_narrator and shotmap_delayed_narrator:
        issues.append("EDITORIAL_NARRATION_ENTRY_CONFLICT")
    if not scene["script"].get("approved"):
        issues.append("LITERARY_SCRIPT_NOT_LOCKED")
    if "35 דקות" not in contract or "6 מערכות" not in contract:
        issues.append("SIX_ACT_DIRECTING_SCOPE_UNVERIFIED")
    if "DRAFT — לא מקור נעול" not in literary:
        issues.append("LITERARY_DRAFT_MARKER_CHANGED_REVIEW")
    if "תכנון בלבד" not in shotmap:
        issues.append("SHOTMAP_DRAFT_MARKER_CHANGED_REVIEW")
    if "unresolved" not in scene_voice:
        issues.append("VOICE_STATE_NOT_EXPLICITLY_PENDING")
    # 45-second original literary sequence and 91-second revised shotmap are
    # *not* silently equivalent; passing frame parity doesn't resolve pacing.
    if "0:00–0:45" in literary and rows[-1]["end_sec"] == 91:
        issues.append("LITERARY_45S_VS_SHOTMAP_91S_TIMING_REVIEW")
    if any(s["asset"].get("state") == "SUNSET_CANDIDATE" for s in shots):
        issues.append("DAWN_SCRIPT_VS_SUNSET_ASSET_CANDIDATES")
    if any(s["source"].get("verified") is not True for s in shots):
        issues.append("SOURCE_LINKAGE_NOT_APPROVED")
    if len({s["script_span"][0] for s in shots}) == 1 and len(shots) > 1:
        issues.append("ALL_SHOTS_USE_GENERIC_SCRIPT_SPAN_REVIEW")
    return {
        "status": "EDITORIAL_REVIEW_REQUIRED" if issues else "CROSSWALK_STRUCTURALLY_MATCHED_NOT_RELEASED",
        "scene_id": scene["id"],
        "literary_script": LITERARY, "shotmap": SHOTMAP,
        "scene_manifest": SCENE_MANIFEST,
        "shot_count": len(rows), "shotmap_duration_sec": rows[-1]["end_sec"],
        "shot_ids": [r["id"] for r in rows],
        "issues": sorted(set(issues)),
        "structural_issues": [
            x for x in issues if x.startswith(("SHOT_", "SHOTMAP_"))
        ],
        "suggested_approach_he": (
            "הצעה בלבד: לשמור את 15 השוטים כטיוטת בימוי, לבחור במפורש "
            "את מיקום כניסת הקריין ואת האורך אחרי בדיקת קריינות; "
            "להשאיר אור שחר לפי התסריט או לכתוב מעבר מבוקר, ולא "
            "להכניס אוטומטית תמונות שקיעה שלא אושרו."
        ),
        "inference_requests": 0,
        "generation_authorized": False,
        "approval_promoted": False,
    }


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("--root", default=".")
    args = p.parse_args(argv)
    try:
        result = analyze(args.root)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 2 if result["issues"] else 0
    except (OSError, KeyError, ValueError, TypeError) as ex:
        print(json.dumps({
            "status": "BLOCKED", "reason": str(ex) if isinstance(ex, SceneBlocked)
            else type(ex).__name__,
            "generation_authorized": False, "inference_requests": 0,
        }, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    sys.exit(main())
