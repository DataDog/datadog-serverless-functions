import base64
import gzip
import json
import os
import pprint
import unittest

from io import BufferedReader, BytesIO
from mock import Mock, patch

os.environ['DD_TEST_ONLY'] = "true"
import lambda_function

tags_response = {
    'ResponseMetadata': {
        'RetryAttempts': 0,
        'HTTPStatusCode': 200,
        'RequestId': 'dummy',
        'HTTPHeaders': {
            'x-amzn-requestid': 'dummy',
            'date': 'Mon, 12 Aug 2019 12:17:27 GMT',
            'content-length': '0',
            'content-type': 'application/x-amz-json-1.1'
        }
    },
    u'tags': {
        u'dd-tag-env': u'myapi:staging',
        u'dd-tag-mytag': u'someval',
        u'aws-tag-costcenter': u'department'
    }
}

test_awslogs_data = {
    u'logStream': u'testLogStream',
    u'messageType': u'DATA_MESSAGE',
    u'logEvents': [
        {
            u'timestamp': 1440442987000,
            u'message': u'[ERROR] First test message',
            u'id': u'eventId1'
        }, {
            u'timestamp': 1440442987001,
            u'message': u'[ERROR] Second test message',
            u'id': u'eventId2'
        }
    ],
    u'owner': u'123456789123',
    u'subscriptionFilters': [u'testFilter'],
    u'logGroup': u'testLogGroup'
}

def test_awslogs_event(data):
    return {
        'awslogs': {
            'data': data
        }
    }

def encode_awslogs_data(data):
    out = BytesIO()
    with gzip.GzipFile(fileobj=out, mode="w") as f:
        f.write(json.dumps(data))
    return base64.b64encode(out.getvalue())

def decode_awslogs_data(data):
    with gzip.GzipFile(fileobj=BytesIO(base64.b64decode(data))) as f:
        # Reading line by line avoid a bug where gzip would take a very long
        # time (>5min) for file around 60MB gzipped
        json_str = b"".join(BufferedReader(f))
    return json.loads(json_str)

class TestParser(unittest.TestCase):
    @patch('boto3.client')
    def test_parse_awslogs(self, boto3_client):
        logs_client = Mock()
        logs_client.list_tags_log_group.return_value = tags_response
        boto3_client.return_value = logs_client

        event = test_awslogs_event(encode_awslogs_data(test_awslogs_data))

        context = Mock()
        function_arn = 'arn:aws:lambda:eu-middle-1:012345678910:function:serverlessrepo-Datadog-Log-For-loglambdaddfunction'
        context.invoked_function_arn = function_arn

        parsed = lambda_function.parse(event, context)

        self.assertEqual(len(parsed), 2)

        actual = parsed[0]
        logs_client.list_tags_log_group.assert_called_once()
        ddtags = actual["ddtags"].split(",")
        self.assertTrue(len(ddtags) >= 2)
        self.assertTrue("env:myapi:staging" in ddtags)
        self.assertTrue("mytag:someval" in ddtags)

    @patch('boto3.client')
    def test_parse_awslogs_list_tags_log_group_exception(self, boto3_client):
        logs_client = Mock()
        logs_client.list_tags_log_group.side_effect = Exception("Something went wrong")
        boto3_client.return_value = logs_client

        event = test_awslogs_event(encode_awslogs_data(test_awslogs_data))

        context = Mock()
        function_arn = 'arn:aws:lambda:eu-middle-1:012345678910:function:serverlessrepo-Datadog-Log-For-loglambdaddfunction'
        context.invoked_function_arn = function_arn

        parsed = lambda_function.parse(event, context)

        self.assertEqual(len(parsed), 2)

        actual = parsed[0]
        logs_client.list_tags_log_group.assert_called_once()
        ddtags = actual["ddtags"].split(",")
        self.assertFalse("env:myapi:staging" in ddtags)
        self.assertFalse("mytag:someval" in ddtags)





