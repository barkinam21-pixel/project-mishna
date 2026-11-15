"""Offline unit tests for owner-only signed M3 status probe."""
import hashlib
import hmac
import io
import json
import unittest
from unittest import mock
from tools import m3_owner_status_probe as m

KEY = "ab" * 32


class Response:
    status = 200
    def __enter__(self): return self
    def __exit__(self, *args): return False
    def read(self, n): return b'{"status":"NOT_INITIALIZED","live_dispatch_enabled":false}'


class Transport:
    def __init__(self): self.requests = []
    def open(self, req, timeout):
        self.requests.append((req, timeout))
        return Response()


class M3ProbeTests(unittest.TestCase):
    def test_exact_hmac_signature(self):
        body, headers = m.prepare_status("EP-P07", KEY, timestamp="2026-11-15T00:00:00Z")
        self.assertEqual(json.loads(body)["operation"], "status")
        self.assertEqual(json.loads(body)["payload"], {})
        message = b"POST\n/m3/v1/offline\n2026-11-15T00:00:00Z\n" + body
        self.assertEqual(headers["X-M3-Signature"],
                         hmac.new(bytes.fromhex(KEY), message, hashlib.sha256).hexdigest())

    def test_only_https_worker_root_accepted(self):
        self.assertEqual(m.safe_url("https://private.workers.dev"),
                         "https://private.workers.dev/m3/v1/offline")
        for bad in ["http://private.workers.dev", "https://evil.example",
                    "https://a.workers.dev/other", "https://user@a.workers.dev",
                    "https://a.workers.dev?secret=x", "https://127.0.0.1"]:
            with self.subTest(bad=bad), self.assertRaises(m.M3ProbeBlocked):
                m.safe_url(bad)

    def test_missing_key_and_invalid_scene_denied(self):
        for scene, key in [("EP-P07", ""), ("EP-P07", "zz"*32), ("../bad", KEY)]:
            with self.assertRaises(m.M3ProbeBlocked):
                m.prepare_status(scene, key)

    def test_offline_default_never_opens_network(self):
        with mock.patch.object(m, "probe_status", side_effect=AssertionError("NETWORK")):
            with mock.patch("sys.stdout", new_callable=io.StringIO) as output:
                self.assertEqual(m.main([]), 0)
                self.assertIn("DRY_RUN_NO_NETWORK", output.getvalue())

    def test_readonly_request_never_grants_inference(self):
        t = Transport()
        out = m.probe_status("https://private.workers.dev", "EP-P07", KEY, transport=t)
        self.assertEqual(out["status"], "M3_STATUS_READ_ONLY")
        self.assertFalse(out["authorization_to_generate"])
        self.assertFalse(out["live_dispatch_enabled"])
        self.assertEqual(len(t.requests), 1)
        self.assertEqual(t.requests[0][0].get_header("User-agent"),
                         "Mishnah-M3-PrivateRunner/1")
        self.assertEqual(t.requests[0][0].get_method(), "POST")
        self.assertEqual(json.loads(t.requests[0][0].data)["operation"], "status")


if __name__ == "__main__":
    unittest.main()
