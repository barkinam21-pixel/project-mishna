"""M3 safe scene-level batch admission and OFFLINE simulation.

It reuses M1's source/continuity validation and append-only SceneStore.
This module deliberately has NO network/provider/Drive imports or live submit
operation. A real Cloudflare call still requires the independently reviewed,
owner-scoped Issue54 one-shot bridge and its fresh private safety gate.
Simulation exercises exact-shot idempotency and crash recovery, not art quality.
"""
import argparse
import copy
import hashlib
import json
import re
import sys
from pathlib import Path

from tools.scene_factory import (
    SceneBlocked, SceneStore, digest, keys, load, validate, within, writer_lock
)

REQUEST_RE = re.compile(r"[A-Za-z0-9_-]{1,80}")
SHOT_RE = re.compile(r"[A-Z0-9-]{1,80}")


def selection(scene, requested):
    ids = [shot["id"] for shot in scene["shots"]]
    if not isinstance(requested, list) or not requested:
        raise SceneBlocked("M3_EMPTY_SHOT_SELECTION")
    if len(requested) != len(set(requested)) or any(
        not isinstance(x, str) or not SHOT_RE.fullmatch(x) or x not in ids
        for x in requested
    ):
        raise SceneBlocked("M3_INVALID_SHOT_SELECTION")
    if requested != [x for x in ids if x in requested]:
        raise SceneBlocked("M3_SHOT_ORDER_CHANGED")
    return requested


def admission_identity(scene, bible, shots, max_attempts):
    # The batch is immutable. Even a source/approval/wardrobe change invalidates
    # the request; a second request id is required after explicit review.
    return digest({
        "version": "M3_SIMULATION_ONLY_V1",
        "scene": scene,
        "bible": bible,
        "shots": shots,
        "max_attempts": max_attempts,
        "backend": "OFFLINE_FAKE_IMAGE_V1",
    })


class OfflineFakeImageBackend:
    """Deterministic mock response; never creates media or calls a provider."""
    def produce(self, scene_id, shot_id, asset_key):
        evidence = f"M3_FAKE_IMAGE_V1:{scene_id}:{shot_id}:{asset_key}"
        return {
            "kind": "OFFLINE_FAKE_NOT_IMAGE",
            "sha256": hashlib.sha256(evidence.encode()).hexdigest(),
            "accepted": False,
            "provider_calls": 0,
            "external_cost_usd": 0,
        }


class BatchCoordinator:
    def __init__(self, state_path):
        self.store = SceneStore(state_path)

    def plan(self, scene, bible, root, request_id, shot_ids, max_attempts):
        if not isinstance(request_id, str) or not REQUEST_RE.fullmatch(request_id):
            raise SceneBlocked("M3_REQUEST_ID_INVALID")
        selection(scene, shot_ids)
        if type(max_attempts) is not int or not 0 <= max_attempts <= len(shot_ids):
            raise SceneBlocked("M3_ATTEMPT_LIMIT_INVALID")
        # This is an offline scheduler, not authorization for a real POST.
        if scene.get("authorization", {}).get("generation_approved") is not False:
            raise SceneBlocked("M3_PRODUCTION_GATE_NOT_AVAILABLE")
        if scene["authorization"].get("budget_usd") != 0:
            raise SceneBlocked("M3_NONZERO_COST_FORBIDDEN")
        identity = admission_identity(scene, bible, shot_ids, max_attempts)
        with writer_lock(self.store.path / "writer.lock"):
            state, _, _ = self.store.recover()
            batches = state.setdefault("m3_batches", {})
            old = batches.get(request_id)
            if old and old["identity"] != identity:
                raise SceneBlocked("M3_REQUEST_SPEC_CHANGED")
            issues = validate(scene, bible, root)  # EVERY request, not cached.
            if old:
                if issues != old["issues"]:
                    raise SceneBlocked("M3_PREFLIGHT_CHANGED_NEW_REQUEST_REQUIRED")
                return dict(old, cache_hit=True)
            batch = {
                "identity": identity,
                "scene_id": scene["id"],
                "shot_ids": list(shot_ids),
                "max_attempts": max_attempts,
                "attempted": 0,
                "status": "BLOCKED" if issues else "SIMULATION_READY",
                "issues": issues,
                "spec_keys": {x: keys(scene, bible)["asset_keys"][x] for x in shot_ids},
                "results": {},
                "external_inference_requests": 0,
                "external_charge_usd": 0,
                "live_generation_enabled": False,
                "owner_approved_for_live_generation": False,
                "artistic_scene_complete": False,
                "cache_hit": False,
            }
            batches[request_id] = batch
            self.store.commit(state, "M3_BATCH_PLAN_OFFLINE")
            return dict(batch)

    def simulate(self, scene, bible, root, request_id, shot_ids, max_attempts,
                 *, fail_after_reservation_at=None):
        """Exercise a batch's durable reservations with a NO-NETWORK mock.

        If a process crashes between reservation and receipt, the reservation
        is intentionally left UNCERTAIN; never re-submit automatically.
        """
        self.plan(scene, bible, root, request_id, shot_ids, max_attempts)
        backend = OfflineFakeImageBackend()
        for shot_id in shot_ids[:max_attempts]:
            with writer_lock(self.store.path / "writer.lock"):
                state, _, _ = self.store.recover()
                b = state["m3_batches"][request_id]
                if b["status"] == "BLOCKED":
                    return dict(b)
                result = b["results"].get(shot_id)
                if result is not None:
                    if result["status"] == "CANDIDATE":
                        continue  # Resume without regenerating a finished shot.
                    if result["status"] == "RESERVED_UNCERTAIN":
                        b["status"] = "HALTED_UNCERTAIN"
                        self.store.commit(state, "M3_HALT_UNCERTAIN_NO_RETRY")
                        return dict(b)  # Potential submit = no automatic retry.
                    raise SceneBlocked("M3_INVALID_RECORDED_STATUS")
                if b["attempted"] >= b["max_attempts"]:
                    break
                token = digest({"batch": b["identity"], "shot": shot_id,
                                "spec": b["spec_keys"][shot_id]})
                b["results"][shot_id] = {
                    "status": "RESERVED_UNCERTAIN", "idempotency_key": token,
                    "spec_key": b["spec_keys"][shot_id]
                }
                b["attempted"] += 1
                b["status"] = "SIMULATING"
                self.store.commit(state, "M3_RESERVE_BEFORE_MOCK")
            # The already committed reservation survives sudden termination.
            if shot_id == fail_after_reservation_at:
                raise SceneBlocked("M3_SIMULATED_CRASH_AFTER_RESERVATION")
            evidence = backend.produce(b["scene_id"], shot_id, b["spec_keys"][shot_id])
            if (evidence["kind"] != "OFFLINE_FAKE_NOT_IMAGE"
                or evidence["accepted"] is not False
                or evidence["provider_calls"] != 0
                or evidence["external_cost_usd"] != 0):
                raise SceneBlocked("M3_MOCK_RECEIPT_INVALID")
            with writer_lock(self.store.path / "writer.lock"):
                state, _, _ = self.store.recover()
                b = state["m3_batches"][request_id]
                pending = b["results"].get(shot_id)
                if (not pending or pending["status"] != "RESERVED_UNCERTAIN"
                    or pending["spec_key"] != b["spec_keys"][shot_id]):
                    raise SceneBlocked("M3_RESERVATION_LOST")
                pending.update(status="CANDIDATE", receipt=evidence)
                b["status"] = "SIMULATION_READY"
                self.store.commit(state, "M3_FAKE_RECEIPT")
        with writer_lock(self.store.path / "writer.lock"):
            state, _, _ = self.store.recover()
            b = state["m3_batches"][request_id]
            if b["status"] == "SIMULATION_READY":
                b["status"] = "SIMULATED_NOT_ART"
                self.store.commit(state, "M3_BATCH_SIMULATION_COMPLETE")
            return dict(b)

    def status(self, request_id):
        with writer_lock(self.store.path / "writer.lock"):
            state, _, n = self.store.recover()
            b = state.get("m3_batches", {}).get(request_id)
            if not b:
                raise SceneBlocked("M3_UNKNOWN_REQUEST")
            return dict(b, journal_events=n)


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("command", choices=("plan", "simulate", "status"))
    p.add_argument("--manifest", default="episodes/berakhot-01-01/scene-prologue-v02.json")
    p.add_argument("--root", default=".")
    p.add_argument("--state", default="private-media/scene-factory")
    p.add_argument("--request-id", default="m3-prologue-demo")
    p.add_argument("--shot-ids", default="EP-P01,EP-P02")
    p.add_argument("--max-attempts", type=int, default=2)
    a = p.parse_args(argv)
    try:
        root = Path(a.root).resolve()
        state_path = within(root, a.state)
        if "private-media" not in state_path.relative_to(root).parts:
            raise SceneBlocked("M3_PRIVATE_STATE_REQUIRED")
        q = BatchCoordinator(state_path)
        if a.command == "status":
            r = q.status(a.request_id)
        else:
            scene = load(within(root, a.manifest))
            bible = load(within(root, scene["bible"]["path"]))
            ids = a.shot_ids.split(",")
            if a.command == "plan":
                r = q.plan(scene, bible, root, a.request_id, ids, a.max_attempts)
            else:
                r = q.simulate(scene, bible, root, a.request_id, ids, a.max_attempts)
        print(json.dumps(r, ensure_ascii=False, indent=2))
        return 2 if r["status"] in ("BLOCKED", "HALTED_UNCERTAIN") else 0
    except (ValueError, KeyError, TypeError, OSError) as err:
        print(json.dumps({"status": "BLOCKED", "reason": str(err) if isinstance(err, SceneBlocked)
                          else type(err).__name__, "external_inference_requests": 0,
                          "live_generation_enabled": False}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    sys.exit(main())
