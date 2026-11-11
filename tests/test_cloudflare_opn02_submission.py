"""No-network tests for Cloudflare one-shot / fresh pre-submit gating."""
import base64
import unittest
from unittest.mock import Mock
from tools.cloudflare_image_backend import CloudflareClient, CloudflareBlocked


class TestCloudflareOPN02Submission(unittest.TestCase):
    def make_client(self):
        client = CloudflareClient({"safety": {}}, request=Mock(return_value={
            "success": True,
            "result": {"image": base64.b64encode(b"fake-image-bytes").decode()}
        }))
        client.receipt = {"checked": True}
        client._prepared_spec = {"size": [1024, 576]}
        client.images = [b"fake-reference"]
        client.readiness = Mock()
        return client

    def test_rechecks_readiness_immediately_before_post(self):
        client = self.make_client()
        client.submit({"prompt": "test"}, zero_cost_verified=True, authorized=True)
        client.readiness.assert_called_once_with(client._prepared_spec)
        self.assertEqual(client.transport.call_count, 1)

    def test_preflight_failure_blocks_any_post(self):
        client = self.make_client()
        client.readiness.side_effect = CloudflareBlocked("FREE_ALLOWANCE_HEADROOM_INSUFFICIENT")
        with self.assertRaisesRegex(CloudflareBlocked, "HEADROOM"):
            client.submit({"prompt": "test"}, zero_cost_verified=True, authorized=True)
        client.transport.assert_not_called()

    def test_no_retry_after_first_success(self):
        client = self.make_client()
        client.submit({"prompt": "test"}, zero_cost_verified=True, authorized=True)
        with self.assertRaisesRegex(CloudflareBlocked, "ONE_SHOT_ALREADY_ATTEMPTED"):
            client.submit({"prompt": "test"}, zero_cost_verified=True, authorized=True)
        self.assertEqual(client.transport.call_count, 1)

    def test_no_retry_after_uncertain_transport_failure(self):
        client = self.make_client()
        client.transport.side_effect = CloudflareBlocked("TRANSPORT_FAILED_NO_AUTOMATIC_RETRY")
        with self.assertRaises(CloudflareBlocked):
            client.submit({"prompt": "test"}, zero_cost_verified=True, authorized=True)
        with self.assertRaisesRegex(CloudflareBlocked, "ONE_SHOT_ALREADY_ATTEMPTED"):
            client.submit({"prompt": "test"}, zero_cost_verified=True, authorized=True)
        self.assertEqual(client.transport.call_count, 1)

    def test_missing_reference_preparation_blocks(self):
        client = self.make_client()
        client._prepared_spec = None
        with self.assertRaisesRegex(CloudflareBlocked, "REFERENCE_PREPARATION_MISSING"):
            client.submit({"prompt": "test"}, zero_cost_verified=True, authorized=True)
        client.transport.assert_not_called()

    def test_unauthorized_request_blocks(self):
        client = self.make_client()
        with self.assertRaisesRegex(CloudflareBlocked, "SUBMISSION_NOT_AUTHORIZED"):
            client.submit({"prompt": "test"}, zero_cost_verified=False, authorized=True)
        client.transport.assert_not_called()


if __name__ == "__main__":
    unittest.main()
