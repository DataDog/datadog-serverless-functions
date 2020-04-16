# Unless explicitly stated otherwise all files in this repository are licensed
# under the Apache License Version 2.0.
# This product includes software developed at Datadog (https://www.datadoghq.com/).
# Copyright 2019 Datadog, Inc.
from datadog_lambda.wrapper import datadog_lambda_wrapper
from datadog_lambda.metric import lambda_stats
import gzip
import json
import os
import re
import base64
import logging
from io import BufferedReader, BytesIO

log = logging.getLogger()
log.setLevel(logging.getLevelName(
    os.environ.get("DD_LOG_LEVEL", "INFO").upper()))


def _lambda_distribution_metric(name, value, timestamp, tags, host):
    # Some rds metrics give non-numeric values and datadog doesn't handle those
    if type(value) != str:
        lambda_stats.distribution(
            name, value, timestamp=timestamp, tags=tags, host=host
        )

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

    _lambda_distribution_metric(
        'aws.rds.uptime', uptime, timestamp=ts, tags=tags, host=host_id
    )

    _lambda_distribution_metric(
        'aws.rds.virtual_cpus', message["numVCPUs"], timestamp=ts, tags=tags, host=host_id
    )

    if "loadAverageMinute" in message:
        _lambda_distribution_metric(
            'aws.rds.load.1', message["loadAverageMinute"]["one"],
            timestamp=ts, tags=tags, host=host_id
        )
        _lambda_distribution_metric(
            'aws.rds.load.5', message["loadAverageMinute"]["five"],
            timestamp=ts, tags=tags, host=host_id
        )
        _lambda_distribution_metric(
            'aws.rds.load.15', message["loadAverageMinute"]["fifteen"],
            timestamp=ts, tags=tags, host=host_id
        )

    for namespace in ["cpuUtilization", "memory", "tasks", "swap"]:
        for key, value in message.get(namespace, {}).items():
            _lambda_distribution_metric(
                'aws.rds.%s.%s' % (namespace.lower(), key), value,
                timestamp=ts, tags=tags, host=host_id
            )
            

    for network_stats in message.get("network", []):
        if "interface" in network_stats:
            network_tag = ["interface:%s" % network_stats.pop("interface")]
        else:
            network_tag = []
        for key, value in network_stats.items():
            _lambda_distribution_metric(
                'aws.rds.network.%s' % key, value,
                timestamp=ts, tags=tags + network_tag, host=host_id
            )
    

    disk_stats = message.get("diskIO", [{}])[0]  # we never expect to have more than one disk
    for key, value in disk_stats.items():
        _lambda_distribution_metric(
            'aws.rds.diskio.%s' % key, value,
            timestamp=ts, tags=tags, host=host_id
        )
        

    for fs_stats in message.get("fileSys", []):
        fs_tag = []
        for tag_key in ["name", "mountPoint"]:
            if tag_key in fs_stats:
                fs_tag.append("%s:%s" % (tag_key, fs_stats.pop(tag_key)))
        for key, value in fs_stats.items():
            _lambda_distribution_metric(
                'aws.rds.filesystem.%s' % key, value,
                timestamp=ts, tags=tags + fs_tag, host=host_id
            )
            

    for process_stats in message.get("processList", []):
        process_tag = []
        for tag_key in ["name", "id"]:
            if tag_key in process_stats:
                process_tag.append("%s:%s" % (tag_key, process_stats.pop(tag_key)))
        for key, value in process_stats.items():
            _lambda_distribution_metric(
                'aws.rds.process.%s' % key, value,
                timestamp=ts, tags=tags + process_tag, host=host_id
            )
            


@datadog_lambda_wrapper
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

    return {'Status': 'OK'}
