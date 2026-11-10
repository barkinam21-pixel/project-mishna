"""Offline tests: no Modal credentials, API calls or GPUs involved."""
import unittest
from tools.modal_gpu_budget_gate import check_trial


class ModalBudgetGateTests(unittest.TestCase):
    def args(self, **overrides):
        params = dict(hourly_usd="1.50", max_seconds=300,
                      available_credit_usd="1", hard_cap_usd="1",
                      owner_approved=True, model_license_verified=True,
                      private_runtime_verified=True)
        params.update(overrides)
        return params

    def test_no_owner_approval(self):
        self.assertEqual(check_trial(**self.args(owner_approved=False))["status"],
                         "BLOCKED_APPROVAL_OR_RIGHTS")

    def test_no_private_runtime(self):
        self.assertEqual(check_trial(**self.args(private_runtime_verified=False))["status"],
                         "BLOCKED_APPROVAL_OR_RIGHTS")

    def test_no_license(self):
        self.assertEqual(check_trial(**self.args(model_license_verified=False))["status"],
                         "BLOCKED_APPROVAL_OR_RIGHTS")

    def test_cost_exceeds_credit(self):
        self.assertEqual(check_trial(**self.args(hourly_usd="100"))["status"],
                         "BLOCKED_ESTIMATE_EXCEEDS_CAP")

    def test_cost_within_cap_still_not_authorized(self):
        result = check_trial(**self.args())
        self.assertEqual(result["status"], "ESTIMATE_WITHIN_CAP_NOT_AUTHORIZED_TO_RUN")
        self.assertEqual(result["gpu_requests"], 0)

    def test_invalid_costs(self):
        for rate in ("-1", "NaN", "Infinity", "0", "oops"):
            with self.subTest(rate=rate):
                self.assertEqual(check_trial(**self.args(hourly_usd=rate))["status"],
                                 "BLOCKED_INVALID_BUDGET")

    def test_zero_credit(self):
        self.assertEqual(check_trial(**self.args(available_credit_usd=0))["status"],
                         "BLOCKED_INVALID_BUDGET")


if __name__ == "__main__":
    unittest.main()
