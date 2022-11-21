from unittest.mock import MagicMock, patch
import os
import sys
import unittest
import json
import gzip
import base64
from time import time
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
from lambda_function import (
    invoke_additional_target_lambdas,
    extract_metric,
    extract_host_from_cloudtrails,
    extract_host_from_guardduty,
    extract_host_from_route53,
    extract_trace_payload,
    enrich,
    transform,
    split,
)
from parsing import parse, parse_event_type

env_patch.stop()


class TestExtractHostFromLogEvents(unittest.TestCase):
    def test_parse_source_cloudtrail(self):
        event = {
            "ddsource": "cloudtrail",
            "message": {
                "userIdentity": {
                    "arn": "arn:aws:sts::601427279990:assumed-role/gke-90725aa7-management/i-99999999"
                }
            },
        }
        extract_host_from_cloudtrails(event)
        self.assertEqual(event["host"], "i-99999999")

    def test_parse_source_guardduty(self):
        event = {
            "ddsource": "guardduty",
            "detail": {"resource": {"instanceDetails": {"instanceId": "i-99999999"}}},
        }
        extract_host_from_guardduty(event)
        self.assertEqual(event["host"], "i-99999999")

    def test_parse_source_route53(self):
        event = {
            "ddsource": "route53",
            "message": {"srcids": {"instance": "i-99999999"}},
        }
        extract_host_from_route53(event)
        self.assertEqual(event["host"], "i-99999999")


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


class TestExtractMetric(unittest.TestCase):
    def test_empty_event(self):
        self.assertEqual(extract_metric({}), None)

    def test_missing_keys(self):
        self.assertEqual(extract_metric({"e": 0, "v": 1, "m": "foo"}), None)

    def test_tags_instance(self):
        self.assertEqual(extract_metric({"e": 0, "v": 1, "m": "foo", "t": 666}), None)

    def test_value_instance(self):
        self.assertEqual(extract_metric({"e": 0, "v": 1.1, "m": "foo", "t": []}), None)

    def test_value_instance_float(self):
        self.assertEqual(extract_metric({"e": 0, "v": None, "m": "foo", "t": []}), None)


class Context:
    function_version = 0
    invoked_function_arn = "arn:aws:lambda:sa-east-1:601427279990:function:inferred-spans-python-dev-initsender"
    function_name = "inferred-spans-python-dev-initsender"
    memory_limit_in_mb = "10"


def create_cloudwatch_log_event_from_data(data):
    # CloudWatch log event data is a base64-encoded ZIP archive
    # see https://docs.aws.amazon.com/lambda/latest/dg/services-cloudwatchlogs.html
    gzipped_data = gzip.compress(bytes(data, encoding="utf-8"))
    encoded_data = base64.b64encode(gzipped_data).decode("utf-8")
    return encoded_data


class TestLambdaFunctionEndToEnd(unittest.TestCase):
    @patch("cloudwatch_log_group_cache.CloudwatchLogGroupTagsCache.get")
    @patch("base_tags_cache.send_forwarder_internal_metrics")
    @patch("enhanced_lambda_metrics.LambdaTagsCache.get_cache_from_s3")
    def test_datadog_forwarder(
        self, mock_get_s3_cache, mock_forward_metrics, cw_logs_tags_get
    ):
        mock_get_s3_cache.return_value = (
            {
                "arn:aws:lambda:sa-east-1:601427279990:function:inferred-spans-python-dev-initsender": [
                    "team:metrics",
                    "monitor:datadog",
                    "env:prod",
                    "creator:swf",
                    "service:hello",
                ]
            },
            time(),
        )
        context = Context()
        my_path = os.path.abspath(os.path.dirname(__file__))
        path = os.path.join(my_path, "events/cloudwatch_logs.json")

        with open(
            path,
            "r",
        ) as input_file:
            input_data = input_file.read()

        event = {"awslogs": {"data": create_cloudwatch_log_event_from_data(input_data)}}
        os.environ["DD_FETCH_LAMBDA_TAGS"] = "True"

        event_type = parse_event_type(event)
        self.assertEqual(event_type, "awslogs")

        normalized_events = parse(event, context)
        enriched_events = enrich(normalized_events)
        transformed_events = transform(enriched_events)

        metrics, logs, trace_payloads = split(transformed_events)
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

        del os.environ["DD_FETCH_LAMBDA_TAGS"]


class TestLambdaFunctionExtractTracePayload(unittest.TestCase):
    def test_extract_trace_payload_none_no_trace(self):
        message_json = """{
            "key": "value"
        }"""
        self.assertEqual(extract_trace_payload({"message": message_json}), None)

    def test_extract_trace_payload_none_exception(self):
        message_json = """{
            "invalid_json"
        }"""
        self.assertEqual(extract_trace_payload({"message": message_json}), None)

    def test_extract_trace_payload_unrelated_datadog_trace(self):
        message_json = """{"traces":["I am a trace"]}"""
        self.assertEqual(extract_trace_payload({"message": message_json}), None)

    def test_extract_trace_payload_valid_trace(self):
        message_json = """{"traces":[[{"trace_id":1234}]]}"""
        tags_json = """["key0:value", "key1:value1"]"""
        item = {
            "message": '{"traces":[[{"trace_id":1234}]]}',
            "tags": '["key0:value", "key1:value1"]',
        }
        self.assertEqual(
            extract_trace_payload({"message": message_json, "ddtags": tags_json}), item
        )


if __name__ == "__main__":
    unittest.main()
