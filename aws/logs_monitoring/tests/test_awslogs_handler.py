import base64
import gzip
import json
import os
import unittest
import sys
from unittest.mock import patch, MagicMock
from approvaltests.approvals import verify_as_json
from approvaltests.namer import NamerFactory
from caching.cache_layer import CacheLayer

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
from steps.handlers.awslogs_handler import (
    awslogs_handler,
    process_lambda_logs,
    get_state_machine_arn,
    get_lower_cased_lambda_function_name,
)
from steps.handlers.aws_attributes import AwsAttributes

env_patch.stop()


class TestAWSLogsHandler(unittest.TestCase):
    def test_awslogs_handler_rds_postgresql(self):
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
        context = None
        metadata = {"ddsource": "postgresql", "ddtags": "env:dev"}
        cache_layer = CacheLayer()
        cache_layer.cloudwatch_log_group_cache.get = MagicMock(
            return_value=["test_tag_key:test_tag_value"]
        )

        verify_as_json(list(awslogs_handler(event, context, metadata, cache_layer)))
        verify_as_json(metadata, options=NamerFactory.with_parameters("metadata"))

    @patch("caching.cloudwatch_log_group_cache.send_forwarder_internal_metrics")
    def test_awslogs_handler_step_functions_tags_added_properly(
        self,
        mock_forward_metrics,
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
                                            "message": '{"id":"1","type":"ExecutionStarted","details":{"input":"{"Comment": "Insert your JSON here"}","inputDetails":{"truncated":false},"roleArn":"arn:aws:iam::425362996713:role/service-role/StepFunctions-logs-to-traces-sequential-role-ccd69c03"},",previous_event_id":"0","event_timestamp":"1668095539607","execution_arn":"arn:aws:states:sa-east-1:425362996713:express:logs-to-traces-sequential:d0dbefd8-a0f6-b402-da4c-f4863def7456:7fa0cfbe-be28-4a20-9875-73c37f5dc39e"}',
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
        context = None
        metadata = {"ddsource": "postgresql", "ddtags": "env:dev"}
        mock_forward_metrics.side_effect = MagicMock()
        cache_layer = CacheLayer()
        cache_layer.step_functions_cache.get = MagicMock(
            return_value=["test_tag_key:test_tag_value"]
        )

        verify_as_json(list(awslogs_handler(event, context, metadata, cache_layer)))
        verify_as_json(metadata, options=NamerFactory.with_parameters("metadata"))

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
        context = None
        process_lambda_logs(aws_attributes, context, metadata)
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
        context = MagicMock()
        context.invoked_function_arn = "arn:aws:lambda:sa-east-1:601427279990:function:inferred-spans-python-dev-initsender"
        process_lambda_logs(aws_attributes, context, metadata)
        self.assertEqual(
            metadata,
            {
                "ddsource": "postgresql",
                "ddtags": "env:dev",
            },
        )
        self.assertEqual(
            aws_attributes.to_dict().get("lambda", None).get("arn", None),
            "arn:aws:lambda:sa-east-1:601427279990:function:test-lambda-default-log-group",
        )

        # env not set
        metadata = {"ddsource": "postgresql", "ddtags": ""}
        process_lambda_logs(aws_attributes, context, metadata)
        self.assertEqual(
            metadata,
            {
                "ddsource": "postgresql",
                "ddtags": ",env:none",
            },
        )


class TestLambdaCustomizedLogGroup(unittest.TestCase):
    def test_get_lower_cased_lambda_function_name(self):
        self.assertEqual(True, True)
        # Non Lambda log
        stepfunction_loggroup = {
            "messageType": "DATA_MESSAGE",
            "logGroup": "/aws/vendedlogs/states/logs-to-traces-sequential-Logs",
            "logStream": "states/logs-to-traces-sequential/2022-11-10-15-50/7851b2d9",
            "logEvents": [],
        }
        self.assertEqual(
            get_lower_cased_lambda_function_name(
                stepfunction_loggroup["logStream"], stepfunction_loggroup["logGroup"]
            ),
            None,
        )
        lambda_default_loggroup = {
            "messageType": "DATA_MESSAGE",
            "logGroup": "/aws/lambda/test-lambda-default-log-group",
            "logStream": "2023/11/06/[$LATEST]b25b1f977b3e416faa45a00f427e7acb",
            "logEvents": [],
        }
        self.assertEqual(
            get_lower_cased_lambda_function_name(
                lambda_default_loggroup["logStream"],
                lambda_default_loggroup["logGroup"],
            ),
            "test-lambda-default-log-group",
        )
        lambda_customized_loggroup = {
            "messageType": "DATA_MESSAGE",
            "logGroup": "customizeLambdaGrop",
            "logStream": "2023/11/06/test-customized-log-group1[$LATEST]13e304cba4b9446eb7ef082a00038990",
            "logEvents": [],
        }
        self.assertEqual(
            get_lower_cased_lambda_function_name(
                lambda_customized_loggroup["logStream"],
                lambda_customized_loggroup["logGroup"],
            ),
            "test-customized-log-group1",
        )


class TestParsingStepFunctionLogs(unittest.TestCase):
    def test_get_state_machine_arn(self):
        invalid_sf_log_message = {"no_execution_arn": "xxxx/yyy"}
        self.assertEqual(get_state_machine_arn(invalid_sf_log_message), "")

        normal_sf_log_message = {
            "execution_arn": "arn:aws:states:sa-east-1:425362996713:express:my-Various-States:7f653fda-c79a-430b-91e2-3f97eb87cabb:862e5d40-a457-4ca2-a3c1-78485bd94d3f"
        }
        self.assertEqual(
            get_state_machine_arn(normal_sf_log_message),
            "arn:aws:states:sa-east-1:425362996713:stateMachine:my-Various-States",
        )

        forward_slash_sf_log_message = {
            "execution_arn": "arn:aws:states:sa-east-1:425362996713:express:my-Various-States/7f653fda-c79a-430b-91e2-3f97eb87cabb:862e5d40-a457-4ca2-a3c1-78485bd94d3f"
        }
        self.assertEqual(
            get_state_machine_arn(forward_slash_sf_log_message),
            "arn:aws:states:sa-east-1:425362996713:stateMachine:my-Various-States",
        )

        back_slash_sf_log_message = {
            "execution_arn": "arn:aws:states:sa-east-1:425362996713:express:my-Various-States\\7f653fda-c79a-430b-91e2-3f97eb87cabb:862e5d40-a457-4ca2-a3c1-78485bd94d3f"
        }
        self.assertEqual(
            get_state_machine_arn(back_slash_sf_log_message),
            "arn:aws:states:sa-east-1:425362996713:stateMachine:my-Various-States",
        )


if __name__ == "__main__":
    unittest.main()
