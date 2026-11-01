#!/usr/bin/env python3
"""SH09 fal.ai one-image proof. DRY RUN by default. Python standard library only.

WARNING: local budget reservations are NOT a provider-side hard spending limit.
Do not run concurrent instances, and configure billing controls in fal.ai.
"""
import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import sys
import time
import urllib.request
import urllib.error

MODEL = "fal-ai/flux-2-pro/edit"
ENDPOINT = "https://fal.run/" + MODEL
RESERVATION_USD = 0.25  # Conservative internal allowance, NOT a quoted price.
PROMPT = (
    "Use the supplied reference as the strict visual anchor. Cinematic painterly "
    "historical illustration for an adult Mishnah Berakhot learning film: "
    "two adult brothers on the left in simple historically plausible modest "
    "clothing, approaching a humble stone courtyard doorway on the RIGHT, "
    "night sky, restrained amber oil-lamp illumination, muted indigo shadows, "
    "warm natural expressions, consistent faces and architecture, 16:9 wide shot. "
    "Keep the reference composition, character count, and doorway side. "
    "No modern facades, no signs, no text, no extra people, no photorealism."
)

def atomic_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    temp.replace(path)

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--reference", required=True, type=Path, help="Private PNG/JPEG; never commit")
    p.add_argument("--out-dir", default="local-output/fal-sh09", type=Path)
    p.add_argument("--max-budget-usd", type=float, default=50.0)
    p.add_argument("--authorize-paid", action="store_true",
                   help="EXPLICITLY submit ONE paid request; never used by CI")
    a = p.parse_args()
    if a.max_budget_usd <= 0 or a.max_budget_usd > 50:
        p.error("Budget must be greater than zero and at most $50")
    if not a.reference.is_file():
        p.error("Reference file missing")
    blob = a.reference.read_bytes()
    if len(blob) > 12_000_000:
        p.error("Reference exceeds 12MB")
    suffix = a.reference.suffix.lower()
    if suffix not in (".png", ".jpg", ".jpeg"):
        p.error("Only PNG/JPEG reference supported")
    mime = "image/png" if suffix == ".png" else "image/jpeg"
    plan = {"model": MODEL, "endpoint": ENDPOINT, "scene": "SH09",
            "reference_sha256": hashlib.sha256(blob).hexdigest(),
            "reference_bytes": len(blob), "prompt": PROMPT,
            "output": "one image", "estimated_reservation_usd": RESERVATION_USD,
            "max_project_budget_usd": a.max_budget_usd,
            "mode": "paid-one-shot" if a.authorize_paid else "dry-run",
            "warning": "Reservation is not an exact provider charge or provider-side cap."}
    if not a.authorize_paid:
        print(json.dumps(plan, indent=2, ensure_ascii=False))
        print("DRY RUN: no API request, no payment, no reference upload.")
        return 0
    key = os.environ.get("FAL_KEY", "").strip()
    if not key:
        p.error("FAL_KEY is missing; never paste it into chat or commit it")
    # Only one run per output directory; refuse ambiguous prior attempts.
    ledger = a.out_dir / "ledger.json"
    if ledger.exists():
        p.error("Existing ledger found. Refusing to run again automatically; review manually.")
    if RESERVATION_USD > a.max_budget_usd:
        p.error("Insufficient local project budget for conservative reservation")
    a.out_dir.mkdir(parents=True, exist_ok=True)
    # Reserve BEFORE network call. Any uncertainty remains reserved, never auto-retry.
    atomic_json(ledger, {"status": "submitted_or_unknown", "reserved_usd": RESERVATION_USD,
                         "actual_provider_charge_usd": None, "plan": plan})
    payload = {"prompt": PROMPT,
               "image_urls": ["data:" + mime + ";base64," +
                              base64.b64encode(blob).decode("ascii")],
               "image_size": {"width": 1280, "height": 720},
               "output_format": "png", "enable_safety_checker": True}
    request = urllib.request.Request(
        ENDPOINT, data=json.dumps(payload).encode("utf-8"),
        headers={"Authorization": "Key " + key,
                 "Content-Type": "application/json"}, method="POST")
    started_at = time.monotonic()
    try:
        with urllib.request.urlopen(request, timeout=240) as resp:
            result = json.load(resp)
        urls = [i["url"] for i in result.get("images", [])]
        if len(urls) != 1 or not urls[0].startswith("https://"):
            raise ValueError("Expected one HTTPS image URL")
        # Do not log API keys, reference bytes, or full response.
        with urllib.request.urlopen(urls[0], timeout=90) as img:
            image = img.read(30_000_001)
        if len(image) > 30_000_000 or not image.startswith(bytes.fromhex("89504e470d0a1a0a")):
            raise ValueError("Invalid or oversized PNG result")
        output = a.out_dir / "SH09_fal_unreviewed.png"
        output.write_bytes(image)
        atomic_json(ledger, {"status": "image_received_unreviewed",
                             "reserved_usd": RESERVATION_USD,
                             "actual_provider_charge_usd": None,
                             "image_sha256": hashlib.sha256(image).hexdigest(),
                             "provider_seed": result.get("seed"),
                             "provider_request_id": result.get("request_id"),
                             "model_revision": "unknown (not returned by endpoint)",
                             "elapsed_seconds": round(time.monotonic() - started_at, 3),
                             "plan": plan})
        print("ONE unreviewed image saved:", output)
        print("Review quality and actual provider billing before any next request.")
        return 0
    except Exception as exc:
        print("Request failed or billing outcome uncertain; no automatic retry:", type(exc).__name__, file=sys.stderr)
        return 1

if __name__ == "__main__":
    sys.exit(main())
