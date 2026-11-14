"""Scene-native EP-P blocking and character visibility, not old OPN sunset controls.

Pure, offline authoring validator. This module never imports the pinned image
engine, performs inference, reads private media, or approves a shot. A draft
blocking map is *not* an assertion that the proposed composition is historical.
"""
import re

from tools.scene_factory import SceneBlocked

SHOT_ID = re.compile(r"^EP-P(0[1-9]|1[0-5])$")
SHA = re.compile(r"^[0-9a-f]{64}$")
BLOCKING_FIELDS = {
    "review_status", "shot_id", "cast_visible", "positions", "axis",
    "camera_side", "screen_direction", "sun_direction", "time_of_day",
    "shot_type", "composition", "human_detail_unattributed", "source_anchor",
}
POSITION_VALUES = {
    "screen-left", "screen-right", "center", "foreground-left",
    "foreground-right", "background-left", "background-right",
}
SHOT_TYPES = {"extreme_wide", "wide", "medium", "ots", "reaction", "insert", "close_up"}


def compile_native_direction(shot, state):
    """Validate explicit per-shot staging against the authoritative state.

    Do not infer cast presence from a shared character bible: that dictionary
    names characters in the *scene*, not necessarily in any given frame.
    """
    sid = shot.get("id")
    if not isinstance(sid, str) or not SHOT_ID.fullmatch(sid):
        raise SceneBlocked("NATIVE_EP_SHOT_ID_INVALID")
    b = shot.get("blocking")
    if not isinstance(b, dict) or set(b) != BLOCKING_FIELDS:
        raise SceneBlocked("NATIVE_BLOCKING_SCHEMA_INVALID:" + sid)
    if b["shot_id"] != sid or b["review_status"] != "DRAFT_REQUIRES_REVIEW":
        raise SceneBlocked("NATIVE_BLOCKING_SCOPE_OR_APPROVAL_INVALID:" + sid)
    expected_anchor = "docs/epic-intro-prologue-shotmap-v02.md#P" + sid[-2:]
    if b["source_anchor"] != expected_anchor:
        raise SceneBlocked("NATIVE_SHOT_SOURCE_ANCHOR_INVALID:" + sid)
    if (b["axis"] != state.get("axis")
        or b["screen_direction"] != state.get("screen_direction")
        or b["sun_direction"] != state.get("sun_direction")
        or b["time_of_day"] != state.get("time_of_day")):
        raise SceneBlocked("NATIVE_AXIS_OR_DAYLIGHT_CONFLICT:" + sid)
    if not isinstance(b["axis"], str) or not b["axis"].startswith(b["camera_side"] + " side"):
        raise SceneBlocked("NATIVE_CAMERA_SIDE_CROSSES_AXIS:" + sid)
    if b["shot_type"] not in SHOT_TYPES or not isinstance(b["composition"], str) or not b["composition"].strip():
        raise SceneBlocked("NATIVE_CAMERA_COMPOSITION_INVALID:" + sid)
    cast = b["cast_visible"]
    if not isinstance(cast, list) or len(set(map(str, cast))) != len(cast):
        raise SceneBlocked("NATIVE_CAST_VISIBILITY_INVALID:" + sid)
    if any(not isinstance(name, str) or name not in state.get("characters", {}) for name in cast):
        raise SceneBlocked("NATIVE_CAST_NOT_IN_BIBLE:" + sid)
    positions = b["positions"]
    if (not isinstance(positions, dict) or set(positions) != set(cast)
        or any(v not in POSITION_VALUES for v in positions.values())):
        raise SceneBlocked("NATIVE_CAST_POSITION_INVALID:" + sid)
    if (type(b["human_detail_unattributed"]) is not bool
        or (cast and b["human_detail_unattributed"])):
        raise SceneBlocked("NATIVE_UNATTRIBUTED_DETAIL_INVALID:" + sid)
    # The same named actor cannot occupy two places; the reverse is allowed in
    # long-distance views but must remain draft until a human reviews the frame.
    characters = {}
    for name in cast:
        c = state["characters"][name]
        if not isinstance(c.get("reference_sha256"), str) or not SHA.fullmatch(c["reference_sha256"]):
            raise SceneBlocked("NATIVE_CHARACTER_REFERENCE_ID_INVALID:" + sid)
        characters[name] = {
            "description": (
                c["face_lock"] + "; age " + c["age"] +
                "; proportions " + c["proportions"] +
                "; costume " + c["costume"] +
                "; frame position " + positions[name]
            ),
            # No per-actor private reference rights/role has been established.
            # Do NOT take the legacy global image references as actor consent.
            "references": [],
            "reference_sha256": c["reference_sha256"],
        }
    return {
        "scene_native_schema": 1,
        "scene_shot_id": sid,
        "review_status": b["review_status"],
        "cast_visible": list(cast),
        "characters": characters,
        "positions": dict(positions),
        "axis": b["axis"],
        "camera_side": b["camera_side"],
        "screen_direction": b["screen_direction"],
        "sun_direction": b["sun_direction"],
        "time_of_day": b["time_of_day"],
        "shot_type": b["shot_type"],
        "composition": b["composition"],
        "human_detail_unattributed": b["human_detail_unattributed"],
        "source_anchor": b["source_anchor"],
    }
