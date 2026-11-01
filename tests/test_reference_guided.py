"""Offline tests with mock backend; no GPU, no weights, no network, no real image claims."""
import json
import tempfile
import unittest
from pathlib import Path

from tools import reference_guided as rg

ALL = {"torch": True, "diffusers": True, "transformers": True}


def mock_runner(plan, layout, reference):
    # Reuses the layout map as stand-in bytes: a MOCK, not a generated illustration.
    return layout, {"gpu": "MOCK", "model_revision": "mock"}


class ReferenceGuidedTests(unittest.TestCase):
    def setUp(self):
        t = tempfile.TemporaryDirectory()
        self.addCleanup(t.cleanup)
        self.root = Path(t.name)
        self.plan, self.layout = rg.build_plan(out_root=self.root)

    def test_plan_is_deterministic_and_unapproved(self):
        plan2, layout2 = rg.build_plan(out_root=self.root)
        self.assertEqual(self.layout, layout2)
        self.assertEqual(self.plan, plan2)
        self.assertEqual(self.plan["constraints"]["figures"], 2)
        self.assertFalse(self.plan["accepted"])
        self.assertEqual(self.plan["max_generation_attempts"], 1)

    def test_reference_is_hashed(self):
        ref = self.root / "ref.bin"
        ref.write_bytes(b"x")
        plan, _ = rg.build_plan(reference=ref, out_root=self.root)
        self.assertEqual(plan["references"][0]["sha256"], rg.sha256(b"x"))

    def test_offline_default_blocks_generation(self):
        report = rg.preflight(self.plan, modules={})
        self.assertTrue(report["offline_ok"])
        self.assertFalse(report["can_generate"])
        result = rg.generate_one(self.plan, self.layout, runner=mock_runner, modules=ALL)
        self.assertEqual(result["status"], "BLOCKED")
        self.assertFalse((Path(self.plan["output_dir"]) / "candidate.png").exists())

    def test_missing_gpu_stack_blocks_even_with_permission(self):
        result = rg.generate_one(self.plan, self.layout, True, runner=mock_runner, modules={})
        self.assertEqual(result["status"], "BLOCKED")

    def test_one_attempt_only(self):
        first = rg.generate_one(self.plan, self.layout, True, runner=mock_runner, modules=ALL)
        self.assertEqual(first["status"], "GENERATED_UNAPPROVED")
        self.assertFalse(first["accepted"])
        self.assertEqual(first["billing"], "unknown")
        second = rg.generate_one(self.plan, self.layout, True, runner=mock_runner, modules=ALL)
        self.assertEqual(second["status"], "BLOCKED")

    def test_failure_is_not_retried(self):
        calls = []

        def boom(*a):
            calls.append(1)
            raise RuntimeError("oom")
        self.assertEqual(rg.generate_one(self.plan, self.layout, True, runner=boom, modules=ALL)["status"], "FAILED")
        rg.generate_one(self.plan, self.layout, True, runner=boom, modules=ALL)
        self.assertEqual(len(calls), 1)

    def test_evaluate_is_advisory_and_export_stays_unaccepted(self):
        rg.generate_one(self.plan, self.layout, True, runner=mock_runner, modules=ALL)
        report = rg.evaluate(Path(self.plan["output_dir"]) / "candidate.png")
        self.assertTrue(report["advisory_only"])
        self.assertFalse(report["accepted"])
        self.assertEqual(report["checks"]["actor_count_is_two"], "unknown_requires_human_review")
        exported = rg.export(self.plan)
        self.assertFalse(exported["accepted"])
        self.assertTrue(Path(exported["zip"]).exists())

    def test_export_without_candidate_fails(self):
        with self.assertRaises(FileNotFoundError):
            rg.export(self.plan)

    def test_cli_dry_run_end_to_end(self):
        import contextlib
        import io
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            self.assertEqual(rg.main(["all", "--out-root", str(self.root)]), 0)
        self.assertTrue((self.root / "SH09" / "layout-map.png").exists())
        self.assertFalse((self.root / "SH09" / "candidate.png").exists())
        self.assertFalse(json.loads(buf.getvalue())["can_generate"])


if __name__ == "__main__":
    unittest.main()
