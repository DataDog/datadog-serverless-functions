import base64
import gzip
import json
import os
import unittest
import sys
from unittest.mock import patch, MagicMock
from approvaltests.approvals import verify_as_json
from approvaltests.namer import NamerFactory

from steps.enums import AwsEventSource

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
from settings import DD_HOST, DD_SOURCE
from steps.handlers.awslogs_handler import AwsLogsHandler
from steps.handlers.aws_attributes import AwsAttributes
from caching.cache_layer import CacheLayer

env_patch.stop()


class Context:
    function_version = 0
    invoked_function_arn = "invoked_function_arn"
    function_name = "function_name"
    memory_limit_in_mb = "10"


class TestAWSLogsHandler(unittest.TestCase):
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
                                            "id": "31953106606966983378809025079804211143289615424298221568",
                                            "timestamp": 1609556645000,
                                            "message": "2021-01-02 03:04:05 UTC::@:[5306]:LOG:  database system is ready to accept connections",
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
        context = Context()
        mock_cache_init.return_value = None
        cache_layer = CacheLayer("")
        cache_layer._cloudwatch_log_group_cache.get = MagicMock(
            return_value=["test_tag_key:test_tag_value"]
        )

        awslogs_handler = AwsLogsHandler(context, cache_layer)
        verify_as_json(list(awslogs_handler.handle(event)))

    @patch("caching.cloudwatch_log_group_cache.CloudwatchLogGroupTagsCache.__init__")
    @patch("caching.cloudwatch_log_group_cache.send_forwarder_internal_metrics")
    @patch.dict("os.environ", {"DD_STEP_FUNCTIONS_TRACE_ENABLED": "true"})
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
                                    "logGroup": "/aws/vendedlogs/states/logs-to-traces-sequential-Logs",
                                    "logStream": "states/logs-to-traces-sequential/2022-11-10-15-50/7851b2d9",
                                    "subscriptionFilters": ["testFilter"],
                                    "logEvents": [
                                        {
                                            "id": "37199773595581154154810589279545129148442535997644275712",
                                            "timestamp": 1668095539607,
                                            "message": '{"id": "1","type": "ExecutionStarted","details": {"input": "{}","inputDetails": {"truncated": "false"},"roleArn": "arn:aws:iam::12345678910:role/service-role/StepFunctions-test-role-a0iurr4pt"},"previous_event_id": "0","event_timestamp": "1716992192441","execution_arn": "arn:aws:states:us-east-1:12345678910:execution:StepFunction1:ccccccc-d1da-4c38-b32c-2b6b07d713fa","redrive_count": "0"}',
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
        context = Context()
        mock_forward_metrics.side_effect = MagicMock()
        mock_cache_init.return_value = None
        cache_layer = CacheLayer("")
        cache_layer._step_functions_cache.get = MagicMock(
            return_value=["test_tag_key:test_tag_value"]
        )
        cache_layer._cloudwatch_log_group_cache.get = MagicMock()

        awslogs_handler = AwsLogsHandler(context, cache_layer)
        verify_as_json(list(awslogs_handler.handle(event)))

    @patch("caching.cloudwatch_log_group_cache.CloudwatchLogGroupTagsCache.__init__")
    @patch("caching.cloudwatch_log_group_cache.send_forwarder_internal_metrics")
    @patch.dict("os.environ", {"DD_STEP_FUNCTIONS_TRACE_ENABLED": "true"})
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
                                    "logStream": "states/logs-to-traces-sequential/2022-11-10-15-50/7851b2d9",
                                    "subscriptionFilters": ["testFilter"],
                                    "logEvents": [
                                        {
                                            "id": "37199773595581154154810589279545129148442535997644275712",
                                            "timestamp": 1668095539607,
                                            "message": '{"id": "1","type": "ExecutionStarted","details": {"input": "{}","inputDetails": {"truncated": "false"},"roleArn": "arn:aws:iam::12345678910:role/service-role/StepFunctions-test-role-a0iurr4pt"},"previous_event_id": "0","event_timestamp": "1716992192441","execution_arn": "arn:aws:states:us-east-1:12345678910:execution:StepFunction2:ccccccc-d1da-4c38-b32c-2b6b07d713fa","redrive_count": "0"}',
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
        context = Context()
        mock_forward_metrics.side_effect = MagicMock()
        mock_cache_init.return_value = None
        cache_layer = CacheLayer("")
        cache_layer._step_functions_cache.get = MagicMock(
            return_value=["test_tag_key:test_tag_value"]
        )
        cache_layer._cloudwatch_log_group_cache.get = MagicMock()

        awslogs_handler = AwsLogsHandler(context, cache_layer)
        # for some reasons, the below two are needed to update the context of the handler
        verify_as_json(list(awslogs_handler.handle(eventFromCustomizedLogGroup)))

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
            stepfunction_loggroup.get("logGroup"),
            stepfunction_loggroup.get("logStream"),
            stepfunction_loggroup.get("owner"),
        )
        context = Context()
        aws_handler = AwsLogsHandler(context, CacheLayer(""))

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
            lambda_default_loggroup.get("logGroup"),
            lambda_default_loggroup.get("logStream"),
            lambda_default_loggroup.get("owner"),
        )
        context = Context()

        aws_handler = AwsLogsHandler(context, CacheLayer(""))
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
        self.aws_handler = AwsLogsHandler(None, None)

    def test_get_lower_cased_lambda_function_name(self):
        self.assertEqual(True, True)
        # Non Lambda log
        aws_attributes = AwsAttributes(
            "/aws/vendedlogs/states/logs-to-traces-sequential-Logs",
            "states/logs-to-traces-sequential/2022-11-10-15-50/7851b2d9",
            [],
        )
        self.assertEqual(
            self.aws_handler.get_lower_cased_lambda_function_name(aws_attributes),
            None,
        )

        aws_attributes = AwsAttributes(
            "/aws/lambda/test-lambda-default-log-group",
            "2023/11/06/[$LATEST]b25b1f977b3e416faa45a00f427e7acb",
            [],
        )
        self.assertEqual(
            self.aws_handler.get_lower_cased_lambda_function_name(aws_attributes),
            "test-lambda-default-log-group",
        )

        aws_attributes = AwsAttributes(
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
        self.aws_handler = AwsLogsHandler(None, None)

    def test_get_state_machine_arn(self):
        aws_attributes = AwsAttributes(
            log_events=[
                {
                    "message": json.dumps({"no_execution_arn": "xxxx/yyy"}),
                }
            ]
        )

        self.assertEqual(self.aws_handler.get_state_machine_arn(aws_attributes), "")

        aws_attributes = AwsAttributes(
            log_events=[
                {
                    "message": json.dumps(
                        {
                            "execution_arn": "arn:aws:states:sa-east-1:425362996713:express:my-Various-States:7f653fda-c79a-430b-91e2-3f97eb87cabb:862e5d40-a457-4ca2-a3c1-78485bd94d3f"
                        }
                    ),
                }
            ]
        )
        self.assertEqual(
            self.aws_handler.get_state_machine_arn(aws_attributes),
            "arn:aws:states:sa-east-1:425362996713:stateMachine:my-Various-States",
        )

        aws_attributes = AwsAttributes(
            log_events=[
                {
                    "message": json.dumps(
                        {
                            "execution_arn": "arn:aws:states:sa-east-1:425362996713:express:my-Various-States/7f653fda-c79a-430b-91e2-3f97eb87cabb:862e5d40-a457-4ca2-a3c1-78485bd94d3f"
                        }
                    )
                }
            ]
        )

        self.assertEqual(
            self.aws_handler.get_state_machine_arn(aws_attributes),
            "arn:aws:states:sa-east-1:425362996713:stateMachine:my-Various-States",
        )

        aws_attributes = AwsAttributes(
            log_events=[
                {
                    "message": json.dumps(
                        {
                            "execution_arn": "arn:aws:states:sa-east-1:425362996713:express:my-Various-States\\7f653fda-c79a-430b-91e2-3f97eb87cabb:862e5d40-a457-4ca2-a3c1-78485bd94d3f"
                        }
                    )
                }
            ]
        )
        self.assertEqual(
            self.aws_handler.get_state_machine_arn(aws_attributes),
            "arn:aws:states:sa-east-1:425362996713:stateMachine:my-Various-States",
        )


if __name__ == "__main__":
    unittest.main()
