from unittest.mock import MagicMock, patch
import os
import sys
import unittest
import json
from botocore.exceptions import ClientError

sys.modules["trace_forwarder.connection"] = MagicMock()
sys.modules["datadog_lambda.wrapper"] = MagicMock()
sys.modules["datadog_lambda.metric"] = MagicMock()
sys.modules["datadog"] = MagicMock()
sys.modules["requests"] = MagicMock()
sys.modules["requests_futures.sessions"] = MagicMock()

env_patch = patch.dict(
    os.environ,
    {
        "DD_API_KEY": "11111111111111111111111111111111",
        "DD_ADDITIONAL_TARGET_LAMBDAS": "ironmaiden,megadeth",
    },
)
env_patch.start()
from lambda_function import invoke_additional_target_lambdas, extract_metric

env_patch.stop()


class TestInvokeAdditionalTargetLambdas(unittest.TestCase):
    @patch("lambda_function.boto3")
    def test_additional_lambda(self, boto3):
        self.assertEqual(invoke_additional_target_lambdas({"ironmaiden": "foo"}), None)
        boto3.client.assert_called_with("lambda")
        lambda_payload = json.dumps({"ironmaiden": "foo"})

        self.assertEqual(boto3.client().invoke.call_count, 2)
        boto3.client().invoke.assert_called_with(
            FunctionName="megadeth", InvocationType="Event", Payload=lambda_payload
        )

    @patch("lambda_function.boto3")
    def test_lambda_invocation_exception(self, boto3):
        boto3.client.return_value.invoke.side_effect = ClientError(
            {"Error": {"Code": "403", "Message": "Unauthorized"}}, "Invoke"
        )
        self.assertEqual(invoke_additional_target_lambdas({"ironmaiden": "foo"}), None)
        boto3.client.assert_called_with("lambda")
        lambda_payload = json.dumps({"ironmaiden": "foo"})

        self.assertEqual(boto3.client().invoke.call_count, 2)
        boto3.client().invoke.assert_called_with(
            FunctionName="megadeth", InvocationType="Event", Payload=lambda_payload
        )


class TestExtractMetric(unittest.TestCase):
    def test_empty_event(self):
        self.assertEqual(extract_metric({}), None)

    def test_missing_keys(self):
        self.assertEqual(extract_metric({"e": 0, "v": 1, "m": "foo"}), None)

    def test_tags_instance(self):
        self.assertEqual(extract_metric({"e": 0, "v": 1, "m": "foo", "t": 666}), None)

    def test_value_instance(self):
        self.assertEqual(extract_metric({"e": 0, "v": 1.1, "m": "foo", "t": []}), None)

    def test_value_instance_float(self):
        self.assertEqual(extract_metric({"e": 0, "v": None, "m": "foo", "t": []}), None)


if __name__ == "__main__":
    unittest.main()
