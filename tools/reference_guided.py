"""Reference-guided single-image pipeline for SH09 (tooling only; nothing here approves art).

Phases: plan -> preflight -> generate-one -> evaluate -> export.  Default is an OFFLINE
dry run: no network, no GPU, no weights, no spend.  Real generation needs --allow-generate
plus an authorized, user-run GPU environment, and is capped at ONE attempt (a lock file
blocks any retry).  Outputs live in git-ignored private-media/.  accepted is always false.
Backend: SDXL base + ControlNet canny, true image-to-image: the private --reference is the
img2img source and Canny edges are derived from it (low strength). No reference => real
generation is blocked (never a silent prompt-only fallback). GPU/VRAM/CUDA are probed.  See docs/reference-guided-image-pipeline.md.
"""
import argparse
import dataclasses
import hashlib
import importlib.util
import json
from pathlib import Path
import struct
import sys
import time
import zipfile
import zlib

ROOT = Path(__file__).resolve().parents[1]
EPISODE = ROOT / "episodes" / "berakhot-01-01"
PACK = EPISODE / "free-cloud-image-prompts.json"
OUT_ROOT = ROOT / "private-media" / "reference-guided"
STRENGTH = 0.3
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
BACKEND = {
    "name": "sdxl-controlnet-canny-img2img-from-reference",
    "base_model": "stabilityai/stable-diffusion-xl-base-1.0",
    "controlnet": "diffusers/controlnet-canny-sdxl-1.0",
    "controlnet_license": "openrail++ (Hugging Face model card; review requirements before use/release)",
    "ip_adapter": "not enabled (compatibility with this pipeline unverified)",
    "library": "diffusers",
    "min_vram_gb": 12,
    "free_gpu": "Google Colab free T4 (~15 GB) when available; quota is NOT measurable here",
    "copilot_image_feature": "chat/IDE only, no programmatic credentials: manual provider, no adapter built",
}


@dataclasses.dataclass(frozen=True)
class SceneConstraints:
    shot_id: str
    figures: int
    time_of_day: str
    setting: str
    door_side: str
    lamp: str
    width: int
    height: int


@dataclasses.dataclass
class Check:
    name: str
    ok: bool
    detail: str


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def file_sha256(path):
    return sha256(Path(path).read_bytes())


def load_shot(shot_id="SH09", pack_path=PACK):
    pack = json.loads(Path(pack_path).read_text(encoding="utf-8"))
    shot = next(s for s in pack["shots"] if s["shot_id"] == shot_id)
    return pack, shot


def constraints_for(shot, pack):
    size = pack["image_size"]
    return SceneConstraints(
        shot_id=shot["shot_id"], figures=2, time_of_day="night",
        setting="modest ancient stone courtyard house", door_side="right",
        lamp="amber oil lamp at door", width=size["width"], height=size["height"])


# ---- PNG helper (tests build tiny mock PNGs with it; never an illustration) ----
def png_chunk(kind, payload):
    return struct.pack(">I", len(payload)) + kind + payload + struct.pack(">I", zlib.crc32(kind + payload) & 0xffffffff)


def encode_gray_png(width, height, rows):
    raw = b"".join(b"\x00" + bytes(r) for r in rows)
    return (PNG_SIGNATURE + png_chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 0, 0, 0, 0))
            + png_chunk(b"IDAT", zlib.compress(raw, 9)) + png_chunk(b"IEND", b""))


# ---- phases ----
MODE_IMG2IMG = "controlnet_canny_img2img_from_reference"
MODE_BLOCKED = "blocked_no_reference"


def build_plan(shot_id="SH09", pack_path=PACK, reference=None, out_root=OUT_ROOT):
    """Reference present -> img2img mode; absent -> real generation is deliberately blocked."""
    pack, shot = load_shot(shot_id, pack_path)
    c = constraints_for(shot, pack)
    refs = []
    if reference:
        ref = Path(reference)
        refs.append({"basename": ref.name, "sha256": file_sha256(ref) if ref.is_file() else None})
    return {
        "schema_version": 2, "shot_id": shot_id, "constraints": dataclasses.asdict(c),
        "backend": BACKEND, "mode": MODE_IMG2IMG if reference else MODE_BLOCKED,
        "seed": shot["seed"], "max_generation_attempts": 1,
        "prompt": shot["render_lead"], "style": shot.get("render_style", pack["render_style"]),
        "negative_prompt": shot.get("render_negative_prompt", pack["render_negative_prompt"]),
        "guidance_scale": shot.get("guidance_scale", 6.0), "steps": 24,
        "strength": STRENGTH, "controlnet_conditioning_scale": 0.6,
        "references": refs, "output_dir": str(Path(out_root) / shot_id),
        "accepted": False, "private": True,
    }


def probe_environment():
    """Real hardware/dependency probe. Tests inject a dict with the same keys instead."""
    env = {"torch": False, "cuda_available": False, "vram_gb": 0.0, "pillow": False,
           "cv2": False, "accelerate": False, "controlnet_img2img_pipeline": False}
    for name, module in (("pillow", "PIL"), ("cv2", "cv2"), ("accelerate", "accelerate")):
        env[name] = importlib.util.find_spec(module) is not None
    try:
        import torch
        env["torch"] = True
        env["cuda_available"] = bool(torch.cuda.is_available())
        if env["cuda_available"]:
            env["vram_gb"] = round(torch.cuda.get_device_properties(0).total_memory / 2**30, 1)
    except Exception:
        pass
    try:
        import diffusers
        env["controlnet_img2img_pipeline"] = hasattr(diffusers, "StableDiffusionXLControlNetImg2ImgPipeline")
    except Exception:
        pass
    return env


def preflight(plan, pack_path=PACK, allow_generate=False, env=None):
    pack = json.loads(Path(pack_path).read_text(encoding="utf-8"))
    env = probe_environment() if env is None else env
    out = Path(plan["output_dir"])
    refs = plan["references"]
    ref_ok = bool(refs) and all(r["sha256"] and len(r["sha256"]) == 64 for r in refs)
    checks = [
        Check("prompt_pack", plan["shot_id"] in {s["shot_id"] for s in pack["shots"]}, "shot present in prompt pack"),
        Check("spend_zero", pack.get("monetary_spend_authorized_usd") == 0, "external spend authorization must be 0"),
        Check("license_recorded", "RAIL" in pack.get("model_license", ""), "base model license noted; confirm before release"),
        Check("single_attempt", plan["max_generation_attempts"] == 1, "automatic attempts capped at one"),
        Check("no_prior_attempt", not (out / "attempt.lock").exists(), "no earlier attempt lock; retries need explicit manual cleanup"),
    ]
    gates = [
        Check("reference_image_present", ref_ok and plan["mode"] == MODE_IMG2IMG,
              "a private --reference image is required; no silent fallback to prompt-only SDXL"),
        Check("cuda_available", bool(env.get("torch") and env.get("cuda_available")), "torch.cuda.is_available() must be true (CPU is not accepted)"),
        Check("vram_sufficient", env.get("vram_gb", 0) >= BACKEND["min_vram_gb"],
              f"detected {env.get('vram_gb', 0)} GB; need >= {BACKEND['min_vram_gb']} GB"),
        Check("dependencies", all(env.get(k) for k in ("pillow", "cv2", "accelerate")), "Pillow, opencv (Canny) and accelerate required"),
        Check("controlnet_img2img_supported", bool(env.get("controlnet_img2img_pipeline")),
              "installed diffusers must provide StableDiffusionXLControlNetImg2ImgPipeline"),
    ]
    offline_ok = all(c.ok for c in checks)
    gates_ok = all(c.ok for c in gates)
    can = offline_ok and gates_ok and allow_generate
    blocked = None if can else (
        "preflight failed: " + ", ".join(c.name for c in checks + gates if not c.ok) if not (offline_ok and gates_ok)
        else "no explicit --allow-generate")
    return {
        "offline_ok": offline_ok, "can_generate": can, "generation_blocked_reason": blocked,
        "checks": [dataclasses.asdict(c) for c in checks + gates],
        "remaining_usage": "unknown (free Colab quota is not exposed)",
    }


def write_plan(plan):
    out = Path(plan["output_dir"])
    out.mkdir(parents=True, exist_ok=True)
    (out / "plan.json").write_text(json.dumps(plan, indent=2, ensure_ascii=False), encoding="utf-8")


def default_runner(plan, reference):  # pragma: no cover - needs GPU and weights
    import io
    import cv2
    import numpy as np
    import torch
    from diffusers import ControlNetModel, StableDiffusionXLControlNetImg2ImgPipeline
    from PIL import Image
    width, height = plan["constraints"]["width"], plan["constraints"]["height"]
    source = Image.open(reference).convert("RGB").resize((width, height))
    edges = cv2.Canny(np.array(source), 100, 200)
    control = Image.fromarray(np.stack([edges] * 3, axis=-1))
    cn = ControlNetModel.from_pretrained(plan["backend"]["controlnet"], torch_dtype=torch.float16)
    pipe = StableDiffusionXLControlNetImg2ImgPipeline.from_pretrained(
        plan["backend"]["base_model"], controlnet=cn, torch_dtype=torch.float16)
    # Prefer model CPU offload on the free T4: lower peak VRAM, slower but safer.
    # Hugging Face recommends this for SDXL/ControlNet memory pressure.
    pipe.enable_model_cpu_offload()
    image = pipe(
        prompt=plan["prompt"], prompt_2=plan["style"], negative_prompt=plan["negative_prompt"],
        image=source, control_image=control, strength=plan["strength"],
        num_inference_steps=plan["steps"], guidance_scale=plan["guidance_scale"],
        controlnet_conditioning_scale=plan["controlnet_conditioning_scale"],
        generator=torch.Generator("cuda").manual_seed(plan["seed"])).images[0]
    buf = io.BytesIO()
    image.save(buf, "PNG")
    return buf.getvalue(), {"gpu": torch.cuda.get_device_name(0), "model_revision": "unknown"}


def generate_one(plan, allow_generate=False, reference=None, runner=None, pack_path=PACK, env=None):
    """Exactly one attempt; the lock is only taken after preflight passes; never retries or accepts."""
    report = preflight(plan, pack_path, allow_generate, env)
    if not report["can_generate"]:
        return {"status": "BLOCKED", "reason": report["generation_blocked_reason"], "preflight": report}
    out = Path(plan["output_dir"])
    write_plan(plan)
    (out / "attempt.lock").write_text(time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), encoding="utf-8")
    start = time.monotonic()
    try:
        data, info = (runner or default_runner)(plan, reference)
    except Exception as exc:  # recorded, never retried
        result = {"status": "FAILED", "error": f"{type(exc).__name__}: {exc}", "attempts": 1}
        (out / "attempt-result.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
        return result
    (out / "candidate.png").write_bytes(data)
    record = {
        "status": "GENERATED_UNAPPROVED", "attempts": 1, "image_sha256": sha256(data),
        "seed": plan["seed"], "mode": plan["mode"], "backend": plan["backend"]["name"],
        "base_model": plan["backend"]["base_model"], "controlnet": plan["backend"]["controlnet"],
        "strength": plan["strength"], "model_revision": info.get("model_revision", "unknown"),
        "gpu": info.get("gpu", "unknown"), "duration_seconds_measured": round(time.monotonic() - start, 1),
        "references": plan["references"], "synthetic_mock": bool(info.get("synthetic_mock", False)),
        "billing": "unknown", "paid_api_calls": 0, "accepted": False,
    }
    (out / "attempt-result.json").write_text(json.dumps(record, indent=2), encoding="utf-8")
    return record


# ---- advisory evaluation ----
def decode_png_rgb(data):
    if not data.startswith(PNG_SIGNATURE):
        raise ValueError("not a PNG")
    pos, idat, w = 8, [], None
    while pos < len(data):
        n = struct.unpack(">I", data[pos:pos + 4])[0]
        kind, body = data[pos + 4:pos + 8], data[pos + 8:pos + 8 + n]
        if kind == b"IHDR":
            w, h, depth, color = struct.unpack(">IIBB", body[:10])
            if depth != 8 or color not in (0, 2, 6):
                raise ValueError("only 8-bit gray/RGB/RGBA PNG supported")
            bpp = {0: 1, 2: 3, 6: 4}[color]
        elif kind == b"IDAT":
            idat.append(body)
        pos += 12 + n
    raw = zlib.decompress(b"".join(idat))
    stride, prev, rows = w * bpp, bytearray(w * bpp), []
    for y in range(h):
        base = y * (stride + 1)
        f, line = raw[base], bytearray(raw[base + 1:base + 1 + stride])
        for i in range(stride):
            a = line[i - bpp] if i >= bpp else 0
            b = prev[i]
            c = prev[i - bpp] if i >= bpp else 0
            if f == 1:
                line[i] = (line[i] + a) & 255
            elif f == 2:
                line[i] = (line[i] + b) & 255
            elif f == 3:
                line[i] = (line[i] + (a + b) // 2) & 255
            elif f == 4:
                p = a + b - c
                pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
                line[i] = (line[i] + (a if pa <= pb and pa <= pc else b if pb <= pc else c)) & 255
        rows.append(line)
        prev = line
    return w, h, bpp, rows


def evaluate(image_path, constraints=None):
    """Advisory metrics only. Actor count/architecture need human or model review: reported 'unknown'."""
    data = Path(image_path).read_bytes()
    w, h, bpp, rows = decode_png_rgb(data)
    lum = []
    for y in range(0, h, 4):
        r = rows[y]
        lum.extend(r[x] if bpp == 1 else (299 * r[x] + 587 * r[x + 1] + 114 * r[x + 2]) // 1000
                   for x in range(0, w * bpp, 4 * bpp))
    lum.sort()
    mean = sum(lum) / len(lum)
    spread = lum[int(len(lum) * .9)] - lum[int(len(lum) * .1)]
    exp = constraints
    size_ok = exp is None or (w, h) == (exp.width, exp.height)
    return {
        "advisory_only": True, "accepted": False, "image_sha256": sha256(data), "size": [w, h],
        "checks": {
            "size_matches": size_ok,
            "night_like_low_mean_luminance": mean < 110,
            "contrast_p10_p90_adequate": spread >= 40,
            "actor_count_is_two": "unknown_requires_human_review",
            "historical_architecture": "unknown_requires_human_review",
            "scene_focus": "unknown_requires_human_review",
        },
        "mean_luminance": round(mean, 1), "p10_p90_spread": spread,
        "human_approval_required": True,
    }


def export(plan, out_dir=None):
    out = Path(out_dir or plan["output_dir"])
    cand = out / "candidate.png"
    if not cand.exists():
        raise FileNotFoundError("no candidate.png: nothing generated (blocked or not run)")
    meta = json.loads((out / "attempt-result.json").read_text(encoding="utf-8"))
    meta["accepted"] = False
    report = evaluate(cand)
    zpath = out / f"{plan['shot_id']}-reference-guided-unapproved.zip"
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.write(cand, f"{plan['shot_id']}.png")
        zf.writestr("metadata.json", json.dumps(meta, indent=2))
        zf.writestr("advisory-evaluation.json", json.dumps(report, indent=2))
    return {"zip": str(zpath), "zip_sha256": file_sha256(zpath), "accepted": False}


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("phase", choices=["plan", "preflight", "generate-one", "evaluate", "export", "all"], nargs="?", default="all")
    p.add_argument("--shot", default="SH09")
    p.add_argument("--reference", help="private reference image (hashed only, never uploaded)")
    p.add_argument("--out-root", default=str(OUT_ROOT))
    p.add_argument("--allow-generate", action="store_true", help="explicit permission for the single real attempt")
    a = p.parse_args(argv)
    plan = build_plan(a.shot, reference=a.reference, out_root=a.out_root)
    write_plan(plan)
    out = Path(plan["output_dir"])
    if a.phase == "plan":
        print(json.dumps(plan, indent=2, ensure_ascii=False))
    elif a.phase == "preflight":
        print(json.dumps(preflight(plan, allow_generate=a.allow_generate), indent=2))
    elif a.phase == "evaluate":
        print(json.dumps(evaluate(out / "candidate.png"), indent=2))
    elif a.phase == "export":
        print(json.dumps(export(plan), indent=2))
    else:
        result = generate_one(plan, a.allow_generate, a.reference)
        print(json.dumps(result, indent=2))
        # A blocked/failed attempt must fail the CLI too. Colab checks the exit
        # code before exporting; returning 0 could falsely expose a stale ZIP
        # from an earlier successful run in the same runtime.
        if result.get("status") != "GENERATED_UNAPPROVED":
            return 2
        if a.phase == "all":
            print(json.dumps(evaluate(out / "candidate.png"), indent=2))
            print(json.dumps(export(plan), indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
