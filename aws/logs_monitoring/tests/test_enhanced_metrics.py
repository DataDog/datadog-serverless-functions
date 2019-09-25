import unittest

from enhanced_metrics import (
    sanitize_aws_tag_string,
    parse_metrics_from_report_log,
    parse_lambda_tags_from_arn,
    generate_enhanced_lambda_metrics,
)


# python -m unittest tests.test_enhanced_metrics from parent dir
class TestEnhancedMetrics(unittest.TestCase):

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
        self.assertEqual(
            parse_lambda_tags_from_arn(
                "arn:aws:lambda:us-east-1:1234597598159:function:swf-hello-test"
            ),
            [
                "region:us-east-1",
                "account_id:1234597598159",
                "functionname:swf-hello-test",
            ],
        )

    def test_parse_metrics_from_report_log(self):
        parsed_metrics = parse_metrics_from_report_log(self.malformed_report)
        self.assertEqual(parsed_metrics, [])

        parsed_metrics = parse_metrics_from_report_log(self.standard_report)
        self.assertEqual(
            [metric.__dict__ for metric in parsed_metrics],
            [
                {"name": "duration", "tags": ["memorysize:128"], "value": 0.62},
                {"name": "billed_duration", "tags": ["memorysize:128"], "value": 100},
                {"name": "max_memory_used", "tags": ["memorysize:128"], "value": 51},
            ],
        )

        parsed_metrics = parse_metrics_from_report_log(self.report_with_xray)
        self.assertEqual(
            [metric.__dict__ for metric in parsed_metrics],
            [
                {"name": "duration", "tags": ["memorysize:128"], "value": 1711.87},
                {"name": "billed_duration", "tags": ["memorysize:128"], "value": 1800},
                {"name": "max_memory_used", "tags": ["memorysize:128"], "value": 98},
            ],
        )

    def test_generate_enhanced_lambda_metrics(self):
        logs_input = [
            {
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
            },
            {
                "message": "REPORT RequestId: 4d30924b-6c69-463c-9ee2-9d831592f624\tDuration: 143.55 ms\tBilled Duration: 200 ms\tMemory Size: 512 MB\tMax Memory Used: 89 MB\t\nXRAY TraceId: 1-5d8bba5f-0ceae97823c479c00c75754e\tSegmentId: 36d912a53c0f3c24\tSampled: true\t\n",
                "aws": {
                    "awslogs": {
                        "logGroup": "/aws/lambda/post-coupon-staging",
                        "logStream": "2019/09/25/[$LATEST]fa386a866c4c45feaba6e8a0a0d8ac3b",
                        "owner": "172597598159",
                    },
                    "function_version": "$LATEST",
                    "invoked_function_arn": "arn:aws:lambda:us-east-1:172597598159:function:collect_logs_datadog_demo",
                },
                "lambda": {
                    "arn": "arn:aws:lambda:us-east-1:172597598159:function:post-coupon-staging"
                },
            },
        ]

        generated_metrics = generate_enhanced_lambda_metrics(logs_input, {})
        expected_metrics = [
            {
                "name": "duration",
                "tags": [
                    "memorysize:128",
                    "region:us-east-1",
                    "account_id:172597598159",
                    "functionname:post-coupon-prod-us",
                ],
                "value": 3470.65,
            },
            {
                "name": "billed_duration",
                "tags": [
                    "memorysize:128",
                    "region:us-east-1",
                    "account_id:172597598159",
                    "functionname:post-coupon-prod-us",
                ],
                "value": 3500.0,
            },
            {
                "name": "max_memory_used",
                "tags": [
                    "memorysize:128",
                    "region:us-east-1",
                    "account_id:172597598159",
                    "functionname:post-coupon-prod-us",
                ],
                "value": 89.0,
            },
            {
                "name": "duration",
                "tags": [
                    "memorysize:512",
                    "region:us-east-1",
                    "account_id:172597598159",
                    "functionname:post-coupon-staging",
                ],
                "value": 143.55,
            },
            {
                "name": "billed_duration",
                "tags": [
                    "memorysize:512",
                    "region:us-east-1",
                    "account_id:172597598159",
                    "functionname:post-coupon-staging",
                ],
                "value": 200.0,
            },
            {
                "name": "max_memory_used",
                "tags": [
                    "memorysize:512",
                    "region:us-east-1",
                    "account_id:172597598159",
                    "functionname:post-coupon-staging",
                ],
                "value": 89.0,
            },
        ]
        self.assertEqual(
            [metric.__dict__ for metric in generated_metrics], expected_metrics
        )

        tags_by_arn = {
            "arn:aws:lambda:us-east-1:172597598159:function:post-coupon-staging": [
                "team:serverless",
                "monitor:datadog",
                "env:staging",
                "creator:swf",
            ],
            "arn:aws:lambda:us-east-1:172597598159:function:post-coupon-prod-us": [
                "team:metrics",
                "monitor:datadog",
                "env:prod",
                "creator:swf",
            ],
        }
        generated_metrics = generate_enhanced_lambda_metrics(logs_input, tags_by_arn)
        expected_metrics = [
            {
                "name": "duration",
                "tags": [
                    "memorysize:128",
                    "region:us-east-1",
                    "account_id:172597598159",
                    "functionname:post-coupon-prod-us",
                    "team:metrics",
                    "monitor:datadog",
                    "env:prod",
                    "creator:swf",
                ],
                "value": 3470.65,
            },
            {
                "name": "billed_duration",
                "tags": [
                    "memorysize:128",
                    "region:us-east-1",
                    "account_id:172597598159",
                    "functionname:post-coupon-prod-us",
                    "team:metrics",
                    "monitor:datadog",
                    "env:prod",
                    "creator:swf",
                ],
                "value": 3500.0,
            },
            {
                "name": "max_memory_used",
                "tags": [
                    "memorysize:128",
                    "region:us-east-1",
                    "account_id:172597598159",
                    "functionname:post-coupon-prod-us",
                    "team:metrics",
                    "monitor:datadog",
                    "env:prod",
                    "creator:swf",
                ],
                "value": 89.0,
            },
            {
                "name": "duration",
                "tags": [
                    "memorysize:512",
                    "region:us-east-1",
                    "account_id:172597598159",
                    "functionname:post-coupon-staging",
                    "team:serverless",
                    "monitor:datadog",
                    "env:staging",
                    "creator:swf",
                ],
                "value": 143.55,
            },
            {
                "name": "billed_duration",
                "tags": [
                    "memorysize:512",
                    "region:us-east-1",
                    "account_id:172597598159",
                    "functionname:post-coupon-staging",
                    "team:serverless",
                    "monitor:datadog",
                    "env:staging",
                    "creator:swf",
                ],
                "value": 200.0,
            },
            {
                "name": "max_memory_used",
                "tags": [
                    "memorysize:512",
                    "region:us-east-1",
                    "account_id:172597598159",
                    "functionname:post-coupon-staging",
                    "team:serverless",
                    "monitor:datadog",
                    "env:staging",
                    "creator:swf",
                ],
                "value": 89.0,
            },
        ]
        self.assertEqual(
            [metric.__dict__ for metric in generated_metrics], expected_metrics
        )


if __name__ == "__main__":
    unittest.main()
