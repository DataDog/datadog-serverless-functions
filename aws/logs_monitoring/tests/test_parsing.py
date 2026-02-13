import json
import unittest
from unittest.mock import MagicMock, patch

from settings import DD_CUSTOM_TAGS, DD_SOURCE
from steps.common import get_service_from_tags_and_remove_duplicates, parse_event_source
from steps.enums import AwsEventSource, AwsEventType
from steps.parsing import parse, parse_event_type


class Context:
    function_version = "$LATEST"
    invoked_function_arn = (
        "arn:aws:lambda:us-east-1:123456789012:function:datadog-forwarder"
    )
    function_name = "datadog-forwarder"
    memory_limit_in_mb = "128"


def _make_s3_event(bucket, key):
    return {"Records": [{"s3": {"bucket": {"name": bucket}, "object": {"key": key}}}]}


def _make_sqs_record(body, message_id="msg-1"):
    return {
        "messageId": message_id,
        "body": body if isinstance(body, str) else json.dumps(body),
        "eventSource": "aws:sqs",
        "eventSourceARN": "arn:aws:sqs:us-east-1:123456789012:q",
    }


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
        """EventBridge S3 events are correctly identified"""
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
        self.assertEqual(
            parse_event_type(eventbridge_s3_event), AwsEventType.EVENTBRIDGE_S3
        )

    def test_parse_direct_s3_event_type(self):
        """Direct S3 events are correctly identified"""
        self.assertEqual(
            parse_event_type(_make_s3_event("my-bucket", "my-key")), AwsEventType.S3
        )

    def test_parse_non_s3_eventbridge_event_type(self):
        """Non-S3 EventBridge events are identified as EVENTS type"""
        eventbridge_other_event = {
            "version": "0",
            "detail-type": "EC2 Instance State-change Notification",
            "source": "aws.ec2",
            "detail": {"instance-id": "i-1234567890abcdef0", "state": "terminated"},
        }
        self.assertEqual(parse_event_type(eventbridge_other_event), AwsEventType.EVENTS)

    def test_parse_sqs_event_type(self):
        """SQS events are correctly identified"""
        sqs_event = {"Records": [_make_sqs_record(_make_s3_event("b", "k"))]}
        self.assertEqual(parse_event_type(sqs_event), AwsEventType.SQS)

    def test_direct_s3_event_not_detected_as_sqs(self):
        """Direct S3 events must still be detected as S3, not SQS"""
        self.assertEqual(
            parse_event_type(_make_s3_event("my-bucket", "my-key")), AwsEventType.S3
        )

    def test_sns_event_not_detected_as_sqs(self):
        """SNS events must still be detected as SNS, not SQS"""
        sns_event = {"Records": [{"Sns": {"Message": "hello"}}]}
        self.assertEqual(parse_event_type(sns_event), AwsEventType.SNS)

    def test_kinesis_event_not_detected_as_sqs(self):
        """Kinesis events must still be detected as Kinesis, not SQS"""
        kinesis_event = {"Records": [{"kinesis": {"data": "base64data"}}]}
        self.assertEqual(parse_event_type(kinesis_event), AwsEventType.KINESIS)


class TestSQSEventParsing(unittest.TestCase):
    @patch("steps.parsing.S3EventHandler")
    def test_parse_sqs_s3_event(self, mock_s3_handler_cls):
        """S3 event delivered via SQS is unwrapped and forwarded to S3EventHandler"""
        mock_s3_handler = mock_s3_handler_cls.return_value
        mock_s3_handler.handle.return_value = iter([{"message": "log line"}])

        sqs_event = {
            "Records": [_make_sqs_record(_make_s3_event("my-bucket", "my-key.log"))]
        }

        result = parse(sqs_event, Context(), MagicMock())

        mock_s3_handler.handle.assert_called_once()
        inner_event = mock_s3_handler.handle.call_args.args[0]
        self.assertEqual(inner_event["Records"][0]["s3"]["bucket"]["name"], "my-bucket")
        self.assertEqual(len(result), 1)
        self.assertIn("ddsourcecategory", result[0])
        self.assertIn("aws", result[0])
        self.assertIn("invoked_function_arn", result[0]["aws"])

    @patch("steps.parsing.S3EventHandler")
    def test_parse_sqs_sns_s3_event(self, mock_s3_handler_cls):
        """S3 event delivered via SNS -> SQS is unwrapped and forwarded to S3EventHandler"""
        mock_s3_handler = mock_s3_handler_cls.return_value
        mock_s3_handler.handle.return_value = iter([{"message": "log line"}])

        sns_body = {
            "Type": "Notification",
            "MessageId": "a1b2c3d4",
            "TopicArn": "arn:aws:sns:us-east-1:123456789012:my-topic",
            "Message": json.dumps(_make_s3_event("sns-bucket", "sns-key.log")),
        }
        sqs_event = {"Records": [_make_sqs_record(sns_body)]}

        result = parse(sqs_event, Context(), MagicMock())

        mock_s3_handler.handle.assert_called_once()
        inner_event = mock_s3_handler.handle.call_args.args[0]
        self.assertEqual(
            inner_event["Records"][0]["s3"]["bucket"]["name"], "sns-bucket"
        )
        self.assertEqual(len(result), 1)

    @patch("steps.parsing.S3EventHandler")
    def test_parse_sqs_batch_multiple_records(self, mock_s3_handler_cls):
        """Multiple SQS records in a single batch are all processed"""
        mock_s3_handler = mock_s3_handler_cls.return_value
        mock_s3_handler.handle.side_effect = [
            iter([{"message": "line1"}]),
            iter([{"message": "line2"}]),
        ]

        sqs_event = {
            "Records": [
                _make_sqs_record(_make_s3_event("b1", "k1"), message_id="msg-1"),
                _make_sqs_record(_make_s3_event("b2", "k2"), message_id="msg-2"),
            ]
        }

        result = parse(sqs_event, Context(), MagicMock())

        self.assertEqual(mock_s3_handler.handle.call_count, 2)
        self.assertEqual(len(result), 2)

    @patch("steps.parsing.S3EventHandler")
    def test_parse_sqs_malformed_body_skipped(self, mock_s3_handler_cls):
        """SQS records with malformed body are skipped without crashing"""
        mock_s3_handler = mock_s3_handler_cls.return_value
        mock_s3_handler.handle.return_value = iter([{"message": "ok"}])

        sqs_event = {
            "Records": [
                _make_sqs_record("not valid json", message_id="bad"),
                _make_sqs_record(_make_s3_event("b", "k"), message_id="good"),
            ]
        }

        result = parse(sqs_event, Context(), MagicMock())

        mock_s3_handler.handle.assert_called_once()
        self.assertEqual(len(result), 1)

    @patch("steps.parsing.S3EventHandler")
    def test_parse_sqs_non_object_body_skipped(self, mock_s3_handler_cls):
        """SQS records with valid JSON but non-object body are skipped"""
        mock_s3_handler = mock_s3_handler_cls.return_value
        mock_s3_handler.handle.return_value = iter([{"message": "ok"}])

        sqs_event = {
            "Records": [
                _make_sqs_record(json.dumps("just a string"), message_id="str"),
                _make_sqs_record(json.dumps(42), message_id="num"),
                _make_sqs_record(json.dumps([1, 2, 3]), message_id="arr"),
                _make_sqs_record(_make_s3_event("b", "k"), message_id="good"),
            ]
        }

        result = parse(sqs_event, Context(), MagicMock())

        mock_s3_handler.handle.assert_called_once()
        self.assertEqual(len(result), 1)

    @patch("steps.parsing.S3EventHandler")
    def test_parse_sqs_unrecognized_body_skipped(self, mock_s3_handler_cls):
        """SQS records with valid JSON but unrecognized content are skipped"""
        mock_s3_handler = mock_s3_handler_cls.return_value

        sqs_event = {"Records": [_make_sqs_record({"foo": "bar"})]}

        result = parse(sqs_event, Context(), MagicMock())

        mock_s3_handler.handle.assert_not_called()
        self.assertEqual(len(result), 0)


class TestEventBridgeS3Parsing(unittest.TestCase):
    @patch("steps.parsing.S3EventHandler")
    def test_parse_normalizes_eventbridge_s3_event_before_s3_handler(
        self, mock_s3_handler_cls
    ):
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

        parse(eventbridge_event, Context(), MagicMock())

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
