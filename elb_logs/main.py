''' FIXME: Documentation on what this function does, and how to configure it
'''

import json
from base64 import b64decode
import datetime
import time

import boto3
s3 = boto3.resource('s3')

from datadog import initialize, ThreadStats

# retrieve datadog options from KMS
ENCRYPTED_EXPECTED_TOKEN = "<kmsEncryptedToken>"  # Enter the base-64 encoded, encrypted Datadog token (CiphertextBlob)
kms = boto3.client('kms')
datadog_keys = kms.decrypt(CiphertextBlob=b64decode(KMS_ENCRYPTED_KEYS))['Plaintext']
initialize(**json.loads(datadog_keys))

stats = ThreadStats()
stats.start(flush_in_thread=False)

print 'Lambda function initialized, ready to send metrics'


def _process_elb_log_line(log_line, base_tags):
    if not log_line.strip():
        return
    split_line = log_line.split(' ', 11)
    ts = split_line[0]
    ts = time.mktime(datetime.datetime.strptime(ts, "%Y-%m-%dT%H:%M:%S.%fZ").timetuple())
    elb = split_line[1]
    # _client_ip, _client_port = split_line[2].split(':')
    backend_ip, backend_port = split_line[3].split(':')
    request_processing_time = float(split_line[4])
    backend_processing_time = float(split_line[5])
    response_processing_time = float(split_line[6])
    elb_status_code = split_line[7]
    backend_status_code = split_line[8]
    received_bytes = int(split_line[9])
    sent_bytes = int(split_line[10])

    tags = base_tags + [
        'name:%s' % elb,
        'backend_ip:%s' % backend_ip,
        'backend_port:%s' % backend_port,
        'name:%s' % elb,
        'status_code:%s' % elb_status_code,
        'backend_status_code:%s' % backend_status_code,
    ]

    stats.histogram('aws.elb.request_processing_time', request_processing_time, timestamp=ts, tags=tags)
    stats.histogram('aws.elb.backend_processing_time', backend_processing_time, timestamp=ts, tags=tags)
    stats.histogram('aws.elb.response_processing_time', response_processing_time, timestamp=ts, tags=tags)
    stats.histogram('aws.elb.received_bytes', received_bytes, timestamp=ts, tags=tags)
    stats.histogram('aws.elb.sent_bytes', sent_bytes, timestamp=ts, tags=tags)


def send_metric(event, context):
    """
    """
    base_tags = [
        # 'account:%s' % event['owner'],  # FIXME
    ]

    for record in event['Records']:
        bucket_name = record['s3']['bucket']['name']
        key = record['s3']['object']['key']
        print bucket_name, key
        s3_object = s3.Object(bucket_name=bucket_name, key=key)
        content = s3_object.get()["Body"].read()
        log_lines_processed = 0
        for log_line in content.split('\n'):
            _process_elb_log_line(log_line, base_tags)
            log_lines_processed += 1
        print 'processed %s log lines' % log_lines_processed

    stats.flush()
    return {'Status': 'OK'}
