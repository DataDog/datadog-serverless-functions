'''
This function processes a RDS enhanced monitoring DATA_MESSAGE, coming from CloudWatch Logs

Follow these steps to encrypt your Datadog api keys for use in this function:

  1. Create a KMS key - http://docs.aws.amazon.com/kms/latest/developerguide/create-keys.html.

  2. Encrypt the token using the AWS CLI.
     $ aws kms encrypt --key-id alias/<KMS key name> --plaintext '{"api_key":"<dd_api_key>", "app_key":"<dd_app_key>"}'

  3. Copy the base-64 encoded, encrypted key (CiphertextBlob) to the KMS_ENCRYPTED_KEYS variable.

  4. Give your function's role permission for the kms:Decrypt action.
     Example:
       {
         "Version": "2012-10-17",
         "Statement": [
           {
             "Effect": "Allow",
             "Action": [
               "kms:Decrypt"
             ],
             "Resource": [
               "<your KMS key ARN>"
             ]
           }
         ]
       }
'''

import gzip
import json
import re
from StringIO import StringIO
from base64 import b64decode

import boto3

from datadog import initialize, ThreadStats

# retrieve datadog options from KMS
KMS_ENCRYPTED_KEYS = "<KMS_ENCRYPTED_KEYS>"  # Enter the base-64 encoded, encrypted Datadog token (CiphertextBlob)
kms = boto3.client('kms')
datadog_keys = kms.decrypt(CiphertextBlob=b64decode(KMS_ENCRYPTED_KEYS))['Plaintext']
initialize(**json.loads(datadog_keys))

stats = ThreadStats()
stats.start(flush_in_thread=False)

print 'Lambda function initialized, ready to send metrics'


def _process_rds_enhanced_monitoring_message(base_tags, ts, message):
    engine = message["engine"]
    instance_id = message["instanceID"]

    tags = [
        'engine:%s' % engine,
        'dbinstanceidentifier:%s' % instance_id,
    ] + base_tags

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
        'dd.aws.rds.uptime', uptime, timestamp=ts, tags=tags
    )

    stats.gauge(
        'dd.aws.rds.virtual_cpus', message["numVCPUs"], timestamp=ts, tags=tags
    )

    stats.gauge(
        'dd.aws.rds.load.1', message["loadAverageMinute"]["one"],
        timestamp=ts, tags=tags
    )
    stats.gauge(
        'dd.aws.rds.load.5', message["loadAverageMinute"]["five"],
        timestamp=ts, tags=tags
    )
    stats.gauge(
        'dd.aws.rds.load.15', message["loadAverageMinute"]["fifteen"],
        timestamp=ts, tags=tags
    )

    for namespace in ["cpuUtilization", "memory", "tasks", "swap"]:
        for key, value in message[namespace].iteritems():
            stats.gauge(
                'dd.aws.rds.%s.%s' % (namespace.lower(), key), value,
                timestamp=ts, tags=tags
            )

    for network_stats in message["network"]:
        network_tag = ["interface:%s" % network_stats.pop("interface")]
        for key, value in network_stats.iteritems():
            stats.gauge(
                'dd.aws.rds.network.%s' % key, value,
                timestamp=ts, tags=tags + network_tag
            )

    disk_stats = message["diskIO"][0]  # we never expect to have more than one disk
    for key, value in disk_stats.iteritems():
        stats.gauge(
            'dd.aws.rds.diskio.%s' % key, value,
            timestamp=ts, tags=tags
        )

    for fs_stats in message["fileSys"]:
        fs_tag = [
            "name:%s" % fs_stats.pop("name"),
            "mountPoint:%s" % fs_stats.pop("mountPoint")
        ]
        for key, value in fs_stats.iteritems():
            stats.gauge(
                'dd.aws.rds.filesystem.%s' % key, value,
                timestamp=ts, tags=tags + fs_tag
            )

    for process_stats in message["processList"]:
        process_tag = [
            "name:%s" % process_stats.pop("name"),
            "id:%s" % process_stats.pop("id")
        ]
        for key, value in process_stats.iteritems():
            stats.gauge(
                'dd.aws.rds.process.%s' % key, value,
                timestamp=ts, tags=tags + process_tag
            )


def send_metric(event, context):
    """ Process a RDS enhenced monitoring DATA_MESSAGE,
        coming from CLOUDWATCH LOGS
    """

    # event is a dict containing a base64 string gzipped
    event = event['awslogs']['data']
    event = json.loads(
        gzip.GzipFile(fileobj=StringIO(event.decode('base64'))).read()
    )

    base_tags = [
        'account:%s' % event['owner'],
        'function_name:%s' % context.function_name,
        'function_version:%s' % context.function_version,
    ]

    for log_event in event['logEvents']:
        message = json.loads(log_event['message'])
        ts = log_event['timestamp'] / 1000
        _process_rds_enhanced_monitoring_message(base_tags, ts, message)

    stats.flush()
    return {'Status': 'OK'}
