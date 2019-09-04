from log_forwarder import app
from moto import mock_s3
from unittest.mock import MagicMock
import pytest
import boto3

# TODO: Add actual tests

@mock_s3
def test_log_forward():
    # create a client with fake credentials
    client = boto3.client(
        's3',
        region_name='us-east-1',
        aws_access_key_id='foo',
        aws_secret_access_key='bar'
    )

    # mock the script's client with the fake one just created
    app.s3_client = MagicMock(return_value=client)
    assert 1 == 1

