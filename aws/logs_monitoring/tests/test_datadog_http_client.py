import unittest
import sys
import types
from unittest.mock import MagicMock, patch

botocore = types.ModuleType("botocore")
botocore.config = types.ModuleType("botocore.config")
botocore.config.Config = MagicMock()
sys.modules["boto3"] = MagicMock()
sys.modules["botocore"] = botocore
sys.modules["botocore.config"] = botocore.config
sys.modules["requests"] = MagicMock()
sys.modules["requests_futures.sessions"] = MagicMock()


class TestDatadogHTTPClient(unittest.TestCase):
    def _client(self, session):
        from logs.datadog_http_client import DatadogHTTPClient

        scrubber = MagicMock()
        scrubber.scrub.side_effect = lambda payload: payload

        client = DatadogHTTPClient("example.com", 443, False, False, "apikey", scrubber)
        client._session = session
        return client

    def test_send_raises_future_exception(self):
        future = MagicMock()
        future.result.side_effect = Exception("network error")
        session = MagicMock()
        session.post.return_value = future

        with self.assertRaisesRegex(Exception, "network error"):
            self._client(session).send(['{"message":"hello"}'])

    def test_send_raises_http_error_response(self):
        response = MagicMock()
        response.raise_for_status.side_effect = Exception("403 Client Error")
        future = MagicMock()
        future.result.return_value = response
        session = MagicMock()
        session.post.return_value = future

        with self.assertRaisesRegex(Exception, "403 Client Error"):
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


if __name__ == "__main__":
    unittest.main()
