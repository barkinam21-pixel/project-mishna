"""Reference-guided single-image pipeline for SH09 (tooling only; nothing here approves art).

Phases: plan -> preflight -> generate-one -> evaluate -> export.  Default is an OFFLINE
dry run: no network, no GPU, no weights, no spend.  Real generation needs --allow-generate
plus an authorized, user-run GPU environment, and is capped at ONE attempt (a lock file
blocks any retry).  Outputs live in git-ignored private-media/.  accepted is always false.
Backend: SDXL base + ControlNet (canny/line layout map, Apache-2.0 weights) via diffusers
img2img, optional IP-Adapter reference.  See docs/reference-guided-image-pipeline.md.
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
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
BACKEND = {
    "name": "sdxl-controlnet-canny-img2img",
    "base_model": "stabilityai/stable-diffusion-xl-base-1.0",
    "controlnet": "diffusers/controlnet-canny-sdxl-1.0",
    "controlnet_license": "Apache-2.0 (verify on model card before use)",
    "ip_adapter": "h94/IP-Adapter (optional, only when a reference image is supplied)",
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
        setting="modest ancient stone courtyard house", door_side="left",
        lamp="amber oil lamp at door", width=size["width"], height=size["height"])


# ---- layout map (conditioning input made by code; NOT an illustration) ----
def png_chunk(kind, payload):
    return struct.pack(">I", len(payload)) + kind + payload + struct.pack(">I", zlib.crc32(kind + payload) & 0xffffffff)


def encode_gray_png(width, height, rows):
    raw = b"".join(b"\x00" + bytes(r) for r in rows)
    return (PNG_SIGNATURE + png_chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 0, 0, 0, 0))
            + png_chunk(b"IDAT", zlib.compress(raw, 9)) + png_chunk(b"IEND", b""))


def layout_map(c):
    """Deterministic line-art layout: house wall, doorway, two figures, ground line."""
    w, h = c.width, c.height
    px = [[0] * w for _ in range(h)]

    def box(x0, y0, x1, y1):
        x0, x1 = max(0, x0), min(w - 1, x1)
        y0, y1 = max(0, y0), min(h - 1, y1)
        for x in range(x0, x1 + 1):
            px[y0][x] = px[y1][x] = 255
        for y in range(y0, y1 + 1):
            px[y][x0] = px[y][x1] = 255

    ground = int(h * 0.78)
    box(int(w * .03), int(h * .12), int(w * .97), ground)           # house wall
    dx = int(w * .10) if c.door_side == "left" else int(w * .72)
    box(dx, int(h * .30), dx + int(w * .16), ground)                # doorway
    box(dx - 8, int(h * .26), dx + int(w * .16) + 8, int(h * .30))  # lintel
    for fx in (int(w * .38), int(w * .52)):                         # two adult figures
        fw = int(w * .08)
        box(fx, int(h * .34), fx + fw, ground + int(h * .17))
        box(fx + fw // 4, int(h * .26), fx + fw * 3 // 4, int(h * .34))  # head
    for x in range(w):
        px[ground][x] = 255
    return encode_gray_png(w, h, px)


# ---- phases ----
def build_plan(shot_id="SH09", pack_path=PACK, reference=None, out_root=OUT_ROOT):
    pack, shot = load_shot(shot_id, pack_path)
    c = constraints_for(shot, pack)
    layout = layout_map(c)
    refs = []
    if reference:
        refs.append({"basename": Path(reference).name, "sha256": file_sha256(reference)})
    return {
        "schema_version": 1, "shot_id": shot_id, "constraints": dataclasses.asdict(c),
        "backend": BACKEND, "seed": shot["seed"], "max_generation_attempts": 1,
        "prompt": shot["render_lead"], "style": shot.get("render_style", pack["render_style"]),
        "negative_prompt": shot.get("render_negative_prompt", pack["render_negative_prompt"]),
        "guidance_scale": shot.get("guidance_scale", 6.0), "steps": 24,
        "layout_map_sha256": sha256(layout), "references": refs,
        "output_dir": str(Path(out_root) / shot_id),
        "accepted": False, "private": True,
    }, layout


def preflight(plan, pack_path=PACK, allow_generate=False, modules=None):
    pack = json.loads(Path(pack_path).read_text(encoding="utf-8"))
    present = modules if modules is not None else {
        m: importlib.util.find_spec(m) is not None for m in ("torch", "diffusers", "transformers")}
    out = Path(plan["output_dir"])
    checks = [
        Check("prompt_pack", plan["shot_id"] in {s["shot_id"] for s in pack["shots"]}, "shot present in prompt pack"),
        Check("spend_zero", pack.get("monetary_spend_authorized_usd") == 0, "external spend authorization must be 0"),
        Check("license_recorded", "RAIL" in pack.get("model_license", ""), "base model license noted; confirm before release"),
        Check("single_attempt", plan["max_generation_attempts"] == 1, "automatic attempts capped at one"),
        Check("no_prior_attempt", not (out / "attempt.lock").exists(), "no earlier attempt lock; retries need explicit manual cleanup"),
        Check("references_hashed", all(len(r["sha256"]) == 64 for r in plan["references"]), "reference inputs hashed, never uploaded"),
    ]
    gpu = {m: bool(v) for m, v in present.items()}
    gpu_ok = all(gpu.get(m) for m in ("torch", "diffusers", "transformers"))
    checks.append(Check("gpu_stack_importable", gpu_ok, f"modules: {gpu}; VRAM >= {BACKEND['min_vram_gb']} GB and quota are unknown offline"))
    offline_ok = all(c.ok for c in checks if c.name != "gpu_stack_importable")
    return {
        "offline_ok": offline_ok,
        "can_generate": offline_ok and gpu_ok and allow_generate,
        "generation_blocked_reason": None if offline_ok and gpu_ok and allow_generate else
        "no explicit --allow-generate" if not allow_generate else "preflight failed or GPU stack missing",
        "checks": [dataclasses.asdict(c) for c in checks],
        "remaining_usage": "unknown",
    }


def write_plan(plan, layout):
    out = Path(plan["output_dir"])
    out.mkdir(parents=True, exist_ok=True)
    (out / "layout-map.png").write_bytes(layout)
    (out / "plan.json").write_text(json.dumps(plan, indent=2, ensure_ascii=False), encoding="utf-8")


def default_runner(plan, layout, reference):  # pragma: no cover - needs GPU and weights
    import io
    import torch
    from diffusers import ControlNetModel, StableDiffusionXLControlNetPipeline
    from PIL import Image
    cn = ControlNetModel.from_pretrained(plan["backend"]["controlnet"], torch_dtype=torch.float16)
    pipe = StableDiffusionXLControlNetPipeline.from_pretrained(
        plan["backend"]["base_model"], controlnet=cn, torch_dtype=torch.float16).to("cuda")
    kwargs = {}
    if reference:
        pipe.load_ip_adapter("h94/IP-Adapter", subfolder="sdxl_models", weight_name="ip-adapter_sdxl.bin")
        kwargs["ip_adapter_image"] = Image.open(reference).convert("RGB")
    image = pipe(
        prompt=plan["prompt"], prompt_2=plan["style"], negative_prompt=plan["negative_prompt"],
        image=Image.open(io.BytesIO(layout)).convert("RGB"), width=plan["constraints"]["width"],
        height=plan["constraints"]["height"], num_inference_steps=plan["steps"],
        guidance_scale=plan["guidance_scale"], controlnet_conditioning_scale=0.6,
        generator=torch.Generator("cuda").manual_seed(plan["seed"]), **kwargs).images[0]
    buf = io.BytesIO()
    image.save(buf, "PNG")
    return buf.getvalue(), {"gpu": torch.cuda.get_device_name(0), "model_revision": "unknown"}


def generate_one(plan, layout, allow_generate=False, reference=None, runner=None, pack_path=PACK, modules=None):
    """Exactly one attempt; never retries; never marks accepted."""
    report = preflight(plan, pack_path, allow_generate, modules)
    if not report["can_generate"]:
        return {"status": "BLOCKED", "reason": report["generation_blocked_reason"], "preflight": report}
    out = Path(plan["output_dir"])
    write_plan(plan, layout)
    (out / "attempt.lock").write_text(time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), encoding="utf-8")
    start = time.monotonic()
    try:
        data, info = (runner or default_runner)(plan, layout, reference)
    except Exception as exc:  # recorded, never retried
        result = {"status": "FAILED", "error": f"{type(exc).__name__}: {exc}", "attempts": 1}
        (out / "attempt-result.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
        return result
    (out / "candidate.png").write_bytes(data)
    record = {
        "status": "GENERATED_UNAPPROVED", "attempts": 1, "image_sha256": sha256(data),
        "seed": plan["seed"], "backend": plan["backend"]["name"], "base_model": plan["backend"]["base_model"],
        "controlnet": plan["backend"]["controlnet"], "model_revision": info.get("model_revision", "unknown"),
        "gpu": info.get("gpu", "unknown"), "duration_seconds_measured": round(time.monotonic() - start, 1),
        "layout_map_sha256": plan["layout_map_sha256"], "references": plan["references"],
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
    plan, layout = build_plan(a.shot, reference=a.reference, out_root=a.out_root)
    write_plan(plan, layout)
    if a.phase == "plan":
        print(json.dumps(plan, indent=2, ensure_ascii=False))
    elif a.phase in ("preflight", "all"):
        print(json.dumps(preflight(plan, allow_generate=a.allow_generate), indent=2))
    if a.phase in ("generate-one", "all") and (a.phase == "generate-one" or a.allow_generate):
        print(json.dumps(generate_one(plan, layout, a.allow_generate, a.reference), indent=2))
    if a.phase == "evaluate":
        print(json.dumps(evaluate(Path(plan["output_dir"]) / "candidate.png"), indent=2))
    if a.phase == "export":
        print(json.dumps(export(plan), indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
