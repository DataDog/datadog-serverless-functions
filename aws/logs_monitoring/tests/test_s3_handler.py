import gzip
import unittest
from unittest.mock import MagicMock, patch
from approvaltests.combination_approvals import verify_all_combinations
from steps.handlers.s3_handler import S3EventHandler, S3EventDataStore
from caching.cache_layer import CacheLayer


class TestS3EventsHandler(unittest.TestCase):
    class Context:
        function_version = 0
        invoked_function_arn = "invoked_function_arn"
        function_name = "function_name"
        memory_limit_in_mb = "10"

    def __init__(self, methodName: str = "runTest") -> None:
        super().__init__(methodName)
        self.s3_handler = S3EventHandler(self.Context(), {"ddtags": ""}, MagicMock())

    def parse_lines(self, data, key, source):
        bucket = "my-bucket"
        gzip_data = gzip.compress(bytes(data, "utf-8"))

        data_store = S3EventDataStore()
        data_store.data = gzip_data
        data_store.bucket = bucket
        data_store.key = key
        data_store.source = source

        self.s3_handler.data_store = data_store

        return [l for l in self.s3_handler._get_structured_lines_for_s3_handler()]

    def test_get_structured_lines_waf(self):
        key = "mykey"
        source = "waf"
        verify_all_combinations(
            lambda d: self.parse_lines(d, key, source),
            [
                [
                    '{"timestamp": 12345, "key1": "value1", "key2":"value2"}\n',
                    '{"timestamp": 12345, "key1": "value1", "key2":"value2"}\n{"timestamp": 789760, "key1": "value1", "key3":"value4"}\n',
                    '{"timestamp": 12345, "key1": "value1", "key2":"value2" "key3": {"key5" : "value5"}}\r{"timestamp": 12345, "key1": "value1"}\n',
                    '{"timestamp": 12345, "key1": "value1", "key2":"value2" "key3": {"key5" : "value5"}}\f{"timestamp": 12345, "key1": "value1"}\n',
                    '{"timestamp": 12345, "key1": "value1", "key2":"value2" "key3": {"key5" : "value5"}}\u00A0{"timestamp": 12345, "key1": "value1"}\n',
                    "",
                    "\n",
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
                    '{"Records": [{"event_key" : "logs-from-s3"}, {"key1" : "data1", "key2" : "data2"}]}',
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
        self.assertEqual(self.s3_handler.metadata["host"], "arn:aws:s3:::my-bucket")

    def test_s3_handler_with_sns(self):
        event = {
            "Records": [
                {
                    "Sns": {
                        "Message": '{"Records": [{"s3": {"bucket": {"name": "my-bucket"}, "object": {"key": "sns-my-key"}}}]}'
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
        self.assertEqual(self.s3_handler.metadata["host"], "arn:aws:s3:::my-bucket")

    @patch("steps.handlers.s3_handler.S3EventHandler._get_s3_client")
    def test_s3_tags_not_added_to_metadata(self, mock_get_s3_client):
        mock_get_s3_client.side_effect = MagicMock()
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

        assert "s3_tag:tag_value" not in self.s3_handler.metadata["ddtags"]

    @patch("caching.cloudwatch_log_group_cache.CloudwatchLogGroupTagsCache.__init__")
    @patch("steps.handlers.s3_handler.S3EventHandler._parse_service_arn")
    @patch("steps.handlers.s3_handler.S3EventHandler._get_s3_client")
    def test_s3_tags_added_to_metadata(
        self,
        mock_get_s3_client,
        mock_parse_service_arn,
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

        mock_parse_service_arn.return_value = ""
        _ = list(self.s3_handler.handle(event))

        assert "s3_tag:tag_value" in self.s3_handler.metadata["ddtags"]

    def test_elb_s3_key_invalid(self):
        self.s3_handler.metadata["ddsource"] = "elb"
        self.s3_handler.key = "123456789123/elasticloadbalancing/us-east-1/2022/02/08/123456789123_elasticloadbalancing_us-east-1_app.my-alb-name.123456789aabcdef_20220208T1127Z_10.0.0.2_1abcdef2.log.gz"
        self.assertEqual(
            self.s3_handler._parse_service_arn(),
            None,
        )

    def test_elb_s3_key_no_prefix(self):
        self.s3_handler.data_store.source = "elb"
        self.s3_handler.data_store.key = "AWSLogs/123456789123/elasticloadbalancing/us-east-1/2022/02/08/123456789123_elasticloadbalancing_us-east-1_app.my-alb-name.123456789aabcdef_20220208T1127Z_10.0.0.2_1abcdef2.log.gz"
        self.assertEqual(
            self.s3_handler._parse_service_arn(),
            "arn:aws:elasticloadbalancing:us-east-1:123456789123:loadbalancer/app/my-alb-name/123456789aabcdef",
        )

    def test_elb_s3_key_single_prefix(self):
        self.s3_handler.data_store.source = "elb"
        self.s3_handler.data_store.key = "elasticloadbalancing/AWSLogs/123456789123/elasticloadbalancing/us-east-1/2022/02/08/123456789123_elasticloadbalancing_us-east-1_app.my-alb-name.123456789aabcdef_20220208T1127Z_10.0.0.2_1abcdef2.log.gz"
        self.assertEqual(
            self.s3_handler._parse_service_arn(),
            "arn:aws:elasticloadbalancing:us-east-1:123456789123:loadbalancer/app/my-alb-name/123456789aabcdef",
        )

    def test_elb_s3_key_multi_prefix(self):
        self.s3_handler.data_store.source = "elb"
        self.s3_handler.data_store.key = "elasticloadbalancing/my-alb-name/AWSLogs/123456789123/elasticloadbalancing/us-east-1/2022/02/08/123456789123_elasticloadbalancing_us-east-1_app.my-alb-name.123456789aabcdef_20220208T1127Z_10.0.0.2_1abcdef2.log.gz"
        self.assertEqual(
            self.s3_handler._parse_service_arn(),
            "arn:aws:elasticloadbalancing:us-east-1:123456789123:loadbalancer/app/my-alb-name/123456789aabcdef",
        )

    def test_elb_s3_key_multi_prefix_gov(self):
        self.s3_handler.data_store.source = "elb"
        self.s3_handler.data_store.key = "elb/my-alb-name/AWSLogs/123456789123/elasticloadbalancing/us-gov-east-1/2022/02/08/123456789123_elasticloadbalancing_us-gov-east-1_app.my-alb-name.123456789aabcdef_20220208T1127Z_10.0.0.2_1abcdef2.log.gz"
        self.assertEqual(
            self.s3_handler._parse_service_arn(),
            "arn:aws-us-gov:elasticloadbalancing:us-gov-east-1:123456789123:loadbalancer/app/my-alb-name"
            "/123456789aabcdef",
        )


if __name__ == "__main__":
    unittest.main()
