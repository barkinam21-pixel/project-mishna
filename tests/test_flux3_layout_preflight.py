"""CPU-only regressions for the FLUX.3 OPN02 offline layout adapter."""
import json
from pathlib import Path
import unittest
from tools.flux3_layout_preflight import compile_layout, LayoutError, main

SPEC = Path(__file__).resolve().parents[1] / "episodes/berakhot-01-01/opn02-flux3-layout-draft.json"


class LayoutTests(unittest.TestCase):
    def setUp(self):
        self.spec = json.loads(SPEC.read_text(encoding="utf-8"))

    def test_official_cli_units_and_scale(self):
        boxes = compile_layout(self.spec)
        self.assertEqual(len(boxes), 4)
        elder = next(x for x in boxes if x["id"] == "elder_1")
        self.assertEqual(elder["bbox"], [0.635, 0.39, 0.945, 0.485])
        self.assertAlmostEqual(elder["bbox"][2] - elder["bbox"][0], 0.31)
        self.assertTrue(all(0 <= n <= 1 for row in boxes for n in row["bbox"]))

    def test_no_generation_authorization(self):
        self.spec["generation_authorized"] = True
        with self.assertRaisesRegex(LayoutError, "GENERATION_AUTHORIZATION"):
            compile_layout(self.spec)

    def test_no_reference_upload(self):
        self.spec["reference_images_uploaded"] = True
        with self.assertRaisesRegex(LayoutError, "REFERENCE_UPLOAD"):
            compile_layout(self.spec)

    def test_no_mixed_coordinate_units(self):
        self.spec["boxes_1000"][1]["bbox"][0] = 0.635
        with self.assertRaisesRegex(LayoutError, "BBOX_MUST_BE"):
            compile_layout(self.spec)

    def test_no_oversized_people(self):
        self.spec["boxes_1000"][1]["bbox"][0] = 150
        with self.assertRaisesRegex(LayoutError, "TRAVELER_SCALE"):
            compile_layout(self.spec)

    def test_no_swapped_or_overlapping_people(self):
        self.spec["boxes_1000"][1]["bbox"][3] = 600
        with self.assertRaisesRegex(LayoutError, "CHARACTER_LEFT_RIGHT"):
            compile_layout(self.spec)

    def test_no_silent_model_swap(self):
        self.spec["model"] = "black-forest-labs/flux-2-klein-4b"
        with self.assertRaisesRegex(LayoutError, "MODEL_NOT_SUPPORTED"):
            compile_layout(self.spec)

    def test_no_provider_call_on_preflight(self):
        self.assertEqual(main([str(SPEC)]), 0)


if __name__ == "__main__":
    unittest.main()
