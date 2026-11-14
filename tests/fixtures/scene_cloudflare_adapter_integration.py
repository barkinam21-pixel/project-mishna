"""Contract test against the EXACT pinned private engine code, never its network.

Usage after checked-out reviewed-runtime and Pillow installed:
 python tests/fixtures/scene_cloudflare_adapter_integration.py reviewed-runtime

A synthetic PNG is used only to exercise the old CloudflareClient.prepare API.
No token, hosted model or real project media is opened or submitted.
"""
import copy
import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image
# This script is invoked as a file, not via -m: add repo root explicitly.
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from tools.scene_factory import load
from tools.scene_production_packet import build_packet
from tools.scene_cloudflare_spec_adapter import compile_previews

ROOT=Path(__file__).resolve().parents[2]
PINNED=Path(sys.argv[1]).resolve()
assert PINN.is_dir() and (PINN/"tools/cloudflare_image_backend.py").is_file()
manifest=load(ROOT/"episodes/berakhot-01-01/scene-prologue-v02.json")
bible=load(ROOT/manifest["bible"]["path"])
packet=build_packet(manifest,bible,ROOT)
legacy=load(PINNED/"episodes/berakhot-01-01/comfy-opening-images.json")
original=compile_previews(packet,legacy,ROOT)
assert original["job_count"]==15 and not original["provider_dispatch_authorized"]
assert original["provider_calls"]==0
assert original["native_legacy_engine_compatible"] is False
assert original["reference_status"]==["PRIVATE_REFERENCE_NOT_RESTORED"]

with tempfile.TemporaryDirectory(prefix="mishnah-offline-fixture-") as tmp:
    reference=Path(tmp)/"mock.png"
    Image.new("RGB",(64,64),(80,90,100)).save(reference,"PNG")
    sha=hashlib.sha256(reference.read_bytes()).hexdigest()
    fixture=copy.deepcopy(legacy)
    fixture["references"]=[{
        "path":"private-media/synthetic-only.png",
        "sha256":sha,
        "expected_sha256":sha,
        "synthesis_rights_confirmed":True,
        "role":"OFFLINE_SYNTHETIC_TEST_ONLY",
    }]
    fxroot=Path(tmp)
    p=fxroot/"private-media"/"synthetic-only.png"
    p.parent.mkdir(exist_ok=True)
    p.write_bytes(reference.read_bytes())
    packet_preview=compile_previews(packet,fixture,fxroot)
    assert packet_preview["reference_status"]==["PRIVATE_BYTES_HASH_VERIFIED_ONLY"]
    spec=packet_preview["jobs"][0]["engine_spec_preview"]
    assert "dawn" in spec["prompt"].lower()
    assert "sunset" not in spec["prompt"].lower()
    assert not packet_preview["provider_dispatch_authorized"]

    # Import the old, immutable CloudflareClient and its prompt_text from the
    # pinned checkout in a subprocess; do NOT import the public repo copy.
    checker=r'''
import json,sys
from pathlib import Path
from tools.cloudflare_image_backend import CloudflareClient

class FakeOnlyCloudflareClient(CloudflareClient):
    def readiness(self,spec):
        self.receipt={"OFFLINE_TEST_FIXTURE_ONLY":True}
        return self.receipt
    def submit(self,*args,**kwargs):
        raise AssertionError("PROVIDER_SUBMIT_FORBIDDEN")

inp=json.load(sys.stdin)
c=FakeOnlyCloudflareClient({"safety":{"free_hard_cap_verified":False}})
payload=c.prepare(inp["spec"],[Path(inp["reference"])])
assert payload["width"]==1024 and payload["height"]==576
assert "dawn" in payload["prompt"].lower() and "sunset" not in payload["prompt"].lower()
assert "EP-P01" in payload["prompt"]
assert payload["seed"]==inp["spec"]["seed"]
assert len(c.images)==1 and not c._submission_attempted
assert c.receipt=={"OFFLINE_TEST_FIXTURE_ONLY":True,"references":[
    {"sha256":inp["spec"]["references"][0]["sha256"],"role":"OFFLINE_SYNTHETIC_TEST_ONLY"}]}
print(json.dumps({"status":"PINNED_CLOUDFLARE_PREPARE_MOCK_COMPATIBLE",
 "provider_submit_called":False,"inference_requests":0,
 "synthetic_reference_only":True}))
'''
    outcome=subprocess.run([sys.executable,"-c",checker],
        input=json.dumps({"spec":spec,"reference":str(reference)}),
        cwd=PINNED,text=True,capture_output=True,timeout=25,check=True)
    print(outcome.stdout.strip())
