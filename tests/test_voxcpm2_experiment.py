"""Offline regression checks: importing/planning must never download a model."""
import importlib.util
import inspect
import json
import subprocess
import sys
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / 'experiments/voxcpm2_mature_hebrew_research.py'


class VoxCPMExperimentTests(unittest.TestCase):
    def test_plan_needs_no_model_dependencies_or_generation(self):
        result = subprocess.run([sys.executable, str(SCRIPT), '--plan'], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        plan = json.loads(result.stdout)
        self.assertEqual([v['id'] for v in plan['variants']], ['warm', 'dramatic'])
        self.assertFalse(plan['generation_started'])
        self.assertFalse(plan['narrator_approved'])

    def module(self):
        spec = importlib.util.spec_from_file_location('vox_research', SCRIPT)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_published_api_does_not_receive_unsupported_seed(self):
        # Actual VoxCPM2.0.3 _generate parameter names, inspected before changing code.
        def released(text, prompt_wav_path=None, prompt_text=None, reference_wav_path=None,
                     cfg_value=2., inference_timesteps=10, min_len=2, max_len=4096,
                     normalize=False, denoise=False, retry_badcase=True,
                     retry_badcase_max_times=3, retry_badcase_ratio_threshold=6., streaming=False):
            pass
        options = self.module().generation_options(released, 731)
        inspect.signature(released).bind('Hebrew text', **options)
        self.assertNotIn('seed', options)
        self.assertFalse(options['retry_badcase'])
        self.assertEqual(options['retry_badcase_max_times'], 1)
        self.assertFalse(options['normalize'])
        self.assertFalse(options['denoise'])

    def test_newer_api_can_use_its_native_seed(self):
        def current(*, seed=None, **kwargs):
            pass
        self.assertEqual(self.module().generation_options(current, 731)['seed'], 731)
