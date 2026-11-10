"""No network, Modal import, provider upload, GPU, or private references in tests."""
import base64
import hashlib
import os
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

from tools.modal_image_backend import ModalBlocked, ModalKleinClient, MODEL

REV = "a" * 40
ENVS = {
    "MODAL_TOKEN_ID": "unit-test-token-id",
    "MODAL_TOKEN_SECRET": "unit-test-secret",
    "MODAL_PRIVATE_RUNTIME_VERIFIED": "true",
    "MODAL_HARD_CAP_VERIFIED": "true",
    "MODAL_REFERENCE_TRANSFER_APPROVED": "true",
    "MODAL_ONE_SHOT_APPROVED": "true",
}


def backend(**safety):
    opts = dict(private_runtime_verified=True,
                provider_hard_spend_cap_verified=True, license_verified=True,
                reference_transfer_approved=True)
    opts.update(safety)
    return dict(type="modal", revision=REV, safety=opts)


def spec(sha):
    return {
        "model": {"id": MODEL},
        "size": [1024, 576],
        "seed": 73002,
        "style": "cinematic painterly",
        "prompt": "two small travelers viewed from behind",
        "characters": {},
        "references": [{"sha256": sha}],
    }


class ModalIndependentBackendTests(unittest.TestCase):
    def test_manifest_registered_but_not_authorized(self):
        import json
        m = json.loads(Path("episodes/berakhot-01-01/comfy-opening-images.json").read_text())
        self.assertEqual(m["available_backends"]["modal"]["type"], "modal")
        self.assertIsNone(m["available_backends"]["modal"]["revision"])
        self.assertIs(m["authorization"]["generation_approved"], False)

    def test_missing_model_revision_blocks(self):
        c = ModalKleinClient(dict(backend(), revision=None))
        with patch.dict(os.environ, ENVS, clear=True):
            with self.assertRaisesRegex(ModalBlocked, "REVISION_NOT_PINNED"):
                c.readiness(spec("b" * 64))

    def test_missing_env_gate_blocks(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(ModalBlocked, "ENV_GATE"):
                ModalKleinClient(backend()).readiness(spec("b" * 64))

    def test_string_true_cannot_bypass_safety_boolean(self):
        with patch.dict(os.environ, ENVS, clear=True):
            with self.assertRaisesRegex(ModalBlocked, "SAFETY_GATE"):
                ModalKleinClient(backend(private_runtime_verified="true")).readiness(spec("b" * 64))

    def test_preparation_checks_bytes_and_never_persists_them_in_workflow(self):
        raw = b"verified-private-image-test-bytes"
        digest = hashlib.sha256(raw).hexdigest()
        with tempfile.TemporaryDirectory() as temp, patch.dict(os.environ, ENVS, clear=True):
            f = Path(temp) / "ref.png"
            f.write_bytes(raw)
            client = ModalKleinClient(backend())
            workflow = client.prepare(spec(digest), [f])
            self.assertEqual(workflow["reference_sha256"], [digest])
            self.assertNotIn("image_base64", str(workflow))
            self.assertNotIn(base64.b64encode(raw).decode(), str(workflow))
            f.write_bytes(b"modified-image")
            with self.assertRaisesRegex(ModalBlocked, "HASH_MISMATCH"):
                ModalKleinClient(backend()).prepare(spec(digest), [f])

    def test_no_submission_without_explicit_runtime_authorization(self):
        raw = b"image-pixels"
        digest = hashlib.sha256(raw).hexdigest()
        with tempfile.TemporaryDirectory() as temp, patch.dict(os.environ, ENVS, clear=True):
            f = Path(temp) / "ref.png"
            f.write_bytes(raw)
            client = ModalKleinClient(backend())
            workflow = client.prepare(spec(digest), [f])
            with self.assertRaisesRegex(ModalBlocked, "NOT_AUTHORIZED"):
                client.submit(workflow, zero_cost_verified=False, authorized=True)
            self.assertIsNotNone(client._reference_bytes)

    def test_mocked_remote_one_call_and_provenance(self):
        raw = b"reference"
        digest = hashlib.sha256(raw).hexdigest()
        image = b"fake-output-png"
        image_hash = hashlib.sha256(image).hexdigest()
        received = []
        class Remote:
            def remote(self, payload):
                received.append(payload)
                return dict(status="IMAGE_RETURNED", model=MODEL, model_revision=REV,
                            reference_sha256=[digest], native_sha256=image_hash,
                            seed=73002, image_base64=base64.b64encode(image).decode())
        fake_modal = types.SimpleNamespace(Function=types.SimpleNamespace(
            from_name=lambda app, fn: Remote()))
        with tempfile.TemporaryDirectory() as temp, patch.dict(os.environ, ENVS, clear=True):
            f = Path(temp) / "ref.png"
            f.write_bytes(raw)
            client = ModalKleinClient(backend())
            workflow = client.prepare(spec(digest), [f])
            with patch.dict(sys.modules, {"modal": fake_modal}):
                history = client.wait(client.submit(workflow, zero_cost_verified=True, authorized=True))
            self.assertEqual(len(received), 1)
            self.assertEqual(received[0]["references"][0]["sha256"], digest)
            result = client.result(history)
            self.assertEqual(client.download(result), image)
            bad = dict(history, reference_sha256=["0" * 64])
            with self.assertRaisesRegex(ModalBlocked, "PROVENANCE"):
                client.result(bad)

    def test_response_checksum_failure_blocks(self):
        client = ModalKleinClient(backend())
        bad = {"image_base64": base64.b64encode(b"not-approved").decode(),
               "receipt": {"native_sha256": "0" * 64}}
        with self.assertRaisesRegex(ModalBlocked, "CHECKSUM_MISMATCH"):
            client.download(bad)


if __name__ == "__main__":
    unittest.main()
