import json
import logging
import os

import boto3
from botocore.exceptions import ClientError

from retry.base_storage import BaseStorage
from settings import DD_SQS_QUEUE_URL

logger = logging.getLogger(__name__)
logger.setLevel(logging.getLevelName(os.environ.get("DD_LOG_LEVEL", "INFO").upper()))

# SQS max message size is 256KB; use 240KB to leave room for attributes/overhead
SQS_MAX_CHUNK_BYTES = 240 * 1024
SQS_MAX_MESSAGES_PER_RECEIVE = 10
SQS_MAX_POLL_ITERATIONS = 10


class SQSStorage(BaseStorage):
    def __init__(self, function_prefix):
        self.queue_url = DD_SQS_QUEUE_URL
        self.sqs_client = boto3.client("sqs")
        self.function_prefix = function_prefix

    def get_data(self, prefix):
        """Poll SQS for messages matching prefix and function_prefix.

        Returns {receipt_handle: data} for matching messages.
        Non-matching messages are released immediately by resetting their
        visibility timeout to 0.
        """
        key_data = {}

        for _ in range(SQS_MAX_POLL_ITERATIONS):
            try:
                response = self.sqs_client.receive_message(
                    QueueUrl=self.queue_url,
                    MaxNumberOfMessages=SQS_MAX_MESSAGES_PER_RECEIVE,
                    MessageAttributeNames=["retry_prefix", "function_prefix"],
                    WaitTimeSeconds=0,
                )
            except ClientError as e:
                logger.error(f"Failed to receive SQS messages: {e}")
                break

            messages = response.get("Messages", [])
            if not messages:
                break

            for message in messages:
                receipt_handle = message["ReceiptHandle"]
                msg_retry_prefix = self._get_message_attr(message, "retry_prefix")
                msg_function_prefix = self._get_message_attr(message, "function_prefix")

                if (
                    msg_retry_prefix != str(prefix)
                    or msg_function_prefix != self.function_prefix
                ):
                    self._release_message(receipt_handle)
                    continue

                data = self._deserialize(message["Body"])
                if data is not None:
                    key_data[receipt_handle] = data

        if logger.isEnabledFor(logging.DEBUG):
            logger.debug(
                f"Found {len(key_data)} SQS retry messages for prefix {prefix}"
            )

        return key_data

    def store_data(self, prefix, data):
        """Store data as one or more SQS messages, chunking to stay under the size limit."""
        if logger.isEnabledFor(logging.DEBUG):
            logger.debug(f"Storing retry data to SQS for prefix {prefix}")

        chunks = self._chunk_data(data)
        for chunk in chunks:
            serialized = self._serialize(chunk)
            try:
                self.sqs_client.send_message(
                    QueueUrl=self.queue_url,
                    MessageBody=serialized,
                    MessageAttributes={
                        "retry_prefix": {
                            "DataType": "String",
                            "StringValue": str(prefix),
                        },
                        "function_prefix": {
                            "DataType": "String",
                            "StringValue": self.function_prefix,
                        },
                    },
                )
            except ClientError as e:
                logger.error(f"Failed to send SQS message for prefix {prefix}: {e}")

    def delete_data(self, key):
        """Delete a message by receipt handle. Idempotent — logs and swallows errors."""
        try:
            self.sqs_client.delete_message(
                QueueUrl=self.queue_url,
                ReceiptHandle=key,
            )
        except ClientError as e:
            logger.error(f"Failed to delete SQS message (receipt={key}): {e}")

    def _release_message(self, receipt_handle):
        """Make a non-matching message immediately visible to other consumers."""
        try:
            self.sqs_client.change_message_visibility(
                QueueUrl=self.queue_url,
                ReceiptHandle=receipt_handle,
                VisibilityTimeout=0,
            )
        except ClientError as e:
            logger.error(f"Failed to release SQS message: {e}")

    @staticmethod
    def _get_message_attr(message, attr_name):
        """Extract a string attribute value from an SQS message."""
        attrs = message.get("MessageAttributes", {})
        return attrs.get(attr_name, {}).get("StringValue")

    def _chunk_data(self, data):
        """Split a list of items into chunks that each fit under SQS_MAX_CHUNK_BYTES."""
        if not isinstance(data, list):
            return [data]

        chunks = []
        current_chunk = []
        current_size = 2  # account for JSON array brackets "[]"

        for item in data:
            item_json = json.dumps(item, ensure_ascii=False)
            item_size = len(item_json.encode("UTF-8"))
            # +1 for the comma separator between items
            separator_size = 1 if current_chunk else 0

            if current_size + separator_size + item_size > SQS_MAX_CHUNK_BYTES:
                if current_chunk:
                    chunks.append(current_chunk)
                if 2 + item_size > SQS_MAX_CHUNK_BYTES:
                    logger.warning(
                        f"Single item exceeds SQS message size limit "
                        f"({item_size} bytes > {SQS_MAX_CHUNK_BYTES} bytes). "
                        f"SQS send will fail for this chunk."
                    )
                current_chunk = [item]
                current_size = 2 + item_size
            else:
                current_chunk.append(item)
                current_size += separator_size + item_size

        if current_chunk:
            chunks.append(current_chunk)

        return chunks or [data]

    def _serialize(self, data):
        return json.dumps(data, ensure_ascii=False)

    def _deserialize(self, data):
        try:
            return json.loads(data)
        except (json.JSONDecodeError, TypeError) as e:
            logger.error(f"Failed to deserialize SQS message body: {e}")
            return None
