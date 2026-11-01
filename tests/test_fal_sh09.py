import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

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

if __name__ == "__main__":
    unittest.main()
