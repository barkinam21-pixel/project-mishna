"""OFFLINE-only one-call 15-shot batch rehearsal over existing M3 CAS mock.

Accepts the *existing* #101 packet and #102/#103 pinned-Cloudflare prepare
previews, but never imports a live provider, Google Drive client, credentials,
or a network transport. Fake receipts are explicitly NOT art/cache assets.
This is a test seam, not a production dispatcher or live M3 admission.
"""
import copy
import hashlib
import re

from tools.scene_factory import SceneBlocked, digest
from tools.scene_m3_remote import (
    AtomicMemoryJournal, OfflineRemoteCoordinator, history_sha256,
)

_SHA = re.compile(r"^[a-f0-9]{64}$")
_REQUEST = re.compile(r"^[a-f0-9]{32}$")


class _FakeReadOnlyPath:
    def __init__(self, data):
        self._data = bytes(data)

    def read_bytes(self):
        return self._data


class OfflineFakeDrive:
    """In-memory synthetic references/cache; never touches Google Drive."""

    def __init__(self, references, cache=None):
        self.references = dict(references)
        self.cache = copy.deepcopy(cache or {})
        self.reference_reads = 0

    def restore_refs(self, spec):
        paths = []
        for ref in spec["references"]:
            path = ref.get("path")
            if not isinstance(path, str) or not path.startswith("private-media/"):
                raise SceneBlocked("BATCH_FAKE_REFERENCE_NOT_PRIVATE")
            raw = self.references.get(path)
            if not isinstance(raw, bytes) or hashlib.sha256(raw).hexdigest() != ref.get("sha256"):
                raise SceneBlocked("BATCH_FAKE_REFERENCE_HASH_OR_BYTES_MISSING")
            self.reference_reads += 1
            paths.append(_FakeReadOnlyPath(raw))
        return paths

    def accepted_synthetic_cache_hit(self, job):
        entry = self.cache.get(job["asset_key"])
        if not isinstance(entry, dict):
            return False
        # This in-memory fixture never authorizes production asset acceptance.
        if entry.get("accepted") is not True or entry.get("rights_verified") is not True:
            return False
        if entry.get("origin") != "OFFLINE_SYNTHETIC_FIXTURE" or entry.get("shot_id") != job["shot_id"]:
            raise SceneBlocked("BATCH_FAKE_ACCEPTED_CACHE_PROVENANCE_INVALID")
        raw = entry.get("bytes")
        if (not isinstance(raw, bytes) or not isinstance(entry.get("sha256"), str)
            or not _SHA.fullmatch(entry["sha256"])
            or hashlib.sha256(raw).hexdigest() != entry["sha256"]):
            raise SceneBlocked("BATCH_FAKE_ACCEPTED_CACHE_HASH_CHANGED")
        return True


class OfflineFakeCloudflare:
    """Only tests the lower-level prepare shape, cannot call the model."""

    def __init__(self):
        self.prepares = []
        self.submit_calls = 0

    def prepare(self, spec, reference_paths):
        if (not isinstance(spec, dict) or not isinstance(spec.get("seed"), int)
            or not 0 <= spec["seed"] < 2**64
            or spec.get("size") != [1024, 576]
            or not isinstance(spec.get("prompt"), str)
            or not spec["prompt"].strip()
            or not isinstance(spec.get("characters"), dict)
            or not isinstance(spec.get("director"), dict)
            or spec["director"].get("review_status") != "DRAFT_REQUIRES_REVIEW"
            or spec["director"].get("time_of_day") != "dawn"
            or len(reference_paths) != len(spec.get("references", []))):
            raise SceneBlocked("BATCH_FAKE_PROVIDER_SHAPE_INVALID")
        for ref, path in zip(spec["references"], reference_paths):
            if hashlib.sha256(path.read_bytes()).hexdigest() != ref.get("sha256"):
                raise SceneBlocked("BATCH_FAKE_PROVIDER_REF_CHANGED")
        self.prepares.append(spec["director"]["shot_id"])
        return {"kind": "FAKE_PREPARED_NO_INFERENCE", "seed": spec["seed"]}

    def submit(self, *args, **kwargs):
        self.submit_calls += 1
        raise SceneBlocked("BATCH_REAL_PROVIDER_SUBMISSION_FORBIDDEN")


def _verify_inputs(packet, previews, drive, provider, journal, baseline, request_id, max_attempts):
    if (type(drive) is not OfflineFakeDrive
        or type(provider) is not OfflineFakeCloudflare
        or type(journal) is not AtomicMemoryJournal):
        raise SceneBlocked("BATCH_ONLY_FAKE_DEPENDENCIES_ALLOWED")
    if not isinstance(request_id, str) or not _REQUEST.fullmatch(request_id):
        raise SceneBlocked("BATCH_FAKE_REQUEST_ID_INVALID")
    if type(max_attempts) is not int or max_attempts < 1:
        raise SceneBlocked("BATCH_FAKE_ATTEMPT_LIMIT_INVALID")
    if (not isinstance(packet, dict) or not isinstance(previews, dict)
        or packet.get("packet_sha256") != digest({k: v for k,v in packet.items() if k != "packet_sha256"})
        or previews.get("preview_sha256") != digest({k: v for k,v in previews.items() if k != "preview_sha256"})):
        raise SceneBlocked("BATCH_PACKET_OR_PREVIEW_CHANGED")
    if (packet.get("status") != "SCENE_PACKET_DRAFT_NOT_AUTHORIZED"
        or packet.get("generation_gate_closed") is not True
        or packet.get("provider_dispatch_authorized") is not False
        or packet.get("inference_requests") != 0
        or previews.get("status") != "OFFLINE_PROVIDER_SHAPE_PREVIEW_NO_DISPATCH"
        or previews.get("native_legacy_engine_compatible") is not False
        or previews.get("provider_dispatch_authorized") is not False
        or previews.get("provider_calls") != 0
        or previews.get("reference_status") != ["PRIVATE_BYTES_HASH_VERIFIED_ONLY"]
        or packet.get("scene_id") != previews.get("scene_id")
        or packet.get("packet_sha256") != previews.get("scene_packet_sha256")):
        raise SceneBlocked("BATCH_FAKE_REQUIRES_CLOSED_SAFE_PREVIEW")
    jobs, pieces = packet.get("jobs"), previews.get("jobs")
    if not isinstance(jobs, list) or not isinstance(pieces, list) or len(jobs) != 15 or len(pieces) != 15:
        raise SceneBlocked("BATCH_FAKE_15_SHOT_PACKET_REQUIRED")
    for a, b in zip(jobs, pieces):
        if (a.get("shot_id") != b.get("shot_id")
            or a.get("asset_key") != b.get("asset_key")
            or a.get("ready_for_model_submission") is not False
            or b.get("provider_dispatch_authorized") is not False
            or b.get("reference_rights_scope") != "NOT_APPROVED_FOR_SCENE_BATCH"
            or "HOSTED_M3_AND_GENERATION_POLICY_CLOSED" not in b.get("blockers", [])
            or b.get("provider_calls") != 0):
            raise SceneBlocked("BATCH_FAKE_JOB_OR_GATE_CHANGED")
    if (not isinstance(baseline, dict) or type(baseline.get("attempts")) is not list
        or len(baseline["attempts"]) < 6
        or not isinstance(baseline.get("entries"), dict)):
        raise SceneBlocked("BATCH_FAKE_BASELINE_INVALID")


def rehearse_once(packet, previews, *, drive, provider, journal, baseline,
                  request_id, max_attempts, step_limit=None, crash_after_reservation=False):
    """Resume one offline batch, preserving existing M3 no-retry reservations.

    A recorded mock receipt explicitly means 'not artwork'. The caller may
    invoke again with the same journal, immutable baseline and request scope.
    """
    _verify_inputs(packet, previews, drive, provider, journal, baseline,
                   request_id, max_attempts)
    missing = [j for j in packet["jobs"] if not drive.accepted_synthetic_cache_hit(j)]
    cached = [j["shot_id"] for j in packet["jobs"] if j not in missing]
    if len(missing) < max_attempts:
        raise SceneBlocked("BATCH_FAKE_TOO_MANY_ATTEMPTS_FOR_MISSING_SLOTS")
    if step_limit is not None and (type(step_limit) is not int or step_limit < 0):
        raise SceneBlocked("BATCH_FAKE_STEP_LIMIT_INVALID")
    admission = {
        "status": "OFFLINE_TICKET_CHECKED_NO_LIVE_DISPATCH",
        "scene_id": packet["scene_id"], "request_id": request_id,
        "shot_ids": [j["shot_id"] for j in missing],
        "max_attempts": max_attempts, "max_charge_usd": 0,
        "historical_attempts": len(baseline["attempts"]),
        "history_sha256": history_sha256(baseline),
        "total_attempt_limit": len(baseline["attempts"]) + max_attempts,
        "asset_keys": {j["shot_id"]:j["asset_key"] for j in missing},
        "live_dispatch_enabled": False,
    }
    coordinator = OfflineRemoteCoordinator(journal)
    coordinator.begin(admission)
    status = coordinator.status(request_id)
    if status["status"] == "RESERVED_UNCERTAIN":
        return {
            "status": "OFFLINE_HALTED_UNCERTAIN_NO_RETRY",
            "scene_id": packet["scene_id"],
            "cached_synthetic": cached,
            "recorded_fake_receipts": len(status["receipts"]),
            "pending_shot_id": status["reserved"][-1]["shot_id"],
            "provider_prepares": len(provider.prepares),
            "provider_submissions": provider.submit_calls,
            "external_inference_requests": 0, "generation_authorized": False,
        }
    remaining = max_attempts - len(status["reserved"])
    limit = remaining if step_limit is None else min(remaining, step_limit)
    for i in range(limit):
        job = missing[len(status["reserved"])+i]
        pjob = pieces_by_id(previews)[job["shot_id"]]
        spec = pjob["engine_spec_preview"]
        refs = drive.restore_refs(spec)
        response = provider.prepare(spec, refs)
        if response.get("kind") != "FAKE_PREPARED_NO_INFERENCE":
            raise SceneBlocked("BATCH_FAKE_PROVIDER_PREPARE_INVALID")
        coordinator.reserve(request_id, job["shot_id"])
        if crash_after_reservation:
            # An uncertain production POST could have occurred: no implicit retry.
            raise SceneBlocked("BATCH_FAKE_CRASH_AFTER_RESERVATION")
        h = hashlib.sha256(("M3_FAKE_IMAGE_V1:" + packet["scene_id"] + ":" +
                           job["shot_id"] + ":" + job["asset_key"]).encode()).hexdigest()
        coordinator.record_mock_receipt(request_id, job["shot_id"], {
            "kind": "OFFLINE_FAKE_NOT_IMAGE", "sha256": h,
            "accepted": False, "provider_calls": 0, "external_cost_usd": 0,
        })
    finished = coordinator.status(request_id)
    return {
        "status": ("OFFLINE_FAKE_BATCH_DONE_NOT_ART"
                   if finished["status"] == "SIMULATED_NOT_ART"
                   else "OFFLINE_FAKE_PARTIAL_RESUMABLE"),
        "scene_id": packet["scene_id"], "cached_synthetic": cached,
        "recorded_fake_receipts": len(finished["receipts"]),
        "attempt_limit": max_attempts,
        "provider_prepares": len(provider.prepares),
        "provider_submissions": provider.submit_calls,
        "external_inference_requests": 0, "generation_authorized": False,
    }


def pieces_by_id(previews):
    return {j["shot_id"]: j for j in previews["jobs"]}
