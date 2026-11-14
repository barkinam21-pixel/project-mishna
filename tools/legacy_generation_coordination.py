"""Bridge a VERIFIED legacy Issue54 OPN02/OPN03 ticket to M3's SQLite scene
reservation contract. All operations here are OFFLINE / fail closed.

Never treats the new SQLite Durable Object's OFFLINE reservation as permission
to call Cloudflare Workers AI. No network, Drive, provider, or secret access.
"""
import hashlib
import json
import re

from tools.chat_issue_bridge import RequestBlocked


def _digest(data):
    return hashlib.sha256(json.dumps(
        data, sort_keys=True, separators=(",", ":")
    ).encode()).hexdigest()


def legacy_offline_admission(ticket, history, *, scene_id="ACT1-PROLOGUE"):
    """Translate *validated* legacy ticket, never a raw Issue body.

    An existing validated one-shot ticket still needs 6+ saved attempts to
    enter the new M3 coordinator. No changed history, replay, over-limit shot,
    or paid ticket may be used for this conversion.
    """
    if not isinstance(ticket, dict) or ticket.get("status") != "ONE_SHOT_TICKET_VALIDATED_NOT_SUBMITTED":
        raise RequestBlocked("M3_HANDOFF_OWNER_TICKET_NOT_VALIDATED")
    if not re.fullmatch("[A-Z0-9][A-Z0-9-]{2,79}", str(scene_id)):
        raise RequestBlocked("M3_HANDOFF_SCENE_ID_INVALID")
    if not isinstance(history, dict) or type(history.get("attempts")) is not list:
        raise RequestBlocked("M3_HANDOFF_HISTORY_INVALID")
    attempts = history["attempts"]
    if (len(attempts) < 6 or type(ticket.get("historical_attempts")) is not int
        or ticket["historical_attempts"] != len(attempts)
        or ticket.get("history_sha256") != _digest(history)):
        raise RequestBlocked("M3_HANDOFF_PRIVATE_HISTORY_MISMATCH")
    if (ticket.get("max_charge_usd") != 0
        or type(ticket.get("max_charge_usd")) not in (int, float)
        or type(ticket.get("total_attempt_limit")) is not int
        or ticket["total_attempt_limit"] != len(attempts) + 1):
        raise RequestBlocked("M3_HANDOFF_NOT_EXACT_ZERO_COST_ONE_SHOT")
    rid, shot, spec = (ticket.get("request_id"), ticket.get("shot_id"),
                       ticket.get("spec_sha256"))
    if (not isinstance(rid, str) or not re.fullmatch("[a-f0-9]{32}", rid)
        or shot not in ("OPN02", "OPN03")
        or not isinstance(spec, str) or not re.fullmatch("[a-f0-9]{64}", spec)):
        raise RequestBlocked("M3_HANDOFF_UNSUPPORTED_SHOT_OR_SPEC")
    if any(isinstance(a, dict) and a.get("request_id") == rid for a in attempts):
        raise RequestBlocked("M3_HANDOFF_ALREADY_RESERVED_NO_RETRY")
    return {
        "status": "OFFLINE_TICKET_CHECKED_NO_LIVE_DISPATCH",
        "scene_id": scene_id, "request_id": rid,
        "shot_ids": [shot], "max_attempts": 1,
        "max_charge_usd": 0,
        "historical_attempts": len(attempts),
        "history_sha256": ticket["history_sha256"],
        "total_attempt_limit": len(attempts) + 1,
        "asset_keys": {shot: spec},
        "live_dispatch_enabled": False,
    }


def stage_offline_reservation(ticket, history, coordinator):
    """ONLY used in isolated staging. It consumes an OFFLINE fake reservation.

    Real production MUST NOT call this function and proceed with a provider
    request. An offline reservation is *never* a live dispatch permit.
    """
    admission = legacy_offline_admission(ticket, history)
    if coordinator is None:
        raise RequestBlocked("M3_OFFLINE_COORDINATOR_UNAVAILABLE")
    begun = coordinator.begin_offline(admission)
    if (not isinstance(begun, dict)
        or begun.get("status") != "OFFLINE_READY"
        or begun.get("replay") is not False
        or begun.get("live_dispatch_enabled") is not False):
        raise RequestBlocked("M3_OFFLINE_BEGIN_NOT_FRESH")
    reservation = coordinator.reserve_offline(
        admission["request_id"], admission["shot_ids"][0]
    )
    if (not isinstance(reservation, dict)
        or reservation.get("status") != "OFFLINE_RESERVED_UNCERTAIN_NO_RETRY"
        or reservation.get("live_dispatch_enabled") is not False
        or reservation.get("external_inference_requests") != 0):
        raise RequestBlocked("M3_OFFLINE_RESERVATION_UNVERIFIED")
    return {
        "status": "M3_LEGACY_TICKET_RESERVED_OFFLINE_ONLY",
        "scene_id": admission["scene_id"],
        "request_id": admission["request_id"],
        "shot_id": admission["shot_ids"][0],
        "historical_attempts": admission["historical_attempts"],
        "new_offline_reservations": 1,
        "external_inference_requests": 0,
        "live_dispatch_enabled": False,
        "provider_submission_authorized": False,
    }
