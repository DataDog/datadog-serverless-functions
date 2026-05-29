import unittest
from unittest.mock import MagicMock, patch

import settings as _settings_module
from settings import is_api_key_valid

VALID_API_KEY = "11111111111111111111111111111111"


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


if __name__ == "__main__":
    unittest.main()
