"""Offline tests with mock backend; no GPU, no weights, no network, no real image claims."""
import contextlib
import io
import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

from tools import reference_guided as rg

GOOD = {"torch": True, "cuda_available": True, "vram_gb": 15.0, "pillow": True, "cv2": True,
        "accelerate": True, "controlnet_img2img_pipeline": True}
CPU_ONLY = dict(GOOD, cuda_available=False, vram_gb=0.0)


def mock_runner(plan, reference):
    # Tiny gray TEST PNG: a MOCK, flagged synthetic, not an illustration.
    return rg.encode_gray_png(8, 8, [[20] * 8] * 8), {"gpu": "MOCK", "model_revision": "mock", "synthetic_mock": True}


class ReferenceGuidedTests(unittest.TestCase):
    def setUp(self):
        t = tempfile.TemporaryDirectory()
        self.addCleanup(t.cleanup)
        self.root = Path(t.name)
        self.ref = self.root / "ref.bin"
        self.ref.write_bytes(b"private reference bytes")
        self.plan = rg.build_plan(reference=self.ref, out_root=self.root)
        self.out = Path(self.plan["output_dir"])

    def test_mode_selection_and_reference_hash(self):
        self.assertEqual(self.plan["mode"], rg.MODE_IMG2IMG)
        self.assertEqual(self.plan["references"][0]["sha256"], rg.sha256(b"private reference bytes"))
        self.assertEqual(self.plan["strength"], 0.3)
        self.assertFalse(self.plan["accepted"])
        self.assertEqual(self.plan, rg.build_plan(reference=self.ref, out_root=self.root))
        self.assertEqual(rg.build_plan(out_root=self.root)["mode"], rg.MODE_BLOCKED)

    def test_no_reference_blocks_real_generation_without_lock(self):
        plan = rg.build_plan(out_root=self.root)
        result = rg.generate_one(plan, True, runner=mock_runner, env=GOOD)
        self.assertEqual(result["status"], "BLOCKED")
        self.assertIn("reference_image_present", result["reason"])
        self.assertFalse((Path(plan["output_dir"]) / "attempt.lock").exists())

    def test_cpu_only_blocks_and_does_not_consume_lock(self):
        result = rg.generate_one(self.plan, True, str(self.ref), runner=mock_runner, env=CPU_ONLY)
        self.assertEqual(result["status"], "BLOCKED")
        self.assertIn("cuda_available", result["reason"])
        self.assertFalse((self.out / "attempt.lock").exists())

    def test_insufficient_vram_and_missing_deps_and_pipeline_block(self):
        for bad in (dict(GOOD, vram_gb=4.0), dict(GOOD, cv2=False), dict(GOOD, controlnet_img2img_pipeline=False)):
            self.assertFalse(rg.preflight(self.plan, allow_generate=True, env=bad)["can_generate"])

    def test_probe_environment_reports_cpu_honestly(self):
        fake = mock.MagicMock()
        fake.cuda.is_available.return_value = False
        with mock.patch.dict("sys.modules", {"torch": fake}):
            env = rg.probe_environment()
        self.assertTrue(env["torch"])
        self.assertFalse(env["cuda_available"])
        self.assertEqual(env["vram_gb"], 0.0)

    def test_requires_explicit_permission(self):
        self.assertEqual(rg.generate_one(self.plan, False, str(self.ref), runner=mock_runner, env=GOOD)["status"], "BLOCKED")
        self.assertFalse((self.out / "candidate.png").exists())

    def test_one_attempt_only_and_never_accepted(self):
        first = rg.generate_one(self.plan, True, str(self.ref), runner=mock_runner, env=GOOD)
        self.assertEqual(first["status"], "GENERATED_UNAPPROVED")
        self.assertFalse(first["accepted"])
        self.assertTrue(first["synthetic_mock"])
        self.assertEqual(first["billing"], "unknown")
        self.assertEqual(rg.generate_one(self.plan, True, str(self.ref), runner=mock_runner, env=GOOD)["status"], "BLOCKED")

    def test_failure_is_locked_not_retried(self):
        calls = []

        def boom(*a):
            calls.append(1)
            raise RuntimeError("oom")
        self.assertEqual(rg.generate_one(self.plan, True, str(self.ref), runner=boom, env=GOOD)["status"], "FAILED")
        self.assertEqual(rg.generate_one(self.plan, True, str(self.ref), runner=boom, env=GOOD)["status"], "BLOCKED")
        self.assertEqual(len(calls), 1)

    def test_evaluate_advisory_and_export(self):
        rg.generate_one(self.plan, True, str(self.ref), runner=mock_runner, env=GOOD)
        report = rg.evaluate(self.out / "candidate.png")
        self.assertTrue(report["advisory_only"])
        self.assertFalse(report["accepted"])
        self.assertEqual(report["checks"]["actor_count_is_two"], "unknown_requires_human_review")
        exported = rg.export(self.plan)
        self.assertFalse(exported["accepted"])
        with zipfile.ZipFile(exported["zip"]) as zf:
            meta = json.loads(zf.read("metadata.json"))
        self.assertTrue(meta["synthetic_mock"])
        self.assertFalse(meta["accepted"])

    def test_export_without_candidate_fails(self):
        with self.assertRaises(FileNotFoundError):
            rg.export(self.plan)

    def run_cli(self, *args):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rg.main(["all", "--out-root", str(self.root), *args])
        return buf.getvalue()

    def test_cli_default_is_offline_and_blocked(self):
        text = self.run_cli("--reference", str(self.ref))
        self.assertIn("BLOCKED", text)
        self.assertFalse((self.out / "candidate.png").exists())

    def test_cli_all_allow_generate_runs_evaluate_and_export(self):
        with mock.patch.object(rg, "probe_environment", return_value=GOOD), \
                mock.patch.object(rg, "default_runner", mock_runner):
            text = self.run_cli("--reference", str(self.ref), "--allow-generate")
        self.assertIn("GENERATED_UNAPPROVED", text)
        self.assertIn("advisory_only", text)
        self.assertTrue(any(self.out.glob("*-unapproved.zip")))


if __name__ == "__main__":
    unittest.main()
