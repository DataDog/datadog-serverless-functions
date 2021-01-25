import unittest
import os
from time import time
from botocore.exceptions import ClientError

from unittest.mock import patch
from unittest import mock

from enhanced_lambda_metrics import (
    sanitize_aws_tag_string,
    parse_metrics_from_report_log,
    parse_lambda_tags_from_arn,
    generate_enhanced_lambda_metrics,
    LambdaTagsCache,
    parse_get_resources_response_for_tags_by_arn,
    create_timeout_enhanced_metric,
    create_out_of_memory_enhanced_metric,
    get_dd_tag_string_from_aws_dict,
)


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

    def test_sanitize_tag_string(self):
        self.assertEqual(sanitize_aws_tag_string("serverless"), "serverless")
        # Don't replace : \ / . in middle of string
        self.assertEqual(sanitize_aws_tag_string("ser-/.ver_less"), "ser-/.ver_less")
        # Remove invalid characters
        self.assertEqual(sanitize_aws_tag_string("s+e@rv_erl_ess"), "s_e_rv_erl_ess")
        # Dedup underscores
        self.assertEqual(sanitize_aws_tag_string("serverl___ess"), "serverl_ess")
        # Keep colons when remove_colons=False
        self.assertEqual(sanitize_aws_tag_string("serv:erless:"), "serv:erless:")
        # Substitute colon when remove_colons=True
        self.assertEqual(
            sanitize_aws_tag_string("serv:erless:", remove_colons=True), "serv_erless"
        )
        # Convert to lower
        self.assertEqual(sanitize_aws_tag_string("serVerLess"), "serverless")
        self.assertEqual(sanitize_aws_tag_string(""), "")
        self.assertEqual(sanitize_aws_tag_string("6.6.6"), ".6.6")
        self.assertEqual(
            sanitize_aws_tag_string("6.6.6", remove_leading_digits=False), "6.6.6"
        )

    def test_get_dd_tag_string_from_aws_dict(self):
        # Sanitize the key and value, combine them into a string
        test_dict = {
            "Key": "region",
            "Value": "us-east-1",
        }

        self.assertEqual(get_dd_tag_string_from_aws_dict(test_dict), "region:us-east-1")

        # Truncate to 200 characters
        long_string = "a" * 300

        test_dict = {
            "Key": "too-long",
            "Value": long_string,
        }

        self.assertEqual(
            get_dd_tag_string_from_aws_dict(test_dict), f"too-long:{long_string[0:191]}"
        )

    def test_parse_lambda_tags_from_arn(self):
        self.assertListEqual(
            parse_lambda_tags_from_arn(
                "arn:aws:lambda:us-east-1:1234597598159:function:swf-hello-test"
            ),
            [
                "region:us-east-1",
                "account_id:1234597598159",
                "aws_account:1234597598159",
                "functionname:swf-hello-test",
            ],
        )

    def test_generate_custom_tags_cache(self):
        self.assertEqual(
            parse_get_resources_response_for_tags_by_arn(
                {
                    "ResourceTagMappingList": [
                        {
                            "ResourceARN": "arn:aws:lambda:us-east-1:123497598159:function:my-test-lambda-dev",
                            "Tags": [
                                {"Key": "stage", "Value": "dev"},
                                {"Key": "team", "Value": "serverless"},
                                {"Key": "empty", "Value": ""},
                            ],
                        },
                        {
                            "ResourceARN": "arn:aws:lambda:us-east-1:123497598159:function:my-test-lambda-prod",
                            "Tags": [
                                {"Key": "stage", "Value": "prod"},
                                {"Key": "team", "Value": "serverless"},
                                {"Key": "datacenter", "Value": "eu"},
                                {"Key": "empty", "Value": ""},
                            ],
                        },
                    ]
                }
            ),
            {
                "arn:aws:lambda:us-east-1:123497598159:function:my-test-lambda-dev": [
                    "stage:dev",
                    "team:serverless",
                    "empty",
                ],
                "arn:aws:lambda:us-east-1:123497598159:function:my-test-lambda-prod": [
                    "stage:prod",
                    "team:serverless",
                    "datacenter:eu",
                    "empty",
                ],
            },
        )

    def test_parse_metrics_from_report_log(self):
        parsed_metrics = parse_metrics_from_report_log(self.malformed_report)
        self.assertEqual(parsed_metrics, [])

        parsed_metrics = parse_metrics_from_report_log(self.standard_report)

        # The timestamps are None because the timestamp is added after the metrics are parsed
        self.assertListEqual(
            [metric.__dict__ for metric in parsed_metrics],
            [
                {
                    "name": "aws.lambda.enhanced.duration",
                    "tags": [
                        "memorysize:128",
                        "cold_start:false",
                    ],
                    "value": 0.00062,
                    "timestamp": None,
                },
                {
                    "name": "aws.lambda.enhanced.billed_duration",
                    "tags": [
                        "memorysize:128",
                        "cold_start:false",
                    ],
                    "value": 0.1000,
                    "timestamp": None,
                },
                {
                    "name": "aws.lambda.enhanced.max_memory_used",
                    "tags": [
                        "memorysize:128",
                        "cold_start:false",
                    ],
                    "value": 51.0,
                    "timestamp": None,
                },
                {
                    "name": "aws.lambda.enhanced.estimated_cost",
                    "tags": [
                        "memorysize:128",
                        "cold_start:false",
                    ],
                    "timestamp": None,
                    "value": 4.0833375e-07,
                },
            ],
        )

        parsed_metrics = parse_metrics_from_report_log(self.cold_start_report)
        self.assertEqual(
            [metric.__dict__ for metric in parsed_metrics],
            [
                {
                    "name": "aws.lambda.enhanced.duration",
                    "tags": [
                        "memorysize:128",
                        "cold_start:true",
                    ],
                    "value": 0.0008100000000000001,
                    "timestamp": None,
                },
                {
                    "name": "aws.lambda.enhanced.billed_duration",
                    "tags": [
                        "memorysize:128",
                        "cold_start:true",
                    ],
                    "value": 0.1000,
                    "timestamp": None,
                },
                {
                    "name": "aws.lambda.enhanced.max_memory_used",
                    "tags": [
                        "memorysize:128",
                        "cold_start:true",
                    ],
                    "value": 90.0,
                    "timestamp": None,
                },
                {
                    "name": "aws.lambda.enhanced.init_duration",
                    "tags": [
                        "memorysize:128",
                        "cold_start:true",
                    ],
                    "value": 1.234,
                    "timestamp": None,
                },
                {
                    "name": "aws.lambda.enhanced.estimated_cost",
                    "tags": [
                        "memorysize:128",
                        "cold_start:true",
                    ],
                    "timestamp": None,
                    "value": 4.0833375e-07,
                },
            ],
        )
        parsed_metrics = parse_metrics_from_report_log(self.report_with_xray)
        self.assertListEqual(
            [metric.__dict__ for metric in parsed_metrics],
            [
                {
                    "name": "aws.lambda.enhanced.duration",
                    "tags": [
                        "memorysize:128",
                        "cold_start:false",
                    ],
                    "timestamp": None,
                    "value": 1.71187,
                },
                {
                    "name": "aws.lambda.enhanced.billed_duration",
                    "tags": [
                        "memorysize:128",
                        "cold_start:false",
                    ],
                    "timestamp": None,
                    "value": 1.8,
                },
                {
                    "name": "aws.lambda.enhanced.max_memory_used",
                    "tags": [
                        "memorysize:128",
                        "cold_start:false",
                    ],
                    "timestamp": None,
                    "value": 98.0,
                },
                {
                    "name": "aws.lambda.enhanced.estimated_cost",
                    "tags": [
                        "memorysize:128",
                        "cold_start:false",
                    ],
                    "timestamp": None,
                    "value": 3.9500075e-06,
                },
            ],
        )

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

    @patch("enhanced_lambda_metrics.send_forwarder_internal_metrics")
    @patch("enhanced_lambda_metrics.get_cache_from_s3")
    def test_generate_enhanced_lambda_metrics(
        self, mock_get_s3_cache, mock_forward_metrics
    ):
        mock_get_s3_cache.return_value = (
            {
                "arn:aws:lambda:us-east-1:172597598159:function:post-coupon-prod-us": [
                    "team:metrics",
                    "monitor:datadog",
                    "env:prod",
                    "creator:swf",
                ]
            },
            time(),
        )
        tags_cache = LambdaTagsCache()

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

        os.environ["DD_FETCH_LAMBDA_TAGS"] = "False"

        generated_metrics = generate_enhanced_lambda_metrics(logs_input, tags_cache)
        self.assertEqual(
            [metric.__dict__ for metric in generated_metrics],
            [
                {
                    "name": "aws.lambda.enhanced.duration",
                    "tags": [
                        "memorysize:128",
                        "cold_start:false",
                        "region:us-east-1",
                        "account_id:172597598159",
                        "aws_account:172597598159",
                        "functionname:post-coupon-prod-us",
                    ],
                    "timestamp": 10000,
                    "value": 3.47065,
                },
                {
                    "name": "aws.lambda.enhanced.billed_duration",
                    "tags": [
                        "memorysize:128",
                        "cold_start:false",
                        "region:us-east-1",
                        "account_id:172597598159",
                        "aws_account:172597598159",
                        "functionname:post-coupon-prod-us",
                    ],
                    "timestamp": 10000,
                    "value": 3.5,
                },
                {
                    "name": "aws.lambda.enhanced.max_memory_used",
                    "tags": [
                        "memorysize:128",
                        "cold_start:false",
                        "region:us-east-1",
                        "account_id:172597598159",
                        "aws_account:172597598159",
                        "functionname:post-coupon-prod-us",
                    ],
                    "timestamp": 10000,
                    "value": 89.0,
                },
                {
                    "name": "aws.lambda.enhanced.estimated_cost",
                    "tags": [
                        "memorysize:128",
                        "cold_start:false",
                        "region:us-east-1",
                        "account_id:172597598159",
                        "aws_account:172597598159",
                        "functionname:post-coupon-prod-us",
                    ],
                    "timestamp": 10000,
                    "value": 0.00000749168125,
                },
            ],
        )

        del os.environ["DD_FETCH_LAMBDA_TAGS"]

    @patch("enhanced_lambda_metrics.send_forwarder_internal_metrics")
    @patch("enhanced_lambda_metrics.get_cache_from_s3")
    def test_generate_enhanced_lambda_metrics_with_tags(
        self, mock_get_s3_cache, mock_forward_metrics
    ):
        mock_get_s3_cache.return_value = (
            {
                "arn:aws:lambda:us-east-1:172597598159:function:post-coupon-prod-us": [
                    "team:metrics",
                    "monitor:datadog",
                    "env:prod",
                    "creator:swf",
                ]
            },
            time(),
        )
        tags_cache = LambdaTagsCache()
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

        generated_metrics = generate_enhanced_lambda_metrics(logs_input, tags_cache)
        self.assertEqual(
            [metric.__dict__ for metric in generated_metrics],
            [
                {
                    "name": "aws.lambda.enhanced.duration",
                    "tags": [
                        "memorysize:128",
                        "cold_start:false",
                        "region:us-east-1",
                        "account_id:172597598159",
                        "aws_account:172597598159",
                        "functionname:post-coupon-prod-us",
                        "team:metrics",
                        "monitor:datadog",
                        "env:prod",
                        "creator:swf",
                    ],
                    "timestamp": 10000,
                    "value": 3.47065,
                },
                {
                    "name": "aws.lambda.enhanced.billed_duration",
                    "tags": [
                        "memorysize:128",
                        "cold_start:false",
                        "region:us-east-1",
                        "account_id:172597598159",
                        "aws_account:172597598159",
                        "functionname:post-coupon-prod-us",
                        "team:metrics",
                        "monitor:datadog",
                        "env:prod",
                        "creator:swf",
                    ],
                    "timestamp": 10000,
                    "value": 3.5,
                },
                {
                    "name": "aws.lambda.enhanced.max_memory_used",
                    "tags": [
                        "memorysize:128",
                        "cold_start:false",
                        "region:us-east-1",
                        "account_id:172597598159",
                        "aws_account:172597598159",
                        "functionname:post-coupon-prod-us",
                        "team:metrics",
                        "monitor:datadog",
                        "env:prod",
                        "creator:swf",
                    ],
                    "timestamp": 10000,
                    "value": 89.0,
                },
                {
                    "name": "aws.lambda.enhanced.estimated_cost",
                    "tags": [
                        "memorysize:128",
                        "cold_start:false",
                        "region:us-east-1",
                        "account_id:172597598159",
                        "aws_account:172597598159",
                        "functionname:post-coupon-prod-us",
                        "team:metrics",
                        "monitor:datadog",
                        "env:prod",
                        "creator:swf",
                    ],
                    "timestamp": 10000,
                    "value": 0.00000749168125,
                },
            ],
        )

        del os.environ["DD_FETCH_LAMBDA_TAGS"]

    @patch("enhanced_lambda_metrics.send_forwarder_internal_metrics")
    @patch("enhanced_lambda_metrics.get_cache_from_s3")
    def test_generate_enhanced_lambda_metrics_once_with_missing_arn(
        self, mock_get_s3_cache, mock_forward_metrics
    ):
        mock_get_s3_cache.return_value = ({}, time())
        tags_cache = LambdaTagsCache()

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

        generated_metrics = generate_enhanced_lambda_metrics(logs_input, tags_cache)
        mock_get_s3_cache.assert_called_once()
        mock_get_s3_cache.reset_mock()

        generated_metrics = generate_enhanced_lambda_metrics(logs_input, tags_cache)
        mock_get_s3_cache.assert_not_called()

        del os.environ["DD_FETCH_LAMBDA_TAGS"]

    @patch("enhanced_lambda_metrics.send_forwarder_internal_metrics")
    @patch("enhanced_lambda_metrics.get_cache_from_s3")
    def test_generate_enhanced_lambda_metrics_refresh_on_new_arn(
        self, mock_get_s3_cache, mock_forward_metrics
    ):
        mock_get_s3_cache.return_value = (
            {
                "arn:aws:lambda:us-east-1:172597598159:function:post-coupon-prod-us": [
                    "team:metrics",
                    "monitor:datadog",
                    "env:prod",
                    "creator:swf",
                ]
            },
            time(),
        )
        tags_cache = LambdaTagsCache()

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

        generated_metrics = generate_enhanced_lambda_metrics(logs_input, tags_cache)
        mock_get_s3_cache.assert_called_once()
        mock_get_s3_cache.reset_mock()

        del os.environ["DD_FETCH_LAMBDA_TAGS"]

    @patch("enhanced_lambda_metrics.acquire_s3_cache_lock")
    @patch("enhanced_lambda_metrics.release_s3_cache_lock")
    @patch("enhanced_lambda_metrics.write_cache_to_s3")
    @patch("enhanced_lambda_metrics.build_tags_by_arn_cache")
    @patch("enhanced_lambda_metrics.send_forwarder_internal_metrics")
    @patch("enhanced_lambda_metrics.get_cache_from_s3")
    def test_generate_enhanced_lambda_metrics_refresh_s3_cache(
        self,
        mock_get_s3_cache,
        mock_forward_metrics,
        mock_build_cache,
        mock_write_cache,
        mock_acquire_lock,
        mock_release_lock,
    ):
        mock_acquire_lock.return_value = True
        mock_get_s3_cache.return_value = (
            {},
            1000,
        )
        mock_build_cache.return_value = (
            True,
            {
                "arn:aws:lambda:us-east-1:172597598159:function:post-coupon-prod-us": [
                    "team:metrics",
                    "monitor:datadog",
                    "env:prod",
                    "creator:swf",
                ]
            },
        )
        tags_cache = LambdaTagsCache()

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

        generated_metrics = generate_enhanced_lambda_metrics(logs_input, tags_cache)
        mock_get_s3_cache.assert_called_once()
        mock_build_cache.assert_called_once()
        mock_write_cache.assert_called_once()
        mock_get_s3_cache.reset_mock()
        assert mock_forward_metrics.call_count == 2

        del os.environ["DD_FETCH_LAMBDA_TAGS"]

    @patch("enhanced_lambda_metrics.acquire_s3_cache_lock")
    @patch("enhanced_lambda_metrics.release_s3_cache_lock")
    @patch("enhanced_lambda_metrics.resource_tagging_client")
    @patch("enhanced_lambda_metrics.write_cache_to_s3")
    @patch("enhanced_lambda_metrics.parse_get_resources_response_for_tags_by_arn")
    @patch("enhanced_lambda_metrics.send_forwarder_internal_metrics")
    @patch("enhanced_lambda_metrics.get_cache_from_s3")
    def test_generate_enhanced_lambda_metrics_client_error(
        self,
        mock_get_s3_cache,
        mock_forward_metrics,
        mock_parse_responses,
        mock_write_cache,
        mock_boto3,
        mock_acquire_lock,
        mock_release_lock,
    ):
        mock_acquire_lock.return_value = True
        mock_get_s3_cache.return_value = (
            {},
            1000,
        )
        paginator = mock.MagicMock()
        paginator.paginate.return_value = ["foo"]
        mock_boto3.get_paginator.return_value = paginator

        mock_parse_responses.side_effect = ClientError(
            {"ResponseMetadata": {"HTTPStatusCode": 429}}, "Client Error"
        )
        tags_cache = LambdaTagsCache()

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

        generated_metrics = generate_enhanced_lambda_metrics(logs_input, tags_cache)
        mock_get_s3_cache.assert_called_once()
        mock_boto3.get_paginator.assert_called_once()
        paginator.paginate.assert_called_once()
        mock_get_s3_cache.reset_mock()
        print(mock_forward_metrics.call_count)
        assert mock_forward_metrics.call_count == 4

        del os.environ["DD_FETCH_LAMBDA_TAGS"]

    @patch("enhanced_lambda_metrics.send_forwarder_internal_metrics")
    @patch("enhanced_lambda_metrics.get_cache_from_s3")
    def test_generate_enhanced_lambda_metrics_timeout(
        self, mock_get_s3_cache, mock_forward_metrics
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
        tags_cache = LambdaTagsCache()

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
        self.assertEqual(
            [metric.__dict__ for metric in generated_metrics],
            [
                {
                    "name": "aws.lambda.enhanced.timeouts",
                    "tags": [
                        "region:us-east-1",
                        "account_id:0",
                        "aws_account:0",
                        "functionname:cloudwatch-event",
                        "team:metrics",
                        "monitor:datadog",
                        "env:prod",
                        "creator:swf",
                    ],
                    "timestamp": 1591714946151,
                    "value": 1.0,
                }
            ],
        )
        del os.environ["DD_FETCH_LAMBDA_TAGS"]

    @patch("enhanced_lambda_metrics.send_forwarder_internal_metrics")
    @patch("enhanced_lambda_metrics.get_cache_from_s3")
    def test_generate_enhanced_lambda_metrics_out_of_memory(
        self, mock_get_s3_cache, mock_forward_metrics
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
        tags_cache = LambdaTagsCache()

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
        self.assertEqual(
            [metric.__dict__ for metric in generated_metrics],
            [
                {
                    "name": "aws.lambda.enhanced.out_of_memory",
                    "tags": [
                        "region:us-east-1",
                        "account_id:0",
                        "aws_account:0",
                        "functionname:cloudwatch-event",
                        "team:metrics",
                        "monitor:datadog",
                        "env:prod",
                        "creator:swf",
                    ],
                    "timestamp": 1591714946151,
                    "value": 1.0,
                }
            ],
        )
        del os.environ["DD_FETCH_LAMBDA_TAGS"]


if __name__ == "__main__":
    unittest.main()
