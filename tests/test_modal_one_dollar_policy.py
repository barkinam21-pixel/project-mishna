"""Offline guard tests: no Modal SDK, network, GPU, credentials or spending."""
import tempfile
import unittest
from pathlib import Path
from tools.modal_one_dollar_policy import assess, worker_limits

BASE = '''import modal
app = modal.App("mishnah")
@app.function(gpu="L4", timeout=600, retries=0, scaledown_window=15,
              min_containers=0, max_containers=1)
def generate(payload):
    return payload
'''


class TestModalOneDollarPolicy(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / 'worker.py'
        self.path.write_text(BASE, encoding='utf-8')

    def tearDown(self):
        self.temp.cleanup()

    def test_realistic_worker_limit_is_read_from_source(self):
        self.assertEqual(worker_limits(self.path)['timeout_seconds'], 600)

    def test_dollar_ceiling_is_not_assumed_from_estimate(self):
        result = assess(self.path)
        self.assertEqual(result['owner_limit_usd'], '1.00')
        self.assertEqual(result['reason'], 'PROVIDER_WORKSPACE_BUDGET_NOT_INDEPENDENTLY_VERIFIED')
        self.assertFalse(result['gpu_execution_authorized'])
        self.assertFalse(result['estimate_is_a_spend_cap'])
        self.assertEqual(result['new_external_spend_initiated_usd'], '0')
        self.assertLess(float(result['planning_estimate_usd']), 1)

    def test_missing_budget_evidence_blocks_even_with_claimed_cap(self):
        result = assess(self.path, verified_workspace_budget_usd='1.00',
                        license_cleared=True, references_authorized=True,
                        private_runtime_verified=True)
        self.assertFalse(result['provider_workspace_budget_verified'])

    def test_budget_over_limit_blocks_even_if_claimed_verified(self):
        result = assess(self.path, verified_workspace_budget_usd='1.01',
                        independent_budget_evidence=True)
        self.assertEqual(result['reason'], 'WORKSPACE_BUDGET_EXCEEDS_OWNER_LIMIT')

    def test_all_verified_still_requires_one_shot_manual_gate(self):
        result = assess(self.path, verified_workspace_budget_usd='1.00',
                        independent_budget_evidence=True, license_cleared=True,
                        references_authorized=True, private_runtime_verified=True)
        self.assertTrue(result['provider_workspace_budget_verified'])
        self.assertFalse(result['gpu_execution_authorized'])
        self.assertEqual(result['reason'], 'MANUAL_SINGLE_RUN_AUTHORIZATION_AND_REMAINDER_REQUIRED')

    def test_paid_gpu_swap_is_blocked(self):
        self.path.write_text(BASE.replace('gpu="L4"', 'gpu="H100"'))
        self.assertEqual(assess(self.path)['reason'], 'WORKER_CONTRACT_INVALID')

    def test_second_container_is_blocked(self):
        self.path.write_text(BASE.replace('max_containers=1', 'max_containers=2'))
        self.assertEqual(assess(self.path)['reason'], 'WORKER_CONTRACT_INVALID')

    def test_unbounded_timeout_is_blocked(self):
        self.path.write_text(BASE.replace('timeout=600', 'timeout=601'))
        self.assertEqual(assess(self.path)['reason'], 'WORKER_CONTRACT_INVALID')

    def test_retries_blocked(self):
        self.path.write_text(BASE.replace('retries=0', 'retries=1'))
        self.assertEqual(assess(self.path)['reason'], 'WORKER_CONTRACT_INVALID')

    def test_missing_worker_fails_closed(self):
        self.assertEqual(assess(self.path.with_name('missing.py'))['reason'], 'WORKER_CONTRACT_INVALID')

    def test_bool_integer_bypass_is_rejected(self):
        self.path.write_text(BASE.replace('max_containers=1', 'max_containers=True'))
        self.assertEqual(assess(self.path)['reason'], 'WORKER_CONTRACT_INVALID')


if __name__ == '__main__':
    unittest.main()
