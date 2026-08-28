import os
import unittest
from unittest.mock import MagicMock, patch

env_patch = patch.dict(
    os.environ,
    {
        "DD_API_KEY": "11111111111111111111111111111111",
    },
)
env_patch.start()
from lambda_function import _datadog_keys, get_region_from_arn

env_patch.stop()

# A key that is not also valid JSON, so it round-trips through the plain-string
# branch of the Secrets Manager and SSM lookups
STORED_API_KEY = "abcdef1234567890abcdef1234567890"
SECRET_ARN = "arn:aws:secretsmanager:eu-west-1:123456789012:secret:dd-api-key-AbCdEf"
PARAMETER_ARN = "arn:aws:ssm:us-west-2:123456789012:parameter/datadog/api-key"


class TestGetRegionFromArn(unittest.TestCase):
    def test_secret_arn(self):
        self.assertEqual(get_region_from_arn(SECRET_ARN), "eu-west-1")

    def test_ssm_parameter_arn(self):
        self.assertEqual(get_region_from_arn(PARAMETER_ARN), "us-west-2")

    def test_arn_in_another_partition(self):
        self.assertEqual(
            get_region_from_arn(
                "arn:aws-us-gov:secretsmanager:us-gov-west-1:123456789012:secret:dd-api-key"
            ),
            "us-gov-west-1",
        )

    def test_ssm_parameter_name(self):
        self.assertIsNone(get_region_from_arn("/datadog/api-key"))

    def test_secret_friendly_name(self):
        self.assertIsNone(get_region_from_arn("dd-api-key"))

    def test_arn_without_a_region(self):
        self.assertIsNone(
            get_region_from_arn("arn:aws:iam::123456789012:role/dd-forwarder")
        )

    def test_truncated_arn(self):
        self.assertIsNone(get_region_from_arn("arn:aws:secretsmanager:eu-west-1"))


class TestApiKeyClientRegion(unittest.TestCase):
    def _boto3_client(self):
        boto3_client = MagicMock()
        boto3_client.return_value.get_secret_value.return_value = {
            "SecretString": STORED_API_KEY
        }
        boto3_client.return_value.get_parameter.return_value = {
            "Parameter": {"Value": STORED_API_KEY}
        }
        return boto3_client

    @patch.dict(os.environ, {"DD_API_KEY_SECRET_ARN": SECRET_ARN})
    def test_secret_client_targets_the_secret_region(self):
        boto3_client = self._boto3_client()

        with patch("lambda_function.boto3.client", boto3_client):
            keys = _datadog_keys()

        self.assertEqual(keys, {"api_key": STORED_API_KEY})
        self.assertEqual(boto3_client.call_args.args[0], "secretsmanager")
        self.assertEqual(boto3_client.call_args.kwargs["region_name"], "eu-west-1")

    @patch.dict(os.environ, {"DD_API_KEY_SSM_NAME": PARAMETER_ARN})
    def test_ssm_client_targets_the_parameter_region(self):
        boto3_client = self._boto3_client()

        with patch("lambda_function.boto3.client", boto3_client):
            keys = _datadog_keys()

        self.assertEqual(keys, {"api_key": STORED_API_KEY})
        self.assertEqual(boto3_client.call_args.args[0], "ssm")
        self.assertEqual(boto3_client.call_args.kwargs["region_name"], "us-west-2")

    @patch.dict(os.environ, {"DD_API_KEY_SSM_NAME": "/datadog/api-key"})
    def test_ssm_client_keeps_the_default_region_for_a_parameter_name(self):
        boto3_client = self._boto3_client()

        with patch("lambda_function.boto3.client", boto3_client):
            keys = _datadog_keys()

        self.assertEqual(keys, {"api_key": STORED_API_KEY})
        self.assertEqual(boto3_client.call_args.args[0], "ssm")
        self.assertIsNone(boto3_client.call_args.kwargs["region_name"])


if __name__ == "__main__":
    unittest.main()
