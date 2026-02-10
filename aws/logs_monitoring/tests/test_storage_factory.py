import unittest
from unittest.mock import patch

from retry.storage import S3Storage
from retry.sqs_storage import SQSStorage


class TestCreateStorage(unittest.TestCase):
    @patch("retry.sqs_storage.boto3")
    @patch("retry.DD_SQS_QUEUE_URL", "https://sqs.us-east-1.amazonaws.com/123/queue")
    @patch("retry.DD_S3_BUCKET_NAME", "my-bucket")
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
    @patch("retry.DD_S3_BUCKET_NAME", "my-bucket")
    @patch("retry.storage.DD_S3_BUCKET_NAME", "my-bucket")
    def test_s3_backend_when_no_queue_url(self, mock_boto3):
        from retry import create_storage

        storage = create_storage("func_prefix")
        self.assertIsInstance(storage, S3Storage)

    @patch("retry.DD_SQS_QUEUE_URL", None)
    @patch("retry.DD_S3_BUCKET_NAME", None)
    def test_raises_when_no_backend_configured(self):
        from retry import create_storage

        with self.assertRaises(ValueError) as ctx:
            create_storage("func_prefix")
        self.assertIn("No storage backend configured", str(ctx.exception))

    @patch("retry.sqs_storage.boto3")
    @patch("retry.DD_SQS_QUEUE_URL", "https://sqs.us-east-1.amazonaws.com/123/queue")
    @patch("retry.DD_S3_BUCKET_NAME", None)
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
