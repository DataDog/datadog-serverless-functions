# Unless explicitly stated otherwise all files in this repository are licensed
# under the Apache License Version 2.0.
# This product includes software developed at Datadog (https://www.datadoghq.com/).
# Copyright 2020 Datadog, Inc.
import gzip
import json
import os
import re
import time
import base64
from io import BufferedReader, BytesIO
from urllib.request import Request, urlopen
from urllib.parse import urlencode

import botocore
import boto3


DD_SITE = os.getenv('DD_SITE', default='datadoghq.com')


def _datadog_keys():
    if 'kmsEncryptedKeys' in os.environ:
        KMS_ENCRYPTED_KEYS = os.environ['kmsEncryptedKeys']
        kms = boto3.client('kms')
        # kmsEncryptedKeys should be created through the Lambda's encryption
        # helpers and as such will have the EncryptionContext
        return json.loads(kms.decrypt(
            CiphertextBlob=base64.b64decode(KMS_ENCRYPTED_KEYS),
            EncryptionContext={'LambdaFunctionName': os.environ['AWS_LAMBDA_FUNCTION_NAME']},
        )['Plaintext'])

    if 'DD_API_KEY_SECRET_ARN' in os.environ:
        SECRET_ARN = os.environ['DD_API_KEY_SECRET_ARN']
        DD_API_KEY = boto3.client('secretsmanager').get_secret_value(SecretId=SECRET_ARN)['SecretString']
        return {'api_key': DD_API_KEY}

    if 'DD_API_KEY_SSM_NAME' in os.environ:
        SECRET_NAME = os.environ['DD_API_KEY_SSM_NAME']
        DD_API_KEY = boto3.client('ssm').get_parameter(
            Name=SECRET_NAME, WithDecryption=True
        )['Parameter']['Value']
        return {'api_key': DD_API_KEY}

    if 'DD_KMS_API_KEY' in os.environ:
        ENCRYPTED = os.environ['DD_KMS_API_KEY']

        # For interop with other DD Lambdas taking in DD_KMS_API_KEY, we'll
        # optionally try the EncryptionContext associated with this Lambda.
        try:
            DD_API_KEY = boto3.client('kms').decrypt(
                CiphertextBlob=base64.b64decode(ENCRYPTED),
                EncryptionContext={'LambdaFunctionName': os.environ['AWS_LAMBDA_FUNCTION_NAME']},
            )['Plaintext']
        except botocore.exceptions.ClientError:
            DD_API_KEY = boto3.client('kms').decrypt(
                CiphertextBlob=base64.b64decode(ENCRYPTED),
            )['Plaintext']

        if type(DD_API_KEY) is bytes:
            DD_API_KEY = DD_API_KEY.decode('utf-8')
        return {'api_key': DD_API_KEY}

    if 'DD_API_KEY' in os.environ:
        DD_API_KEY = os.environ['DD_API_KEY']
        return {'api_key': DD_API_KEY}

    raise ValueError("Datadog API key is not defined, see documentation for environment variable options")


# Preload the keys so we can bail out early if they're misconfigured
datadog_keys = _datadog_keys()
print('INFO Lambda function initialized, ready to send metrics')


def _process_rds_enhanced_monitoring_message(ts, message, account, region):
    instance_id = message["instanceID"]
    host_id = message["instanceResourceID"]
    tags = [
        'dbinstanceidentifier:%s' % instance_id,
        'aws_account:%s' % account,
        'engine:%s' % message["engine"],
    ]

    # metrics generation

    # uptime: "54 days, 1:53:04" to be converted into seconds
    uptime = 0
    uptime_msg = re.split(' days?, ', message["uptime"])  # edge case "1 day 1:53:04"
    if len(uptime_msg) == 2:
        uptime += 24 * 3600 * int(uptime_msg[0])
    uptime_day = uptime_msg[-1].split(':')
    uptime += 3600 * int(uptime_day[0])
    uptime += 60 * int(uptime_day[1])
    uptime += int(uptime_day[2])
    stats.gauge(
        'aws.rds.uptime', uptime, timestamp=ts, tags=tags, host=host_id
    )

    stats.gauge(
        'aws.rds.virtual_cpus', message["numVCPUs"], timestamp=ts, tags=tags, host=host_id
    )

    if "loadAverageMinute" in message:
        stats.gauge(
            'aws.rds.load.1', message["loadAverageMinute"]["one"],
            timestamp=ts, tags=tags, host=host_id
        )
        stats.gauge(
            'aws.rds.load.5', message["loadAverageMinute"]["five"],
            timestamp=ts, tags=tags, host=host_id
        )
        stats.gauge(
            'aws.rds.load.15', message["loadAverageMinute"]["fifteen"],
            timestamp=ts, tags=tags, host=host_id
        )

    for namespace in ["cpuUtilization", "memory", "tasks", "swap"]:
        for key, value in message.get(namespace, {}).items():
            stats.gauge(
                'aws.rds.%s.%s' % (namespace.lower(), key), value,
                timestamp=ts, tags=tags, host=host_id
            )

    for network_stats in message.get("network", []):
        if "interface" in network_stats:
            network_tag = ["interface:%s" % network_stats.pop("interface")]
        else:
            network_tag = []
        for key, value in network_stats.items():
            stats.gauge(
                'aws.rds.network.%s' % key, value,
                timestamp=ts, tags=tags + network_tag, host=host_id
            )

    disk_stats = message.get("diskIO", [{}])[0]  # we never expect to have more than one disk
    for key, value in disk_stats.items():
        stats.gauge(
            'aws.rds.diskio.%s' % key, value,
            timestamp=ts, tags=tags, host=host_id
        )

    for fs_stats in message.get("fileSys", []):
        fs_tag = []
        for tag_key in ["name", "mountPoint"]:
            if tag_key in fs_stats:
                fs_tag.append("%s:%s" % (tag_key, fs_stats.pop(tag_key)))
        for key, value in fs_stats.items():
            stats.gauge(
                'aws.rds.filesystem.%s' % key, value,
                timestamp=ts, tags=tags + fs_tag, host=host_id
            )

    for process_stats in message.get("processList", []):
        process_tag = []
        for tag_key in ["name", "id"]:
            if tag_key in process_stats:
                process_tag.append("%s:%s" % (tag_key, process_stats.pop(tag_key)))
        for key, value in process_stats.items():
            stats.gauge(
                'aws.rds.process.%s' % key, value,
                timestamp=ts, tags=tags + process_tag, host=host_id
            )


def lambda_handler(event, context):
    ''' Process a RDS enhenced monitoring DATA_MESSAGE,
        coming from CLOUDWATCH LOGS
    '''
    # event is a dict containing a base64 string gzipped
    with gzip.GzipFile(
        fileobj=BytesIO(base64.b64decode(event["awslogs"]["data"]))
    ) as decompress_stream:
        data = b"".join(BufferedReader(decompress_stream))

    event = json.loads(data)

    account = event['owner']
    region = context.invoked_function_arn.split(':', 4)[3]

    log_events = event['logEvents']

    for log_event in log_events:
        message = json.loads(log_event['message'])
        ts = log_event['timestamp'] / 1000
        _process_rds_enhanced_monitoring_message(ts, message, account, region)

    stats.flush()
    return {'Status': 'OK'}


# Helpers to send data to Datadog, inspired from https://github.com/DataDog/datadogpy

class Stats(object):

    def __init__(self):
        self.series = []

    def gauge(self, metric, value, timestamp=None, tags=None, host=None):
        base_dict = {
            'metric': metric,
            'points': [(int(timestamp or time.time()), value)],
            'type': 'gauge',
            'tags': tags,
        }
        if host:
            base_dict.update({'host': host})
        self.series.append(base_dict)

    def flush(self):
        metrics_dict = {
            'series': self.series,
        }
        self.series = []

        creds = urlencode(datadog_keys)
        data = json.dumps(metrics_dict).encode('ascii')
        url = '%s?%s' % (datadog_keys.get('api_host', 'https://app.%s/api/v1/series' % DD_SITE), creds)
        req = Request(url, data, {'Content-Type': 'application/json'})
        response = urlopen(req)
        print('INFO Submitted data with status%s' % response.getcode())

stats = Stats()
