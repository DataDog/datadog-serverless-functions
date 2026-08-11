import json
import os
import sys
import unittest
from importlib import reload
from unittest.mock import MagicMock, patch

from settings import is_api_key_valid

VALID_API_KEY = "11111111111111111111111111111111"


# For the integration tests to work because of other tests set sys.modules["requests"] as a MagicMock.
class _FakeNetworkError(Exception):
    pass


SECRET_ARN = "arn:aws:secretsmanager:us-east-1:123456789012:secret:test"

# A plaintext secret that happens to be all-digits (like VALID_API_KEY) is
# valid JSON too (it parses as an int), which exercises a different, unrelated
# code path. Use a hex-looking key with a letter so json.loads() reliably
# raises JSONDecodeError and the plaintext fallback branch is what's tested.
PLAINTEXT_API_KEY = "abcd1234abcd1234abcd1234abcd1234"


class TestApiKeySecretArn(unittest.TestCase):
    def _reload_with_secret_string(self, secret_string):
        mock_secretsmanager = MagicMock()
        mock_secretsmanager.get_secret_value.return_value = {
            "SecretString": secret_string
        }
        with patch("boto3.client", return_value=mock_secretsmanager):
            reload(sys.modules["settings"])
        return sys.modules["settings"].DD_API_KEY

    @patch.dict(os.environ, {"DD_API_KEY_SECRET_ARN": SECRET_ARN})
    def test_plaintext_secret(self):
        self.assertEqual(
            self._reload_with_secret_string(PLAINTEXT_API_KEY), PLAINTEXT_API_KEY
        )

    @patch.dict(os.environ, {"DD_API_KEY_SECRET_ARN": SECRET_ARN})
    def test_dd_api_key_json_field(self):
        secret_string = json.dumps({"DD_API_KEY": VALID_API_KEY})
        self.assertEqual(self._reload_with_secret_string(secret_string), VALID_API_KEY)

    @patch.dict(os.environ, {"DD_API_KEY_SECRET_ARN": SECRET_ARN})
    def test_aws_managed_secret_api_key_field(self):
        # AWS Secrets Manager's managed rotation for the Datadog API key
        # secret type stores the key under 'apiKey', alongside 'apiKeyId'.
        secret_string = json.dumps({"apiKey": VALID_API_KEY, "apiKeyId": "some-uuid"})
        self.assertEqual(self._reload_with_secret_string(secret_string), VALID_API_KEY)

    @patch.dict(os.environ, {"DD_API_KEY_SECRET_ARN": SECRET_ARN})
    def test_dd_api_key_field_takes_precedence_over_api_key(self):
        other_key = "2" * 32
        secret_string = json.dumps({"DD_API_KEY": VALID_API_KEY, "apiKey": other_key})
        self.assertEqual(self._reload_with_secret_string(secret_string), VALID_API_KEY)


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


if __name__ == "__main__":
    unittest.main()
