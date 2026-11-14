"""M3 owner-scoped scene ticket validator. PURE/OFFLINE: never dispatches.

The existing Issue54 provider bridge only understands OPN02/OPN03 one-shots.
This module validates an immutable multi-shot envelope and stage-specific
readiness without changing or weakening that live bridge. It must not be
treated as a production ticket runner until remote reservation and live
provider/Drive integration are separately reviewed and proven.
"""
import datetime as dt
import hashlib
import json
import re
from tools.scene_factory import SceneBlocked, validate, digest, keys

EXPECTED_REPO = "barkinam21-pixel/project-mishna"
EXPECTED_OWNER = "barkinam21-pixel"
EXPECTED_ISSUE = 54
OWNER_PHRASE = "APPROVE_SCENE_ZERO_CHARGE_EXACT_SCOPE_V1"
BLOCK = re.compile(r"^```mishnah-scene-request\n([^\`]{1,16384})\n```[ \t]*$", re.M)
FIELDS = {
    "version", "request_id", "scene_id", "script_sha256", "bible_sha256",
    "shot_ids", "asset_keys", "issued_at", "approval",
    "max_attempts", "max_charge_usd", "history_sha256",
    "historical_attempts", "total_attempt_limit",
}


def _unique(pairs):
    result = {}
    for k, v in pairs:
        if k in result:
            raise SceneBlocked("M3_DUPLICATE_TICKET_FIELD")
        result[k] = v
    return result


def _date(value):
    if not isinstance(value, str):
        raise SceneBlocked("M3_TIME_INVALID")
    try:
        d = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
        if d.tzinfo is None:
            raise ValueError()
        return d.astimezone(dt.timezone.utc)
    except (ValueError, TypeError):
        raise SceneBlocked("M3_TIME_INVALID") from None


def _history_digest(history):
    return hashlib.sha256(json.dumps(history, sort_keys=True,
                                     separators=(",", ":")).encode()).hexdigest()


def _stage_issues(scene, bible, root):
    """Allow only clean, not-yet-produced assets and draft audio spotting.

    All script/source, era, image mismatch, license violations on existing
    audio, editorial and continuity issues remain hard blockers.
    """
    original = validate(scene, bible, root)
    by_id = {s["id"]: s for s in scene["shots"]}
    waived = []
    blocked = []
    for issue in original:
        if issue.startswith("ASSET_NOT_APPROVED:"):
            shot = by_id.get(issue.split(":", 1)[1])
            a = shot["asset"] if shot else {}
            if (a.get("origin") == "missing" and a.get("accepted") is False
                and a.get("path") is None and a.get("sha256") is None
                and a.get("state") is None):
                waived.append(issue)
                continue
        if issue.startswith("SOUND_MISSING_OR_UNLICENSED:"):
            cue_id = issue.split(":", 1)[1]
            cue = next((c for s in scene["shots"] for c in s["sound"]
                        if c["id"] == cue_id), {})
            if cue.get("kind") == "spotting draft" and cue.get("path") is None:
                waived.append(issue)
                continue
        blocked.append(issue)
    return sorted(set(blocked)), sorted(set(waived))


def verify(event, policy, history, scene, bible, root, *, now=None):
    """Validate scope against trusted repo event, policy, history and scene.

    Output is OFFLINE_TICKET_CHECKED_NO_LIVE_DISPATCH, never an executable
    provider authorization. A separate distributed journal gate is mandatory.
    """
    now = now or dt.datetime.now(dt.timezone.utc)
    if now.tzinfo is None:
        raise SceneBlocked("M3_TIME_INVALID")
    now = now.astimezone(dt.timezone.utc)
    if (event.get("action") != "edited"
        or event.get("sender", {}).get("login") != EXPECTED_OWNER
        or event.get("repository", {}).get("full_name") != EXPECTED_REPO
        or event.get("repository", {}).get("owner", {}).get("login") != EXPECTED_OWNER):
        raise SceneBlocked("M3_TRUSTED_OWNER_EVENT_REQUIRED")
    issue = event.get("issue", {})
    if (type(issue.get("number")) is not int or issue["number"] != EXPECTED_ISSUE
        or issue.get("state") != "open" or "pull_request" in issue):
        raise SceneBlocked("M3_OWNER_ISSUE_REQUIRED")
    body = issue.get("body", "")
    if not isinstance(body, str) or len(body) > 65536:
        raise SceneBlocked("M3_ISSUE_BODY_INVALID")
    blocks = BLOCK.findall(body)
    if len(blocks) != 1:
        raise SceneBlocked("M3_EXACTLY_ONE_SCENE_TICKET_REQUIRED")
    try:
        ticket = json.loads(blocks[0], object_pairs_hook=_unique)
    except SceneBlocked:
        raise
    except (ValueError, TypeError):
        raise SceneBlocked("M3_TICKET_JSON_INVALID") from None
    if not isinstance(ticket, dict) or set(ticket) != FIELDS:
        raise SceneBlocked("M3_TICKET_FIELDS_INVALID")
    if (type(ticket["version"]) is not int or ticket["version"] != 1
        or ticket["approval"] != OWNER_PHRASE):
        raise SceneBlocked("M3_EXPLICIT_SCOPED_APPROVAL_REQUIRED")
    if (not isinstance(ticket["request_id"], str)
        or not re.fullmatch("[a-f0-9]{32}", ticket["request_id"])):
        raise SceneBlocked("M3_REQUEST_ID_INVALID")
    previous = event.get("changes", {}).get("body", {}).get("from")
    if not isinstance(previous, str) or ticket["request_id"] in previous:
        raise SceneBlocked("M3_NOT_A_FRESH_OWNER_EDIT")
    if not -60 <= (now - _date(ticket["issued_at"])).total_seconds() <= 900:
        raise SceneBlocked("M3_TICKET_EXPIRED")
    if not isinstance(policy, dict) or not all(
        policy.get(k) is True
        for k in ("privacy_verified", "free_hard_cap_verified", "quota_verified")
    ):
        raise SceneBlocked("M3_FREE_PRIVACY_QUOTA_NOT_VERIFIED")
    verified_time = _date(policy.get("verified_at"))
    if not 0 <= (now - verified_time).total_seconds() <= 900:
        raise SceneBlocked("M3_SAFETY_EVIDENCE_STALE")
    if ticket["scene_id"] != scene["id"]:
        raise SceneBlocked("M3_SCENE_ID_CHANGED")
    if (ticket["script_sha256"] != scene["script"]["sha256"]
        or ticket["bible_sha256"] != digest(bible)
        or scene["bible"]["sha256"] != digest(bible)):
        raise SceneBlocked("M3_SOURCE_OR_BIBLE_CHANGED")
    # M1's production switch is intentionally false. The only future
    # authorization is a freshly verified ticket + separate live engine gate.
    if (scene["authorization"].get("generation_approved") is not False
        or scene["authorization"].get("budget_usd") != 0):
        raise SceneBlocked("M3_M1_PRODUCTION_SWITCH_MUST_STAY_CLOSED")
    from tools.scene_m3 import selection
    shot_ids = selection(scene, ticket["shot_ids"])
    if (type(ticket["max_attempts"]) is not int
        or ticket["max_attempts"] < 1
        or ticket["max_attempts"] > len(shot_ids)):
        raise SceneBlocked("M3_ATTEMPT_LIMIT_INVALID")
    if type(ticket["max_charge_usd"]) not in (int, float) or ticket["max_charge_usd"] != 0:
        raise SceneBlocked("M3_ZERO_CHARGE_ONLY")
    expected = {x: keys(scene, bible)["asset_keys"][x] for x in shot_ids}
    if type(ticket["asset_keys"]) is not dict or ticket["asset_keys"] != expected:
        raise SceneBlocked("M3_IMAGE_SPEC_CHANGED")
    by_id = {x["id"]: x for x in scene["shots"]}
    for shot_id in shot_ids:
        asset = by_id[shot_id]["asset"]
        if (asset["origin"] != "missing" or asset["accepted"] is not False
            or asset["state"] is not None or asset["path"] is not None):
            raise SceneBlocked("M3_SELECTED_SHOT_ALREADY_HAS_ART:"+shot_id)
    if (not isinstance(history, dict) or type(history.get("attempts")) is not list
        or len(history["attempts"]) < 6
        or any(not isinstance(x, dict) for x in history["attempts"])):
        raise SceneBlocked("M3_PRIOR_HISTORY_INVALID")
    if (ticket["history_sha256"] != _history_digest(history)
        or type(ticket["historical_attempts"]) is not int
        or ticket["historical_attempts"] != len(history["attempts"])):
        raise SceneBlocked("M3_PRIVATE_JOURNAL_CHANGED")
    if (type(ticket["total_attempt_limit"]) is not int
        or ticket["total_attempt_limit"] != len(history["attempts"]) + ticket["max_attempts"]):
        raise SceneBlocked("M3_TOTAL_ATTEMPT_LIMIT_INVALID")
    if any(x.get("request_id") == ticket["request_id"] for x in history["attempts"]):
        raise SceneBlocked("M3_ATTEMPT_ALREADY_RESERVED_NO_RETRY")
    blocking, waived = _stage_issues(scene, bible, root)
    if blocking:
        return {"status": "BLOCKED", "issues": blocking, "waived_draft_only": waived,
                "external_inference_requests": 0, "live_dispatch_enabled": False}
    return {
        "status": "OFFLINE_TICKET_CHECKED_NO_LIVE_DISPATCH",
        "scene_id": scene["id"], "request_id": ticket["request_id"],
        "shot_ids": shot_ids, "max_attempts": ticket["max_attempts"],
        "max_charge_usd": 0, "historical_attempts": len(history["attempts"]),
        "history_sha256": ticket["history_sha256"],
        "total_attempt_limit": ticket["total_attempt_limit"],
        "asset_keys": expected, "waived_draft_only": waived,
        "external_inference_requests": 0,
        "live_dispatch_enabled": False,
        "requires_next": "REMOTE_ATOMIC_JOURNAL_AND_EXISTING_ONE_SHOT_PROVIDER_GATE",
    }
