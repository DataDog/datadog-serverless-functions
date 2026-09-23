import unittest
import sys
from unittest.mock import MagicMock, call, patch

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

    @patch("logs.datadog_client.time.sleep")
    def test_send_raises_future_exception(self, mock_sleep):
        from logs.datadog_client import DatadogClient

        future = MagicMock()
        future.result.side_effect = Exception("network error")
        session = MagicMock()
        session.post.return_value = future

        with self.assertRaisesRegex(Exception, "network error"):
            DatadogClient(self._client(session)).send(['{"message":"hello"}'])

        session.post.assert_called_once()
        mock_sleep.assert_not_called()

    @patch("logs.datadog_client.time.sleep")
    def test_send_retries_5xx_then_succeeds(self, mock_sleep):
        from logs.datadog_client import DatadogClient

        for status in range(500, 600):
            with self.subTest(status=status):
                mock_sleep.reset_mock()
                unavailable = MagicMock(status_code=status)
                success = MagicMock(status_code=202)
                session = MagicMock()
                session.post.return_value.result.side_effect = [unavailable, success]

                DatadogClient(self._client(session)).send(['{"message":"hello"}'])

                self.assertEqual(session.post.call_count, 2)
                self.assertEqual(
                    session.post.call_args_list[0], session.post.call_args_list[1]
                )
                mock_sleep.assert_called_once_with(1)
                success.raise_for_status.assert_called_once_with()

    @patch("logs.datadog_client.time.sleep")
    def test_other_http_errors_are_not_retried(self, mock_sleep):
        from logs.datadog_client import DatadogClient

        for status in (400, 403, 429, 499, 600):
            with self.subTest(status=status):
                error = Exception(f"HTTP {status}")
                response = MagicMock(status_code=status)
                response.raise_for_status.side_effect = error
                session = MagicMock()
                session.post.return_value.result.return_value = response

                with self.assertRaises(Exception) as raised:
                    DatadogClient(self._client(session)).send(['"hello"'])

                self.assertIs(raised.exception, error)
                session.post.assert_called_once()
        mock_sleep.assert_not_called()

    def test_send_returns_after_successful_response(self):
        response = MagicMock()
        future = MagicMock()
        future.result.return_value = response
        session = MagicMock()
        session.post.return_value = future

        self._client(session).send(['{"message":"hello"}'])

        response.raise_for_status.assert_called_once_with()


class TestForwarderFailedLogs(unittest.TestCase):
    @patch("logs.datadog_client.time.sleep")
    @patch("forwarder.send_event_metric")
    @patch("forwarder.DatadogHTTPClient")
    @patch("forwarder.DD_STORE_FAILED_EVENTS", True)
    def test_forward_logs_stores_failed_batch(
        self, mock_http_client, mock_send_metric, mock_sleep
    ):
        from forwarder import Forwarder
        from logs.exceptions import RetriableException
        from retry.enums import RetryPrefix

        client = MagicMock()
        client.__enter__.return_value = client
        client.send.side_effect = RetriableException("HTTP 503")
        mock_http_client.return_value = client

        forwarder = Forwarder.__new__(Forwarder)
        forwarder.storage = MagicMock()
        forwarder._scrubber = MagicMock()
        forwarder._matcher = MagicMock()
        forwarder._matcher.match.return_value = True
        forwarder._batcher = MagicMock()
        forwarder._batcher.batch.return_value = [['"hello"']]

        for provider, attempts, sleeps in (
            (None, 3, [call(1), call(2)]),
            (lambda: 15_000, 1, []),
        ):
            with self.subTest(attempts=attempts):
                client.send.reset_mock()
                mock_sleep.reset_mock()
                mock_send_metric.reset_mock()
                forwarder.storage.reset_mock()

                forwarder._forward_logs(["hello"], remaining_time_provider=provider)

                self.assertEqual(client.send.call_count, attempts)
                self.assertEqual(mock_sleep.call_args_list, sleeps)
                forwarder.storage.store_data.assert_called_once_with(
                    RetryPrefix.LOGS, ['"hello"']
                )
                mock_send_metric.assert_any_call("logs_failed", ['"hello"'])
                mock_send_metric.assert_any_call("logs_forwarded", 0)


class TestDatadogClient(unittest.TestCase):
    @patch("logs.datadog_client.time.sleep")
    def test_retry_budget_is_live_and_checked_after_sleep(self, mock_sleep):
        from logs.datadog_client import DatadogClient
        from logs.exceptions import RetriableException

        for budgets, attempts, sleeps in (
            ([16_000], 1, []),
            ([60_000, 15_000], 1, [call(1)]),
            ([60_000, 59_000, 17_000], 2, [call(1)]),
        ):
            with self.subTest(budgets=budgets):
                mock_sleep.reset_mock()
                client = MagicMock()
                error = RetriableException("HTTP 503")
                client.send.side_effect = error
                remaining_time = MagicMock(side_effect=budgets)

                with self.assertRaises(RetriableException) as raised:
                    DatadogClient(client, remaining_time_provider=remaining_time).send(
                        ["log"]
                    )

                self.assertIs(raised.exception, error)
                self.assertEqual(client.send.call_count, attempts)
                self.assertEqual(mock_sleep.call_args_list, sleeps)
                self.assertEqual(remaining_time.call_count, len(budgets))

    @patch("logs.datadog_client.time.sleep")
    def test_zero_retries_sends_once(self, mock_sleep):
        from logs.datadog_client import DatadogClient
        from logs.exceptions import RetriableException

        client = MagicMock()
        client.send.side_effect = RetriableException("HTTP 503")
        with self.assertRaises(RetriableException):
            DatadogClient(client, max_retries=0).send(["log"])

        client.send.assert_called_once_with(["log"])
        mock_sleep.assert_not_called()


if __name__ == "__main__":
    unittest.main()
