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

from caching.cache_layer import CacheLayer
from steps.handlers.aws_attributes import AwsAttributes
from steps.handlers.awslogs_handler import AwsLogsHandler

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
    },
)
env_patch.start()

env_patch.stop()


class Context:
    def __init__(self, invoked_function_arn="invoked_function_arn"):
        self.invoked_function_arn = invoked_function_arn

    function_version = "$LATEST"
    invoked_function_arn = "invoked_function_arn"
    function_name = "function_name"
    memory_limit_in_mb = "10"


class TestAWSLogsHandler(unittest.TestCase):
    def setUp(self):
        self.scrubber = create_regex_scrubber(
            r"forwarder_version:\d+\.\d+\.\d+",
            "forwarder_version:<redacted>",
        )
        self.context = Context()

    @patch("caching.cloudwatch_log_group_cache.CloudwatchLogGroupTagsCache.__init__")
    def test_handle_with_overridden_source(self, mock_cache_init):
        with patch.dict(os.environ, {"DD_SOURCE": "something"}):
            reload(sys.modules["settings"])
            reload(sys.modules["steps.common"])
            # Create a minimal test event
            event = {
                "awslogs": {
                    "data": base64.b64encode(
                        gzip.compress(
                            bytes(
                                json.dumps(
                                    {
                                        "owner": "123456789012",
                                        "logGroup": "/aws/lambda/test-function",
                                        "logStream": "2024/03/14/[$LATEST]abc123",
                                        "logEvents": [
                                            {
                                                "id": "123456789",
                                                "timestamp": 1710428400000,
                                                "message": "Test log message",
                                            }
                                        ],
                                    }
                                ),
                                "utf-8",
                            )
                        )
                    )
                }
            }

            # Create required args
            mock_cache_init.return_value = None
            cache_layer = CacheLayer("")
            cache_layer._cloudwatch_log_group_cache.get = MagicMock(return_value=[])

            # Process the event
            awslogs_handler = AwsLogsHandler(self.context, cache_layer)

            # Verify
            verify_as_json(
                list(awslogs_handler.handle(event)),
                options=Options().with_scrubber(self.scrubber),
            )

        reload(sys.modules["settings"])
        reload(sys.modules["steps.common"])

    @patch("caching.cloudwatch_log_group_cache.CloudwatchLogGroupTagsCache.__init__")
    def test_awslogs_handler_rds_postgresql(self, mock_cache_init):
        event = {
            "awslogs": {
                "data": base64.b64encode(
                    gzip.compress(
                        bytes(
                            json.dumps(
                                {
                                    "owner": "123456789012",
                                    "logGroup": "/aws/rds/instance/datadog/postgresql",
                                    "logStream": "datadog.0",
                                    "logEvents": [
                                        {
                                            "id": (
                                                "31953106606966983378809025079804211143289615424298221568"
                                            ),
                                            "timestamp": 1609556645000,
                                            "message": (
                                                "2021-01-02 03:04:05 UTC::@:[5306]:LOG:  database system is ready to accept connections"
                                            ),
                                        }
                                    ],
                                }
                            ),
                            "utf-8",
                        )
                    )
                )
            }
        }
        mock_cache_init.return_value = None
        cache_layer = CacheLayer("")
        cache_layer._cloudwatch_log_group_cache.get = MagicMock(
            return_value=["test_tag_key:test_tag_value"]
        )

        awslogs_handler = AwsLogsHandler(self.context, cache_layer)
        verify_as_json(
            list(awslogs_handler.handle(event)),
            options=Options().with_scrubber(self.scrubber),
        )

    @patch("caching.cloudwatch_log_group_cache.CloudwatchLogGroupTagsCache.__init__")
    @patch("caching.cloudwatch_log_group_cache.send_forwarder_internal_metrics")
    @patch.dict(
        "os.environ",
        {
            "DD_STEP_FUNCTIONS_TRACE_ENABLED": "true",
            "DD_FETCH_STEP_FUNCTIONS_TAGS": "true",
        },
    )
    def test_awslogs_handler_step_functions_tags_added_properly(
        self,
        mock_forward_metrics,
        mock_cache_init,
    ):
        event = {
            "awslogs": {
                "data": base64.b64encode(
                    gzip.compress(
                        bytes(
                            json.dumps(
                                {
                                    "messageType": "DATA_MESSAGE",
                                    "owner": "425362996713",
                                    "logGroup": (
                                        "/aws/vendedlogs/states/logs-to-traces-sequential-Logs"
                                    ),
                                    "logStream": (
                                        "states/logs-to-traces-sequential/2022-11-10-15-50/7851b2d9"
                                    ),
                                    "subscriptionFilters": ["testFilter"],
                                    "logEvents": [
                                        {
                                            "id": (
                                                "37199773595581154154810589279545129148442535997644275712"
                                            ),
                                            "timestamp": 1668095539607,
                                            "message": (
                                                '{"id": "1","type": "ExecutionStarted","details": {"input": "{}","inputDetails": {"truncated": "false"},"roleArn": "arn:aws:iam::12345678910:role/service-role/StepFunctions-test-role-a0iurr4pt"},"previous_event_id": "0","event_timestamp": "1716992192441","execution_arn": "arn:aws:states:us-east-1:12345678910:execution:StepFunction1:ccccccc-d1da-4c38-b32c-2b6b07d713fa","redrive_count": "0"}'
                                            ),
                                        }
                                    ],
                                }
                            ),
                            "utf-8",
                        )
                    )
                )
            }
        }
        mock_forward_metrics.side_effect = MagicMock()
        mock_cache_init.return_value = None
        cache_layer = CacheLayer("")
        cache_layer._step_functions_cache.get = MagicMock(
            return_value=["test_tag_key:test_tag_value", "service:customservice"]
        )
        cache_layer._cloudwatch_log_group_cache.get = MagicMock()

        awslogs_handler = AwsLogsHandler(self.context, cache_layer)
        verify_as_json(
            list(awslogs_handler.handle(event)),
            options=Options().with_scrubber(self.scrubber),
        )

    @patch("caching.cloudwatch_log_group_cache.CloudwatchLogGroupTagsCache.__init__")
    @patch("caching.cloudwatch_log_group_cache.send_forwarder_internal_metrics")
    @patch.dict(
        "os.environ",
        {
            "DD_STEP_FUNCTIONS_TRACE_ENABLED": "true",
            "DD_FETCH_STEP_FUNCTIONS_TAGS": "true",
        },
    )
    def test_awslogs_handler_step_functions_customized_log_group(
        self,
        mock_forward_metrics,
        mock_cache_init,
    ):
        # SF customized log group
        eventFromCustomizedLogGroup = {
            "awslogs": {
                "data": base64.b64encode(
                    gzip.compress(
                        bytes(
                            json.dumps(
                                {
                                    "messageType": "DATA_MESSAGE",
                                    "owner": "425362996713",
                                    "logGroup": "test/logs",
                                    "logStream": (
                                        "states/logs-to-traces-sequential/2022-11-10-15-50/7851b2d9"
                                    ),
                                    "subscriptionFilters": ["testFilter"],
                                    "logEvents": [
                                        {
                                            "id": (
                                                "37199773595581154154810589279545129148442535997644275712"
                                            ),
                                            "timestamp": 1668095539607,
                                            "message": (
                                                '{"id": "1","type": "ExecutionStarted","details": {"input": "{}","inputDetails": {"truncated": "false"},"roleArn": "arn:aws:iam::12345678910:role/service-role/StepFunctions-test-role-a0iurr4pt"},"previous_event_id": "0","event_timestamp": "1716992192441","execution_arn": "arn:aws:states:us-east-1:12345678910:execution:StepFunction2:ccccccc-d1da-4c38-b32c-2b6b07d713fa","redrive_count": "0"}'
                                            ),
                                        }
                                    ],
                                }
                            ),
                            "utf-8",
                        )
                    )
                )
            }
        }
        mock_forward_metrics.side_effect = MagicMock()
        mock_cache_init.return_value = None
        cache_layer = CacheLayer("")
        cache_layer._step_functions_cache.get = MagicMock(
            return_value=["test_tag_key:test_tag_value"]
        )
        cache_layer._cloudwatch_log_group_cache.get = MagicMock()

        awslogs_handler = AwsLogsHandler(self.context, cache_layer)
        # for some reasons, the below two are needed to update the context of the handler
        verify_as_json(
            list(awslogs_handler.handle(eventFromCustomizedLogGroup)),
            options=Options().with_scrubber(self.scrubber),
        )

    def test_awslogs_handler_lambda_log(self):
        event = {
            "awslogs": {
                "data": base64.b64encode(
                    gzip.compress(
                        bytes(
                            json.dumps(
                                {
                                    "messageType": "DATA_MESSAGE",
                                    "owner": "123456789012",
                                    "logGroup": (
                                        "/aws/lambda/test-lambda-default-log-group"
                                    ),
                                    "logStream": (
                                        "2023/11/06/[$LATEST]b25b1f977b3e416faa45a00f427e7acb"
                                    ),
                                    "subscriptionFilters": ["testFilter"],
                                    "logEvents": [
                                        {
                                            "id": (
                                                "37199773595581154154810589279545129148442535997644275712"
                                            ),
                                            "timestamp": 1668095539607,
                                            "message": (
                                                "2021-01-02 03:04:05 UTC::@:[5306]:LOG:  database system is ready to accept connections"
                                            ),
                                        }
                                    ],
                                }
                            ),
                            "utf-8",
                        )
                    )
                )
            }
        }
        cache_layer = CacheLayer("")
        cache_layer._cloudwatch_log_group_cache.get = MagicMock()
        cache_layer._lambda_cache.get = MagicMock(
            return_value=["service:customtags_service"]
        )

        awslogs_handler = AwsLogsHandler(self.context, cache_layer)
        verify_as_json(
            list(awslogs_handler.handle(event)),
            options=Options().with_scrubber(self.scrubber),
        )

    def test_process_lambda_logs(self):
        # Non Lambda log
        stepfunction_loggroup = {
            "messageType": "DATA_MESSAGE",
            "logGroup": "/aws/vendedlogs/states/logs-to-traces-sequential-Logs",
            "logStream": "states/logs-to-traces-sequential/2022-11-10-15-50/7851b2d9",
            "logEvents": [],
        }
        metadata = {"ddsource": "postgresql", "ddtags": ""}
        aws_attributes = AwsAttributes(
            self.context,
            stepfunction_loggroup.get("logGroup"),
            stepfunction_loggroup.get("logStream"),
            stepfunction_loggroup.get("owner"),
        )
        aws_handler = AwsLogsHandler(self.context, CacheLayer(""))

        aws_handler.process_lambda_logs(metadata, aws_attributes)
        self.assertEqual(metadata, {"ddsource": "postgresql", "ddtags": ""})

        # Lambda log
        lambda_default_loggroup = {
            "messageType": "DATA_MESSAGE",
            "logGroup": "/aws/lambda/test-lambda-default-log-group",
            "logStream": "2023/11/06/[$LATEST]b25b1f977b3e416faa45a00f427e7acb",
            "logEvents": [],
        }
        metadata = {"ddsource": "postgresql", "ddtags": "env:dev"}
        aws_attributes = AwsAttributes(
            self.context,
            lambda_default_loggroup.get("logGroup"),
            lambda_default_loggroup.get("logStream"),
            lambda_default_loggroup.get("owner"),
        )

        aws_handler = AwsLogsHandler(self.context, CacheLayer(""))
        aws_handler.process_lambda_logs(metadata, aws_attributes)
        self.assertEqual(
            metadata,
            {
                "ddsource": "postgresql",
                "ddtags": "env:dev",
            },
        )
        self.assertEqual(
            aws_attributes.to_dict().get("lambda", None).get("arn", None),
            "invoked_function_arnfunction:test-lambda-default-log-group",
        )

        # env not set
        metadata = {"ddsource": "postgresql", "ddtags": ""}
        aws_handler.process_lambda_logs(metadata, aws_attributes)
        self.assertEqual(
            metadata,
            {
                "ddsource": "postgresql",
                "ddtags": ",env:none",
            },
        )


class TestLambdaCustomizedLogGroup(unittest.TestCase):
    def setUp(self):
        self.context = Context()
        self.aws_handler = AwsLogsHandler(self.context, None)

    def test_get_lower_cased_lambda_function_name(self):
        # Non Lambda log
        aws_attributes = AwsAttributes(
            self.context,
            "/aws/vendedlogs/states/logs-to-traces-sequential-Logs",
            "states/logs-to-traces-sequential/2022-11-10-15-50/7851b2d9",
            [],
        )
        self.assertEqual(
            self.aws_handler.get_lower_cased_lambda_function_name(aws_attributes),
            None,
        )

        aws_attributes = AwsAttributes(
            self.context,
            "/aws/lambda/test-lambda-default-log-group",
            "2023/11/06/[$LATEST]b25b1f977b3e416faa45a00f427e7acb",
            [],
        )
        self.assertEqual(
            self.aws_handler.get_lower_cased_lambda_function_name(aws_attributes),
            "test-lambda-default-log-group",
        )

        aws_attributes = AwsAttributes(
            self.context,
            "customizeLambdaGrop",
            "2023/11/06/test-customized-log-group1[$LATEST]13e304cba4b9446eb7ef082a00038990",
            [],
        )
        self.assertEqual(
            self.aws_handler.get_lower_cased_lambda_function_name(aws_attributes),
            "test-customized-log-group1",
        )


class TestParsingStepFunctionLogs(unittest.TestCase):
    def setUp(self):
        self.context = Context()
        self.aws_handler = AwsLogsHandler(self.context, None)

    def test_get_state_machine_arn(self):
        aws_attributes = AwsAttributes(
            context=self.context,
            log_events=[
                {
                    "message": json.dumps({"no_execution_arn": "xxxx/yyy"}),
                }
            ],
        )

        self.assertEqual(self.aws_handler.get_state_machine_arn(aws_attributes), "")

        aws_attributes = AwsAttributes(
            context=self.context,
            log_events=[
                {
                    "message": json.dumps(
                        {
                            "execution_arn": (
                                "arn:aws:states:sa-east-1:425362996713:express:my-Various-States:7f653fda-c79a-430b-91e2-3f97eb87cabb:862e5d40-a457-4ca2-a3c1-78485bd94d3f"
                            )
                        }
                    ),
                }
            ],
        )
        self.assertEqual(
            self.aws_handler.get_state_machine_arn(aws_attributes),
            "arn:aws:states:sa-east-1:425362996713:stateMachine:my-Various-States",
        )

        aws_attributes = AwsAttributes(
            context=self.context,
            log_events=[
                {
                    "message": json.dumps(
                        {
                            "execution_arn": (
                                "arn:aws:states:sa-east-1:425362996713:express:my-Various-States/7f653fda-c79a-430b-91e2-3f97eb87cabb:862e5d40-a457-4ca2-a3c1-78485bd94d3f"
                            )
                        }
                    )
                }
            ],
        )

        self.assertEqual(
            self.aws_handler.get_state_machine_arn(aws_attributes),
            "arn:aws:states:sa-east-1:425362996713:stateMachine:my-Various-States",
        )

        aws_attributes = AwsAttributes(
            context=self.context,
            log_events=[
                {
                    "message": json.dumps(
                        {
                            "execution_arn": (
                                "arn:aws:states:sa-east-1:425362996713:express:my-Various-States\\7f653fda-c79a-430b-91e2-3f97eb87cabb:862e5d40-a457-4ca2-a3c1-78485bd94d3f"
                            )
                        }
                    )
                }
            ],
        )
        self.assertEqual(
            self.aws_handler.get_state_machine_arn(aws_attributes),
            "arn:aws:states:sa-east-1:425362996713:stateMachine:my-Various-States",
        )


class TestAwsPartitionExtraction(unittest.TestCase):
    def test_get_log_group_aws_partition(self):
        # default partition
        context = Context(
            invoked_function_arn="arn:aws:lambda:us-east-1:12345678910:function:test-lambda"
        )
        aws_attributes = AwsAttributes(
            context=context,
            log_group="my-log-group",
        )

        aws_attributes.set_account_region(
            "arn:aws:lambda:us-east-1:12345678910:function:test-lambda"
        )

        self.assertEqual(
            aws_attributes.get_log_group_arn(),
            "arn:aws:logs:us-east-1:12345678910:log-group:my-log-group",
        )

        # aws-cn partition
        context = Context(
            invoked_function_arn="arn:aws-cn:lambda:cn-north-1:12345678910:function:test-lambda"
        )
        aws_attributes = AwsAttributes(
            context=context,
            log_group="my-log-group",
        )
        aws_attributes.set_account_region(
            "arn:aws-cn:lambda:cn-north-1:12345678910:function:test-lambda"
        )
        self.assertEqual(
            aws_attributes.get_log_group_arn(),
            "arn:aws-cn:logs:cn-north-1:12345678910:log-group:my-log-group",
        )

        # aws-us-gov partition
        context = Context(
            invoked_function_arn="arn:aws-us-gov:lambda:us-gov-west-1:12345678910:function:test-lambda"
        )
        aws_attributes = AwsAttributes(
            context=context,
            log_group="my-log-group",
        )
        aws_attributes.set_account_region(
            "arn:aws-us-gov:lambda:us-gov-west-1:12345678910:function:test-lambda"
        )
        self.assertEqual(
            aws_attributes.get_log_group_arn(),
            "arn:aws-us-gov:logs:us-gov-west-1:12345678910:log-group:my-log-group",
        )


if __name__ == "__main__":
    unittest.main()
