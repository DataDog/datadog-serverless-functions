import unittest
from unittest.mock import MagicMock, patch

from settings import DD_CUSTOM_TAGS, DD_SOURCE
from steps.common import get_service_from_tags_and_remove_duplicates, parse_event_source
from steps.enums import AwsEventSource, AwsEventType
from steps.parsing import parse, parse_event_type


class TestParseEventSource(unittest.TestCase):
    def test_aws_source_if_none_found(self):
        self.assertEqual(parse_event_source({}, "asdfalsfhalskjdfhalsjdf"), "aws")

    def test_cloudtrail_event(self):
        self.assertEqual(
            parse_event_source(
                {"Records": ["logs-from-s3"]},
                "cloud-trail/AWSLogs/123456779121/CloudTrail/us-west-3/2018/01/07/123456779121_CloudTrail_eu-west-3_20180707T1735Z_abcdefghi0MCRL2O.json.gz",
            ),
            str(AwsEventSource.CLOUDTRAIL),
        )

    def test_cloudtrail_digest_event(self):
        self.assertEqual(
            parse_event_source(
                {"Records": ["logs-from-s3"]},
                "cloud-trail/AWSLogs/123456779121/CloudTrail/us-east-1/2018/01/07/123456779121_CloudTrail-Digest_us-east-1_AWS-CloudTrail_us-east-1_20180707T173567Z.json.gz",
            ),
            str(AwsEventSource.CLOUDTRAIL),
        )

    def test_cloudtrail_gov_event(self):
        self.assertEqual(
            parse_event_source(
                {"Records": ["logs-from-s3"]},
                "cloud-trail/AWSLogs/123456779121/CloudTrail/us-gov-west-1/2018/01/07/123456779121_CloudTrail_us-gov-west-1_20180707T1735Z_abcdefghi0MCRL2O.json.gz",
            ),
            str(AwsEventSource.CLOUDTRAIL),
        )

    def test_cloudtrail_event_with_service_substrings(self):
        # Assert that source "cloudtrail" is parsed even though substrings "waf" and "sns" are present in the key
        self.assertEqual(
            parse_event_source(
                {"Records": ["logs-from-s3"]},
                "cloud-trail/AWSLogs/123456779121/CloudTrail/us-west-3/2018/01/07/123456779121_CloudTrail_eu-west-3_20180707T1735Z_xywafKsnsXMBrdsMCRL2O.json.gz",
            ),
            str(AwsEventSource.CLOUDTRAIL),
        )

    def test_rds_event(self):
        self.assertEqual(
            parse_event_source({"awslogs": "logs"}, "/aws/rds/my-rds-resource"),
            str(AwsEventSource.CLOUDWATCH),
        )

    def test_mariadb_event(self):
        self.assertEqual(
            parse_event_source({"awslogs": "logs"}, "/aws/rds/mariaDB-instance/error"),
            str(AwsEventSource.CLOUDWATCH),
        )

    def test_mysql_event(self):
        self.assertEqual(
            parse_event_source({"awslogs": "logs"}, "/aws/rds/mySQL-instance/error"),
            str(AwsEventSource.CLOUDWATCH),
        )

    def test_postgresql_event(self):
        self.assertEqual(
            parse_event_source(
                {"awslogs": "logs"}, "/aws/rds/instance/datadog/postgresql"
            ),
            str(AwsEventSource.CLOUDWATCH),
        )

    def test_lambda_event(self):
        self.assertEqual(
            parse_event_source({"awslogs": "logs"}, "/aws/lambda/postRestAPI"),
            str(AwsEventSource.LAMBDA),
        )

    def test_sns_event(self):
        self.assertEqual(
            parse_event_source(
                {"awslogs": "logs"}, "sns/us-east-1/123456779121/SnsTopicX"
            ),
            str(AwsEventSource.SNS),
        )

    def test_kinesis_event(self):
        self.assertEqual(
            parse_event_source({"awslogs": "logs"}, "/aws/kinesisfirehose/test"),
            str(AwsEventSource.KINESIS),
        )
        self.assertEqual(
            parse_event_source(
                {"Records": ["logs-from-s3"]}, "AWSLogs/amazon_kinesis/my-s3.json.gz"
            ),
            str(AwsEventSource.KINESIS),
        )

    def test_waf_event(self):
        self.assertEqual(
            parse_event_source(
                {"Records": ["logs-from-s3"]},
                "2020/10/02/21/aws-waf-logs-testing-1-2020-10-02-21-25-30-x123x-x456x",
            ),
            str(AwsEventSource.WAF),
        )

        self.assertEqual(
            parse_event_source(
                {"Records": ["logs-from-s3"]},
                "AWSLogs/123456779121/WAFLogs/us-east-1/xxxxxx-waf/2022/10/11/14/10/123456779121_waflogs_us-east-1_xxxxx-waf_20221011T1410Z_12756524.log.gz",
            ),
            str(AwsEventSource.WAF),
        )

    def test_redshift_event(self):
        self.assertEqual(
            parse_event_source(
                {"Records": ["logs-from-s3"]},
                "AWSLogs/123456779121/redshift/us-east-1/2020/10/21/123456779121_redshift_us-east-1_mycluster_userlog_2020-10-21T18:01.gz",
            ),
            str(AwsEventSource.S3),
        )

    def test_redshift_gov_event(self):
        self.assertEqual(
            parse_event_source(
                {"Records": ["logs-from-s3"]},
                "AWSLogs/123456779121/redshift/us-gov-east-1/2020/10/21/123456779121_redshift_us-gov-east"
                "-1_mycluster_userlog_2020-10-21T18:01.gz",
            ),
            str(AwsEventSource.S3),
        )

    def test_cloudfront_event(self):
        self.assertEqual(
            parse_event_source(
                {"Records": ["logs-from-s3"]},
                "AWSLogs/cloudfront/123456779121/test/01.gz",
            ),
            str(AwsEventSource.S3),
        )

    def test_cloudwatch_source_if_none_found(self):
        self.assertEqual(
            parse_event_source({"awslogs": "logs"}, ""), str(AwsEventSource.CLOUDWATCH)
        )

    def test_s3_source_if_none_found(self):
        self.assertEqual(
            parse_event_source({"Records": ["logs-from-s3"]}, ""),
            str(AwsEventSource.S3),
        )


class TestGetServiceFromTags(unittest.TestCase):
    def test_get_service_from_tags(self):
        metadata = {
            DD_SOURCE: "ecs",
            DD_CUSTOM_TAGS: "env:dev,tag,stack:aws:ecs,service:web,version:v1",
        }
        self.assertEqual(get_service_from_tags_and_remove_duplicates(metadata), "web")

    def test_get_service_from_tags_default_to_source(self):
        metadata = {
            DD_SOURCE: "ecs",
            DD_CUSTOM_TAGS: "env:dev,tag,stack:aws:ecs,version:v1",
        }
        self.assertEqual(get_service_from_tags_and_remove_duplicates(metadata), "ecs")

    def test_get_service_from_tags_removing_duplicates(self):
        metadata = {
            DD_SOURCE: "ecs",
            DD_CUSTOM_TAGS: (
                "env:dev,tag,stack:aws:ecs,service:web,version:v1,service:other"
            ),
        }
        self.assertEqual(get_service_from_tags_and_remove_duplicates(metadata), "web")
        self.assertEqual(
            metadata[DD_CUSTOM_TAGS], "env:dev,tag,stack:aws:ecs,service:web,version:v1"
        )


class TestParseEventType(unittest.TestCase):
    def test_parse_eventbridge_s3_event_type(self):
        """Test that EventBridge S3 events are correctly identified as EventBridge S3 type"""
        eventbridge_s3_event = {
            "version": "0",
            "id": "test-event-id",
            "detail-type": "Object Created",
            "source": "aws.s3",
            "account": "123456789012",
            "time": "2024-01-15T12:00:00Z",
            "region": "us-east-1",
            "resources": ["arn:aws:s3:::my-bucket"],
            "detail": {
                "bucket": {"name": "my-bucket"},
                "object": {"key": "my-key.log"},
            },
        }

        event_type = parse_event_type(eventbridge_s3_event)
        self.assertEqual(event_type, AwsEventType.EVENTBRIDGE_S3)

    def test_parse_direct_s3_event_type(self):
        """Test that direct S3 events are still correctly identified as S3 type"""
        direct_s3_event = {
            "Records": [
                {
                    "s3": {
                        "bucket": {"name": "my-bucket"},
                        "object": {"key": "my-key"},
                    }
                }
            ]
        }

        event_type = parse_event_type(direct_s3_event)
        self.assertEqual(event_type, AwsEventType.S3)

    def test_parse_non_s3_eventbridge_event_type(self):
        """Test that non-S3 EventBridge events are identified as EVENTS type"""
        eventbridge_other_event = {
            "version": "0",
            "detail-type": "EC2 Instance State-change Notification",
            "source": "aws.ec2",
            "detail": {"instance-id": "i-1234567890abcdef0", "state": "terminated"},
        }

        event_type = parse_event_type(eventbridge_other_event)
        self.assertEqual(event_type, AwsEventType.EVENTS)


class TestEventBridgeS3Parsing(unittest.TestCase):
    class Context:
        function_version = "$LATEST"
        invoked_function_arn = (
            "arn:aws:lambda:us-east-1:123456789012:function:datadog-forwarder"
        )
        function_name = "datadog-forwarder"
        memory_limit_in_mb = "128"

    @patch("steps.parsing.S3EventHandler")
    def test_parse_normalizes_eventbridge_s3_event_before_s3_handler(
        self, mock_s3_handler_cls
    ):
        # Arrange: handler yields one log line; we only care about the input event it received
        mock_s3_handler = mock_s3_handler_cls.return_value
        mock_s3_handler.handle.return_value = iter([{"message": "ok"}])

        eventbridge_event = {
            "version": "0",
            "detail-type": "Object Created",
            "source": "aws.s3",
            "detail": {
                "bucket": {"name": "my-bucket"},
                "object": {"key": "my-key.log", "size": 1234},
            },
        }

        cache_layer = MagicMock()

        # Act
        _ = parse(eventbridge_event, self.Context(), cache_layer)

        # Assert: parse() passed a canonical S3-shaped event into the S3 handler
        mock_s3_handler.handle.assert_called_once()
        (normalized_event,) = mock_s3_handler.handle.call_args.args

        self.assertIn("Records", normalized_event)
        self.assertEqual(
            normalized_event["Records"][0]["s3"]["bucket"]["name"], "my-bucket"
        )
        self.assertEqual(
            normalized_event["Records"][0]["s3"]["object"]["key"], "my-key.log"
        )


if __name__ == "__main__":
    unittest.main()
