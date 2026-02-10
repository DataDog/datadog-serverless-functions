import json
import unittest
from unittest.mock import MagicMock, patch

from botocore.exceptions import ClientError

from retry.storage import S3Storage, Storage


class TestS3Storage(unittest.TestCase):
    def setUp(self):
        self.mock_s3 = MagicMock()
        with patch("retry.storage.boto3") as mock_boto3:
            mock_boto3.client.return_value = self.mock_s3
            with patch("retry.storage.DD_S3_BUCKET_NAME", "test-bucket"):
                self.storage = S3Storage("test_function_prefix")

    def test_backward_compatible_alias(self):
        self.assertIs(Storage, S3Storage)

    def test_store_data_puts_object(self):
        self.storage.store_data("logs", [{"message": "hello"}])
        self.mock_s3.put_object.assert_called_once()
        call_kwargs = self.mock_s3.put_object.call_args[1]
        self.assertEqual(call_kwargs["Bucket"], "test-bucket")
        self.assertIn("failed_events/test_function_prefix/logs/", call_kwargs["Key"])
        self.assertEqual(
            json.loads(call_kwargs["Body"].decode("UTF-8")), [{"message": "hello"}]
        )

    def test_store_data_handles_client_error(self):
        self.mock_s3.put_object.side_effect = ClientError(
            {"Error": {"Code": "500", "Message": "Error"}}, "PutObject"
        )
        # Should not raise
        self.storage.store_data("logs", [{"message": "hello"}])

    def test_get_data_returns_data_for_keys(self):
        self.mock_s3.list_objects_v2.return_value = {
            "Contents": [{"Key": "failed_events/test_function_prefix/logs/123"}]
        }
        body_mock = MagicMock()
        body_mock.read.return_value = json.dumps([{"message": "hello"}]).encode("UTF-8")
        self.mock_s3.get_object.return_value = {"Body": body_mock}

        result = self.storage.get_data("logs")
        self.assertEqual(
            result,
            {"failed_events/test_function_prefix/logs/123": [{"message": "hello"}]},
        )

    def test_get_data_handles_empty_bucket(self):
        self.mock_s3.list_objects_v2.return_value = {}
        result = self.storage.get_data("logs")
        self.assertEqual(result, {})

    def test_get_data_handles_list_error(self):
        self.mock_s3.list_objects_v2.side_effect = ClientError(
            {"Error": {"Code": "500", "Message": "Error"}}, "ListObjectsV2"
        )
        result = self.storage.get_data("logs")
        self.assertEqual(result, {})

    def test_get_data_handles_fetch_error(self):
        self.mock_s3.list_objects_v2.return_value = {
            "Contents": [{"Key": "failed_events/test_function_prefix/logs/123"}]
        }
        self.mock_s3.get_object.side_effect = ClientError(
            {"Error": {"Code": "500", "Message": "Error"}}, "GetObject"
        )
        result = self.storage.get_data("logs")
        self.assertEqual(result, {"failed_events/test_function_prefix/logs/123": None})

    def test_delete_data_deletes_object(self):
        self.storage.delete_data("failed_events/test_function_prefix/logs/123")
        self.mock_s3.delete_object.assert_called_once_with(
            Bucket="test-bucket", Key="failed_events/test_function_prefix/logs/123"
        )

    def test_delete_data_handles_client_error(self):
        self.mock_s3.delete_object.side_effect = ClientError(
            {"Error": {"Code": "500", "Message": "Error"}}, "DeleteObject"
        )
        # Should not raise
        self.storage.delete_data("some_key")

    def test_get_key_prefix(self):
        prefix = self.storage._get_key_prefix("logs")
        self.assertEqual(prefix, "failed_events/test_function_prefix/logs/")


if __name__ == "__main__":
    unittest.main()
