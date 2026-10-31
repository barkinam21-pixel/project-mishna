"""No-GPU tests for the one-click free-cloud notebook and its visual source pack."""
import ast
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
EP = ROOT / "episodes" / "berakhot-01-01"


class FreeCloudImageNotebookTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.notebook = json.loads((ROOT / "notebooks/free_mishnah_images_colab.ipynb").read_text(encoding="utf-8"))
        cls.pack = json.loads((EP / "free-cloud-image-prompts.json").read_text(encoding="utf-8"))
        cls.blueprint = json.loads((EP / "proof-blueprint.json").read_text(encoding="utf-8"))
        cls.cells = {c.get("metadata", {}).get("id"): c
                     for c in cls.notebook["cells"] if c["cell_type"] == "code"}

    def test_valid_notebook_and_python_syntax(self):
        self.assertEqual(self.notebook["nbformat"], 4)
        self.assertEqual(len(self.cells), 5)
        self.assertEqual(self.notebook["metadata"]["accelerator"], "GPU")
        for name, cell in self.cells.items():
            ast.parse("".join(cell["source"]), filename="notebook:"+str(name))
            self.assertEqual(cell["outputs"], [])
            self.assertIsNone(cell["execution_count"])

    def test_notebook_preflights_gpu_before_models_or_deps(self):
        order = [c.get("metadata", {}).get("id") for c in self.notebook["cells"] if c["cell_type"] == "code"]
        self.assertEqual(order, ["settings", "gpu", "plan", "deps", "render"])
        gpu = "".join(self.cells["gpu"]["source"])
        self.assertIn("torch.cuda.is_available()", gpu)
        self.assertIn("raise RuntimeError", gpu)
        self.assertNotIn("from_pretrained", gpu)
        deps = "".join(self.cells["deps"]["source"])
        self.assertIn("diffusers", deps)

    def test_no_paid_api_or_hf_auth_or_browser_bypass(self):
        source = "\n".join("".join(c["source"]) for c in self.cells.values())
        for term in ("HF_TOKEN", "OPENAI_API_KEY", "STRIPE", "api.replicate.com",
                     "api.runpod.io", "ngrok", "cloudflared", "gradio.launch",
                     "autoclick", "selenium"):
            self.assertNotIn(term, source)
        self.assertIn("BATCH = \"איור ניסיון אחד\"", source)
        self.assertIn("AUTO_DOWNLOAD_ZIP = True", source)
        self.assertIn("paid_api_calls\": 0", source)
        self.assertIn("external_cash_spend_initiated_usd\": 0", source)

    def test_prompt_pack_matches_every_planned_shot(self):
        pack_ids = [s["shot_id"] for s in self.pack["shots"]]
        plan_ids = [s["id"] for s in self.blueprint["shots"]]
        self.assertEqual(pack_ids, plan_ids)
        for source, shot in zip(self.blueprint["shots"], self.pack["shots"]):
            self.assertEqual(source["scene_id"], shot["scene_id"])
            self.assertFalse(shot["accepted"])
            self.assertFalse(shot["generated"])
            self.assertTrue(shot["shot_prompt"].strip())
            self.assertIsInstance(shot["seed"], int)
            self.assertGreater(shot["seed"], 0)

    def test_release_gates_and_license_not_silently_enabled(self):
        self.assertFalse(self.pack["torah_review_approved"])
        self.assertFalse(self.pack["public_release_authorized"])
        self.assertFalse(self.pack["source_lock"])
        self.assertFalse(self.pack["visual_direction_approved"])
        self.assertEqual(self.pack["monetary_spend_authorized_usd"], 0)
        self.assertEqual(self.pack["model_id"], "stabilityai/stable-diffusion-xl-base-1.0")
        self.assertIn("Open RAIL", self.pack["model_license"])
        self.assertNotIn("Public Domain", self.pack["model_license"])

    def test_ledger_records_one_line_per_generated_image_and_zip(self):
        source = "".join(self.cells["render"]["source"])
        self.assertIn('LEDGER.open("a", encoding="utf-8")', source)
        self.assertIn('json.dumps(record, ensure_ascii=False)+"\\n"', source)
        self.assertIn("save_zip()  # Preserve progress after each generated image.", source)
        self.assertIn("prompt-pack-snapshot.json", source)
        self.assertIn('"accepted": False', source)
        self.assertIn('"public_release_authorized": False', source)

    def test_batch_options_include_full_original_scene_pack(self):
        source = "".join(self.cells["plan"]["source"])
        for shot in ("SH09", "SH10", "SH11", "SH12", "SH13"):
            self.assertIn(shot, source)
        self.assertIn('"כל 16 איורי הניסיון": [s["shot_id"] for s in plan["shots"]]', source)


if __name__ == "__main__":
    unittest.main()
