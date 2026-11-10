"""All tests are offline: no Modal SDK, network, deployment or GPU."""
import contextlib
import io
import json
import os
import subprocess
import unittest
from unittest.mock import patch
from tools import modal_readonly_preflight as check


class ModalReadOnlyPreflightTests(unittest.TestCase):
    def test_no_credentials_makes_no_provider_calls(self):
        with patch.dict(os.environ, {"MODAL_TOKEN_ID": "", "MODAL_TOKEN_SECRET": ""}), \
             patch.object(check.subprocess, "run") as run:
            report = check.audit()
        run.assert_not_called()
        self.assertEqual(report["status"], "BLOCKED_MISSING_CREDENTIALS")
        self.assertFalse(report["gpu_execution_authorized"])

    def test_visible_app_and_billing_still_block_gpu(self):
        responses = [
            subprocess.CompletedProcess([], 0, '[{"name":"mishnah-flux2-klein4b","state":"deployed"}]', ""),
            subprocess.CompletedProcess([], 0, '{"monthly_spend_usd": 29.5, "private_data": "secret"}', ""),
        ]
        with patch.dict(os.environ, {"MODAL_TOKEN_ID": "example-id", "MODAL_TOKEN_SECRET": "secret"}), \
             patch.object(check.subprocess, "run", side_effect=responses) as run:
            report = check.audit()
        self.assertTrue(report["expected_app_visible"])
        self.assertTrue(report["authenticated_account_verified"])
        self.assertFalse(report["hard_spend_cap_verified"])
        self.assertFalse(report["gpu_execution_authorized"])
        self.assertEqual(report["modal_gpu_requests"], 0)
        self.assertEqual([call.args[0] for call in run.call_args_list],
                         [cmd for _, cmd in check.COMMANDS])
        self.assertNotIn("secret", json.dumps(report))
        self.assertNotIn("29.5", json.dumps(report))

    def test_unavailable_apps_and_invalid_billing_are_not_approved(self):
        responses = [
            subprocess.CompletedProcess([], 1, "", "token-invalid-and-secret-text"),
            subprocess.CompletedProcess([], 0, "not json", ""),
        ]
        with patch.dict(os.environ, {"MODAL_TOKEN_ID": "x", "MODAL_TOKEN_SECRET": "y"}), \
             patch.object(check.subprocess, "run", side_effect=responses):
            report = check.audit()
        self.assertEqual(report["app_list"], "COMMAND_FAILED")
        self.assertIsNone(report["expected_app_visible"])
        self.assertEqual(report["billing_summary"], "INVALID_JSON")
        self.assertFalse(report["authenticated_account_verified"])
        self.assertNotIn("token-invalid", json.dumps(report))

    def test_partial_errors_and_timeout_are_fail_closed(self):
        with patch.dict(os.environ, {"MODAL_TOKEN_ID": "x", "MODAL_TOKEN_SECRET": "y"}), \
             patch.object(check.subprocess, "run", side_effect=subprocess.TimeoutExpired("modal", 30)):
            report = check.audit()
        self.assertEqual(report["app_list"], "UNAVAILABLE")
        self.assertFalse(report["gpu_execution_authorized"])

    def test_cli_output_is_safe_and_never_prints_secrets(self):
        response = subprocess.CompletedProcess([], 0, '{"apps": [{"app_name": "other-app"}]}', "")
        with patch.dict(os.environ, {"MODAL_TOKEN_ID": "sensitive-id", "MODAL_TOKEN_SECRET": "sensitive-secret"}), \
             patch.object(check.subprocess, "run", return_value=response), \
             contextlib.redirect_stdout(io.StringIO()) as capture:
            exit_code = check.main()
        result = capture.getvalue()
        self.assertEqual(exit_code, 0)
        self.assertFalse(json.loads(result)["expected_app_visible"])
        self.assertNotIn("sensitive-", result)
        self.assertFalse(json.loads(result)["gpu_execution_authorized"])


if __name__ == "__main__":
    unittest.main()
