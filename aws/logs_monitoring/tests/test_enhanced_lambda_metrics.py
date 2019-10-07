import unittest
import os

from mock import patch

from enhanced_lambda_metrics import (
    sanitize_aws_tag_string,
    parse_metrics_from_report_log,
    parse_lambda_tags_from_arn,
    generate_enhanced_lambda_metrics,
    LambdaTagsCache,
    parse_get_resources_response_for_tags_by_arn,
)


class TestEnhancedLambdaMetrics(unittest.TestCase):

    maxDiff = None

    malformed_report = "REPORT invalid report log line"

    standard_report = (
        "REPORT RequestId: 8edab1f8-7d34-4a8e-a965-15ccbbb78d4c	"
        "Duration: 0.62 ms	Billed Duration: 100 ms	Memory Size: 128 MB	Max Memory Used: 51 MB"
    )

    report_with_xray = (
        "REPORT RequestId: 814ba7cb-071e-4181-9a09-fa41db5bccad\tDuration: 1711.87 ms\t"
        "Billed Duration: 1800 ms\tMemory Size: 128 MB\tMax Memory Used: 98 MB\t\n"
        "XRAY TraceId: 1-5d83c0ad-b8eb33a0b1de97d804fac890\tSegmentId: 31255c3b19bd3637\t"
        "Sampled: true"
    )

    def test_sanitize_tag_string(self):
        self.assertEqual(sanitize_aws_tag_string("serverless"), "serverless")
        self.assertEqual(sanitize_aws_tag_string("ser:ver_less"), "ser_ver_less")
        self.assertEqual(sanitize_aws_tag_string("s-erv:erl_ess"), "s_erv_erl_ess")

    def test_parse_lambda_tags_from_arn(self):
        self.assertListEqual(
            parse_lambda_tags_from_arn(
                "arn:aws:lambda:us-east-1:1234597598159:function:swf-hello-test"
            ),
            [
                "region:us-east-1",
                "account_id:1234597598159",
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
                            ],
                        },
                        {
                            "ResourceARN": "arn:aws:lambda:us-east-1:123497598159:function:my-test-lambda-prod",
                            "Tags": [
                                {"Key": "stage", "Value": "prod"},
                                {"Key": "team", "Value": "serverless"},
                                {"Key": "datacenter", "Value": "eu"},
                            ],
                        },
                    ]
                }
            ),
            {
                "arn:aws:lambda:us-east-1:123497598159:function:my-test-lambda-dev": [
                    "stage:dev",
                    "team:serverless",
                ],
                "arn:aws:lambda:us-east-1:123497598159:function:my-test-lambda-prod": [
                    "stage:prod",
                    "team:serverless",
                    "datacenter:eu",
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
                    "tags": [],
                    "value": 0.00062,
                    "timestamp": None,
                },
                {
                    "name": "aws.lambda.enhanced.billed_duration",
                    "tags": [],
                    "value": 0.1000,
                    "timestamp": None,
                },
                {
                    "name": "aws.lambda.enhanced.max_memory_used",
                    "tags": [],
                    "value": 51.0,
                    "timestamp": None,
                },
                {
                    "name": "aws.lambda.enhanced.estimated_cost",
                    "tags": [],
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
                    "tags": [],
                    "timestamp": None,
                    "value": 1.71187,
                },
                {
                    "name": "aws.lambda.enhanced.billed_duration",
                    "tags": [],
                    "timestamp": None,
                    "value": 1.8,
                },
                {
                    "name": "aws.lambda.enhanced.max_memory_used",
                    "tags": [],
                    "timestamp": None,
                    "value": 98.0,
                },
                {
                    "name": "aws.lambda.enhanced.estimated_cost",
                    "tags": [],
                    "timestamp": None,
                    "value": 3.9500075e-06,
                },
            ],
        )

    @patch("enhanced_lambda_metrics.build_tags_by_arn_cache")
    def test_generate_enhanced_lambda_metrics(self, mock_build_cache):
        mock_build_cache.return_value = {
            "arn:aws:lambda:us-east-1:172597598159:function:post-coupon-prod-us": [
                "team:metrics",
                "monitor:datadog",
                "env:prod",
                "creator:swf",
            ]
        }
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
                        "region:us-east-1",
                        "account_id:172597598159",
                        "functionname:post-coupon-prod-us",
                    ],
                    "timestamp": 10000,
                    "value": 3.47065,
                },
                {
                    "name": "aws.lambda.enhanced.billed_duration",
                    "tags": [
                        "region:us-east-1",
                        "account_id:172597598159",
                        "functionname:post-coupon-prod-us",
                    ],
                    "timestamp": 10000,
                    "value": 3.5,
                },
                {
                    "name": "aws.lambda.enhanced.max_memory_used",
                    "tags": [
                        "region:us-east-1",
                        "account_id:172597598159",
                        "functionname:post-coupon-prod-us",
                    ],
                    "timestamp": 10000,
                    "value": 89.0,
                },
                {
                    "name": "aws.lambda.enhanced.estimated_cost",
                    "tags": [
                        "region:us-east-1",
                        "account_id:172597598159",
                        "functionname:post-coupon-prod-us",
                    ],
                    "timestamp": 10000,
                    "value": 0.00000749168125,
                },
            ],
        )

        del os.environ["DD_FETCH_LAMBDA_TAGS"]

    @patch("enhanced_lambda_metrics.build_tags_by_arn_cache")
    def test_generate_enhanced_lambda_metrics_with_tags(self, mock_build_cache):
        mock_build_cache.return_value = {
            "arn:aws:lambda:us-east-1:172597598159:function:post-coupon-prod-us": [
                "team:metrics",
                "monitor:datadog",
                "env:prod",
                "creator:swf",
            ]
        }
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
                        "region:us-east-1",
                        "account_id:172597598159",
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
                        "region:us-east-1",
                        "account_id:172597598159",
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
                        "region:us-east-1",
                        "account_id:172597598159",
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
                        "region:us-east-1",
                        "account_id:172597598159",
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


if __name__ == "__main__":
    unittest.main()
