"""Real autonomous Modal GPU worker, separate from ChatGPT image generation.

Deployment is intentionally manual/explicit: modal deploy tools/modal_flux2_worker.py
No schedules, auto-deploy, auto-retries, or reference persistence.
Never deploy until private-media policy, provider-side spending limit and rights
have been independently verified. Invocations bill compute, even on failures.
"""
import base64
import hashlib
import io
import re

import modal

app = modal.App("mishnah-flux2-klein4b")
MODEL = "black-forest-labs/FLUX.2-klein-4B"
PINNED_REVISION = "e7b7dc27f91deacad38e78976d1f2b499d76a294"

image = (
    modal.Image.debian_slim(python_version="3.11")
    .pip_install(
        "torch>=2.5,<3", "diffusers>=0.36,<1",
        "transformers>=4.46,<6", "accelerate>=1,<2",
        "pillow>=11,<13", "safetensors>=0.4,<1",
    )
)


def validate(payload):
    """Pure gate, runs before any model download or inference."""
    if not isinstance(payload, dict):
        raise ValueError("INVALID_PAYLOAD")
    if payload.get("model") != MODEL or payload.get("model_revision") != PINNED_REVISION:
        raise ValueError("MODEL_OR_REVISION_NOT_PINNED")
    if (payload.get("width"), payload.get("height")) != (1024, 576):
        raise ValueError("CANVAS_LOCK_MISMATCH")
    if (type(payload.get("seed")) is not int or not
            0 <= payload["seed"] < 2**64):
        raise ValueError("INVALID_SEED")
    if payload.get("steps") != 4 or payload.get("guidance") != 1.0:
        raise ValueError("INFERENCE_SETTINGS_LOCK_MISMATCH")
    if not isinstance(payload.get("prompt"), str) or not payload["prompt"].strip():
        raise ValueError("PROMPT_MISSING")
    refs = payload.get("references")
    hashes = payload.get("reference_sha256")
    if not isinstance(refs, list) or not 1 <= len(refs) <= 4 or not isinstance(hashes, list) or len(hashes) != len(refs):
        raise ValueError("REFERENCE_BINDING_INVALID")
    images = []
    from PIL import Image
    for item, expected in zip(refs, hashes):
        if not isinstance(item, dict) or item.get("sha256") != expected:
            raise ValueError("REFERENCE_SHA_MISMATCH")
        try:
            raw = base64.b64decode(item["image_base64"], validate=True)
        except (KeyError, ValueError) as exc:
            raise ValueError("INVALID_REFERENCE_ENCODING") from exc
        if len(raw) > 8 * 1024 * 1024 or hashlib.sha256(raw).hexdigest() != expected:
            raise ValueError("REFERENCE_BYTES_MISMATCH")
        with Image.open(io.BytesIO(raw)) as img:
            img.load()
            images.append(img.convert("RGB"))
    return images


@app.function(gpu="L4", image=image, timeout=600, retries=0, scaledown_window=15,
              min_containers=0, max_containers=1, max_concurrency=1)
def generate(payload):
    images = validate(payload)
    import torch
    from diffusers import Flux2KleinPipeline

    revision = payload["model_revision"]
    pipe = Flux2KleinPipeline.from_pretrained(
        MODEL, revision=revision, torch_dtype=torch.bfloat16
    )
    pipe.enable_model_cpu_offload()
    result = pipe(
        prompt=payload["prompt"],
        image=images,
        width=payload["width"],
        height=payload["height"],
        guidance_scale=1.0,
        num_inference_steps=4,
        generator=torch.Generator(device="cuda").manual_seed(payload["seed"]),
    ).images[0]
    if result.size != (1024, 576):
        raise ValueError("PROVIDER_CANVAS_MISMATCH")
    sink = io.BytesIO()
    result.save(sink, format="PNG")
    native = sink.getvalue()
    return {
        "status": "IMAGE_RETURNED",
        "model": MODEL,
        "model_revision": revision,
        "reference_sha256": payload["reference_sha256"],
        "native_sha256": hashlib.sha256(native).hexdigest(),
        "seed": payload["seed"],
        "image_base64": base64.b64encode(native).decode("ascii"),
    }
