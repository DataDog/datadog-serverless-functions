import copy
import gzip
import io
import json
import os
import sys
import unittest
from unittest.mock import MagicMock, patch

import lambda_function
from caching.cache_layer import CacheLayer
from steps.parsing import parse

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
env_patch.stop()


class Context:
    function_version = "$LATEST"
    invoked_function_arn = "invoked_function_arn"
    function_name = "function_name"
    memory_limit_in_mb = "10"


test_data = {
    "Records": [
        {
            "eventVersion": "1.08",
            "userIdentity": {
                "type": "AssumedRole",
                "principalId": "AROAYYB64AB3HGPQO2EPR:DatadogAWSIntegration",
                "arn": (
                    "arn:aws:sts::601427279990:assumed-role/Siti_DatadogAWSIntegrationRole/i-08014e4f62ccf762d"
                ),
                "accountId": "601427279990",
                "accessKeyId": "ASIAYYB64AB3DWOY7JNT",
                "sessionContext": {
                    "sessionIssuer": {
                        "type": "Role",
                        "principalId": "AROAYYB64AB3HGPQO2EPR",
                        "arn": (
                            "arn:aws:iam::601427279990:role/Siti_DatadogAWSIntegrationRole"
                        ),
                        "accountId": "601427279990",
                        "userName": "Siti_DatadogAWSIntegrationRole",
                    },
                    "attributes": {
                        "creationDate": "2021-05-02T23:49:01Z",
                        "mfaAuthenticated": "false",
                    },
                },
            },
            "eventTime": "2021-05-02T23:53:28Z",
            "eventSource": "dynamodb.amazonaws.com",
            "eventName": "DescribeTable",
            "awsRegion": "us-east-1",
            "sourceIPAddress": "54.162.201.161",
            "userAgent": "Datadog",
            "requestParameters": {"tableName": "KinesisClientLibraryLocal"},
            "responseElements": None,
            "requestID": "A9K7562IBO4MPDQE4O5G9QETRFVV4KQNSO5AEMVJF66Q9ASUAAJG",
            "eventID": "a5dd11f9-f616-4ea8-8030-0b3eef554352",
            "readOnly": True,
            "resources": [
                {
                    "accountId": "601427279990",
                    "type": "AWS::DynamoDB::Table",
                    "ARN": (
                        "arn:aws:dynamodb:us-east-1:601427279990:table/KinesisClientLibraryLocal"
                    ),
                }
            ],
            "eventType": "AwsApiCall",
            "apiVersion": "2012-08-10",
            "managementEvent": True,
            "recipientAccountId": "601427279990",
            "eventCategory": "Management",
        }
    ]
}


class TestS3CloudwatchParsing(unittest.TestCase):
    def setUp(self):
        self.maxDiff = 9000

    def get_test_data_gzipped(self) -> io.BytesIO:
        return io.BytesIO(
            gzip.compress(json.dumps(copy.deepcopy(test_data)).encode("utf-8"))
        )

    @patch("caching.cloudwatch_log_group_cache.CloudwatchLogGroupTagsCache.__init__")
    @patch("caching.base_tags_cache.boto3")
    @patch("steps.handlers.s3_handler.boto3")
    @patch("lambda_function.boto3")
    def test_s3_cloudtrail_pasing_and_enrichment(
        self, lambda_boto3, parsing_boto3, cache_boto3, mock_cache_init
    ):
        context = Context()
        boto3 = parsing_boto3.client()
        boto3.get_object.return_value = {"Body": self.get_test_data_gzipped()}

        payload = {
            "s3": {
                "bucket": {
                    "name": "test-bucket",
                },
                "object": {
                    "key": (
                        "601427279990_CloudTrail_us-east-1_20210503T0000Z_QrttGEk4ZcBTLwj5.json.gz"
                    )
                },
            }
        }
        mock_cache_init.return_value = None
        cache_layer = CacheLayer("")
        cache_layer._s3_tags_cache.get = MagicMock(return_value=[])
        cache_layer._lambda_cache.get = MagicMock(return_value=[])

        result = parse({"Records": [payload]}, context, cache_layer)

        expected = copy.deepcopy([test_data["Records"][0]])
        expected[0].update(
            {
                "ddsource": "cloudtrail",
                "ddsourcecategory": "aws",
                "service": "cloudtrail",
                "aws": {
                    "s3": {
                        "bucket": payload["s3"]["bucket"]["name"],
                        "key": payload["s3"]["object"]["key"],
                    },
                    "invoked_function_arn": context.invoked_function_arn,
                },
            }
        )

        # yeah, there are tags, but we don't care to compare them
        result[0].pop("ddtags")

        # expected parsed result, now testing enrichment
        self.assertEqual(expected[0], result[0])

        expected[0]["host"] = "i-08014e4f62ccf762d"
        self.assertEqual(expected[0], lambda_function.enrich(result, cache_layer)[0])


if __name__ == "__main__":
    unittest.main()
