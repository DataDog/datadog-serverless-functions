import json
import unittest
from unittest.mock import MagicMock, call, patch

from forwarder import Forwarder
from logs.datadog_batcher import DatadogBatcher
from logs.exceptions import RetriableException
from retry.enums import RetryPrefix


class TestLogDelivery(unittest.TestCase):
    def setUp(self):
        self.http_client = self.enterContext(patch("forwarder.DatadogHTTPClient"))
        self.client = self.http_client.return_value
        self.sleep = self.enterContext(patch("logs.datadog_client.time.sleep"))
        self.send_metric = self.enterContext(patch("forwarder.send_event_metric"))
        self.enterContext(patch("forwarder.DD_STORE_FAILED_EVENTS", True))
        self.forwarder = Forwarder.__new__(Forwarder)
        self.forwarder.storage = MagicMock()
        self.forwarder._scrubber = MagicMock()
        self.forwarder._matcher = MagicMock()
        self.forwarder._matcher.match.return_value = True
        self.forwarder._batcher = DatadogBatcher(512_000, 4_000_000, 1)
        self.logs = [{"message": "one"}, {"message": "two"}, {"message": "three"}]
        self.serialized_logs = [json.dumps(log) for log in self.logs]

    def test_retry_key_is_deleted_only_after_every_batch_succeeds(self):
        deletions_during_sends = []

        def send(batch):
            deletions_during_sends.append(self.forwarder.storage.delete_data.call_count)

        self.client.send.side_effect = send

        self.forwarder._forward_logs(self.serialized_logs, key="retry-key")

        self.assertEqual(self.client.send.call_count, 3)
        self.assertEqual(deletions_during_sends, [0, 0, 0])
        self.forwarder.storage.delete_data.assert_called_once_with("retry-key")
        self.forwarder.storage.store_data.assert_not_called()

    def test_retry_key_survives_failure_before_or_after_success(self):
        for outcomes in (
            [RuntimeError("intake failed"), None, None],
            [None, RuntimeError("intake failed"), None],
            [None, None, RuntimeError("intake failed")],
        ):
            with self.subTest(outcomes=outcomes):
                self.client.send.reset_mock()
                self.client.send.side_effect = outcomes
                self.forwarder.storage.reset_mock()

                self.forwarder._forward_logs(self.serialized_logs, key="retry-key")

                self.forwarder.storage.delete_data.assert_not_called()
                self.forwarder.storage.store_data.assert_not_called()
                self.assertEqual(self.client.send.call_count, 3)

    def test_retry_key_survives_timeout_after_a_successful_batch(self):
        remaining_time = MagicMock(return_value=60_000)

        def send(batch):
            remaining_time.return_value = 15_000

        self.client.send.side_effect = send

        self.forwarder._forward_logs(
            self.serialized_logs,
            key="retry-key",
            remaining_time_provider=remaining_time,
        )

        self.assertEqual(self.client.send.call_count, 1)
        self.forwarder.storage.delete_data.assert_not_called()
        self.forwarder.storage.store_data.assert_not_called()
        self.send_metric.assert_any_call("logs_forwarded", 1)

    def test_timeout_preserves_all_unstarted_batches(self):
        remaining_time = MagicMock(return_value=60_000)

        def send(batch):
            remaining_time.return_value = 15_000

        self.client.send.side_effect = send

        self.forwarder._forward_logs(self.logs, remaining_time_provider=remaining_time)

        self.client.send.assert_called_once_with([self.serialized_logs[0]])
        self.forwarder.storage.store_data.assert_called_once_with(
            RetryPrefix.LOGS, self.serialized_logs[1:]
        )
        self.send_metric.assert_any_call("logs_forwarded", 1)

    def test_failure_exhausts_time_and_preserves_failed_and_unstarted_batches(self):
        remaining_time = MagicMock(return_value=60_000)

        def send(batch):
            remaining_time.return_value = 15_000
            raise RetriableException("intake failed")

        self.client.send.side_effect = send

        self.forwarder._forward_logs(self.logs, remaining_time_provider=remaining_time)

        self.client.send.assert_called_once_with([self.serialized_logs[0]])
        self.sleep.assert_not_called()
        self.forwarder.storage.store_data.assert_called_once_with(
            RetryPrefix.LOGS, self.serialized_logs
        )

    def test_no_storage_raises_for_skipped_logs(self):
        with patch("forwarder.DD_STORE_FAILED_EVENTS", False):
            with self.assertRaisesRegex(RuntimeError, "failed-event storage"):
                self.forwarder._forward_logs(
                    self.logs, remaining_time_provider=lambda: 15_000
                )

        self.client.send.assert_not_called()
        self.forwarder.storage.store_data.assert_not_called()

    def test_no_storage_raises_after_failed_attempts(self):
        for error in (RetriableException("503"), RuntimeError("403")):
            with self.subTest(error=error):
                self.client.send.side_effect = error
                with patch("forwarder.DD_STORE_FAILED_EVENTS", False):
                    with self.assertRaisesRegex(RuntimeError, "failed-event storage"):
                        self.forwarder._forward_logs(self.logs)

        self.forwarder.storage.store_data.assert_not_called()

    def test_existing_retry_record_does_not_require_new_storage(self):
        with patch("forwarder.DD_STORE_FAILED_EVENTS", False):
            self.forwarder._forward_logs(
                self.serialized_logs,
                key="retry-key",
                remaining_time_provider=lambda: 15_000,
            )

        self.client.send.assert_not_called()
        self.forwarder.storage.delete_data.assert_not_called()
        self.forwarder.storage.store_data.assert_not_called()

    def test_storage_write_error_propagates(self):
        self.client.send.side_effect = RuntimeError("intake failed")
        self.forwarder.storage.store_data.side_effect = RuntimeError("storage failed")

        with self.assertRaisesRegex(RuntimeError, "storage failed"):
            self.forwarder._forward_logs(self.logs)

        self.forwarder.storage.delete_data.assert_not_called()

    def test_failed_time_provider_preserves_all_batches(self):
        remaining_time = MagicMock(side_effect=RuntimeError("context unavailable"))

        self.forwarder._forward_logs(self.logs, remaining_time_provider=remaining_time)

        self.client.send.assert_not_called()
        self.forwarder.storage.store_data.assert_called_once_with(
            RetryPrefix.LOGS, self.serialized_logs
        )

    def test_empty_or_filtered_retry_record_is_deleted(self):
        self.forwarder._matcher.match.return_value = False

        self.forwarder._forward_logs(self.serialized_logs, key="retry-key")

        self.client.send.assert_not_called()
        self.forwarder.storage.delete_data.assert_called_once_with("retry-key")

    def test_retry_records_are_acknowledged_independently(self):
        self.forwarder.storage.get_data.return_value = {
            "partial-key": self.serialized_logs[:2],
            "complete-key": self.serialized_logs[2:],
        }
        self.client.send.side_effect = [None, RuntimeError("intake failed"), None]

        self.forwarder._retry_prefix(RetryPrefix.LOGS)

        self.forwarder.storage.delete_data.assert_has_calls([call("complete-key")])
        self.assertEqual(self.forwarder.storage.delete_data.call_count, 1)
