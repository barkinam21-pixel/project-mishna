"""M3 distributed-reservation protocol (OFFLINE mock, NO provider/Drive calls).

CRITICAL: Google Drive v3 media replacement has no established atomic CAS
contract for our existing adapter. It is NOT a CAS store. Production MUST NOT
instantiate this protocol with plain Drive.download + Drive.replace or a
read-before-write wrapper. An atomic version-conditional transport is required.

This module exercises a versioned journal protocol against an in-memory fake
whose compare-and-swap is genuinely atomic. Future production needs separate
review of the transport, end-to-end owner event, and pinned inference backend.
"""
import copy
import hashlib
import json
import re
import threading
from tools.scene_factory import SceneBlocked, digest


def history_sha256(journal):
    return hashlib.sha256(json.dumps(journal, sort_keys=True,
                  separators=(",", ":")).encode()).hexdigest()


def _history(journal):
    if (not isinstance(journal, dict) or not isinstance(journal.get("entries"), dict)
        or type(journal.get("attempts")) is not list
        or any(not isinstance(a, dict) or not isinstance(a.get("key"), str)
               or not a["key"] for a in journal["attempts"])):
        raise SceneBlocked("M3_REMOTE_JOURNAL_INVALID")
    return journal["attempts"]



def _verify_reserved_history(attempts, batch, mismatch_code="M3_REMOTE_HISTORY_CHANGED"):
    """Protect every reserved tail record, not just historical prefix and count."""
    n = batch["historical_attempts"]
    reserved = batch["reserved"]
    if (len(attempts) != n + len(reserved)
        or attempts[:n] != batch["historical_prefix"]):
        raise SceneBlocked(mismatch_code)
    for i, reservation in enumerate(reserved):
        shot_id = reservation["shot_id"]
        expected = {
            "key": reservation["idempotency_key"],
            "request_id": batch["request_id"],
            "shot_id": shot_id,
            "spec_sha256": reservation["spec_sha256"],
            "status": "RESERVED_SUBMISSION_UNCERTAIN_NO_RETRY",
        }
        if (attempts[n+i] != expected
            or shot_id not in batch["shot_ids"]
            or reservation["spec_sha256"] != batch["asset_keys"][shot_id]):
            raise SceneBlocked("M3_REMOTE_RESERVED_ATTEMPT_TAMPERED")


def _verify_batch_integrity(batch):
    """Fail closed on altered offline batch state, flags or mock receipts.

    This is corruption detection in an OFFLINE fake, not authentication of a
    remote writer and not proof that Drive supplies atomic CAS.
    """
    if (not isinstance(batch, dict)
        or batch.get("simulated_only") is not True
        or batch.get("live_dispatch_enabled") is not False
        or type(batch.get("external_inference_requests")) is not int
        or batch["external_inference_requests"] != 0):
        raise SceneBlocked("M3_REMOTE_BATCH_INTEGRITY_FAILURE")
    shots = batch.get("shot_ids")
    assets = batch.get("asset_keys")
    reserved = batch.get("reserved")
    receipts = batch.get("receipts")
    limit = batch.get("max_attempts")
    if (type(shots) is not list or not shots
        or any(not isinstance(s, str) or not s for s in shots)
        or len(shots) != len(set(shots))
        or type(assets) is not dict or set(assets) != set(shots)
        or type(reserved) is not list or type(receipts) is not dict
        or type(limit) is not int or not 1 <= limit <= len(shots)
        or len(reserved) > limit
        or not isinstance(batch.get("identity"), str)
        or not isinstance(batch.get("scene_id"), str)):
        raise SceneBlocked("M3_REMOTE_BATCH_INTEGRITY_FAILURE")
    for i, reservation in enumerate(reserved):
        shot = shots[i]
        spec = assets[shot]
        if (not isinstance(reservation, dict)
            or reservation.get("shot_id") != shot
            or reservation.get("spec_sha256") != spec
            or reservation.get("idempotency_key") != digest({
                "batch": batch["identity"], "shot_id": shot,
                "spec_sha256": spec
            })):
            raise SceneBlocked("M3_REMOTE_BATCH_INTEGRITY_FAILURE")
    reserved_ids = [r["shot_id"] for r in reserved]
    if any(shot not in reserved_ids for shot in receipts):
        raise SceneBlocked("M3_REMOTE_BATCH_INTEGRITY_FAILURE")
    for shot, receipt in receipts.items():
        expected_hash = hashlib.sha256((
            "M3_FAKE_IMAGE_V1:" + batch["scene_id"] + ":" + shot + ":" +
            assets[shot]
        ).encode()).hexdigest()
        if (type(receipt) is not dict
            or set(receipt) != {
                "kind", "sha256", "accepted", "provider_calls",
                "external_cost_usd"
            }
            or receipt["kind"] != "OFFLINE_FAKE_NOT_IMAGE"
            or receipt["sha256"] != expected_hash
            or receipt["accepted"] is not False
            or type(receipt["provider_calls"]) is not int
            or receipt["provider_calls"] != 0
            or type(receipt["external_cost_usd"]) not in (int, float)
            or receipt["external_cost_usd"] != 0):
            raise SceneBlocked("M3_REMOTE_BATCH_INTEGRITY_FAILURE")
    completed = len(receipts)
    pending = len(reserved) - completed
    if (pending not in (0, 1)
        or (pending and reserved[-1]["shot_id"] in receipts)):
        raise SceneBlocked("M3_REMOTE_BATCH_INTEGRITY_FAILURE")
    expected_status = ("READY" if not reserved else
                       "RESERVED_UNCERTAIN" if pending else
                       "SIMULATED_NOT_ART" if len(reserved) == limit else
                       "PARTIAL")
    if (batch.get("status") != expected_status
        and not (pending and batch.get("status") == "HALTED_UNCERTAIN")):
        raise SceneBlocked("M3_REMOTE_BATCH_INTEGRITY_FAILURE")


class AtomicMemoryJournal:
    """Concurrent-CAS test double. NEVER a remote transport."""
    atomic_compare_and_swap = True
    production_transport = False

    def __init__(self, original):
        _history(original)
        self._state = copy.deepcopy(original)
        self._version = 0
        self._lock = threading.Lock()
        self.writes = 0

    def read(self):
        with self._lock:
            return self._version, copy.deepcopy(self._state)

    def compare_and_swap(self, expected, new):
        _history(new)
        with self._lock:
            if expected != self._version:
                return False
            self._state = copy.deepcopy(new)
            self._version += 1
            self.writes += 1
            return True


class NoCASDriveAdapter:
    """Explicit safety stop for existing Drive v3 media replacement."""
    atomic_compare_and_swap = False
    production_transport = False

    def read(self):
        raise SceneBlocked("M3_DRIVE_V3_CAS_NOT_VERIFIED")

    def compare_and_swap(self, expected, new):
        raise SceneBlocked("M3_DRIVE_V3_CAS_NOT_VERIFIED")


def _scope(admission):
    required = (
        "status", "scene_id", "request_id", "shot_ids", "max_attempts",
        "max_charge_usd", "historical_attempts", "history_sha256",
        "total_attempt_limit", "asset_keys", "live_dispatch_enabled",
    )
    if not isinstance(admission, dict) or any(x not in admission for x in required):
        raise SceneBlocked("M3_REMOTE_INVALID_ADMISSION")
    if (admission["status"] != "OFFLINE_TICKET_CHECKED_NO_LIVE_DISPATCH"
        or admission["live_dispatch_enabled"] is not False
        or type(admission["max_charge_usd"]) not in (int, float)
        or admission["max_charge_usd"] != 0):
        raise SceneBlocked("M3_REMOTE_LIVE_NOT_ENABLED")
    shots = admission["shot_ids"]
    count = admission["max_attempts"]
    n = admission["historical_attempts"]
    if (not isinstance(shots, list) or not shots or len(set(shots)) != len(shots)
        or type(count) is not int or not 1 <= count <= len(shots)
        or type(n) is not int or n < 6
        or type(admission["total_attempt_limit"]) is not int
        or admission["total_attempt_limit"] != n + count
        or not isinstance(admission["request_id"], str)
        or not re.fullmatch("[a-f0-9]{32}", admission["request_id"])
        or not re.fullmatch("[a-f0-9]{64}", str(admission["history_sha256"]))):
        raise SceneBlocked("M3_REMOTE_SCOPE_INVALID")
    specs = admission["asset_keys"]
    if (type(specs) is not dict or set(specs) != set(shots)
        or any(not isinstance(k, str) or not re.fullmatch("[a-f0-9]{64}", k)
               for k in specs.values())):
        raise SceneBlocked("M3_REMOTE_SPEC_KEYS_INVALID")
    return {k: copy.deepcopy(admission[k]) for k in required}


class OfflineRemoteCoordinator:
    """CAS-only private attempt ledger; refuses any production dispatcher.

    A reservation represents a possibly submitted image request and is NEVER
    automatically retried, even if a crash occurred before a fake receipt.
    """

    def __init__(self, transport):
        if (not getattr(transport, "atomic_compare_and_swap", False)
            or getattr(transport, "production_transport", True)):
            raise SceneBlocked("M3_ATOMIC_REMOTE_CAS_UNAVAILABLE")
        self.remote = transport

    def _read_batch(self, request_id):
        version, journal = self.remote.read()
        _history(journal)
        batches = journal.get("m3_scene_batches", {})
        if not isinstance(batches, dict):
            raise SceneBlocked("M3_REMOTE_BATCH_FORMAT")
        batch = batches.get(request_id)
        if not isinstance(batch, dict):
            raise SceneBlocked("M3_REMOTE_BATCH_NOT_FOUND")
        _verify_batch_integrity(batch)
        return version, journal, batch

    def _write(self, version, modified):
        if not self.remote.compare_and_swap(version, modified):
            raise SceneBlocked("M3_REMOTE_CAS_CONFLICT_NO_RETRY")
        confirmed = self.remote.read()[1]
        if digest(confirmed) != digest(modified):
            raise SceneBlocked("M3_REMOTE_READBACK_MISMATCH_NO_RETRY")

    def begin(self, admission):
        a = _scope(admission)
        version, journal = self.remote.read()
        old_attempts = _history(journal)
        batches = journal.setdefault("m3_scene_batches", {})
        if not isinstance(batches, dict):
            raise SceneBlocked("M3_REMOTE_BATCH_FORMAT")
        old = batches.get(a["request_id"])
        identity = digest(a)
        if old is not None:
            _verify_batch_integrity(old)
            if old["identity"] != identity:
                raise SceneBlocked("M3_REMOTE_REQUEST_SCOPE_CHANGED")
            _verify_reserved_history(old_attempts, old)
            return dict(copy.deepcopy(old), cache_hit=True)
        if any(b.get("status") in ("READY", "RESERVED_UNCERTAIN", "PARTIAL")
               for b in batches.values()):
            raise SceneBlocked("M3_REMOTE_OTHER_BATCH_ACTIVE")
        if (len(old_attempts) != a["historical_attempts"]
            or history_sha256({k: v for k, v in journal.items()
                            if k != "m3_scene_batches"}) != a["history_sha256"]):
            raise SceneBlocked("M3_REMOTE_HISTORY_CHANGED")
        if any(x.get("request_id") == a["request_id"] for x in old_attempts):
            raise SceneBlocked("M3_REMOTE_REPLAY_NO_RETRY")
        batch = {
            "identity": identity,
            "scene_id": a["scene_id"],
            "request_id": a["request_id"],
            "shot_ids": a["shot_ids"],
            "asset_keys": a["asset_keys"],
            "max_attempts": a["max_attempts"],
            "total_attempt_limit": a["total_attempt_limit"],
            "historical_attempts": a["historical_attempts"],
            "historical_prefix": copy.deepcopy(old_attempts),
            "reserved": [],
            "receipts": {},
            "status": "READY",
            "simulated_only": True,
            "live_dispatch_enabled": False,
            "external_inference_requests": 0,
        }
        batches[a["request_id"]] = batch
        self._write(version, journal)
        return copy.deepcopy(batch)

    def reserve(self, request_id, shot_id):
        version, journal, batch = self._read_batch(request_id)
        attempts = _history(journal)
        _verify_reserved_history(attempts, batch, "M3_REMOTE_FOREIGN_HISTORY_CHANGE")
        if batch["status"] == "HALTED_UNCERTAIN":
            raise SceneBlocked("M3_REMOTE_UNCERTAIN_NO_RETRY")
        if shot_id not in batch["shot_ids"]:
            raise SceneBlocked("M3_REMOTE_UNAUTHORIZED_SHOT")
        if batch["status"] not in ("READY", "PARTIAL"):
            raise SceneBlocked("M3_REMOTE_BATCH_NOT_READY")
        if len(attempts) >= batch["total_attempt_limit"]:
            raise SceneBlocked("M3_REMOTE_GLOBAL_ATTEMPT_LIMIT")
        for shot in batch["reserved"]:
            if shot["shot_id"] == shot_id:
                raise SceneBlocked("M3_REMOTE_SHOT_ALREADY_RESERVED_NO_RETRY")
            if shot["shot_id"] not in batch["receipts"]:
                raise SceneBlocked("M3_REMOTE_PRIOR_UNCERTAIN_NO_RETRY")
        if len(batch["reserved"]) >= batch["max_attempts"]:
            raise SceneBlocked("M3_REMOTE_BATCH_ATTEMPT_LIMIT")
        # Script-defined shot order is immutable; allow the first N selections.
        expected = batch["shot_ids"][len(batch["reserved"])]
        if shot_id != expected:
            raise SceneBlocked("M3_REMOTE_SHOT_ORDER_CHANGED")
        token = digest({"batch": batch["identity"], "shot_id": shot_id,
                        "spec_sha256": batch["asset_keys"][shot_id]})
        attempt = {
            "key": token, "request_id": request_id,
            "shot_id": shot_id, "spec_sha256": batch["asset_keys"][shot_id],
            "status": "RESERVED_SUBMISSION_UNCERTAIN_NO_RETRY",
        }
        attempts.append(attempt)
        batch["reserved"].append({
            "shot_id": shot_id, "idempotency_key": token,
            "spec_sha256": batch["asset_keys"][shot_id],
        })
        batch["status"] = "RESERVED_UNCERTAIN"
        self._write(version, journal)
        return {
            "status": "OFFLINE_RESERVATION_ONLY_NO_PROVIDER_CALL",
            "shot_id": shot_id, "idempotency_key": token,
            "total_attempts": len(attempts), "live_dispatch_enabled": False,
        }

    def record_mock_receipt(self, request_id, shot_id, fake_receipt):
        version, journal, batch = self._read_batch(request_id)
        attempts = _history(journal)
        if (batch["status"] != "RESERVED_UNCERTAIN"
            or not batch["reserved"] or batch["reserved"][-1]["shot_id"] != shot_id
            or shot_id in batch["receipts"]):
            raise SceneBlocked("M3_REMOTE_RECEIPT_WITHOUT_RESERVATION")
        _verify_reserved_history(attempts, batch)
        expected_fake_hash = hashlib.sha256((
            "M3_FAKE_IMAGE_V1:" + batch["scene_id"] + ":" + shot_id + ":" +
            batch["asset_keys"][shot_id]
        ).encode()).hexdigest()
        if not (isinstance(fake_receipt, dict)
                and fake_receipt.get("kind") == "OFFLINE_FAKE_NOT_IMAGE"
                and fake_receipt.get("sha256") == expected_fake_hash
                and fake_receipt.get("accepted") is False
                and type(fake_receipt.get("provider_calls")) is int
                and fake_receipt["provider_calls"] == 0
                and type(fake_receipt.get("external_cost_usd")) in (int, float)
                and fake_receipt["external_cost_usd"] == 0):
            raise SceneBlocked("M3_REMOTE_ONLY_FAKE_RECEIPTS_ALLOWED")
        batch["receipts"][shot_id] = copy.deepcopy(fake_receipt)
        batch["status"] = ("SIMULATED_NOT_ART"
                           if len(batch["reserved"]) == batch["max_attempts"]
                           else "PARTIAL")
        self._write(version, journal)
        return {"status": batch["status"], "shot_id": shot_id,
                "live_dispatch_enabled": False}

    def status(self, request_id):
        _, journal, batch = self._read_batch(request_id)
        attempts = _history(journal)
        _verify_reserved_history(attempts, batch)
        if batch["status"] == "RESERVED_UNCERTAIN":
            # Observation does not mutate history; permanently treat as uncertain.
            return dict(copy.deepcopy(batch), recovery_status="HALTED_UNCERTAIN_NO_RETRY")
        return copy.deepcopy(batch)
