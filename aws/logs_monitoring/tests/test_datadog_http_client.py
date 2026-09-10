import unittest
import sys
import types
from unittest.mock import MagicMock, patch


class FakeRequestException(Exception):
    pass


class FakeHTTPError(FakeRequestException):
    def __init__(self, response=None):
        super().__init__("HTTP error")
        self.response = response


class FakeConnectionError(FakeRequestException):
    pass


sys.modules["requests"] = MagicMock()
sys.modules["requests"].exceptions = types.SimpleNamespace(
    HTTPError=FakeHTTPError,
    RequestException=FakeRequestException,
    ConnectionError=FakeConnectionError,
)
sys.modules["requests_futures.sessions"] = MagicMock()


class TestDatadogHTTPClient(unittest.TestCase):
    def _client(self, session):
        from logs.datadog_http_client import DatadogHTTPClient

        scrubber = MagicMock()
        scrubber.scrub.side_effect = lambda payload: payload

        client = DatadogHTTPClient("example.com", 443, False, False, "apikey", scrubber)
        client._session = session
        return client

    def test_send_raises_retriable_exception_for_network_error(self):
        from logs.exceptions import RetriableException

        future = MagicMock()
        future.result.side_effect = FakeConnectionError("network error")
        session = MagicMock()
        session.post.return_value = future

        with self.assertRaisesRegex(RetriableException, "network error"):
            self._client(session).send(['{"message":"hello"}'])

    def test_send_preserves_unexpected_future_exception(self):
        future = MagicMock()
        future.result.side_effect = Exception("unexpected error")
        session = MagicMock()
        session.post.return_value = future

        with self.assertRaisesRegex(Exception, "unexpected error"):
            self._client(session).send(['{"message":"hello"}'])

    def test_send_raises_retriable_exception_for_server_error(self):
        from logs.exceptions import RetriableException

        response = MagicMock()
        response.status_code = 503
        response.raise_for_status.side_effect = FakeHTTPError(response=response)
        future = MagicMock()
        future.result.return_value = response
        session = MagicMock()
        session.post.return_value = future

        with self.assertRaisesRegex(RetriableException, "HTTP 503"):
            self._client(session).send(['{"message":"hello"}'])

    def test_send_does_not_retry_client_error_response(self):
        response = MagicMock()
        response.status_code = 403
        response.raise_for_status.side_effect = FakeHTTPError(response=response)
        future = MagicMock()
        future.result.return_value = response
        session = MagicMock()
        session.post.return_value = future

        with self.assertRaises(FakeHTTPError):
            self._client(session).send(['{"message":"hello"}'])

    def test_send_returns_after_successful_response(self):
        response = MagicMock()
        future = MagicMock()
        future.result.return_value = response
        session = MagicMock()
        session.post.return_value = future

        self._client(session).send(['{"message":"hello"}'])

        response.raise_for_status.assert_called_once_with()


class TestForwarderFailedLogs(unittest.TestCase):
    @patch("forwarder.send_event_metric")
    @patch("forwarder.DatadogHTTPClient")
    @patch("forwarder.DD_STORE_FAILED_EVENTS", True)
    def test_forward_logs_stores_failed_batch(self, mock_http_client, mock_send_metric):
        from forwarder import Forwarder
        from retry.enums import RetryPrefix

        client = MagicMock()
        client.__enter__.return_value = client
        client.send.side_effect = Exception("send failed")
        mock_http_client.return_value = client

        forwarder = Forwarder.__new__(Forwarder)
        forwarder.storage = MagicMock()
        forwarder._scrubber = MagicMock()
        forwarder._matcher = MagicMock()
        forwarder._matcher.match.return_value = True
        forwarder._batcher = MagicMock()
        forwarder._batcher.batch.return_value = [['"hello"']]

        forwarder._forward_logs(["hello"])

        forwarder.storage.store_data.assert_called_once_with(
            RetryPrefix.LOGS, ['"hello"']
        )
        mock_send_metric.assert_any_call("logs_failed", ['"hello"'])
        mock_send_metric.assert_any_call("logs_forwarded", 0)


class TestDatadogClient(unittest.TestCase):
    @patch("logs.datadog_client.time.sleep")
    def test_retries_retriable_http_failure(self, mock_sleep):
        from logs.datadog_client import DatadogClient
        from logs.exceptions import RetriableException

        client = MagicMock()
        client.send.side_effect = [RetriableException("HTTP 503"), None]

        DatadogClient(client).send(["log"])

        self.assertEqual(client.send.call_count, 2)
        mock_sleep.assert_called_once_with(1)


if __name__ == "__main__":
    unittest.main()
