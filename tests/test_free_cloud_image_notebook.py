"""No-GPU tests for the one-click free-cloud notebook and its visual source pack."""
import ast
import hashlib
import json
import tempfile
import zipfile
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
        self.assertIn("BATCH = \"איור אחד חדש - SH09\"", source)
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

    def test_cache_requires_exact_generation_spec_and_sha(self):
        source = "".join(self.cells["render"]["source"])
        self.assertIn("cached_image_matches(image_path, shot[\"shot_id\"], spec_hash)", source)
        self.assertIn('"negative_prompt_sha256":', source)
        self.assertIn('"generation_spec_sha256": spec_hash', source)
        self.assertIn("hashlib.sha256(path.read_bytes()).hexdigest()", source)
        self.assertIn(".superseded-", source)
        self.assertNotIn('if image_path.exists():\n        print("נמצא כבר בסשן:"', source)

    def test_cache_runtime_rejects_stale_or_tampered_png(self):
        # Execute the actual notebook function offline: no GPU, import or cloud call.
        render_ast = ast.parse("".join(self.cells["render"]["source"]))
        fn = next(node for node in render_ast.body
                  if isinstance(node, ast.FunctionDef) and node.name == "cached_image_matches")
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            picture = tmp / "SH09.png"
            ledger = tmp / "usage-ledger.jsonl"
            namespace = {"hashlib": hashlib, "json": json, "LEDGER": ledger}
            exec(compile(ast.Module(body=[fn], type_ignores=[]), "<cache-function>", "exec"), namespace)
            matches = namespace["cached_image_matches"]
            picture.write_bytes(b"example image bytes")
            sha = hashlib.sha256(picture.read_bytes()).hexdigest()
            self.assertFalse(matches(picture, "SH09", "spec-1"))  # no ledger
            ledger.write_text(json.dumps({
                "shot_id": "SH09", "image_sha256": sha,
                "generation_spec_sha256": "spec-1"
            }) + "\n", encoding="utf-8")
            self.assertTrue(matches(picture, "SH09", "spec-1"))
            self.assertFalse(matches(picture, "SH09", "spec-2"))
            self.assertFalse(matches(picture, "SH10", "spec-1"))
            picture.write_bytes(b"tampered bytes")
            self.assertFalse(matches(picture, "SH09", "spec-1"))

    def test_private_contact_sheet_and_lazy_model_preflight(self):
        source = "".join(self.cells["render"]["source"])
        self.assertIn('SHEET = OUT / "review-contact-sheet.jpg"', source)
        self.assertIn('SHEET.unlink(missing_ok=True)', source)
        self.assertIn("ImageOps.contain", source)  # full frame, no crop
        self.assertIn("DRAFT CONTACT SHEET - NOT APPROVED", source)
        self.assertIn("build_contact_sheet(successful)", source)
        self.assertIn("display(Image.open(SHEET).copy())", source)
        self.assertIn("if pipe is None:", source)
        self.assertIn("pipe = load_pipeline_only_when_needed()", source)
        # Loading a generative model must not happen at module top level.
        render_ast = ast.parse(source)
        self.assertFalse(any(
            isinstance(node, ast.Expr) and isinstance(node.value, ast.Call)
            and isinstance(node.value.func, ast.Attribute)
            and node.value.func.attr == "from_pretrained"
            for node in render_ast.body
        ))
        self.assertIn("zipfile.ZIP_DEFLATED", source)
        self.assertIn('"accepted": False', source)

    def test_zip_export_excludes_old_shots_without_gpu(self):
        # Execute the actual notebook ZIP writer with test bytes only.
        render_ast = ast.parse("".join(self.cells["render"]["source"]))
        fn = next(node for node in render_ast.body
                  if isinstance(node, ast.FunctionDef) and node.name == "save_zip")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name in ("prompt-pack-snapshot.json", "usage-ledger.jsonl",
                         "SH09.png", "SH01.png", "SH10.png",
                         "SH09.superseded-deadbeef1234.png",
                         "review-contact-sheet.jpg"):
                (root / name).write_bytes(b"test-only:" + name.encode("ascii"))
            namespace = {
                "OUT": root, "LEDGER": root / "usage-ledger.jsonl",
                "SHEET": root / "review-contact-sheet.jpg",
                "ZIP_PATH": root / "delivery.zip",
                "successful": [root / "SH09.png"],
                "zipfile": zipfile, "os": __import__("os"),
            }
            exec(compile(ast.Module(body=[fn], type_ignores=[]),
                         "<notebook-zip-writer>", "exec"), namespace)
            namespace["save_zip"]()
            with zipfile.ZipFile(namespace["ZIP_PATH"]) as zf:
                self.assertEqual(set(zf.namelist()), {
                    "SH09.png", "prompt-pack-snapshot.json",
                    "usage-ledger.jsonl", "review-contact-sheet.jpg"
                })
            # A retry with an additional verified shot exports that shot,
            # never an unrelated legacy or superseded file.
            namespace["successful"] = [root / "SH09.png", root / "SH10.png"]
            namespace["save_zip"]()
            with zipfile.ZipFile(namespace["ZIP_PATH"]) as zf:
                self.assertIn("SH10.png", zf.namelist())
                self.assertNotIn("SH01.png", zf.namelist())
                self.assertNotIn("SH09.superseded-deadbeef1234.png", zf.namelist())
            namespace["successful"] = []
            with self.assertRaises(RuntimeError):
                namespace["save_zip"]()

    def test_sh09_has_two_explicit_upgrades_and_prompt_priority(self):
        shot = next(s for s in self.pack["shots"] if s["shot_id"] == "SH09")
        self.assertIn("TWO distinct adult men", shot["shot_prompt"])
        self.assertIn("STONE HOUSE", shot["shot_prompt"])
        self.assertIn("AFTER DARK", shot["shot_prompt"])
        self.assertIn("oil lamp", shot["shot_prompt"])
        self.assertIn("cinematic chiaroscuro", shot["shot_prompt"])
        self.assertLessEqual(len(shot["shot_prompt"].split()), 76)  # prioritize scene before text truncation
        self.assertIn("single person", shot["shot_negative_prompt"])
        self.assertIn("sunny day", shot["shot_negative_prompt"])
        self.assertEqual(shot["guidance_scale"], 7.0)
        source = "".join(self.cells["render"]["source"])
        self.assertIn('full_prompt = shot["shot_prompt"] + ". Visual treatment: " + plan["style_lock"]', source)
        self.assertIn('negative_prompt = plan["negative_prompt"] + (', source)
        self.assertIn('negative_prompt=negative_prompt,', source)
        self.assertIn('guidance_scale=guidance_scale,', source)
        self.assertIn('"prompt_order": "shot_first_v2"', source)

    def test_new_default_does_not_repeat_rejected_sh01(self):
        settings = "".join(self.cells["settings"]["source"])
        plan = "".join(self.cells["plan"]["source"])
        self.assertIn('BATCH = "איור אחד חדש - SH09"', settings)
        self.assertIn('"איור אחד חדש - SH09": ["SH09"]', plan)
        self.assertIn("SH01", " ".join(self.pack["notes"]))


if __name__ == "__main__":
    unittest.main()
