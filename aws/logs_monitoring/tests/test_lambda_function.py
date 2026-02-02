import base64
import gzip
import json
import os
import sys
import unittest
from importlib import reload
from unittest.mock import MagicMock, patch

from approvaltests.approvals import Options, verify_as_json
from approvaltests.scrubbers import create_regex_scrubber
from botocore.exceptions import ClientError

sys.modules["trace_forwarder.connection"] = MagicMock()
sys.modules["datadog_lambda.wrapper"] = MagicMock()
sys.modules["datadog_lambda.metric"] = MagicMock()
sys.modules["datadog"] = MagicMock()
sys.modules["requests"] = MagicMock()
sys.modules["requests_futures.sessions"] = MagicMock()

env_patch = patch.dict(
    os.environ,
    {
        "DD_API_KEY": "11111111111111111111111111111111",
        "DD_ADDITIONAL_TARGET_LAMBDAS": "ironmaiden,megadeth",
    },
)
env_patch.start()

from caching.cache_layer import CacheLayer
from lambda_function import invoke_additional_target_lambdas
from steps.enrichment import enrich
from steps.enums import AwsEventType
from steps.parsing import parse, parse_event_type
from steps.splitting import split
from steps.transformation import transform

env_patch.stop()


class Context:
    function_version = "$LATEST"
    invoked_function_arn = "arn:aws:lambda:sa-east-1:601427279990:function:inferred-spans-python-dev-initsender"
    function_name = "inferred-spans-python-dev-initsender"
    memory_limit_in_mb = "10"


class TestInvokeAdditionalTargetLambdas(unittest.TestCase):
    @patch("lambda_function.boto3")
    def test_additional_lambda(self, boto3):
        self.assertEqual(invoke_additional_target_lambdas({"ironmaiden": "foo"}), None)
        boto3.client.assert_called_with("lambda")
        lambda_payload = json.dumps({"ironmaiden": "foo"})

        self.assertEqual(boto3.client().invoke.call_count, 2)
        boto3.client().invoke.assert_called_with(
            FunctionName="megadeth", InvocationType="Event", Payload=lambda_payload
        )

    @patch("lambda_function.boto3")
    def test_lambda_invocation_exception(self, boto3):
        boto3.client.return_value.invoke.side_effect = ClientError(
            {"Error": {"Code": "403", "Message": "Unauthorized"}}, "Invoke"
        )
        self.assertEqual(invoke_additional_target_lambdas({"ironmaiden": "foo"}), None)
        boto3.client.assert_called_with("lambda")
        lambda_payload = json.dumps({"ironmaiden": "foo"})

        self.assertEqual(boto3.client().invoke.call_count, 2)
        boto3.client().invoke.assert_called_with(
            FunctionName="megadeth", InvocationType="Event", Payload=lambda_payload
        )


class TestLambdaFunctionEndToEnd(unittest.TestCase):
    @patch("caching.cloudwatch_log_group_cache.CloudwatchLogGroupTagsCache.__init__")
    def test_datadog_forwarder(self, mock_cache_init):
        mock_cache_init.return_value = None
        cache_layer = CacheLayer("")
        cache_layer._cloudwatch_log_group_cache.get = MagicMock(return_value=[])
        cache_layer._lambda_cache.get = MagicMock(
            return_value=[
                "team:metrics",
                "monitor:datadog",
                "env:prod",
                "creator:swf",
                "service:hello",
            ]
        )

        context = Context()
        input_data = self._get_input_data()
        event = {"awslogs": {"data": self._create_log_event_from_data(input_data)}}

        event_type = parse_event_type(event)
        self.assertEqual(event_type, AwsEventType.AWSLOGS)

        normalized_events = parse(event, context, cache_layer)
        enriched_events = enrich(normalized_events, cache_layer)
        transformed_events = transform(enriched_events)

        scrubber = create_regex_scrubber(
            r"forwarder_version:\d+\.\d+\.\d+",
            "forwarder_version:<redacted from snapshot>",
        )
        verify_as_json(transformed_events, options=Options().with_scrubber(scrubber))

        _, _, trace_payloads = split(transformed_events)
        self.assertEqual(len(trace_payloads), 1)

        trace_payload = json.loads(trace_payloads[0]["message"])
        traces = trace_payload["traces"]
        self.assertEqual(len(traces), 1)

        trace = traces[0]
        self.assertEqual(len(trace), 9)

        inferred_spans = list(
            filter(
                lambda span: "meta" in span
                and "inferred_span.inherit_lambda" in span["meta"],
                trace,
            )
        )
        self.assertEqual(len(inferred_spans), 1)

        inferred_span = inferred_spans[0]
        self.assertEqual(
            inferred_span["service"], "ialbefmodl.execute-api.sa-east-1.amazonaws.com"
        )
        self.assertEqual(inferred_span["name"], "aws.apigateway")

        # ensure tags not applied to inferred span
        assert "team" not in inferred_span["meta"]
        assert "monitor" not in inferred_span["meta"]
        assert "env" not in inferred_span["meta"]
        assert "creator" not in inferred_span["meta"]
        assert "service" not in inferred_span["meta"]

    @patch("caching.cloudwatch_log_group_cache.CloudwatchLogGroupTagsCache.__init__")
    def test_setting_service_tag_from_log_group_cache(self, mock_cache_init):
        reload(sys.modules["settings"])
        reload(sys.modules["steps.parsing"])
        reload(sys.modules["steps.common"])
        mock_cache_init.return_value = None
        cache_layer = CacheLayer("")
        cache_layer._cloudwatch_log_group_cache.get = MagicMock(
            return_value=["service:log_group_service"]
        )
        context = Context()
        input_data = self._get_input_data()
        event = {"awslogs": {"data": self._create_log_event_from_data(input_data)}}

        normalized_events = parse(event, context, cache_layer)
        enriched_events = enrich(normalized_events, cache_layer)
        transformed_events = transform(enriched_events)

        _, logs, _ = split(transformed_events)
        self.assertEqual(len(logs), 16)
        for log in logs:
            self.assertEqual(log["service"], "log_group_service")

    @patch.dict(os.environ, {"DD_TAGS": "service:dd_tag_service"})
    @patch("caching.cloudwatch_log_group_cache.CloudwatchLogGroupTagsCache.__init__")
    def test_service_override_from_dd_tags(self, mock_cache_init):
        reload(sys.modules["settings"])
        reload(sys.modules["steps.parsing"])
        reload(sys.modules["steps.common"])
        mock_cache_init.return_value = None
        cache_layer = CacheLayer("")
        cache_layer._cloudwatch_log_group_cache.get = MagicMock(
            return_value=["service:log_group_service"]
        )
        context = Context()
        input_data = self._get_input_data()
        event = {"awslogs": {"data": self._create_log_event_from_data(input_data)}}

        normalized_events = parse(event, context, cache_layer)
        enriched_events = enrich(normalized_events, cache_layer)
        transformed_events = transform(enriched_events)

        _, logs, _ = split(transformed_events)
        self.assertEqual(len(logs), 16)
        for log in logs:
            self.assertEqual(log["service"], "dd_tag_service")

    @patch("caching.cloudwatch_log_group_cache.CloudwatchLogGroupTagsCache.__init__")
    @patch("caching.base_tags_cache.send_forwarder_internal_metrics")
    @patch("caching.cloudwatch_log_group_cache.send_forwarder_internal_metrics")
    @patch("caching.lambda_cache.send_forwarder_internal_metrics")
    def test_overrding_service_tag_from_lambda_cache(
        self,
        mock_lambda_send_metrics,
        mock_cw_send_metrics,
        mock_base_send_metrics,
        mock_cache_init,
    ):
        mock_cache_init.return_value = None
        cache_layer = CacheLayer("")
        cache_layer._lambda_cache.get = MagicMock(
            return_value=["service:lambda_service"]
        )
        cache_layer._cloudwatch_log_group_cache = MagicMock()
        context = Context()
        input_data = self._get_input_data()
        event = {"awslogs": {"data": self._create_log_event_from_data(input_data)}}

        normalized_events = parse(event, context, cache_layer)
        enriched_events = enrich(normalized_events, cache_layer)
        transformed_events = transform(enriched_events)

        _, logs, _ = split(transformed_events)
        self.assertEqual(len(logs), 16)
        for log in logs:
            self.assertEqual(log["service"], "lambda_service")

    @patch("caching.cloudwatch_log_group_cache.CloudwatchLogGroupTagsCache.__init__")
    def test_overrding_service_tag_from_lambda_cache_when_dd_tags_is_set(
        self, mock_cache_init
    ):
        mock_cache_init.return_value = None
        cache_layer = CacheLayer("")
        cache_layer._lambda_cache.get = MagicMock(
            return_value=["service:lambda_service"]
        )
        cache_layer._cloudwatch_log_group_cache = MagicMock()
        context = Context()
        input_data = self._get_input_data()
        event = {"awslogs": {"data": self._create_log_event_from_data(input_data)}}
        normalized_events = parse(event, context, cache_layer)
        enriched_events = enrich(normalized_events, cache_layer)
        transformed_events = transform(enriched_events)

        _, logs, _ = split(transformed_events)
        self.assertEqual(len(logs), 16)
        for log in logs:
            self.assertEqual(log["service"], "lambda_service")

    @patch("caching.cloudwatch_log_group_cache.CloudwatchLogGroupTagsCache.__init__")
    def test_overrding_service_tag_from_message_ddtags(self, mock_cache_init):
        mock_cache_init.return_value = None
        cache_layer = CacheLayer("")
        cache_layer._lambda_cache = MagicMock()
        cache_layer._cloudwatch_log_group_cache = MagicMock()
        context = Context()
        input_data = self._get_input_data(path="events/cloudwatch_logs_ddtags.json")
        event = {"awslogs": {"data": self._create_log_event_from_data(input_data)}}
        normalized_events = parse(event, context, cache_layer)
        enriched_events = enrich(normalized_events, cache_layer)
        transformed_events = transform(enriched_events)

        _, logs, _ = split(transformed_events)
        self.assertEqual(len(logs), 1)
        for log in logs:
            self.assertEqual(log["service"], "test-inner-message")
            self.assertTrue(isinstance(log["message"], str))

    @patch("caching.cloudwatch_log_group_cache.CloudwatchLogGroupTagsCache.__init__")
    def test_kinesis_awslogs_handler(self, mock_cache_init):
        mock_cache_init.return_value = None
        cache_layer = CacheLayer("")
        cache_layer._lambda_cache = MagicMock()
        cache_layer._cloudwatch_log_group_cache = MagicMock()
        context = Context()
        input_data1 = self._get_input_data(path="events/cloudwatch_logs_ddtags.json")
        input_data2 = self._get_input_data(path="events/cloudwatch_logs_2.json")
        event = {
            "Records": [
                {"kinesis": {"data": self._create_log_event_from_data(input_data1)}},
                {"kinesis": {"data": self._create_log_event_from_data(input_data2)}},
            ]
        }

        normalized_events = parse(event, context, cache_layer)
        enriched_events = enrich(normalized_events, cache_layer)
        transformed_events = transform(enriched_events)

        scrubber = create_regex_scrubber(
            r"forwarder_version:\d+\.\d+\.\d+",
            "forwarder_version:<redacted from snapshot>",
        )
        verify_as_json(transformed_events, options=Options().with_scrubber(scrubber))

    def _get_input_data(self, path="events/cloudwatch_logs.json"):
        my_path = os.path.abspath(os.path.dirname(__file__))
        path = os.path.join(my_path, path)
        with open(
            path,
            "r",
        ) as input_file:
            input_data = input_file.read()

        return input_data

    def _create_log_event_from_data(self, data):
        # CloudWatch log event data is a base64-encoded ZIP archive
        # see https://docs.aws.amazon.com/lambda/latest/dg/services-cloudwatchlogs.html
        gzipped_data = gzip.compress(bytes(data, encoding="utf-8"))
        encoded_data = base64.b64encode(gzipped_data).decode("utf-8")
        return encoded_data


class TestParseEventType(unittest.TestCase):
    def test_parse_eventbridge_s3_event_type(self):
        """Test that EventBridge S3 events are correctly identified as S3 type"""
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
        self.assertEqual(event_type, AwsEventType.S3)

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
            "detail": {
                "instance-id": "i-1234567890abcdef0",
                "state": "terminated"
            },
        }

        event_type = parse_event_type(eventbridge_other_event)
        self.assertEqual(event_type, AwsEventType.EVENTS)


class TestEventBridgeS3Parsing(unittest.TestCase):
    def setUp(self):
        self.context = Context()
        # Minimal cache layer mock for S3 handler
        self.cache_layer = MagicMock()
        s3_tags_cache = MagicMock()
        s3_tags_cache.get.return_value = []
        self.cache_layer.get_s3_tags_cache.return_value = s3_tags_cache

    @patch("steps.handlers.s3_handler.boto3")
    def test_parse_eventbridge_s3_object_created_end_to_end(self, mock_boto3):
        """EventBridge S3 Object Created event is normalized and processed via parse()."""
        mock_s3_client = MagicMock()
        mock_s3_client.get_object.return_value = {
            "Body": MagicMock(read=MagicMock(return_value=b"test log line"))
        }
        mock_boto3.client.return_value = mock_s3_client

        eventbridge_event = {
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

        logs = parse(eventbridge_event, self.context, self.cache_layer)

        self.assertEqual(len(logs), 1)
        self.assertEqual(logs[0]["message"], "test log line")
        self.assertEqual(logs[0]["aws"]["s3"]["bucket"], "my-bucket")
        self.assertEqual(logs[0]["aws"]["s3"]["key"], "my-key.log")

    @patch("steps.handlers.s3_handler.boto3")
    def test_parse_eventbridge_s3_with_gzip_file_end_to_end(self, mock_boto3):
        """EventBridge S3 event with gzipped file is handled via parse()."""
        mock_s3_client = MagicMock()
        gzip_data = gzip.compress(b"gzipped log line")
        mock_s3_client.get_object.return_value = {
            "Body": MagicMock(read=MagicMock(return_value=gzip_data))
        }
        mock_boto3.client.return_value = mock_s3_client

        eventbridge_event = {
            "version": "0",
            "detail-type": "Object Created",
            "source": "aws.s3",
            "detail": {
                "bucket": {"name": "my-bucket"},
                "object": {"key": "my-key.log.gz"},
            },
        }

        logs = parse(eventbridge_event, self.context, self.cache_layer)

        self.assertEqual(len(logs), 1)
        self.assertEqual(logs[0]["message"], "gzipped log line")
        self.assertEqual(logs[0]["aws"]["s3"]["bucket"], "my-bucket")
        self.assertEqual(logs[0]["aws"]["s3"]["key"], "my-key.log.gz")

    @patch("steps.handlers.s3_handler.boto3")
    def test_parse_eventbridge_s3_cloudtrail_end_to_end(self, mock_boto3):
        """EventBridge S3 event carrying CloudTrail logs is handled via parse()."""
        mock_s3_client = MagicMock()
        cloudtrail_data = {
            "Records": [
                {
                    "eventVersion": "1.05",
                    "eventName": "AssumeRole",
                    "eventSource": "sts.amazonaws.com",
                }
            ]
        }
        mock_s3_client.get_object.return_value = {
            "Body": MagicMock(
                read=MagicMock(
                    return_value=gzip.compress(
                        bytes(str(cloudtrail_data).replace("'", '"'), "utf-8")
                    )
                )
            )
        }
        mock_boto3.client.return_value = mock_s3_client

        eventbridge_event = {
            "version": "0",
            "detail-type": "Object Created",
            "source": "aws.s3",
            "detail": {
                "bucket": {"name": "my-bucket"},
                "object": {
                    "key": "123456779121_CloudTrail_eu-west-3_20180707T1735Z_abcdefghi0MCRL2O.json.gz"
                },
            },
        }

        logs = parse(eventbridge_event, self.context, self.cache_layer)

        self.assertEqual(len(logs), 1)
        self.assertEqual(logs[0]["eventName"], "AssumeRole")
        self.assertEqual(logs[0]["aws"]["s3"]["bucket"], "my-bucket")


if __name__ == "__main__":
    unittest.main()
