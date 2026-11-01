import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tools import fal_sh09

SCRIPT = Path(__file__).resolve().parents[1] / "tools" / "fal_sh09.py"

class FalSafetyTests(unittest.TestCase):
    def test_dry_run_does_not_create_ledger_or_contact_network(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            ref = root / "private.png"
            ref.write_bytes(b"not an actual image: dry-run should never decode or upload")
            out = root / "out"
            p = subprocess.run([sys.executable, str(SCRIPT), "--reference", str(ref),
                                "--out-dir", str(out)], capture_output=True, text=True)
            self.assertEqual(p.returncode, 0, p.stderr)
            self.assertIn("DRY RUN", p.stdout)
            self.assertFalse(out.exists())
            self.assertEqual(json.loads(p.stdout.split("DRY RUN")[0])["mode"], "dry-run")

    def test_rejects_over_budget(self):
        with tempfile.TemporaryDirectory() as d:
            ref = Path(d) / "ref.png"
            ref.write_bytes(b"x")
            p = subprocess.run([sys.executable, str(SCRIPT), "--reference", str(ref),
                                "--max-budget-usd", "51"], capture_output=True, text=True)
            self.assertNotEqual(p.returncode, 0)

    def test_paid_requires_secret_without_network(self):
        with tempfile.TemporaryDirectory() as d:
            ref = Path(d) / "ref.png"
            ref.write_bytes(b"x")
            env = dict(__import__("os").environ)
            env.pop("FAL_KEY", None)
            p = subprocess.run([sys.executable, str(SCRIPT), "--reference", str(ref),
                                "--authorize-paid"], env=env, capture_output=True, text=True)
            self.assertNotEqual(p.returncode, 0)
            self.assertIn("FAL_KEY", p.stderr)
            self.assertFalse((Path(d) / "local-output").exists())

    def test_paid_one_shot_mocked_no_real_network_and_no_second_charge(self):
        # Exercises the previously untested API request / PNG / ledger path using
        # a completely mocked HTTP transport: never contact fal.ai or bill.
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            private_reference = root / "private_reference.png"
            reference_bytes = bytes.fromhex("89504e470d0a1a0a") + b"private-pixels"
            private_reference.write_bytes(reference_bytes)
            out = root / "out"
            requested = []

            def fake_urlopen(req, timeout=None):
                requested.append(req)
                if len(requested) == 1:
                    self.assertEqual(req.full_url, fal_sh09.ENDPOINT)
                    self.assertEqual(req.get_method(), "POST")
                    self.assertIn("Key dummy-secret-do-not-use", req.get_header("Authorization"))
                    payload = json.loads(req.data.decode("utf-8"))
                    self.assertEqual(len(payload["image_urls"]), 1)
                    self.assertTrue(payload["image_urls"][0].startswith("data:image/png;base64,"))
                    self.assertEqual(payload["image_size"], {"width": 1280, "height": 720})
                    self.assertEqual(payload["output_format"], "png")
                    return io.BytesIO(json.dumps({"images": [{"url": "https://images.example.invalid/mock.png"}], "seed": 12345}).encode("utf-8"))
                self.assertEqual(req, "https://images.example.invalid/mock.png")
                return io.BytesIO(bytes.fromhex("89504e470d0a1a0a") + b"fake-output-only")

            args = ["fal_sh09.py", "--reference", str(private_reference),
                    "--out-dir", str(out), "--authorize-paid"]
            with mock.patch.object(sys, "argv", args), \
                 mock.patch.dict(os.environ, {"FAL_KEY": "dummy-secret-do-not-use"}), \
                 mock.patch("urllib.request.urlopen", side_effect=fake_urlopen):
                self.assertEqual(fal_sh09.main(), 0)
                self.assertEqual(len(requested), 2)
                ledger = json.loads((out / "ledger.json").read_text("utf-8"))
                self.assertEqual(ledger["status"], "image_received_unreviewed")
                self.assertEqual(ledger["provider_seed"], 12345)
                self.assertIsNone(ledger["actual_provider_charge_usd"])
                self.assertTrue((out / "SH09_fal_unreviewed.png").exists())
                self.assertNotIn("dummy-secret", (out / "ledger.json").read_text("utf-8"))
                # Re-running in the same directory must be stopped BEFORE any HTTP call.
                with self.assertRaises(SystemExit):
                    fal_sh09.main()
                self.assertEqual(len(requested), 2)

    def test_paid_failure_keeps_uncertain_reservation_without_retry(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            reference = root / "private_reference.png"
            reference.write_bytes(bytes.fromhex("89504e470d0a1a0a") + b"dummy")
            out = root / "out"
            with mock.patch.object(sys, "argv", ["fal_sh09.py", "--reference", str(reference),
                                                  "--out-dir", str(out), "--authorize-paid"]), \
                 mock.patch.dict(os.environ, {"FAL_KEY": "dummy-key"}), \
                 mock.patch("urllib.request.urlopen", side_effect=TimeoutError("mock timeout")) as http:
                self.assertEqual(fal_sh09.main(), 1)
                self.assertEqual(http.call_count, 1)
                ledger = json.loads((out / "ledger.json").read_text("utf-8"))
                self.assertEqual(ledger["status"], "submitted_or_unknown")
                with self.assertRaises(SystemExit):
                    fal_sh09.main()
                self.assertEqual(http.call_count, 1)

if __name__ == "__main__":
    unittest.main()
