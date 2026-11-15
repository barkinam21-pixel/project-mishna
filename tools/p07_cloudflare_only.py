"""Build Cloudflare-only P07 multipart bytes from privately verified originals.

Produces an in-memory, actual FLUX.2 Klein 4B-compatible request BODY; it is
NEVER an authorization to send it. No network client, no hidden provider
fallback, no external-service code, no attempt/reservation changes. Requires
the existing owner-private P07 draft created by scene_p07_private_prepare.py.
"""
from __future__ import annotations
import hashlib
import io
import json
import os
import re
from pathlib import Path

from tools.scene_native_conditioning_preview import NAMES, ROLES, PRIVATE, digest

MODEL = "@cf/black-forest-labs/flux-2-klein-4b"
ENDPOINT = "/ai/run/" + MODEL
MAX_SIDE = 511  # Cloudflare's image-reference constraint: each side < 512
MAX_JPEG_BYTES = 1024 * 1024
SHA = re.compile(r"^[0-9a-f]{64}$")


class P07CloudflareOnlyBlocked(ValueError):
    pass


def _reference_bytes(ref, root, index):
    expected_path = PRIVATE + NAMES[index]
    if (not isinstance(ref, dict)
        or ref.get("path") != expected_path
        or ref.get("role") != ROLES[index]
        or ref.get("synthesis_rights_confirmed") is not False
        or not isinstance(ref.get("sha256"), str)
        or not SHA.fullmatch(ref["sha256"])
        or ref.get("expected_sha256") != ref["sha256"]):
        raise P07CloudflareOnlyBlocked("P07_REFERENCE_SCOPE_OR_RIGHTS_CHANGED")
    path = root / expected_path
    if (path.is_symlink() or not path.is_file()
        or not path.resolve().is_relative_to(root)):
        raise P07CloudflareOnlyBlocked("P07_PRIVATE_REFERENCE_UNSAFE")
    original = path.read_bytes()
    if (hashlib.sha256(original).hexdigest() != ref["sha256"]
        or not original.startswith(b"\xff\xd8\xff")):
        raise P07CloudflareOnlyBlocked("P07_ORIGINAL_IMAGE_SHA_MISMATCH")
    try:
        from PIL import Image, UnidentifiedImageError
    except ImportError:
        raise P07CloudflareOnlyBlocked("P07_PILLOW_REQUIRED_PRIVATE_HOST") from None
    try:
        with Image.open(io.BytesIO(original)) as image:
            if image.format != "JPEG" or image.width * image.height > 35_000_000:
                raise P07CloudflareOnlyBlocked("P07_REFERENCE_IMAGE_FORMAT_OR_SIZE_INVALID")
            image = image.convert("RGB")
            image.thumbnail((MAX_SIDE, MAX_SIDE), Image.Resampling.LANCZOS)
            if not (0 < image.width <= MAX_SIDE and 0 < image.height <= MAX_SIDE):
                raise P07CloudflareOnlyBlocked("P07_REFERENCE_RESIZE_FAILED")
            shape = [image.width, image.height]
            buf = io.BytesIO()
            image.save(buf, format="JPEG", quality=89, optimize=True)
            reduced = buf.getvalue()
    except P07CloudflareOnlyBlocked:
        raise
    except (OSError, ValueError, UnidentifiedImageError) as exc:
        raise P07CloudflareOnlyBlocked("P07_REFERENCE_JPEG_DECODE_FAILED") from exc
    if (not reduced.startswith(b"\xff\xd8\xff") or
        len(reduced) > MAX_JPEG_BYTES):
        raise P07CloudflareOnlyBlocked("P07_REFERENCE_MODEL_INPUT_TOO_LARGE")
    return reduced, shape


def compile_cloudflare_only(draft, owner_root):
    """Compile TRUE JPEG multipart form bytes; never perform an HTTP request.

    This module does not expose a submit function. Separate fresh signed owner
    scope, ref rights and hosted M3 durable admission are still mandatory.
    """
    if os.environ.get("GITHUB_ACTIONS", "").lower() == "true":
        raise P07CloudflareOnlyBlocked("P07_PRIVATE_BYTES_FORBIDDEN_IN_PUBLIC_ACTIONS")
    if not isinstance(draft, dict):
        raise P07CloudflareOnlyBlocked("P07_OWNER_DRAFT_REQUIRED")
    check = draft.get("draft_sha256")
    if (not isinstance(check, str) or not SHA.fullmatch(check)
        or digest({k: v for k, v in draft.items() if k != "draft_sha256"}) != check):
        raise P07CloudflareOnlyBlocked("P07_OWNER_DRAFT_HASH_CHANGED")
    if (draft.get("status") != "DRAFT_OWNER_PRIVATE_CONDITIONING_NOT_APPROVED_NOT_EXECUTABLE"
        or draft.get("shot_id") != "EP-P07"
        or draft.get("candidate_count") != 3
        or draft.get("candidate_reference_filenames") != list(NAMES)
        or draft.get("provider_dispatch_authorized") is not False
        or draft.get("provider_calls") != 0
        or draft.get("rights_for_synthesis") != "NOT_EVALUATED"
        or draft.get("no_automatic_retry") is not True):
        raise P07CloudflareOnlyBlocked("P07_DRAFT_NOT_CLOSED")
    spec = draft.get("proposed_provider_shape")
    if not isinstance(spec, dict):
        raise P07CloudflareOnlyBlocked("P07_MODEL_SPEC_REQUIRED")
    if (spec.get("backend") != {"type": "cloudflare", "model": MODEL}
        or spec.get("size") != [1024, 576]
        or spec.get("model", {}).get("id") != "black-forest-labs/FLUX.2-klein-4B"
        or spec.get("visual_direction", {}).get("owner_conditional_review_only") is not True):
        raise P07CloudflareOnlyBlocked("P07_NOT_EXACT_CLOUDFLARE_4B_PREVIEW")
    director = spec.get("director") or {}
    if (director.get("shot_id") != "EP-P07"
        or director.get("time_of_day") != "dawn"
        or director.get("review_status") != "DRAFT_REQUIRES_REVIEW"
        or director.get("positions") != {"elder": "screen-left", "younger": "screen-right"}
        or director.get("characters_present") != ["elder", "younger"]):
        raise P07CloudflareOnlyBlocked("P07_DAWN_CAST_CHANGED")
    refs = spec.get("references")
    if not isinstance(refs, list) or len(refs) != 3:
        raise P07CloudflareOnlyBlocked("P07_EXPECTS_THREE_PRIVATE_REFERENCES")
    root = Path(owner_root).resolve()
    if not root.is_dir() or (root / "private-media").is_symlink():
        raise P07CloudflareOnlyBlocked("P07_PRIVATE_ROOT_UNSAFE")
    jpeg_and_shapes = [_reference_bytes(ref, root, i) for i, ref in enumerate(refs)]
    prompt = spec.get("prompt")
    if not isinstance(prompt, str) or not prompt.strip() or len(prompt) > 16000:
        raise P07CloudflareOnlyBlocked("P07_PROMPT_INVALID")
    prompt = ("Reference image 0: exact identity of the elder in blue and younger in brown, "
              "and mature painted texture. Reference image 1: rear-wide camera composition. "
              "Reference image 2: winding road, rocky geography and small village. "
              "Use all only as visual references, create a NEW original composition at dawn. "
              + prompt)
    seed = spec.get("seed")
    if type(seed) is not int or seed < 0:
        raise P07CloudflareOnlyBlocked("P07_SEED_INVALID")
    # The earlier draft uses a 64-bit hash; the provider accepts a 32-bit seed.
    provider_seed = seed % 2147483647
    boundary = "mishnah-p07-" + check[:28]
    body = bytearray()
    def add(name, value, *, filename=None, mime=None):
        head = '--' + boundary + '\r\nContent-Disposition: form-data; name="' + name + '"'
        if filename is not None:
            head += '; filename="' + filename + '"'
        head += '\r\n'
        if mime is not None:
            head += 'Content-Type: ' + mime + '\r\n'
        head += '\r\n'
        body.extend(head.encode("ascii"))
        body.extend(value if isinstance(value, bytes) else str(value).encode("utf-8"))
        body.extend(b"\r\n")
    add("prompt", prompt)
    add("width", 1024)
    add("height", 576)
    add("guidance", "1.0")
    add("seed", provider_seed)
    for index, (jpeg, _dims) in enumerate(jpeg_and_shapes):
        add("input_image_" + str(index), jpeg,
            filename="private-reference-" + str(index) + ".jpg", mime="image/jpeg")
    body.extend(("--" + boundary + "--\r\n").encode("ascii"))
    raw = bytes(body)
    report = {
        "status": "CLOUDFLARE_ONLY_REAL_MULTIPART_PREPARED_NOT_SUBMITTED",
        "shot_id": "EP-P07",
        "provider": "Cloudflare Workers AI",
        "model": MODEL,
        "reference_count": 3,
        "reference_dimensions": [dims for _, dims in jpeg_and_shapes],
        "model_input_images_verified": True,
        "request_body_sha256": hashlib.sha256(raw).hexdigest(),
        "draft_sha256": check,
        "no_fallback_provider": True,
        "reference_rights_for_synthesis": "NOT_EVALUATED",
        "provider_dispatch_authorized": False,
        "provider_calls": 0,
        "new_images_generated": 0,
        "requires_next": "HOSTED_ATOMIC_ONE_USE_RESERVATION_AND_REQUEST_SCOPED_RIGHTS",
    }
    return {"body": raw, "content_type": "multipart/form-data; boundary=" + boundary,
            "endpoint_suffix": ENDPOINT, "safe_report": report}


def main(argv=None):
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True)
    parser.add_argument("--private-draft", required=True)
    args = parser.parse_args(argv)
    try:
        p = Path(args.private_draft)
        root = Path(args.root).resolve()
        if (p.is_symlink() or not p.is_file()
            or not p.resolve().is_relative_to(root / "private-media")):
            raise P07CloudflareOnlyBlocked("P07_DRAFT_NOT_PRIVATE")
        draft = json.loads(p.read_text(encoding="utf-8"))
        report = compile_cloudflare_only(draft, root)["safe_report"]
        print(json.dumps(report, sort_keys=True))
        return 0
    except Exception as exc:
        reason = str(exc) if isinstance(exc, P07CloudflareOnlyBlocked) else type(exc).__name__
        print(json.dumps({"status": "BLOCKED", "reason": reason,
                          "provider_calls": 0, "new_images_generated": 0},
                         sort_keys=True))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
