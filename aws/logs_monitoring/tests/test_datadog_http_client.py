import unittest
import sys
import types
from concurrent.futures import Future, ThreadPoolExecutor
from threading import BoundedSemaphore, Event, Thread
from unittest.mock import MagicMock, call, patch


class FakeRequestException(Exception):
    pass


class FakeHTTPError(FakeRequestException):
    def __init__(self, response=None):
        super().__init__("HTTP error")
        self.response = response


class FakeConnectionError(FakeRequestException):
    pass


class FakeTimeout(FakeRequestException):
    pass


class FakeChunkedEncodingError(FakeRequestException):
    pass


sys.modules.setdefault("requests", MagicMock())


class TestDatadogHTTPClient(unittest.TestCase):
    def _client(self, session):
        import logs.datadog_http_client as datadog_http_client

        request_module = types.SimpleNamespace(
            exceptions=types.SimpleNamespace(
                HTTPError=FakeHTTPError,
                RequestException=FakeRequestException,
                ConnectionError=FakeConnectionError,
                Timeout=FakeTimeout,
                ChunkedEncodingError=FakeChunkedEncodingError,
            )
        )
        self.enterContext(patch.object(datadog_http_client, "requests", request_module))
        self.enterContext(
            patch.object(datadog_http_client, "_request_slots", BoundedSemaphore(1))
        )

        scrubber = MagicMock()
        scrubber.scrub.side_effect = lambda payload: payload

        client = datadog_http_client.DatadogHTTPClient(
            "example.com", 443, False, False, "apikey", scrubber
        )
        client._session = session
        client._executor = MagicMock()
        client._executor.submit.return_value = session.post.return_value
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
        response.close.assert_called_once_with()

    def test_transport_failures_are_retryable(self):
        from logs.exceptions import RetriableException

        for error in (FakeConnectionError(), FakeTimeout(), FakeChunkedEncodingError()):
            with self.subTest(error=error):
                session = MagicMock()
                session.post.return_value.result.side_effect = error
                with self.assertRaises(RetriableException) as raised:
                    self._client(session).send(['"hello"'])
                self.assertIs(raised.exception.__cause__, error)

    def test_other_request_errors_are_not_retried(self):
        error = FakeRequestException("invalid request configuration")
        session = MagicMock()
        session.post.return_value.result.side_effect = error

        with self.assertRaises(FakeRequestException) as raised:
            self._client(session).send(['"hello"'])

        self.assertIs(raised.exception, error)

    def test_http_status_classification(self):
        from logs.exceptions import RetriableException

        for status in (400, 401, 403, 404, 413, 429, 500, 502, 503, 504, 599):
            with self.subTest(status=status):
                response = MagicMock(status_code=status)
                error = FakeHTTPError(response)
                response.raise_for_status.side_effect = error
                session = MagicMock()
                session.post.return_value.result.return_value = response
                expected = RetriableException if status >= 500 else FakeHTTPError

                with self.assertRaises(expected):
                    self._client(session).send(['"hello"'])

                response.close.assert_called_once_with()

    def test_request_budget_is_rechecked_after_scrubbing(self):
        from logs.exceptions import LogForwardingDeadlineExceeded

        session = MagicMock()
        client = self._client(session)
        remaining_time = MagicMock(return_value=60_000)
        client._remaining_time_provider = remaining_time

        def scrub(payload):
            remaining_time.return_value = 4_000
            return payload

        client._scrubber.scrub.side_effect = scrub

        with self.assertRaises(LogForwardingDeadlineExceeded):
            client.send(['"hello"'])

        client._executor.submit.assert_not_called()

    def test_request_wait_reserves_storage_time(self):
        session = MagicMock()
        client = self._client(session)
        client._remaining_time_provider = lambda: 8_000

        client.send(['"hello"'])

        self.assertEqual(client._executor.submit.call_args.kwargs["timeout"], 3)
        wait_timeout = session.post.return_value.result.call_args.kwargs["timeout"]
        self.assertGreater(wait_timeout, 0)
        self.assertLessEqual(wait_timeout, 3)

    def test_stalled_request_does_not_block_failure_storage_or_cleanup(self):
        from logs.exceptions import LogForwardingDeadlineExceeded

        started, release, finished = Event(), Event(), Event()
        response = MagicMock()
        errors = []

        def post(*args, **kwargs):
            started.set()
            release.wait(5)
            return response

        session = MagicMock()
        session.post.side_effect = post
        client = self._client(session)
        client._timeout = 0.02
        executor = ThreadPoolExecutor(max_workers=1)
        client._executor = MagicMock(wraps=executor)

        def forward():
            try:
                client.send(['"hello"'])
            except Exception as e:
                errors.append(e)
                try:
                    client.send(['"another batch"'])
                except Exception as repeated:
                    errors.append(repeated)
            finally:
                client._close()
                finished.set()

        thread = Thread(target=forward)
        thread.start()
        try:
            self.assertTrue(started.wait(1))
            self.assertTrue(
                finished.wait(1), "request or cleanup exceeded its deadline"
            )
            self.assertEqual(len(errors), 2)
            for error in errors:
                self.assertIsInstance(error, LogForwardingDeadlineExceeded)
            self.assertEqual(client._executor.submit.call_count, 1)
            session.close.assert_not_called()
        finally:
            release.set()
            thread.join(2)
            executor.shutdown(wait=True)

        response.close.assert_called_once_with()
        session.close.assert_called_once_with()

    def test_abandoned_failed_or_cancelled_request_cleanup(self):
        session = MagicMock()
        client = self._client(session)
        failed = Future()
        failed.set_exception(FakeConnectionError("network error"))
        client._close_abandoned_response(failed)
        session.close.assert_called_once_with()
        session.close.reset_mock()
        cancelled = Future()
        cancelled.cancel()
        client._close_abandoned_response(cancelled)
        session.close.assert_called_once_with()

    def test_busy_workers_do_not_queue_more_requests(self):
        from logs.exceptions import LogForwardingDeadlineExceeded

        session = MagicMock()
        client = self._client(session)
        slots = BoundedSemaphore(1)
        slots.acquire()
        with patch("logs.datadog_http_client._request_slots", slots):
            with self.assertRaises(LogForwardingDeadlineExceeded):
                client.send(['"hello"'])

        client._executor.submit.assert_not_called()

    def test_worker_capacity_is_released_after_submission_failure(self):
        session = MagicMock()
        client = self._client(session)
        client._executor.submit.side_effect = RuntimeError("executor unavailable")
        slots = BoundedSemaphore(1)
        with patch("logs.datadog_http_client._request_slots", slots):
            with self.assertRaisesRegex(RuntimeError, "executor unavailable"):
                client.send(['"hello"'])

        self.assertTrue(slots.acquire(blocking=False))

    def test_worker_capacity_is_released_after_request_failure(self):
        from logs.exceptions import RetriableException

        session = MagicMock()
        client = self._client(session)
        session.post.side_effect = FakeConnectionError("network error")
        slots = BoundedSemaphore(1)
        with patch("logs.datadog_http_client._request_slots", slots):
            with ThreadPoolExecutor(max_workers=1) as executor:
                client._executor = executor
                with self.assertRaises(RetriableException):
                    client.send(['"hello"'])

        self.assertTrue(slots.acquire(blocking=False))

    def test_completed_request_releases_capacity_before_callbacks_finish(self):
        run_request, callback_started, release_callback = Event(), Event(), Event()
        session = MagicMock()
        client = self._client(session)
        executor = ThreadPoolExecutor(max_workers=1)

        class DelayedCallbackExecutor:
            submissions = 0

            def submit(self, fn, *args, **kwargs):
                self.submissions += 1
                if self.submissions > 1:
                    release_callback.set()
                    return executor.submit(fn, *args, **kwargs)

                def run():
                    run_request.wait(2)
                    return fn(*args, **kwargs)

                def delay_callback(completed):
                    callback_started.set()
                    release_callback.wait(2)

                future = executor.submit(run)
                future.add_done_callback(delay_callback)
                run_request.set()
                return future

        client._executor = DelayedCallbackExecutor()
        try:
            client.send(['"first"'])
            self.assertTrue(callback_started.wait(1))
            client.send(['"second"'])
            self.assertEqual(client._executor.submissions, 2)
            self.assertEqual(session.post.call_count, 2)
        finally:
            run_request.set()
            release_callback.set()
            executor.shutdown(wait=True)
            client._close()

    def test_cancelled_queued_request_releases_capacity(self):
        from logs.exceptions import LogForwardingDeadlineExceeded

        release_worker = Event()
        session = MagicMock()
        client = self._client(session)
        client._timeout = 0.02
        slots = BoundedSemaphore(1)
        executor = ThreadPoolExecutor(max_workers=1)
        executor.submit(release_worker.wait, 2)
        client._executor = executor
        try:
            with patch("logs.datadog_http_client._request_slots", slots):
                with self.assertRaises(LogForwardingDeadlineExceeded):
                    client.send(['"hello"'])
            client._close()
            self.assertTrue(slots.acquire(blocking=False))
            session.post.assert_not_called()
            session.close.assert_called_once_with()
        finally:
            release_worker.set()
            executor.shutdown(wait=True)


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
        client.send.side_effect = RetriableException("send failed")
        mock_http_client.return_value = client

        forwarder = Forwarder.__new__(Forwarder)
        forwarder.storage = MagicMock()
        forwarder._scrubber = MagicMock()
        forwarder._matcher = MagicMock()
        forwarder._matcher.match.return_value = True
        forwarder._batcher = MagicMock()
        forwarder._batcher.batch.return_value = [['"hello"']]

        forwarder._forward_logs(["hello"])

        self.assertEqual(client.send.call_count, 6)
        self.assertEqual(
            mock_sleep.call_args_list,
            [call(1), call(2), call(4), call(8), call(16)],
        )
        forwarder.storage.store_data.assert_called_once_with(
            RetryPrefix.LOGS, ['"hello"']
        )
        mock_send_metric.assert_any_call("logs_failed", ['"hello"'])
        mock_send_metric.assert_any_call("logs_forwarded", 0)

    @patch("forwarder.send_event_metric")
    @patch("forwarder.DatadogHTTPClient")
    @patch("forwarder.DD_STORE_FAILED_EVENTS", True)
    def test_forward_logs_stores_batch_skipped_near_timeout(
        self, mock_http_client, mock_send_metric
    ):
        from forwarder import Forwarder
        from retry.enums import RetryPrefix

        client = MagicMock()
        client.__enter__.return_value = client
        mock_http_client.return_value = client

        forwarder = Forwarder.__new__(Forwarder)
        forwarder.storage = MagicMock()
        forwarder._scrubber = MagicMock()
        forwarder._matcher = MagicMock()
        forwarder._matcher.match.return_value = True
        forwarder._batcher = MagicMock()
        forwarder._batcher.batch.return_value = [['"one"'], ['"two"']]

        remaining_time_provider = MagicMock(side_effect=[16_000, 14_000])
        forwarder._forward_logs(
            ["one", "two"], remaining_time_provider=remaining_time_provider
        )

        client.send.assert_called_once_with(['"one"'])
        forwarder.storage.store_data.assert_called_once_with(
            RetryPrefix.LOGS, ['"two"']
        )
        mock_send_metric.assert_any_call("logs_failed", ['"two"'])
        mock_send_metric.assert_any_call("logs_forwarded", 1)


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

    @patch("logs.datadog_client.time.sleep")
    def test_stops_after_max_retries(self, mock_sleep):
        from logs.datadog_client import DatadogClient
        from logs.exceptions import RetriableException

        client = MagicMock()
        client.send.side_effect = RetriableException("HTTP 503")

        with self.assertRaises(RetriableException):
            DatadogClient(client, max_retries=2).send(["log"])

        self.assertEqual(client.send.call_count, 3)
        self.assertEqual(mock_sleep.call_args_list, [call(1), call(2)])

    @patch("logs.datadog_client.time.sleep")
    def test_stops_retries_when_lambda_is_near_timeout(self, mock_sleep):
        from logs.datadog_client import DatadogClient
        from logs.exceptions import RetriableException

        client = MagicMock()
        client.send.side_effect = RetriableException("HTTP 503")
        remaining_time_provider = MagicMock(return_value=17_000)

        def sleep(seconds):
            remaining_time_provider.return_value -= seconds * 1000

        mock_sleep.side_effect = sleep

        with self.assertRaises(RetriableException):
            DatadogClient(
                client,
                remaining_time_provider=remaining_time_provider,
            ).send(["log"])

        self.assertEqual(client.send.call_count, 2)
        mock_sleep.assert_called_once_with(1)
        self.assertEqual(remaining_time_provider.call_count, 4)

    @patch("logs.datadog_client.time.sleep")
    def test_rechecks_budget_after_backoff(self, mock_sleep):
        from logs.datadog_client import DatadogClient
        from logs.exceptions import LogForwardingDeadlineExceeded, RetriableException

        client = MagicMock()
        client.send.side_effect = RetriableException("503")
        remaining_time = MagicMock(return_value=60_000)

        def oversleep(seconds):
            remaining_time.return_value = 10_000

        mock_sleep.side_effect = oversleep
        with self.assertRaises(LogForwardingDeadlineExceeded):
            DatadogClient(client, remaining_time_provider=remaining_time).send(["log"])

        client.send.assert_called_once_with(["log"])
        mock_sleep.assert_called_once_with(1)

    @patch("logs.datadog_client.time.sleep")
    def test_never_starts_without_valid_time_budget(self, mock_sleep):
        from logs.datadog_client import DatadogClient
        from logs.exceptions import LogForwardingDeadlineExceeded

        for remaining in (0, -1, 15_000, None, "unknown", float("nan"), float("inf")):
            with self.subTest(remaining=remaining):
                client = MagicMock()
                with self.assertRaises(LogForwardingDeadlineExceeded):
                    DatadogClient(
                        client, remaining_time_provider=lambda: remaining
                    ).send(["log"])
                client.send.assert_not_called()
        mock_sleep.assert_not_called()

    @patch("logs.datadog_client.time.sleep")
    def test_backoff_does_not_exceed_configured_maximum(self, mock_sleep):
        from logs.datadog_client import DatadogClient
        from logs.exceptions import RetriableException

        client = MagicMock()
        client.send.side_effect = RetriableException("503")
        with self.assertRaises(RetriableException):
            DatadogClient(client, max_backoff=3, max_retries=4).send(["log"])

        self.assertEqual(
            mock_sleep.call_args_list, [call(1), call(2), call(3), call(3)]
        )

    @patch("logs.datadog_client.time.sleep")
    def test_zero_retries_sends_once(self, mock_sleep):
        from logs.datadog_client import DatadogClient
        from logs.exceptions import RetriableException

        client = MagicMock()
        client.send.side_effect = RetriableException("503")
        with self.assertRaises(RetriableException):
            DatadogClient(client, max_retries=0).send(["log"])

        client.send.assert_called_once_with(["log"])
        mock_sleep.assert_not_called()


if __name__ == "__main__":
    unittest.main()
