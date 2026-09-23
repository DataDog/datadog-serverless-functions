import json
import unittest
from unittest.mock import MagicMock, patch

from botocore.exceptions import ClientError

from retry.sqs_storage import SQSStorage, SQS_MAX_CHUNK_BYTES


class TestSQSStorage(unittest.TestCase):
    def setUp(self):
        self.mock_sqs = MagicMock()
        with patch("retry.sqs_storage.boto3") as mock_boto3:
            mock_boto3.client.return_value = self.mock_sqs
            with patch(
                "retry.sqs_storage.DD_SQS_QUEUE_URL",
                "https://sqs.us-east-1.amazonaws.com/123456789012/my-queue",
            ):
                self.storage = SQSStorage("test_function_prefix")

    def test_store_data_sends_message_with_attributes(self):
        data = [{"message": "hello"}]
        self.storage.store_data("logs", data)

        self.mock_sqs.send_message.assert_called_once()
        call_kwargs = self.mock_sqs.send_message.call_args[1]
        self.assertEqual(
            call_kwargs["QueueUrl"],
            "https://sqs.us-east-1.amazonaws.com/123456789012/my-queue",
        )
        self.assertEqual(
            call_kwargs["MessageAttributes"]["retry_prefix"]["StringValue"], "logs"
        )
        self.assertEqual(
            call_kwargs["MessageAttributes"]["function_prefix"]["StringValue"],
            "test_function_prefix",
        )
        self.assertEqual(json.loads(call_kwargs["MessageBody"]), data)

    def test_store_data_chunks_large_data(self):
        # Create two items that each fit individually but together exceed 240KB
        large_item = {"message": "x" * (SQS_MAX_CHUNK_BYTES - 50)}
        small_item = {"message": "y" * 100}
        data = [large_item, small_item]

        self.storage.store_data("logs", data)

        # Should send 2 messages (items can't fit in one chunk)
        self.assertEqual(self.mock_sqs.send_message.call_count, 2)

    def test_store_data_handles_client_error(self):
        self.mock_sqs.send_message.side_effect = ClientError(
            {"Error": {"Code": "500", "Message": "Error"}}, "SendMessage"
        )
        # Should not raise
        self.storage.store_data("logs", [{"message": "hello"}])

    def test_get_data_returns_matching_messages(self):
        self.mock_sqs.receive_message.side_effect = [
            {
                "Messages": [
                    {
                        "ReceiptHandle": "handle1",
                        "Body": json.dumps([{"message": "hello"}]),
                        "MessageAttributes": {
                            "retry_prefix": {"StringValue": "logs"},
                            "function_prefix": {"StringValue": "test_function_prefix"},
                        },
                    }
                ]
            },
            {"Messages": []},
        ]

        result = self.storage.get_data("logs")
        self.assertEqual(result, {"handle1": [{"message": "hello"}]})

    def test_get_data_releases_non_matching_messages(self):
        self.mock_sqs.receive_message.side_effect = [
            {
                "Messages": [
                    {
                        "ReceiptHandle": "handle_other",
                        "Body": json.dumps([{"message": "other"}]),
                        "MessageAttributes": {
                            "retry_prefix": {"StringValue": "metrics"},
                            "function_prefix": {"StringValue": "other_function"},
                        },
                    }
                ]
            },
            {"Messages": []},
        ]

        result = self.storage.get_data("logs")
        self.assertEqual(result, {})
        self.mock_sqs.change_message_visibility.assert_called_once_with(
            QueueUrl="https://sqs.us-east-1.amazonaws.com/123456789012/my-queue",
            ReceiptHandle="handle_other",
            VisibilityTimeout=0,
        )

    def test_get_data_handles_empty_queue(self):
        self.mock_sqs.receive_message.return_value = {"Messages": []}
        result = self.storage.get_data("logs")
        self.assertEqual(result, {})

    def test_get_data_handles_no_messages_key(self):
        self.mock_sqs.receive_message.return_value = {}
        result = self.storage.get_data("logs")
        self.assertEqual(result, {})

    def test_get_data_handles_client_error(self):
        self.mock_sqs.receive_message.side_effect = ClientError(
            {"Error": {"Code": "500", "Message": "Error"}}, "ReceiveMessage"
        )
        result = self.storage.get_data("logs")
        self.assertEqual(result, {})

    def test_get_data_skips_invalid_json(self):
        self.mock_sqs.receive_message.side_effect = [
            {
                "Messages": [
                    {
                        "ReceiptHandle": "handle1",
                        "Body": "not valid json{{{",
                        "MessageAttributes": {
                            "retry_prefix": {"StringValue": "logs"},
                            "function_prefix": {"StringValue": "test_function_prefix"},
                        },
                    }
                ]
            },
            {"Messages": []},
        ]

        result = self.storage.get_data("logs")
        self.assertEqual(result, {})

    def test_delete_data_calls_delete_message(self):
        self.storage.delete_data("receipt_handle_123")
        self.mock_sqs.delete_message.assert_called_once_with(
            QueueUrl="https://sqs.us-east-1.amazonaws.com/123456789012/my-queue",
            ReceiptHandle="receipt_handle_123",
        )

    def test_delete_data_is_idempotent(self):
        self.mock_sqs.delete_message.side_effect = ClientError(
            {"Error": {"Code": "ReceiptHandleIsInvalid", "Message": "Error"}},
            "DeleteMessage",
        )
        # Should not raise
        self.storage.delete_data("already_deleted_handle")

    def test_chunk_data_single_small_list(self):
        data = [{"a": 1}, {"b": 2}]
        chunks = self.storage._chunk_data(data)
        self.assertEqual(len(chunks), 1)
        self.assertEqual(chunks[0], data)

    def test_chunk_data_non_list(self):
        data = {"key": "value"}
        chunks = self.storage._chunk_data(data)
        self.assertEqual(chunks, [data])

    def test_chunk_data_empty_list(self):
        chunks = self.storage._chunk_data([])
        self.assertEqual(chunks, [[]])

    def test_get_data_polls_multiple_iterations(self):
        """Verify that get_data keeps polling until an empty response."""
        self.mock_sqs.receive_message.side_effect = [
            {
                "Messages": [
                    {
                        "ReceiptHandle": f"handle_{i}",
                        "Body": json.dumps([{"msg": i}]),
                        "MessageAttributes": {
                            "retry_prefix": {"StringValue": "logs"},
                            "function_prefix": {"StringValue": "test_function_prefix"},
                        },
                    }
                ]
            }
            for i in range(3)
        ] + [{"Messages": []}]

        result = self.storage.get_data("logs")
        self.assertEqual(len(result), 3)
        self.assertEqual(self.mock_sqs.receive_message.call_count, 4)


if __name__ == "__main__":
    unittest.main()
