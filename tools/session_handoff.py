#!/usr/bin/env python3
"""Conservative offline project-status + Codex handoff from repository declarations.

NO human source, voice, visual, film or licensing approval is inferred from
CI success. Nothing paid or generative is called.
"""
import argparse
import json
from pathlib import Path


def load(path):
    try:
        with path.open(encoding="utf-8") as stream:
            data = json.load(stream)
        if not isinstance(data, dict):
            raise ValueError("Expected JSON object")
        return data
    except (OSError, ValueError, UnicodeError) as exc:
        raise ValueError(f"Cannot read {path}: {exc}") from exc


def flag(obj, *keys):
    for key in keys:
        if not isinstance(obj, dict):
            return False
        obj = obj.get(key)
    return obj is True


def in_checkout(root, name):
    if not isinstance(name, str) or not name.strip():
        return False
    path = Path(name)
    if path.is_absolute() or ".." in path.parts:
        return False
    candidate = (root / path).resolve()
    try:
        candidate.relative_to(root)
    except ValueError:
        return False
    return candidate.is_file()


def audit(root, manifest_path, voice_path):
    root = Path(root).resolve()
    m, v = load(Path(manifest_path)), load(Path(voice_path))
    prod, src, art = m.get("production") or {}, m.get("sources") or {}, m.get("creative") or {}
    rel, cost = m.get("release") or {}, m.get("cost") or {}
    witnesses = src.get("independent_witnesses") or []
    witnessed = sum(x.get("checked") is True for x in witnesses if isinstance(x, dict)) if isinstance(witnesses, list) else 0
    master_ready = (
        isinstance(src.get("working_text"), str) and bool(src.get("working_text").strip())
        and witnessed >= 2 and flag(src, "text_verified") and flag(src, "textual_variants_reviewed")
        and flag(src, "rights_reviewed") and flag(src, "torah_review", "approved")
        and flag(src, "production_text_candidate", "text_locked")
    )
    segments = [x for x in v.get("segments", []) if isinstance(x, dict)]
    assets = [x for x in m.get("assets", []) if isinstance(x, dict)]
    shots = m.get("shots") or []
    n_voice = sum(in_checkout(root, x.get("audio_path")) for x in segments)
    n_assets = sum(in_checkout(root, x.get("path")) for x in assets)
    voice_files = bool(segments) and len(segments) == n_voice
    image_files = bool(assets) and len(assets) == n_assets
    gates = {
        "source_text_and_torah_review": bool(master_ready),
        "script_approved": flag(art, "script_approved"),
        "visual_direction_approved": flag(art, "visual_direction_approved"),
        "voice_approved": flag(art, "voice_approved"),
        "rehearsal_audio_files_present_in_checkout": voice_files,
        "shot_assets_present_in_checkout": image_files,
        "proof_approved": flag(art, "proof_approved"),
        "rights_cleared_for_release": flag(rel, "rights_cleared"),
        "technical_qa_passed": flag(rel, "technical_qa_passed"),
        "human_release_approved": flag(rel, "human_approval"),
    }
    all_ready = all(gates.values())
    errors = []
    # External user-provided proof is intentionally metadata only in this public repository.
    # A verified private trial is not an accepted production asset.
    trial_receipt = root / "episodes/berakhot-01-01/trials.json"
    verified_private_trials = []
    if trial_receipt.is_file():
        try:
            receipt = load(trial_receipt)
            listed = receipt.get("trials")
            if (receipt.get("schema_version") != 1 or
                    receipt.get("episode_id") != m.get("episode_id") or
                    not isinstance(listed, list)):
                raise ValueError("Trial receipt does not match episode/schema")
            seen = set()
            for trial in listed:
                if (not isinstance(trial, dict) or
                        not isinstance(trial.get("shot_id"), str) or
                        trial.get("shot_id") in seen or
                        trial.get("status") != "generated_unapproved" or
                        trial.get("production_asset_accepted") is not False or
                        not isinstance(trial.get("image_sha256"), str) or
                        len(trial["image_sha256"]) != 64):
                    raise ValueError("Malformed/unapproved trial record")
                seen.add(trial["shot_id"])
                verified_private_trials.append(trial["shot_id"])
        except ValueError:
            errors.append("PRIVATE_TRIAL_RECEIPT_INVALID")
            verified_private_trials = []
    if m.get("episode_id") != v.get("episode_id"):
        errors.append("VOICE_EPISODE_MISMATCH")
    if prod.get("fps") != v.get("fps") or prod.get("sample_rate") != v.get("sample_rate"):
        errors.append("VOICE_TIMING_STANDARD_MISMATCH")
    if prod.get("fps") != 24 or prod.get("sample_rate") != 48000:
        errors.append("UNEXPECTED_FRAME_OR_SAMPLE_RATE")
    if gates["voice_approved"] and not voice_files:
        errors.append("VOICE_APPROVED_BUT_NO_REHEARSAL_FILES")
    if gates["proof_approved"] and (not shots or not assets):
        errors.append("PROOF_APPROVED_BUT_NO_SHOTS_OR_ASSETS")
    if flag(prod, "release_authorized") and not all_ready:
        errors.append("RELEASE_AUTHORIZED_WITH_UNSATISFIED_GATES")
    if flag(cost, "external_spend_enabled") and (
        not isinstance(cost.get("max_external_usd"), (int, float)) or cost["max_external_usd"] <= 0
    ):
        errors.append("SPEND_ENABLED_WITHOUT_POSITIVE_BUDGET")
    for i, segment in enumerate(segments):
        name = segment.get("audio_path")
        if not isinstance(name, str) or Path(name).is_absolute() or ".." in Path(name).parts:
            errors.append(f"INVALID_VOICE_PATH_AT_{i}")
    blockers_he = {
        "source_text_and_torah_review": "נוסח, זכויות וביקורת תורנית טרם ננעלו",
        "script_approved": "התסריט עדיין טיוטה",
        "visual_direction_approved": "כיוון חזותי לא אושר",
        "voice_approved": "קולות והגייה לא אושרו",
        "rehearsal_audio_files_present_in_checkout": "אין את כל הקלטות הקריינות בקבצי העבודה",
        "shot_assets_present_in_checkout": "חסרים איורים מקוריים מאושרים",
        "proof_approved": "סרטון עלילתי ראשון לא עבר ביקורת",
        "rights_cleared_for_release": "זכויות הפצה לא הושלמו",
        "technical_qa_passed": "סרט מוגמר לא נבדק טכנית",
        "human_release_approved": "אין אישור אנושי לפרסום",
    }
    stage = ("sources" if not master_ready else
             "adaptation" if not gates["script_approved"] else
             "visuals" if not gates["visual_direction_approved"] else
             "assets" if not (voice_files and image_files and gates["voice_approved"]) else
             "assembly" if not gates["proof_approved"] else "review")
    return {
        "schema_version": 1,
        "episode_id": m.get("episode_id"),
        "scope": "Manifest declarations and checkout files; NOT independent Torah, listening, film or rights review.",
        "health": ("INCONSISTENT_DECLARATIONS" if errors else
                   "WORKFLOW_HEALTHY_RELEASE_BLOCKED" if not all_ready else
                   "DECLARATIONS_READY_FOR_SEPARATE_HUMAN_REVIEW"),
        "stage": stage,
        "gates": gates,
        "blockers": [blockers_he[k] for k, ok in gates.items() if not ok],
        "errors": errors,
        "evidence": {
            "witnesses_marked_checked": witnessed,
            "planned_voice_segments": len(segments),
            "voice_files_present_in_checkout": n_voice,
            "voice_files_missing_in_checkout": len(segments) - n_voice,
            "shots_in_canonical_manifest": len(shots),
            "declared_assets": len(assets),
            "asset_files_present_in_checkout": n_assets,
            "verified_private_trial_ids": verified_private_trials,
            "verified_private_image_trials": len(verified_private_trials),
        },
        "synthetic_test_disclaimer": "Synthetic tone/video validates only timing/encode, not real spoken Hebrew, lip-sync or film quality.",
        "codex_now": False,
        "codex_when": "A scoped multi-file coding task or blocking CI regression, not while choosing source wording or human voice.",
        "spend_authorized_usd": cost.get("max_external_usd", "unknown") if flag(cost, "external_spend_enabled") else 0,
        "workspace_usage": cost.get("workspace_usage", "unknown"),
    }


def as_markdown(a):
    e = a["evidence"]
    rows = [
        "# דוח מסירת סשן — אולפן המשנה",
        "",
        f"**מצב:** `{a['health']}` | **שלב:** `{a['stage']}`",
        "",
        "זהו ניתוח הצהרות וקבצים בצ'קאאוט. אינו אישור מחקר, זכויות, קריינות או סרט.",
        "",
        "## מה אומת כאן",
        f"- המניפסט מצהיר על {e['witnesses_marked_checked']} מקורות בדוקים; דוח זה **לא** השווה אותם בעצמו.",
        f"- {e['planned_voice_segments']} קטעי קול מתוכננים; {e['voice_files_present_in_checkout']} קבצים קיימים; {e['voice_files_missing_in_checkout']} חסרים בצ'קאאוט.",
        f"- {e['shots_in_canonical_manifest']} שוטים במניפסט, {e['declared_assets']} נכסים מוכרזים, {e['asset_files_present_in_checkout']} קובצי איורים קיימים.",
        f"- ניסויי GPU חיצוניים שאומתו בארכיון משתמש: {e['verified_private_image_trials']} ({', '.join(e['verified_private_trial_ids']) or 'אין'}). ניסיון שאומת אינו תמונה מאושרת להפקה; **אין לדרוש שוב ניסוי שכבר בוצע**.",
        "- מבחן צפצופים וקידוד, גם אם עברו ב-CI, **אינם** סרט עלילתי או אישור קול.",
        "",
        "## מה חסום",
    ]
    rows += [f"- {x}" for x in a["blockers"]]
    if a["errors"]:
        rows += ["", "## סתירות (CI צריך להיכשל)"]
        rows += [f"- `{x}`" for x in a["errors"]]
    rows += [
        "", "## הצעד הבא",
        "1. לסגור נוסח 'חייבין/מותרין', זכויות וביקורת תורנית; לא לפרסם או לייצר נוסח סופי קודם.",
        "2. אחרי נעילת המקור, לבחון 3 דגימות לכל קול בעברית ולמדוד בפועל מהירות, הגייה וסנכרון.",
        "3. לאחר אישור, להכין איורים מקוריים עקביים וסרטון הוכחה עלילתי 60–90 שניות.",
        "4. לצפות ולהאזין לסרטון עצמו בארבע בדיקות, ואז להחליט על המשך.",
        "", "## Codex וכלים",
        "- **Codex: לא נחוץ עכשיו.** להשתמש בו למשימת פיתוח מרובת קבצים/תיקון CI, FFmpeg, או חיבור קול ותמונה אחרי אישור; לא לביקורת תורנית אנושית.",
        "- GitHub Actions: בדיקות דטרמיניסטיות; קול טבעי: ספק TTS/הקלטה לאחר בדיקת איכות ועלות; GPU תמונות: ספק חיצוני רק אחרי שערי אישור.",
        "- [Codex בענן](https://chatgpt.com/codex) | [בדיקות GitHub](https://github.com/barkinam21-pixel/project-mishna/actions/workflows/studio-check.yml)",
        "", "## האם בר צריך לעשות משהו?",
        "- **לא כעת.** יבקשו ממנו רק החלטת אישור אמיתית או אישור הוצאה, בפעולה קצרה אחת.",
        "", "## חוזה סיום כל סשן",
        "- לסכם בקצרה מה עשינו; מה אומת; מה חסר/הבא; מתי Codex או תוכנות אחרות; והאם נדרשת פעולה של בר.",
        "",
    ]
    return "\n".join(rows)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parent.parent)
    p.add_argument("--manifest", default="episodes/berakhot-01-01/manifest.json")
    p.add_argument("--voice", default="episodes/berakhot-01-01/voice-rehearsal-draft.json")
    p.add_argument("--out-json", default="build/session-handoff.json")
    p.add_argument("--out-md", default="build/session-handoff.md")
    args = p.parse_args()
    root = args.repo_root.resolve()
    try:
        a = audit(root, root / args.manifest, root / args.voice)
    except ValueError as exc:
        print(f"HANDOFF_INPUT_ERROR: {exc}")
        return 2
    for rel, data in ((args.out_json, json.dumps(a, ensure_ascii=False, indent=2) + "\n"),
                      (args.out_md, as_markdown(a))):
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(data, encoding="utf-8")
    print(f"HANDOFF_STATUS={a['health']} stage={a['stage']} blockers={len(a['blockers'])} voice_missing={a['evidence']['voice_files_missing_in_checkout']}")
    return 2 if a["errors"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
