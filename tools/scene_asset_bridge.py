"""Read-only bridge: reconcile private scene state with the film asset registry.

No approvals are inferred, no private bytes are copied, and no provider is called.
Run only in a runtime where private-media is mounted.
"""
import argparse
import hashlib
import json
from pathlib import Path

from tools.scene_pack_preflight import build, verified_entry, ACCEPTED, EXPECTED_IDS
from tools.comfy_scene_images import under


def digest(path):
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def reconcile(root):
    root = Path(root).resolve()
    report = build(root)
    state_path = under(root, "private-media/director-images/state.json")
    state = json.loads(state_path.read_text(encoding="utf-8")) if state_path.exists() else {}
    registry_path = under(root, "episodes/berakhot-01-01/introduction-proof.json")
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    entries = state.get("entries", {})
    results = []
    for shot in report["shots"]:
        sid, key = shot["shot_id"], shot["key"]
        record = registry["assets"].get(sid, {})
        entry = entries.get(key)
        status, reason = verified_entry(entry, root)
        registry_path_value = record.get("path")
        registry_ok = False
        if registry_path_value and record.get("sha256"):
            try:
                path = under(root, registry_path_value)
                registry_ok = path.is_file() and digest(path) == record["sha256"]
            except (OSError, ValueError, TypeError):
                pass
        same_bytes = bool(status == ACCEPTED and registry_ok and
                          entry.get("sha256") == record.get("sha256"))
        ready = bool(same_bytes and record.get("accepted") is True and
                     record.get("rights_verified") is True)
        results.append({
            "shot_id": sid,
            "director_status": status or shot["status"],
            "registry_hash_verified": registry_ok,
            "same_approved_bytes": same_bytes,
            "ready_for_render": ready,
            "reason": "Both independent registries agree" if ready else
                      (reason or "Missing, unapproved, or mismatched private media"),
        })
    assert [r["shot_id"] for r in results] == EXPECTED_IDS
    return {
        "schema_version": 1,
        "mode": "READ_ONLY_NO_APPROVAL_NO_UPLOAD",
        "ready": all(r["ready_for_render"] for r in results),
        "shots": results,
        "next_action": "Run existing introduction_proof gate" if all(r["ready_for_render"] for r in results)
                       else "Review candidates and reconcile private asset hashes and approvals",
        "provider_calls": 0,
        "workspace_usage": "unknown",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=".")
    parser.add_argument("--out", default="build/scene-asset-bridge.json")
    args = parser.parse_args()
    root = Path(args.root).resolve()
    result = reconcile(root)
    out = under(root, args.out)
    if "private-media" in out.relative_to(root).parts:
        raise ValueError("Bridge report must not be stored alongside private images")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"ready": result["ready"], "report": str(out.relative_to(root)),
                      "verified": sum(s["ready_for_render"] for s in result["shots"])},
                     ensure_ascii=False))


if __name__ == "__main__":
    main()
