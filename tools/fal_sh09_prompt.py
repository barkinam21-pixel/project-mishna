"""Single paid prompt-only SH09 pilot. Requires explicit workflow approval."""
import json
import os
from pathlib import Path
from urllib.request import Request, urlopen

OUT = Path("local-output/fal-sh09-prompt")
OUT.mkdir(parents=True, exist_ok=True)
ledger = OUT / "attempt.json"
if ledger.exists():
    raise SystemExit("Already attempted. No retries.")
key = os.environ.get("FAL_KEY")
if not key or os.environ.get("CONFIRM") != "YES":
    raise SystemExit("No paid request authorized")
prompt = (
    "Cinematic painterly historical illustration of ancient Judea at dusk. "
    "Two adult brothers stand together on the LEFT of a humble stone courtyard, "
    "speaking quietly. A simple ancient stone doorway is on the RIGHT. "
    "Deep indigo evening sky, amber oil-lamp lighting, realistic textured "
    "woven robes, expressive faces, mature warm illustrated visual style, "
    "wide composition, historically plausible architecture. "
    "No modern buildings, no roof tiles, no extra people, no text."
)
ledger.write_text(json.dumps({"status": "submitted_or_unknown", "count": 1,
                              "actual_charge_usd": None}))
req = Request(
    "https://fal.run/fal-ai/flux-2-pro",
    data=json.dumps({"prompt": prompt, "image_size": "landscape_16_9",
                     "output_format": "png"}).encode(),
    headers={"Authorization": "Key " + key, "Content-Type": "application/json"},
    method="POST",
)
try:
    with urlopen(req, timeout=240) as response:
        data = json.load(response)
    images = data.get("images", [])
    if len(images) != 1 or not images[0].get("url", "").startswith("https://"):
        raise ValueError("Expected one image")
    with urlopen(images[0]["url"], timeout=90) as response:
        blob = response.read(20_000_001)
    if len(blob) > 20_000_000 or not blob.startswith(bytes.fromhex("89504e470d0a1a0a")):
        raise ValueError("Invalid PNG")
    (OUT / "SH09_unreviewed.png").write_bytes(blob)
    ledger.write_text(json.dumps({"status": "image_received_unreviewed",
                                  "count": 1, "actual_charge_usd": None}))
    print("One unreviewed candidate saved.")
except Exception as exc:
    print("Failed or billing uncertain; never retry automatically:", type(exc).__name__)
    raise SystemExit(1)
