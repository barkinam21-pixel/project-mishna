"""Modal FLUX.2 Klein 4B client for the EXISTING Mishnah image queue.

No GPU is provisioned on import, prepare, or dry-run. Synchronous provider
responses are never journaled into state.json. Real submission is fail-closed.
"""
import base64
import hashlib
import os
import re
from pathlib import Path

MODEL = "black-forest-labs/FLUX.2-klein-4B"
PINNED_REVISION = "e7b7dc27f91deacad38e78976d1f2b499d76a294"
APP_NAME = "mishnah-flux2-klein4b"
FUNCTION_NAME = "generate"
HEX40 = re.compile(r"[0-9a-f]{40}\Z")


class ModalBlocked(ValueError):
    pass


class ModalKleinClient:
    engine_name = "Modal FLUX.2 Klein 4B"
    synchronous_response = True

    def __init__(self, backend):
        self.backend = backend
        self._reference_bytes = None
        self._reference_hashes = None

    def readiness(self, spec):
        if self.backend.get("type") != "modal":
            raise ModalBlocked("MODAL_BACKEND_NOT_SELECTED")
        if spec.get("model", {}).get("id") != MODEL:
            raise ModalBlocked("MODAL_MODEL_MISMATCH")
        revision = self.backend.get("revision", "")
        if not isinstance(revision, str) or not HEX40.fullmatch(revision) or revision != PINNED_REVISION:
            raise ModalBlocked("MODAL_MODEL_REVISION_NOT_PINNED")
        safety = self.backend.get("safety", {})
        for key in ("private_runtime_verified", "provider_hard_spend_cap_verified",
                    "license_verified", "reference_transfer_approved"):
            if safety.get(key) is not True:
                raise ModalBlocked("MODAL_SAFETY_GATE_" + key.upper())
        # Environment gate must be explicitly configured on the owner's runner.
        for key in ("MODAL_PRIVATE_RUNTIME_VERIFIED", "MODAL_HARD_CAP_VERIFIED",
                    "MODAL_REFERENCE_TRANSFER_APPROVED", "MODAL_ONE_SHOT_APPROVED"):
            if os.environ.get(key) != "true":
                raise ModalBlocked("MODAL_ENV_GATE_" + key)
        if not os.environ.get("MODAL_TOKEN_ID") or not os.environ.get("MODAL_TOKEN_SECRET"):
            raise ModalBlocked("MODAL_CREDENTIALS_UNAVAILABLE")
        return {"status": "READY_TO_REQUEST_NOT_A_BILLING_GUARANTEE", "provider_requests": 0}

    def prepare(self, spec, reference_paths):
        self.readiness(spec)
        from tools.comfy_scene_images import prompt_text
        prep = spec.get("director", {}).get("reference_preparation")
        if prep is not None:
            expected = [c["sha256"] for c in prep["crops"]]
        else:
            expected = [r["sha256"] for r in spec["references"]]
        if not (1 <= len(reference_paths) <= 4) or len(expected) != len(reference_paths):
            raise ModalBlocked("MODAL_REFERENCE_COUNT_MISMATCH")
        data = []
        for file, expected_hash in zip(reference_paths, expected):
            raw = Path(file).read_bytes()
            if len(raw) > 8 * 1024 * 1024:
                raise ModalBlocked("MODAL_REFERENCE_TOO_LARGE")
            if hashlib.sha256(raw).hexdigest() != expected_hash:
                raise ModalBlocked("MODAL_REFERENCE_HASH_MISMATCH")
            data.append(raw)
        width, height = spec["size"]
        if (width, height) != (1024, 576):
            raise ModalBlocked("MODAL_CANVAS_NOT_APPROVED")
        self._reference_bytes = data
        self._reference_hashes = expected
        # NEVER place private image bytes in this workflow: it is journaled to disk.
        return {
            "model": MODEL,
            "model_revision": self.backend["revision"],
            "prompt": prompt_text(spec),
            "width": width, "height": height,
            "seed": spec["seed"],
            "steps": 4, "guidance": 1.0,
            "reference_sha256": expected,
        }

    def submit(self, workflow, *, zero_cost_verified=False, authorized=False):
        if not (zero_cost_verified is True and authorized is True):
            raise ModalBlocked("MODAL_NOT_AUTHORIZED")
        if self._reference_bytes is None or self._reference_hashes is None:
            raise ModalBlocked("MODAL_REFERENCES_NOT_PREPARED")
        if workflow.get("reference_sha256") != self._reference_hashes:
            raise ModalBlocked("MODAL_REFERENCE_REBIND_BLOCKED")
        # Recheck immediately before transfer; no fallback, retries or paid API.
        self.readiness({"model": {"id": MODEL}})
        payload = dict(workflow)
        payload["references"] = [
            {"sha256": digest, "image_base64": base64.b64encode(raw).decode("ascii")}
            for digest, raw in zip(self._reference_hashes, self._reference_bytes)
        ]
        try:
            import modal
        except ImportError as exc:
            raise ModalBlocked("MODAL_SDK_NOT_INSTALLED") from exc
        self._reference_bytes = None
        # Single synchronous request. Modal function retries are disabled in worker.
        remote = modal.Function.from_name(APP_NAME, FUNCTION_NAME)
        result = remote.remote(payload)
        if not isinstance(result, dict) or result.get("status") != "IMAGE_RETURNED":
            raise ModalBlocked("MODAL_PROVIDER_RESULT_INVALID")
        return result

    def wait(self, response, timeout=300):
        # Never re-submit an uncertain synchronous request.
        return response

    def result(self, history):
        if (history.get("model") != MODEL or
                history.get("model_revision") != self.backend.get("revision") or
                history.get("reference_sha256") != self._reference_hashes):
            raise ModalBlocked("MODAL_PROVENANCE_MISMATCH")
        image = history.get("image_base64")
        if not isinstance(image, str) or len(image) > 24 * 1024 * 1024:
            raise ModalBlocked("MODAL_IMAGE_RESPONSE_INVALID")
        receipt = {key: history.get(key) for key in
                   ("model", "model_revision", "native_sha256", "reference_sha256")}
        return {"image_base64": image, "seed": history.get("seed"), "receipt": receipt}

    def download(self, result):
        try:
            raw = base64.b64decode(result["image_base64"], validate=True)
        except (ValueError, KeyError) as exc:
            raise ModalBlocked("MODAL_IMAGE_BASE64_INVALID") from exc
        if len(raw) > 24 * 1024 * 1024:
            raise ModalBlocked("MODAL_IMAGE_TOO_LARGE")
        expected = result.get("receipt", {}).get("native_sha256")
        if expected and hashlib.sha256(raw).hexdigest() != expected:
            raise ModalBlocked("MODAL_IMAGE_CHECKSUM_MISMATCH")
        return raw
