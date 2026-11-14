"""Offline bridge from scene-wide direction packet to PINNED Cloudflare adapter input.

This compiles the *shape accepted by CloudflareClient.prepare(spec, references)*.
It NEVER imports/instantiates a provider, checks quotas, reserves, uploads, or
calls submit. Native legacy engine's OPN01-07 and sunset contracts remain intact.
Generation for EP-P01-15 needs a separately reviewed scene-native dispatcher.
"""
import argparse
import copy
import hashlib
import json
import re
import sys
from pathlib import Path

from tools.scene_factory import SceneBlocked, digest, file_sha, load, within
from tools.scene_production_packet import build_packet

MODEL = "black-forest-labs/FLUX.2-klein-4B"
ENGINE_REF = "80ba1559b785855a1f9f4cbd90083fd0228eec96"
SHA = re.compile(r"^[0-9a-f]{64}$")
SHOT = re.compile(r"^EP-P[0-9]{2}$")


def _private_reference_check(reference, root):
    """Never accept a public URL, outside path, unverified bytes, or stale hash."""
    if not isinstance(reference, dict):
        return "REFERENCE_FORMAT_INVALID"
    path, expected = reference.get("path"), reference.get("sha256")
    if (not isinstance(path, str) or not path.startswith("private-media/")
        or not isinstance(expected, str) or not SHA.fullmatch(expected)):
        return "REFERENCE_PRIVATE_PATH_OR_HASH_INVALID"
    if reference.get("synthesis_rights_confirmed") is not True:
        return "REFERENCE_RIGHTS_NOT_ATTESTED"
    try:
        file = within(root, path)
    except (ValueError, TypeError):
        return "REFERENCE_OUTSIDE_ROOT"
    if not file.is_file():
        return "PRIVATE_REFERENCE_NOT_RESTORED"
    if file_sha(file) != expected or (
        reference.get("expected_sha256") and expected != reference["expected_sha256"]
    ):
        return "PRIVATE_REFERENCE_HASH_CHANGED"
    return None


def compile_previews(packet, legacy_manifest, root):
    """Build all provider-shape specs from an unapproved scene packet (no I/O writes).

    Original legacy OPN IDs are NOT remapped/consumed. EP shot IDs are retained
    and the old sunset director controls are NEVER copied into a dawn scene.
    """
    if not isinstance(packet, dict) or not isinstance(packet.get("packet_sha256"), str):
        raise SceneBlocked("CLOUD_PACKET_MISSING")
    payload = {k:v for k,v in packet.items() if k!="packet_sha256"}
    if digest(payload) != packet["packet_sha256"]:
        raise SceneBlocked("CLOUD_PACKET_CHANGED")
    if (packet.get("schema_version") != 1
        or packet.get("status") != "SCENE_PACKET_DRAFT_NOT_AUTHORIZED"
        or packet.get("generation_gate_closed") is not True
        or packet.get("provider_dispatch_authorized") is not False
        or packet.get("inference_requests") != 0
        or packet.get("scene_approval_scope") != "NONE"):
        raise SceneBlocked("CLOUD_PACKET_LIVE_SCOPE_FORBIDDEN")
    if not isinstance(legacy_manifest, dict) or legacy_manifest.get("schema_version")!=1:
        raise SceneBlocked("CLOUD_LEGACY_MANIFEST_INVALID")
    if legacy_manifest.get("model",{}).get("id") != MODEL:
        raise SceneBlocked("CLOUD_MODEL_CHANGED")
    cfg=legacy_manifest.get("available_backends",{}).get("cloudflare",{})
    if cfg.get("type") != "cloudflare":
        raise SceneBlocked("CLOUD_BACKEND_NOT_PINNED")
    size=legacy_manifest.get("size")
    if size != [1024,576]:
        raise SceneBlocked("CLOUD_DIMENSIONS_CHANGED")
    refs=legacy_manifest.get("references")
    if not isinstance(refs,list) or not 1 <= len(refs) <= 4:
        raise SceneBlocked("CLOUD_REFERENCE_TEMPLATE_INVALID")
    ref_errors=sorted(set(e for r in refs if (e := _private_reference_check(r,root))))
    # This is an immutable preview, NOT a grant for reusing owner rights outside
    # the earlier approved OPN02 reference trial. Each actual scene needs review.
    rights_scope="NOT_APPROVED_FOR_SCENE_BATCH"
    jobs=packet.get("jobs")
    if not isinstance(jobs,list) or len(jobs)!=packet.get("shot_count") or not jobs:
        raise SceneBlocked("CLOUD_JOB_COUNT_INVALID")
    previews=[]; ids=set();next_frame=0
    for job in jobs:
        sid=job.get("shot_id")
        if not isinstance(sid,str) or not SHOT.fullmatch(sid) or sid in ids:
            raise SceneBlocked("CLOUD_SHOT_ID_INVALID")
        ids.add(sid)
        if (type(job.get("start_frame")) is not int
            or type(job.get("end_frame")) is not int
            or job["start_frame"]!=next_frame or job["end_frame"]<=next_frame):
            raise SceneBlocked("CLOUD_TIMELINE_INVALID")
        next_frame=job["end_frame"]
        if not isinstance(job.get("asset_key"),str) or not SHA.fullmatch(job["asset_key"]):
            raise SceneBlocked("CLOUD_ASSET_KEY_INVALID")
        if job.get("ready_for_model_submission") is not False:
            raise SceneBlocked("CLOUD_JOB_NOT_CLOSED")
        if job.get("image_status") not in (
            "NEW_ORIGINAL_IMAGE_REQUIRED","EXISTING_CANDIDATE_REVIEW_ONLY",
            "VERIFIED_ACCEPTED_CACHE","HASH_MISMATCH_BLOCKED"):
            raise SceneBlocked("CLOUD_ASSET_STATUS_INVALID")
        visual=job.get("visual_spec",{})
        locks=visual.get("visual_locks",{})
        if (visual.get("scene_id") != packet["scene_id"]
            or visual.get("shot_id") != sid or visual.get("aspect_ratio")!="16:9"
            or visual.get("width")!=size[0] or visual.get("height")!=size[1]
            or not isinstance(visual.get("positive_prompt"),str)
            or not visual["positive_prompt"].strip()
            or not isinstance(visual.get("negative_prompt"),str)
            or locks.get("time_of_day") not in ("dawn","sunset","day","night")):
            raise SceneBlocked("CLOUD_VISUAL_SPEC_INVALID")
        # One stable synthetic preview seed per visual spec, not a reservation.
        seed=int(hashlib.sha256(("SCENE_IMAGE_PREVIEW_V1:"+job["asset_key"]).encode()).hexdigest()[:16],16)
        # The pinned CloudflareClient.prepare calls the unchanged engine's
        # prompt_text(spec), which reads exactly these fields. No legacy shot
        # aliasing is attempted and old sunset style/director are NOT copied.
        spec={
            "compiler_version":1,
            "model":copy.deepcopy(legacy_manifest["model"]),
            "size":list(size),
            "style":str(locks.get("style",""))+"; "+str(locks.get("palette","")),
            "characters":{},  # Actor visibility has not been locked: fail closed.
            "prompt":visual["positive_prompt"]+" Negative constraints: "+visual["negative_prompt"],
            "seed":seed,
            "references":copy.deepcopy(refs),
            "backend":{"type":"cloudflare","model":cfg.get("model")},
            "visual_direction":{
                "continuity_review":locks,
                "shot_id":sid,
                "camera":visual.get("camera"),
                "character_locks_for_review":visual.get("character_locks_if_visible"),
                "source_label":job.get("source_label"),
            },
        }
        issues=[]
        if ref_errors:issues += ref_errors
        if packet.get("source_and_editorial_blockers"):issues.append("SCENE_EDITORIAL_SOURCE_BLOCKERS")
        if job.get("source_verified") is not True:issues.append("SOURCE_REVIEW_REQUIRED")
        if job.get("image_status")=="EXISTING_CANDIDATE_REVIEW_ONLY":issues.append("CANDIDATE_NOT_APPROVED")
        if job.get("candidate_repeated_in_scene"):issues.append("DUPLICATE_CANDIDATE_COVERAGE")
        if job.get("image_status")=="HASH_MISMATCH_BLOCKED":issues.append("CACHE_HASH_INVALID")
        issues.extend(["SCENE_REFERENCE_RIGHTS_SCOPE_UNAPPROVED",
                       "CHARACTERS_VISIBLE_UNDECLARED",
                       "SCENE_NATIVE_DIRECTOR_CONTROLS_UNMAPPED",
                       "LEGACY_ENGINE_EP_SHOT_IDS_UNSUPPORTED",
                       "HOSTED_M3_AND_GENERATION_POLICY_CLOSED"])
        previews.append({
            "scene_id":packet["scene_id"],"shot_id":sid,"asset_key":job["asset_key"],
            "start_frame":job["start_frame"],"end_frame":job["end_frame"],
            "legacy_candidate_id":job.get("candidate_asset_id"),
            "engine_spec_preview":spec,
            "reference_bytes_verified":not bool(ref_errors),
            "reference_rights_scope":rights_scope,
            "provider_prepare_contract":"CloudflareClient.prepare(spec, reference_paths)",
            "blockers":sorted(set(issues)),
            "provider_dispatch_authorized":False,
            "provider_calls":0,
        })
    if next_frame!=packet.get("duration_frames"):
        raise SceneBlocked("CLOUD_DURATION_INVALID")
    output={
        "schema_version":1,
        "status":"OFFLINE_PROVIDER_SHAPE_PREVIEW_NO_DISPATCH",
        "pinned_engine_ref":ENGINE_REF,
        "scene_id":packet["scene_id"],
        "scene_packet_sha256":packet["packet_sha256"],
        "job_count":len(previews),
        "reference_status":ref_errors or ["PRIVATE_BYTES_HASH_VERIFIED_ONLY"],
        "provider_calls":0,
        "external_cost_usd":0,
        "provider_dispatch_authorized":False,
        "native_legacy_engine_compatible":False,
        "jobs":previews,
    }
    output["preview_sha256"]=digest(output)
    return output


def summarize(output):
    return {
        "status":output["status"],"scene_id":output["scene_id"],
        "job_count":output["job_count"],
        "reference_status":output["reference_status"],
        "blocked_jobs":sum(bool(x["blockers"]) for x in output["jobs"]),
        "provider_calls":output["provider_calls"],
        "provider_dispatch_authorized":output["provider_dispatch_authorized"],
        "native_legacy_engine_compatible":output["native_legacy_engine_compatible"],
        "preview_sha256":output["preview_sha256"],
    }


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--root",default=".")
    p.add_argument("--manifest",default="episodes/berakhot-01-01/scene-prologue-v02.json")
    p.add_argument("--legacy-template",default=None,
                   help="Path to the pinned old studio manifest (never auto-fetch)")
    p.add_argument("--summary",action="store_true")
    a=p.parse_args(argv)
    try:
        if not a.legacy_template:
            raise SceneBlocked("PINNED_LEGACY_TEMPLATE_REQUIRED")
        root=Path(a.root).resolve()
        scene=load(within(root,a.manifest))
        bible=load(within(root,scene["bible"]["path"]))
        packet=build_packet(scene,bible,root)
        legacy=load(Path(a.legacy_template))
        previews=compile_previews(packet,legacy,root)
        print(json.dumps(summarize(previews) if a.summary else previews,
                         ensure_ascii=False,sort_keys=True))
        return 0
    except (OSError,ValueError,KeyError,TypeError) as err:
        print(json.dumps({
            "status":"BLOCKED","reason":str(err) if isinstance(err,SceneBlocked) else type(err).__name__,
            "provider_calls":0,"provider_dispatch_authorized":False,
        },ensure_ascii=False))
        return 2


if __name__=="__main__":sys.exit(main())
