import os
import sys
import unittest
from importlib import reload
from unittest.mock import MagicMock, patch

from settings import get_region_from_arn, is_api_key_valid

VALID_API_KEY = "11111111111111111111111111111111"
# A key that is not also valid JSON, so it round-trips through the plain-string
# branch of the Secrets Manager and SSM lookups
STORED_API_KEY = "abcdef1234567890abcdef1234567890"


# For the integration tests to work because of other tests set sys.modules["requests"] as a MagicMock.
class _FakeNetworkError(Exception):
    pass


class TestIsApiKeyValid(unittest.TestCase):
    @patch("settings.DD_API_KEY", VALID_API_KEY)
    @patch("settings.requests.Session")
    def test_valid_api_key(self, mock_session_cls):
        mock_response = MagicMock()
        mock_response.ok = True
        mock_session_cls.return_value.__enter__.return_value.get.return_value = (
            mock_response
        )
        self.assertTrue(is_api_key_valid())

    @patch("settings.DD_API_KEY", "")
    def test_empty_api_key(self):
        with self.assertRaises(Exception):
            is_api_key_valid()

    @patch("settings.DD_API_KEY", "shortapikey")
    def test_invalid_api_key_format(self):
        with self.assertRaises(Exception):
            is_api_key_valid()

    @patch("settings.DD_API_KEY", VALID_API_KEY)
    @patch("settings.logger")
    @patch("settings.requests.exceptions.RequestException", _FakeNetworkError)
    @patch("settings.requests.Session")
    def test_on_connection_exception(self, mock_session_cls, mock_logger):
        mock_session_cls.return_value.__enter__.return_value.get.side_effect = (
            _FakeNetworkError("DNS resolution failed")
        )
        result = is_api_key_valid()
        self.assertFalse(result)
        mock_logger.warning.assert_called_once()
        self.assertIn("network error", mock_logger.warning.call_args[0][0].lower())

    @patch("settings.DD_API_KEY", VALID_API_KEY)
    @patch("settings.logger")
    @patch("settings.requests.exceptions.RequestException", _FakeNetworkError)
    @patch("settings.requests.Session")
    def test_on_timeout_exception(self, mock_session_cls, mock_logger):
        mock_session_cls.return_value.__enter__.return_value.get.side_effect = (
            _FakeNetworkError("Request timed out")
        )
        result = is_api_key_valid()
        self.assertFalse(result)
        mock_logger.warning.assert_called_once()
        self.assertIn("network error", mock_logger.warning.call_args[0][0].lower())


class TestGetRegionFromArn(unittest.TestCase):
    def test_secret_arn(self):
        self.assertEqual(
            get_region_from_arn(
                "arn:aws:secretsmanager:eu-west-1:123456789012:secret:dd-api-key-AbCdEf"
            ),
            "eu-west-1",
        )

    def test_secret_partial_arn(self):
        self.assertEqual(
            get_region_from_arn(
                "arn:aws:secretsmanager:us-west-2:123456789012:secret:dd-api-key"
            ),
            "us-west-2",
        )

    def test_ssm_parameter_arn(self):
        self.assertEqual(
            get_region_from_arn(
                "arn:aws:ssm:ap-southeast-2:123456789012:parameter/datadog/api-key"
            ),
            "ap-southeast-2",
        )

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
    """
    The API key is fetched while settings is imported, so each case reloads the
    module with a patched boto3 to capture how the client was built.
    """

    API_KEY_SOURCES = (
        "DD_API_KEY_SECRET_ARN",
        "DD_API_KEY_SSM_NAME",
        "DD_KMS_API_KEY",
    )

    def tearDown(self):
        reload(sys.modules["settings"])

    def _reload_settings(self, env, boto3_client):
        with patch.dict(os.environ, env), patch("boto3.client", boto3_client):
            # Only the source under test may win the precedence chain
            for var in self.API_KEY_SOURCES:
                if var not in env:
                    os.environ.pop(var, None)
            reload(sys.modules["settings"])

    def test_secret_client_targets_the_secret_region(self):
        boto3_client = MagicMock()
        boto3_client.return_value.get_secret_value.return_value = {
            "SecretString": STORED_API_KEY
        }

        self._reload_settings(
            {
                "DD_API_KEY_SECRET_ARN": (
                    "arn:aws:secretsmanager:eu-west-1:123456789012:secret:dd-api-key-AbCdEf"
                )
            },
            boto3_client,
        )

        self.assertEqual(boto3_client.call_args.args[0], "secretsmanager")
        self.assertEqual(boto3_client.call_args.kwargs["region_name"], "eu-west-1")
        self.assertEqual(sys.modules["settings"].DD_API_KEY, STORED_API_KEY)

    def test_ssm_client_targets_the_parameter_region(self):
        boto3_client = MagicMock()
        boto3_client.return_value.get_parameter.return_value = {
            "Parameter": {"Value": STORED_API_KEY}
        }

        self._reload_settings(
            {
                "DD_API_KEY_SSM_NAME": (
                    "arn:aws:ssm:us-west-2:123456789012:parameter/datadog/api-key"
                )
            },
            boto3_client,
        )

        self.assertEqual(boto3_client.call_args.args[0], "ssm")
        self.assertEqual(boto3_client.call_args.kwargs["region_name"], "us-west-2")
        self.assertEqual(sys.modules["settings"].DD_API_KEY, STORED_API_KEY)

    def test_ssm_client_keeps_the_default_region_for_a_parameter_name(self):
        boto3_client = MagicMock()
        boto3_client.return_value.get_parameter.return_value = {
            "Parameter": {"Value": STORED_API_KEY}
        }

        self._reload_settings({"DD_API_KEY_SSM_NAME": "/datadog/api-key"}, boto3_client)

        self.assertEqual(boto3_client.call_args.args[0], "ssm")
        self.assertIsNone(boto3_client.call_args.kwargs["region_name"])


if __name__ == "__main__":
    unittest.main()
