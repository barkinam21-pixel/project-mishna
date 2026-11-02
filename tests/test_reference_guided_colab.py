"""Static offline checks for the private, one-shot reference-guided Colab notebook.

No cloud calls, GPU use, installed diffusers or image generation.
"""
import ast
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NOTEBOOK = ROOT / "notebooks" / "reference_guided_sh09_colab.ipynb"


class ReferenceGuidedColabTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.nb = json.loads(NOTEBOOK.read_text(encoding="utf-8"))
        cls.code = [c for c in cls.nb["cells"] if c["cell_type"] == "code"]
        cls.source = "\n".join("".join(c["source"]) for c in cls.code)

    def test_notebook_is_clean_python_and_gpu_tagged(self):
        self.assertEqual(self.nb["nbformat"], 4)
        self.assertEqual(self.nb["metadata"]["accelerator"], "GPU")
        self.assertEqual(len(self.code), 5)
        for cell in self.code:
            self.assertIsNone(cell["execution_count"])
            self.assertEqual(cell["outputs"], [])
            ast.parse("".join(cell["source"]))

    def test_gpu_and_reference_preflight_precede_dependency_download(self):
        self.assertEqual([c["metadata"]["id"] for c in self.code],
                         ["gpu", "reference", "deps", "preflight", "single-generation"])
        self.assertIn("torch.cuda.is_available()", "".join(self.code[0]["source"]))
        self.assertIn("files.upload()", "".join(self.code[1]["source"]))
        self.assertIn('picture.save(PRIVATE_REFERENCE, format="PNG")',
                      "".join(self.code[1]["source"]))
        self.assertIn('REPO_DIR / "tools/reference_guided.py"', "".join(self.code[2]["source"]))
        self.assertIn('"preflight"', "".join(self.code[3]["source"]))
        self.assertIn('if not readiness.get("can_generate"):', "".join(self.code[3]["source"]))

    def test_single_one_click_proof_with_no_paid_backends(self):
        gen = "".join(self.code[4]["source"])
        self.assertIn('"all"', gen)
        self.assertIn('"--reference"', gen)
        self.assertIn('"--allow-generate"', gen)
        self.assertIn('files.download(str(archives[-1]))', gen)
        self.assertIn("SH09-reference-guided-unapproved.zip", gen)
        self.assertNotIn("while ", gen)  # No retry loop
        for term in ("OPENAI_API_KEY", "HF_TOKEN", "replicate.com", "runpod.io",
                     "stripe", "autoclick", "TinyFish"):
            self.assertNotIn(term, self.source)


if __name__ == "__main__":
    unittest.main()
