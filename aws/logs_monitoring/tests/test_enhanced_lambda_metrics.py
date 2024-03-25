import unittest
import os
from time import time
from unittest.mock import patch, MagicMock
from unittest import mock
from approvaltests.approvals import verify_as_json

from enhanced_lambda_metrics import (
    parse_metrics_from_report_log,
    parse_lambda_tags_from_arn,
    generate_enhanced_lambda_metrics,
    create_out_of_memory_enhanced_metric,
)

from caching.lambda_cache import LambdaTagsCache


class TestEnhancedLambdaMetrics(unittest.TestCase):
    maxDiff = None
    malformed_report = "REPORT invalid report log line"
    standard_report = (
        "REPORT RequestId: 8edab1f8-7d34-4a8e-a965-15ccbbb78d4c	"
        "Duration: 0.62 ms	Billed Duration: 100 ms	Memory Size: 128 MB	Max Memory Used: 51 MB"
    )
    cold_start_report = (
        "REPORT RequestId: 8edab1f8-7d34-4a8e-a965-15ccbbb78d4c	"
        "Duration: 0.81 ms	Billed Duration: 100 ms	Memory Size: 128 MB	Max Memory Used: 90 MB	Init Duration: 1234 ms"
    )
    report_with_xray = (
        "REPORT RequestId: 814ba7cb-071e-4181-9a09-fa41db5bccad\tDuration: 1711.87 ms\t"
        "Billed Duration: 1800 ms\tMemory Size: 128 MB\tMax Memory Used: 98 MB\t\n"
        "XRAY TraceId: 1-5d83c0ad-b8eb33a0b1de97d804fac890\tSegmentId: 31255c3b19bd3637\t"
        "Sampled: true"
    )

    def test_parse_lambda_tags_from_arn(self):
        verify_as_json(
            parse_lambda_tags_from_arn(
                "arn:aws:lambda:us-east-1:1234597598159:function:swf-hello-test"
            )
        )

    def test_parse_metrics_from_report_log(self):
        parsed_metrics = parse_metrics_from_report_log(self.malformed_report)
        verify_as_json(parsed_metrics)

    def test_parse_metrics_from_standard_report(self):
        parsed_metrics = parse_metrics_from_report_log(self.standard_report)
        # The timestamps are None because the timestamp is added after the metrics are parsed
        verify_as_json(parsed_metrics)

    def test_parse_metrics_from_cold_start_report(self):
        parsed_metrics = parse_metrics_from_report_log(self.cold_start_report)
        verify_as_json(parsed_metrics)

    def test_parse_metrics_from_report_with_xray(self):
        parsed_metrics = parse_metrics_from_report_log(self.report_with_xray)
        verify_as_json(parsed_metrics)

    def test_create_out_of_memory_enhanced_metric(self):
        go_out_of_memory_error = "fatal error: runtime: out of memory"
        self.assertEqual(
            len(create_out_of_memory_enhanced_metric(go_out_of_memory_error)), 1
        )

        java_out_of_memory_error = (
            "Requested array size exceeds VM limit: java.lang.OutOfMemoryError"
        )
        self.assertEqual(
            len(create_out_of_memory_enhanced_metric(java_out_of_memory_error)), 1
        )

        node_out_of_memory_error = "FATAL ERROR: CALL_AND_RETRY_LAST Allocation failed - JavaScript heap out of memory"
        self.assertEqual(
            len(create_out_of_memory_enhanced_metric(node_out_of_memory_error)), 1
        )

        python_out_of_memory_error = "fatal error: runtime: out of memory"
        self.assertEqual(
            len(create_out_of_memory_enhanced_metric(python_out_of_memory_error)), 1
        )

        ruby_out_of_memory_error = "failed to allocate memory (NoMemoryError)"
        self.assertEqual(
            len(create_out_of_memory_enhanced_metric(ruby_out_of_memory_error)), 1
        )

        success_message = "Success!"
        self.assertEqual(len(create_out_of_memory_enhanced_metric(success_message)), 0)

    def test_generate_enhanced_lambda_metrics(self):
        tags_cache = LambdaTagsCache("")
        tags_cache.get = MagicMock(return_value=[])

        logs_input = {
            "message": "REPORT RequestId: fe1467d6-1458-4e20-8e40-9aaa4be7a0f4\tDuration: 3470.65 ms\tBilled Duration: 3500 ms\tMemory Size: 128 MB\tMax Memory Used: 89 MB\t\nXRAY TraceId: 1-5d8bba5a-dc2932496a65bab91d2d42d4\tSegmentId: 5ff79d2a06b82ad6\tSampled: true\t\n",
            "aws": {
                "awslogs": {
                    "logGroup": "/aws/lambda/post-coupon-prod-us",
                    "logStream": "2019/09/25/[$LATEST]d6c10ebbd9cb48dba94a7d9b874b49bb",
                    "owner": "172597598159",
                },
                "function_version": "$LATEST",
                "invoked_function_arn": "arn:aws:lambda:us-east-1:172597598159:function:collect_logs_datadog_demo",
            },
            "lambda": {
                "arn": "arn:aws:lambda:us-east-1:172597598159:function:post-coupon-prod-us"
            },
            "timestamp": 10000,
        }

        generated_metrics = generate_enhanced_lambda_metrics(logs_input, tags_cache)
        verify_as_json(generated_metrics)

    def test_generate_enhanced_lambda_metrics_with_tags(
        self,
    ):
        tags_cache = LambdaTagsCache("")
        tags_cache.get = MagicMock(
            return_value=["team:metrics", "monitor:datadog", "env:prod", "creator:swf"]
        )

        logs_input = {
            "message": "REPORT RequestId: fe1467d6-1458-4e20-8e40-9aaa4be7a0f4\tDuration: 3470.65 ms\tBilled Duration: 3500 ms\tMemory Size: 128 MB\tMax Memory Used: 89 MB\t\nXRAY TraceId: 1-5d8bba5a-dc2932496a65bab91d2d42d4\tSegmentId: 5ff79d2a06b82ad6\tSampled: true\t\n",
            "aws": {
                "awslogs": {
                    "logGroup": "/aws/lambda/post-coupon-prod-us",
                    "logStream": "2019/09/25/[$LATEST]d6c10ebbd9cb48dba94a7d9b874b49bb",
                    "owner": "172597598159",
                },
                "function_version": "$LATEST",
                "invoked_function_arn": "arn:aws:lambda:us-east-1:172597598159:function:collect_logs_datadog_demo",
            },
            "lambda": {
                "arn": "arn:aws:lambda:us-east-1:172597598159:function:post-coupon-prod-us"
            },
            "timestamp": 10000,
        }

        generated_metrics = generate_enhanced_lambda_metrics(logs_input, tags_cache)
        verify_as_json(generated_metrics)

    def test_generate_enhanced_lambda_metrics_once_with_missing_arn(self):
        tags_cache = LambdaTagsCache("")
        tags_cache.get = MagicMock(return_value=[])

        logs_input = {
            "message": "REPORT RequestId: fe1467d6-1458-4e20-8e40-9aaa4be7a0f4\tDuration: 3470.65 ms\tBilled Duration: 3500 ms\tMemory Size: 128 MB\tMax Memory Used: 89 MB\t\nXRAY TraceId: 1-5d8bba5a-dc2932496a65bab91d2d42d4\tSegmentId: 5ff79d2a06b82ad6\tSampled: true\t\n",
            "aws": {
                "awslogs": {
                    "logGroup": "/aws/lambda/post-coupon-prod-us",
                    "logStream": "2019/09/25/[$LATEST]d6c10ebbd9cb48dba94a7d9b874b49bb",
                    "owner": "172597598159",
                },
                "function_version": "$LATEST",
                "invoked_function_arn": "arn:aws:lambda:us-east-1:172597598159:function:collect_logs_datadog_demo",
            },
            "lambda": {
                "arn": "arn:aws:lambda:us-east-1:172597598159:function:post-coupon-prod-us"
            },
            "timestamp": 10000,
        }

        generate_enhanced_lambda_metrics(logs_input, tags_cache)
        tags_cache.get.assert_called_once()
        tags_cache.get.reset_mock()
        del logs_input["lambda"]
        generate_enhanced_lambda_metrics(logs_input, tags_cache)
        tags_cache.get.assert_not_called()

    @patch("caching.base_tags_cache.send_forwarder_internal_metrics")
    @patch("caching.lambda_cache.send_forwarder_internal_metrics")
    def test_generate_enhanced_lambda_metrics_refresh_s3_cache(self, mock1, mock2):
        tags_cache = LambdaTagsCache("")
        tags_cache.get_cache_from_s3 = MagicMock(return_value=({}, 1000))
        tags_cache.acquire_s3_cache_lock = MagicMock()
        tags_cache.release_s3_cache_lock = MagicMock()
        tags_cache.write_cache_to_s3 = MagicMock()
        tags_cache.build_tags_cache = MagicMock(return_value=(True, {}))

        logs_input = {
            "message": "REPORT RequestId: fe1467d6-1458-4e20-8e40-9aaa4be7a0f4\tDuration: 3470.65 ms\tBilled Duration: 3500 ms\tMemory Size: 128 MB\tMax Memory Used: 89 MB\t\nXRAY TraceId: 1-5d8bba5a-dc2932496a65bab91d2d42d4\tSegmentId: 5ff79d2a06b82ad6\tSampled: true\t\n",
            "aws": {
                "awslogs": {
                    "logGroup": "/aws/lambda/post-coupon-prod-us",
                    "logStream": "2019/09/25/[$LATEST]d6c10ebbd9cb48dba94a7d9b874b49bb",
                    "owner": "172597598159",
                },
                "function_version": "$LATEST",
                "invoked_function_arn": "arn:aws:lambda:us-east-1:172597598159:function:collect_logs_datadog_demo",
            },
            "lambda": {
                "arn": "arn:aws:lambda:us-east-1:172597598159:function:post-coupon-prod-us"
            },
            "timestamp": 10000,
        }

        os.environ["DD_FETCH_LAMBDA_TAGS"] = "True"
        generate_enhanced_lambda_metrics(logs_input, tags_cache)
        tags_cache.get_cache_from_s3.assert_called_once()
        tags_cache.build_tags_cache.assert_called_once()
        tags_cache.write_cache_to_s3.assert_called_once()
        # assert mock_forward_metrics.call_count == 1
        del os.environ["DD_FETCH_LAMBDA_TAGS"]

    @patch("caching.lambda_cache.LambdaTagsCache.release_s3_cache_lock")
    @patch("caching.lambda_cache.LambdaTagsCache.acquire_s3_cache_lock")
    @patch("caching.lambda_cache.LambdaTagsCache.get_resources_paginator")
    @patch("caching.lambda_cache.LambdaTagsCache.write_cache_to_s3")
    @patch("caching.lambda_cache.send_forwarder_internal_metrics")
    @patch("caching.base_tags_cache.send_forwarder_internal_metrics")
    @patch("caching.lambda_cache.LambdaTagsCache.get_cache_from_s3")
    def test_generate_enhanced_lambda_metrics_client_error(
        self,
        mock_get_s3_cache,
        mock_base_tags_cache_forward_metrics,
        mock_lambda_cache_forward_metrics,
        mock_write_cache,
        mock_get_resources_paginator,
        mock_acquire_lock,
        mock_release_lock,
    ):
        mock_acquire_lock.return_value = True
        mock_get_s3_cache.return_value = (
            {},
            1000,
        )
        paginator = mock.MagicMock()
        paginator.paginate.return_value = [{"ResourceTagMappingList": []}]
        mock_get_resources_paginator.return_value = paginator
        tags_cache = LambdaTagsCache("")

        logs_input = {
            "message": "REPORT RequestId: fe1467d6-1458-4e20-8e40-9aaa4be7a0f4\tDuration: 3470.65 ms\tBilled Duration: 3500 ms\tMemory Size: 128 MB\tMax Memory Used: 89 MB\t\nXRAY TraceId: 1-5d8bba5a-dc2932496a65bab91d2d42d4\tSegmentId: 5ff79d2a06b82ad6\tSampled: true\t\n",
            "aws": {
                "awslogs": {
                    "logGroup": "/aws/lambda/post-coupon-prod-us",
                    "logStream": "2019/09/25/[$LATEST]d6c10ebbd9cb48dba94a7d9b874b49bb",
                    "owner": "172597598159",
                },
                "function_version": "$LATEST",
                "invoked_function_arn": "arn:aws:lambda:us-east-1:172597598159:function:collect_logs_datadog_demo",
            },
            "lambda": {
                "arn": "arn:aws:lambda:us-east-1:172597598159:function:post-coupon-prod-us"
            },
            "timestamp": 10000,
        }

        os.environ["DD_FETCH_LAMBDA_TAGS"] = "True"
        generate_enhanced_lambda_metrics(logs_input, tags_cache)
        mock_get_s3_cache.assert_called_once()
        mock_get_s3_cache.reset_mock()
        mock_get_resources_paginator.assert_called_once()
        paginator.paginate.assert_called_once()
        assert mock_base_tags_cache_forward_metrics.call_count == 1
        assert mock_lambda_cache_forward_metrics.call_count == 2
        del os.environ["DD_FETCH_LAMBDA_TAGS"]

    @patch("caching.lambda_cache.send_forwarder_internal_metrics")
    @patch("caching.base_tags_cache.send_forwarder_internal_metrics")
    @patch("caching.lambda_cache.LambdaTagsCache.get_cache_from_s3")
    def test_generate_enhanced_lambda_metrics_timeout(
        self, mock_get_s3_cache, mock_forward_metrics, mock_base_forward_metrics
    ):
        mock_get_s3_cache.return_value = (
            {
                "arn:aws:lambda:us-east-1:0:function:cloudwatch-event": [
                    "team:metrics",
                    "monitor:datadog",
                    "env:prod",
                    "creator:swf",
                ]
            },
            time(),
        )
        tags_cache = LambdaTagsCache("")

        logs_input = {
            "message": "2020-06-09T15:02:26.150Z 7c9567b5-107b-4a6c-8798-0157ac21db52 Task timed out after 3.00 seconds\n\n",
            "aws": {
                "awslogs": {
                    "logGroup": "/aws/lambda/cloudwatch-event",
                    "logStream": "2020/06/09/[$LATEST]b249865adaaf4fad80f95f8ad09725b8",
                    "owner": "601427279990",
                },
                "function_version": "$LATEST",
                "invoked_function_arn": "arn:aws:lambda:us-east-1:0:function:test",
            },
            "lambda": {"arn": "arn:aws:lambda:us-east-1:0:function:cloudwatch-event"},
            "timestamp": 1591714946151,
        }

        os.environ["DD_FETCH_LAMBDA_TAGS"] = "True"
        generated_metrics = generate_enhanced_lambda_metrics(logs_input, tags_cache)
        verify_as_json(generated_metrics)
        del os.environ["DD_FETCH_LAMBDA_TAGS"]

    @patch("caching.lambda_cache.send_forwarder_internal_metrics")
    @patch("telemetry.send_forwarder_internal_metrics")
    @patch("caching.lambda_cache.LambdaTagsCache.get_cache_from_s3")
    def test_generate_enhanced_lambda_metrics_out_of_memory(
        self, mock_get_s3_cache, mock_forward_metrics, mock_base_forward_metrics
    ):
        mock_get_s3_cache.return_value = (
            {
                "arn:aws:lambda:us-east-1:0:function:cloudwatch-event": [
                    "team:metrics",
                    "monitor:datadog",
                    "env:prod",
                    "creator:swf",
                ]
            },
            time(),
        )
        tags_cache = LambdaTagsCache("")

        logs_input = {
            "message": "2020-06-09T15:02:26.150Z 7c9567b5-107b-4a6c-8798-0157ac21db52 FATAL ERROR: CALL_AND_RETRY_LAST Allocation failed - JavaScript heap out of memory\n\n",
            "aws": {
                "awslogs": {
                    "logGroup": "/aws/lambda/cloudwatch-event",
                    "logStream": "2020/06/09/[$LATEST]b249865adaaf4fad80f95f8ad09725b8",
                    "owner": "601427279990",
                },
                "function_version": "$LATEST",
                "invoked_function_arn": "arn:aws:lambda:us-east-1:0:function:test",
            },
            "lambda": {"arn": "arn:aws:lambda:us-east-1:0:function:cloudwatch-event"},
            "timestamp": 1591714946151,
        }

        os.environ["DD_FETCH_LAMBDA_TAGS"] = "True"
        generated_metrics = generate_enhanced_lambda_metrics(logs_input, tags_cache)
        verify_as_json(generated_metrics)
        del os.environ["DD_FETCH_LAMBDA_TAGS"]


if __name__ == "__main__":
    unittest.main()
