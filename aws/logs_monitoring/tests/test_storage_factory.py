import unittest
from unittest.mock import patch

from retry.storage import S3Storage
from retry.sqs_storage import SQSStorage


class TestCreateStorage(unittest.TestCase):
    @patch("retry.sqs_storage.boto3")
    @patch("retry.DD_SQS_QUEUE_URL", "https://sqs.us-east-1.amazonaws.com/123/queue")
    @patch(
        "retry.sqs_storage.DD_SQS_QUEUE_URL",
        "https://sqs.us-east-1.amazonaws.com/123/queue",
    )
    def test_sqs_backend_when_queue_url_set(self, mock_boto3):
        from retry import create_storage

        storage = create_storage("func_prefix")
        self.assertIsInstance(storage, SQSStorage)

    @patch("retry.storage.boto3")
    @patch("retry.DD_SQS_QUEUE_URL", None)
    @patch("retry.storage.DD_S3_BUCKET_NAME", "my-bucket")
    def test_s3_backend_when_no_queue_url(self, mock_boto3):
        from retry import create_storage

        storage = create_storage("func_prefix")
        self.assertIsInstance(storage, S3Storage)

    @patch("retry.storage.boto3")
    @patch("retry.DD_SQS_QUEUE_URL", None)
    def test_falls_back_to_s3_when_no_backend_configured(self, mock_boto3):
        """When no SQS queue is configured, always fall back to S3Storage.

        This preserves backward compatibility: S3Storage with an empty bucket
        name is safe as long as DD_STORE_FAILED_EVENTS is false (the default).
        """
        from retry import create_storage

        storage = create_storage("func_prefix")
        self.assertIsInstance(storage, S3Storage)

    @patch("retry.sqs_storage.boto3")
    @patch("retry.DD_SQS_QUEUE_URL", "https://sqs.us-east-1.amazonaws.com/123/queue")
    @patch(
        "retry.sqs_storage.DD_SQS_QUEUE_URL",
        "https://sqs.us-east-1.amazonaws.com/123/queue",
    )
    def test_sqs_takes_priority_over_s3(self, mock_boto3):
        """SQS is selected even when S3 bucket is not set."""
        from retry import create_storage

        storage = create_storage("func_prefix")
        self.assertIsInstance(storage, SQSStorage)


if __name__ == "__main__":
    unittest.main()
