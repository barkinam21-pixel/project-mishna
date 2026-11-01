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
        self.assertIn('"prompt_2_sha256": prompt_2_digest', source)
        self.assertIn('"prompt_strategy": "dual_encoder_scene_style_v1"', source)
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
        self.assertIn("ZIP_PATH.unlink(missing_ok=True)", source)
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

    def test_sdxl_encoders_prioritize_short_scene_and_separate_visual_style(self):
        source = "".join(self.cells["render"]["source"])
        self.assertIn("prompt=scene_prompt,", source)
        self.assertIn("prompt_2=style_prompt,", source)
        self.assertIn("negative_prompt=negative_prompt,", source)
        self.assertIn("negative_prompt_2=negative_prompt,", source)
        self.assertIn("tokenizer.model_max_length", source)
        self.assertNotIn('prompt=full_prompt,', source)
        self.assertEqual(len(self.pack["shots"]), 16)
        self.assertLessEqual(len(self.pack["render_style"].split()), 37)
        for shot in self.pack["shots"]:
            with self.subTest(shot=shot["shot_id"]):
                self.assertTrue(shot.get("render_lead"))
                self.assertLessEqual(len(shot["render_lead"].split()), 47)
                self.assertLessEqual(len(shot.get("render_style", self.pack["render_style"]).split()), 37)
                self.assertTrue(shot.get("render_negative_prompt", self.pack["render_negative_prompt"]))
        self.assertTrue(self.pack["shots"][8]["render_lead"].startswith("NIGHT"))
        self.assertIn("TWO distinct adult men", self.pack["shots"][8]["render_lead"])

    def test_failed_image_run_reports_stage_instead_of_silent_no_zip(self):
        shot = self.pack["shots"][8]
        self.assertLessEqual(len(shot["render_negative_prompt"].split()), 25)
        self.assertIn("single figure", shot["render_negative_prompt"])
        source = "".join(self.cells["render"]["source"])
        for phrase in ('stage = "load_sdxl"', 'stage = "check_prompt_tokens"',
                       'stage = "generate"', 'stage = "save_image"',
                       'stage = "create_zip"', 'נכשל ב-', 'flush=True'):
            self.assertIn(phrase, source)
        self.assertIn('len(token_ids) > tokenizer.model_max_length', source)
        self.assertIn("לא נוצר ZIP חדש", source)

    def test_sh09_high_clarity_art_direction_is_scoped_and_auditable(self):
        shot = self.pack["shots"][8]
        self.assertEqual(shot["shot_id"], "SH09")
        self.assertTrue(shot["render_lead"].startswith("NIGHT."))
        self.assertIn("TWO distinct adult men", shot["render_lead"])
        self.assertIn("HOUSE DOOR", shot["render_lead"])
        self.assertIn("amber oil lamp", shot["render_lead"])
        self.assertIn("High-clarity hand-painted", shot["render_style"])
        self.assertIn("rich midnight blue and amber", shot["render_style"])
        self.assertIn("washed-out", shot["render_negative_prompt"])
        self.assertIn("solo man", shot["render_negative_prompt"])
        self.assertEqual(shot["guidance_scale"], 7.0)
        self.assertEqual(sum("guidance_scale" in other for other in self.pack["shots"]), 1)
        source = "".join(self.cells["render"]["source"])
        self.assertIn('guidance = float(shot.get("guidance_scale", 6.0))', source)
        self.assertIn('"inference_steps": STEPS, "guidance_scale": guidance', source)
        self.assertIn("guidance_scale=guidance,", source)
        self.assertNotIn('guidance_scale=6.0,\n            generator=generator', source)
        self.assertIn('visual_metrics = visual_diagnostics(image)', source)
        self.assertIn('"visual_diagnostics": visual_metrics', source)

    def test_visual_diagnostics_reports_pixels_not_artistic_approval(self):
        source = "".join(self.cells["render"]["source"])
        tree = ast.parse(source)
        function = next(node for node in tree.body
                        if isinstance(node, ast.FunctionDef)
                        and node.name == "visual_diagnostics")
        class FakeFrame:
            def __init__(self, pixels):
                self.pixels = pixels
            def convert(self, mode):
                self.assert_mode = mode
                return self
            def resize(self, dimensions, resample=None):
                if dimensions != (128, 72):
                    raise AssertionError("Unexpected geometry")
                return self
            def getdata(self):
                return self.pixels
        class FakeImage:
            class Resampling:
                BILINEAR = 2
        context = {"Image": FakeImage}
        exec(compile(ast.Module(body=[function], type_ignores=[]),
                     "visual-diagnostics-only", "exec"), context)
        measure = context["visual_diagnostics"]
        flat = measure(FakeFrame([(128,128,128)]*(128*72)))
        self.assertEqual(flat["saturation_mean_0_255"], 0)
        self.assertEqual(flat["luma_p90_p10_spread"], 0)
        self.assertEqual(flat["mean_neighbor_luma_delta"], 0)
        vivid = measure(FakeFrame([(255,0,0)]*(128*72)))
        self.assertEqual(vivid["saturation_mean_0_255"], 255)
        gradient = measure(FakeFrame(
            [(0,0,0)]*(128*36) + [(255,255,255)]*(128*36)
        ))
        self.assertGreater(gradient["luma_p90_p10_spread"], 200)
        self.assertGreater(gradient["mean_neighbor_luma_delta"], 0)
        for data in (flat, vivid, gradient):
            self.assertEqual(data["meaning"],
                             "descriptive_only_not_a_quality_or_scene_approval")
            self.assertNotIn("accepted", data)
            self.assertNotIn("release_authorized", data)

    def test_three_sh09_variations_are_bounded_without_cloud_use(self):
        settings = "".join(self.cells["settings"]["source"])
        plan = "".join(self.cells["plan"]["source"])
        render = "".join(self.cells["render"]["source"])
        self.assertIn('TAKE = "ניסיון 1 - seed בסיסי"', settings)
        self.assertIn('if TAKE_INDEX and SELECTED_IDS != ["SH09"]:', plan)
        self.assertIn('seed = planned_seed(shot["seed"], TAKE_INDEX)', render)
        self.assertIn('"variation_index": TAKE_INDEX', render)
        parsed = ast.parse(plan)
        seed_fn = next(
            node for node in parsed.body
            if isinstance(node, ast.FunctionDef) and node.name == "planned_seed"
        )
        scope = {}
        exec(compile(ast.Module(body=[seed_fn], type_ignores=[]),
                     "<planned-seed-function>", "exec"), scope)
        for index in (0, 1, 2):
            with self.subTest(index=index):
                self.assertEqual(scope["planned_seed"](173109, index), 173109 + 1009*index)
        for invalid in (-1, 3, True, "2"):
            with self.subTest(invalid=invalid):
                with self.assertRaises(ValueError):
                    scope["planned_seed"](173109, invalid)

    def test_new_default_does_not_repeat_rejected_sh01(self):
        settings = "".join(self.cells["settings"]["source"])
        plan = "".join(self.cells["plan"]["source"])
        self.assertIn('BATCH = "איור אחד חדש - SH09"', settings)
        self.assertIn('"איור אחד חדש - SH09": ["SH09"]', plan)
        self.assertIn("SH01", " ".join(self.pack["notes"]))


if __name__ == "__main__":
    unittest.main()
