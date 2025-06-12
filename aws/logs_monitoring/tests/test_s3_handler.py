import gzip
import re
import unittest
from unittest.mock import MagicMock, patch

from approvaltests.combination_approvals import verify_all_combinations

from caching.cache_layer import CacheLayer
from settings import DD_CUSTOM_TAGS, DD_SOURCE
from steps.handlers.s3_handler import S3EventDataStore, S3EventHandler


class TestS3EventsHandler(unittest.TestCase):
    class Context:
        function_version = 0
        invoked_function_arn = "invoked_function_arn"
        function_name = "function_name"
        memory_limit_in_mb = "10"

    def __init__(self, methodName: str = "runTest") -> None:
        super().__init__(methodName)
        self.s3_handler = S3EventHandler(
            self.Context(), {DD_CUSTOM_TAGS: ""}, MagicMock()
        )

    def parse_lines(self, data, key, source):
        bucket = "my-bucket"
        gzip_data = gzip.compress(bytes(data, "utf-8"))

        data_store = S3EventDataStore()
        data_store.data = gzip_data
        data_store.bucket = bucket
        data_store.key = key
        data_store.source = source

        self.s3_handler.data_store = data_store

        return [line for line in self.s3_handler._get_structured_lines_for_s3_handler()]

    def test_get_structured_lines_waf(self):
        key = "mykey"
        source = "waf"
        verify_all_combinations(
            lambda d: self.parse_lines(d, key, source),
            [
                [
                    '{"timestamp": 12345, "key1": "value1", "key2":"value2"}\n',
                    (
                        '{"timestamp": 12345, "key1": "value1",'
                        ' "key2":"value2"}\r\n{"timestamp": 67890, "key1": "value2",'
                        ' "key2":"value3"}\r\n'
                    ),
                    (
                        '{"timestamp": 12345, "key1": "value1",'
                        ' "key2":"value1"}\n{"timestamp": 67890, "key1": "value2",'
                        ' "key2":"value3"}\r{"timestamp": 123456, "key1": "value3",'
                        ' "key2":"value3"}\r\n{"timestamp": 678901, "key1": "value4",'
                        ' "key2":"value4"}'
                    ),
                    (
                        '{"timestamp": 12345, "key1": "value1",'
                        ' "key2":"value2"}\n{"timestamp": 789760, "key1": "value1",'
                        ' "key3":"value4"}\n'
                    ),
                    (
                        '{"timestamp": 12345, "key1": "value1", "key2":"value2" "key3":'
                        ' {"key5" : "value5"}}\r{"timestamp": 12345, "key1":'
                        ' "value1"}\n'
                    ),
                    (
                        '{"timestamp": 12345, "key1": "value1", "key2":"value2" "key3":'
                        ' {"key5" : "value5"}}\f{"timestamp": 12345, "key1":'
                        ' "value1"}\n'
                    ),
                    (
                        '{"timestamp": 12345, "key1": "value1", "key2":"value2" "key3":'
                        ' {"key5" : "value5"}}\u00a0{"timestamp": 12345, "key1":'
                        ' "value1"}\n'
                    ),
                    (
                        '{"timestamp":1234,'
                        ' "injection":"/Ð²Ð¸ÐºÑÐ¾ÑÐ¸Ñ+Ð²Ð»Ð°ÑÐ¾Ð²Ð°/about"}'
                    ),
                    '{"timestamp":1234, "should_not_be_splitted":"\v"}',
                    '{"timestamp":1234, "should_be_splitted":"\u000d\u000acontinue"}',
                    "\n",
                    "\r\n",
                ]
            ],
        )

    def test_get_structured_lines_cloudtrail(self):
        key = (
            "123456779121_CloudTrail_eu-west-3_20180707T1735Z_abcdefghi0MCRL2O.json.gz"
        )
        source = "cloudtrail"
        verify_all_combinations(
            lambda d: self.parse_lines(d, key, source),
            [
                [
                    '{"Records": [{"event_key" : "logs-from-s3"}]}',
                    (
                        '{"Records": [{"event_key" : "logs-from-s3"}, {"key1" :'
                        ' "data1", "key2" : "data2"}]}'
                    ),
                    '{"Records": {}}',
                    "",
                ]
            ],
        )

    def test_get_partition_from_region(self):
        self.assertEqual(self.s3_handler._get_partition_from_region("us-east-1"), "aws")
        self.assertEqual(
            self.s3_handler._get_partition_from_region("us-gov-west-1"), "aws-us-gov"
        )
        self.assertEqual(
            self.s3_handler._get_partition_from_region("cn-north-1"), "aws-cn"
        )
        self.assertEqual(self.s3_handler._get_partition_from_region(None), "aws")

    def test_s3_handler(self):
        event = {
            "Records": [
                {
                    "s3": {
                        "bucket": {"name": "my-bucket"},
                        "object": {"key": "my-key"},
                    }
                }
            ]
        }
        self.s3_handler._extract_data = MagicMock()
        self.s3_handler.data_store.data = "data".encode("utf-8")
        structured_lines = list(self.s3_handler.handle(event))
        self.assertEqual(
            structured_lines,
            [
                {
                    "aws": {"s3": {"bucket": "my-bucket", "key": "my-key"}},
                    "message": "data",
                }
            ],
        )
        self.assertEqual(self.s3_handler.metadata["ddsource"], "s3")

    def test_s3_handler_overriden_source(self):
        event = {
            "Records": [
                {
                    "s3": {
                        "bucket": {"name": "tf-bedrock"},
                        "object": {"key": "bedrock-run"},
                    }
                }
            ]
        }

        self.s3_handler = S3EventHandler(
            self.Context(), {DD_CUSTOM_TAGS: "", DD_SOURCE: "something"}, MagicMock()
        )

        self.s3_handler._extract_data = MagicMock()
        self.s3_handler.data_store.data = "data".encode("utf-8")
        self.s3_handler.handle(event)
        self.assertEqual(self.s3_handler.metadata["ddsource"], "something")

    def test_s3_handler_with_multiline_regex(self):
        event = {
            "Records": [
                {
                    "s3": {
                        "bucket": {"name": "my-bucket"},
                        "object": {"key": "my-key"},
                    }
                }
            ]
        }
        data = "2022-02-08aaa\nbbbccc\n2022-02-09bbb\n2022-02-10ccc\n"
        self.s3_handler.data_store.data = data.encode("utf-8")
        self.s3_handler.multiline_regex_start_pattern = re.compile(
            r"^\d{4}-\d{2}-\d{2}"
        )
        self.s3_handler.multiline_regex_pattern = re.compile(
            r"[\n\r\f]+(?=\d{4}-\d{2}-\d{2})"
        )
        self.s3_handler._extract_data = MagicMock()
        structured_lines = list(self.s3_handler.handle(event))
        self.assertEqual(
            structured_lines,
            [
                {
                    "aws": {"s3": {"bucket": "my-bucket", "key": "my-key"}},
                    "message": "2022-02-08aaa\nbbbccc",
                },
                {
                    "aws": {"s3": {"bucket": "my-bucket", "key": "my-key"}},
                    "message": "2022-02-09bbb",
                },
                {
                    "aws": {"s3": {"bucket": "my-bucket", "key": "my-key"}},
                    "message": "2022-02-10ccc\n",
                },
            ],
        )

    def test_s3_handler_with_sns(self):
        event = {
            "Records": [
                {
                    "Sns": {
                        "Message": (
                            '{"Records": [{"s3": {"bucket": {"name": "my-bucket"},'
                            ' "object": {"key": "sns-my-key"}}}]}'
                        )
                    }
                }
            ]
        }
        self.s3_handler.data_store.data = "data".encode("utf-8")
        self.s3_handler._extract_data = MagicMock()
        structured_lines = list(self.s3_handler.handle(event))
        self.assertEqual(
            structured_lines,
            [
                {
                    "aws": {"s3": {"bucket": "my-bucket", "key": "sns-my-key"}},
                    "message": "data",
                }
            ],
        )
        self.assertEqual(self.s3_handler.metadata["ddsource"], "s3")

    @patch("caching.cloudwatch_log_group_cache.CloudwatchLogGroupTagsCache.__init__")
    @patch("steps.handlers.s3_handler.S3EventHandler._get_s3_client")
    def test_s3_tags_added_to_metadata(
        self,
        mock_get_s3_client,
        mock_cache_init,
    ):
        mock_get_s3_client.side_effect = MagicMock()
        mock_cache_init.return_value = None
        cache_layer = CacheLayer("")
        cache_layer._s3_tags_cache.get = MagicMock(return_value=["s3_tag:tag_value"])
        self.s3_handler.cache_layer = cache_layer
        event = {
            "Records": [
                {
                    "s3": {
                        "bucket": {"name": "mybucket"},
                        "object": {"key": "mykey"},
                    }
                }
            ]
        }

        _ = list(self.s3_handler.handle(event))

        assert "s3_tag:tag_value" in self.s3_handler.metadata["ddtags"]

    def test_set_source_waf_cloudfront(self):
        self.s3_handler.data_store.key = (
            "AWSLogs/123456779121/WAFLogs/cloudfront/this/is/a/prio/test.log.gz"
        )
        self.s3_handler.data_store.bucket = "my-bucket"
        self.s3_handler._set_source(
            {
                "Records": [
                    {
                        "s3": {
                            "bucket": {"name": "my-bucket"},
                            "object": {"key": self.s3_handler.data_store.key},
                        }
                    }
                ]
            }
        )
        self.assertEqual(
            self.s3_handler.data_store.source,
            "waf",
        )

    def test_set_source_cloudfront(self):
        self.s3_handler.data_store.key = "AWSLogs/123456779121/CloudFront/us-east-1/2020/10/02/21/123456779121_CloudFront_us-east-1_20201002T2100Z_abcdef.log.gz"
        self.s3_handler.data_store.bucket = "my-bucket"
        self.s3_handler._set_source(
            {
                "Records": [
                    {
                        "s3": {
                            "bucket": {"name": "my-bucket"},
                            "object": {"key": self.s3_handler.data_store.key},
                        }
                    }
                ]
            }
        )
        self.assertEqual(
            self.s3_handler.data_store.source,
            "s3",
        )


if __name__ == "__main__":
    unittest.main()
