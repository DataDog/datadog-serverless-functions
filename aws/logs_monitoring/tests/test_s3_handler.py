import gzip
import unittest
from approvaltests.combination_approvals import verify_all_combinations
from steps.handlers.s3_handler import (
    parse_service_arn,
    get_partition_from_region,
    get_structured_lines_for_s3_handler,
)


class TestS3EventsHandler(unittest.TestCase):
    def parse_lines(self, data, key, source):
        bucket = "my-bucket"
        gzip_data = gzip.compress(bytes(data, "utf-8"))

        return [
            l
            for l in get_structured_lines_for_s3_handler(gzip_data, bucket, key, source)
        ]

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
        self.assertEqual(get_partition_from_region("us-east-1"), "aws")
        self.assertEqual(get_partition_from_region("us-gov-west-1"), "aws-us-gov")
        self.assertEqual(get_partition_from_region("cn-north-1"), "aws-cn")
        self.assertEqual(get_partition_from_region(None), "aws")


class TestParseServiceArn(unittest.TestCase):
    def test_elb_s3_key_invalid(self):
        self.assertEqual(
            parse_service_arn(
                "elb",
                "123456789123/elasticloadbalancing/us-east-1/2022/02/08/123456789123_elasticloadbalancing_us-east-1_app.my-alb-name.123456789aabcdef_20220208T1127Z_10.0.0.2_1abcdef2.log.gz",
                None,
                None,
            ),
            None,
        )

    def test_elb_s3_key_no_prefix(self):
        self.assertEqual(
            parse_service_arn(
                "elb",
                "AWSLogs/123456789123/elasticloadbalancing/us-east-1/2022/02/08/123456789123_elasticloadbalancing_us-east-1_app.my-alb-name.123456789aabcdef_20220208T1127Z_10.0.0.2_1abcdef2.log.gz",
                None,
                None,
            ),
            "arn:aws:elasticloadbalancing:us-east-1:123456789123:loadbalancer/app/my-alb-name/123456789aabcdef",
        )

    def test_elb_s3_key_single_prefix(self):
        self.assertEqual(
            parse_service_arn(
                "elb",
                "elasticloadbalancing/AWSLogs/123456789123/elasticloadbalancing/us-east-1/2022/02/08/123456789123_elasticloadbalancing_us-east-1_app.my-alb-name.123456789aabcdef_20220208T1127Z_10.0.0.2_1abcdef2.log.gz",
                None,
                None,
            ),
            "arn:aws:elasticloadbalancing:us-east-1:123456789123:loadbalancer/app/my-alb-name/123456789aabcdef",
        )

    def test_elb_s3_key_multi_prefix(self):
        self.assertEqual(
            parse_service_arn(
                "elb",
                "elasticloadbalancing/my-alb-name/AWSLogs/123456789123/elasticloadbalancing/us-east-1/2022/02/08/123456789123_elasticloadbalancing_us-east-1_app.my-alb-name.123456789aabcdef_20220208T1127Z_10.0.0.2_1abcdef2.log.gz",
                None,
                None,
            ),
            "arn:aws:elasticloadbalancing:us-east-1:123456789123:loadbalancer/app/my-alb-name/123456789aabcdef",
        )

    def test_elb_s3_key_multi_prefix_gov(self):
        self.assertEqual(
            parse_service_arn(
                "elb",
                "elasticloadbalancing/my-alb-name/AWSLogs/123456789123/elasticloadbalancing/us-gov-east-1/2022/02/08"
                "/123456789123_elasticloadbalancing_us-gov-east-1_app.my-alb-name.123456789aabcdef_20220208T1127Z_10"
                ".0.0.2_1abcdef2.log.gz",
                None,
                None,
            ),
            "arn:aws-us-gov:elasticloadbalancing:us-gov-east-1:123456789123:loadbalancer/app/my-alb-name"
            "/123456789aabcdef",
        )


if __name__ == "__main__":
    unittest.main()
