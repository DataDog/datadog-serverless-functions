# Unless explicitly stated otherwise all files in this repository are licensed
# under the Apache License Version 2.0.
# This product includes software developed at Datadog (https://www.datadoghq.com/).
# Copyright 2017 Datadog, Inc.

from __future__ import print_function

import base64
import json
import urllib
import boto3
import time
import os
import socket
import ssl
import re
import zlib

# Parameters
# ddApiKey: Datadog API Key
ddApiKey = "<your_api_key>"
try:
    ddApiKey = os.environ['DD_API_KEY']
except Exception:
    pass


# metadata: Additional metadata to send with the logs
metadata = {
    "aws": {
        "type": "s3_logs"
    },
    "ddsourcecategory": "aws",
}


host = "intake.logs.datadoghq.com"
ssl_port = 10516
cloudtrail_regex = re.compile('\d+_CloudTrail_\w{2}-\w{4,9}-\d_\d{8}T\d{4}Z.+.json.gz$', re.I)


DD_SOURCE = "ddsource"

def lambda_handler(event, context):
    # Check prerequisites
    if ddApiKey == "<your_api_key>" or ddApiKey == "":
        raise Exception(
            "You must configure your API key before starting this lambda function (see #Parameters section)"
        )

    # Attach Datadog's Socket
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

    port = ssl_port
    s = ssl.wrap_socket(s)
    s.connect((host, port))

    # Add the context to meta
    if "aws" not in metadata:
        metadata["aws"] = {}
    aws_meta = metadata["aws"]
    aws_meta["function_name"] = context.function_name
    aws_meta["function_version"] = context.function_version
    aws_meta["invoked_function_arn"] = context.invoked_function_arn
    aws_meta["memory_limit_in_mb"] = context.memory_limit_in_mb


    try:
        # Route to the corresponding parser
        event_type = parse_event_type(event)

        if event_type == "s3":
            logs = s3_handler(s, event)

        elif event_type == "awslogs":
            logs = awslogs_handler(s, event)

        for log in logs:
            send_entry(s, log)

    except Exception as e:
        # Logs through the socket the error
        err_message = 'Error parsing the object. Exception: {}'.format(str(e))
        send_entry(s, err_message)
        raise e
    finally:
        s.close()


# Utility functions

def parse_event_type(event):
    if "Records" in event and len(event["Records"]) > 0:
        if "s3" in event["Records"][0]:
            return "s3"

    elif "awslogs" in event:
        return "awslogs"

    raise Exception("Event type not supported (see #Event supported section)")


# Handle S3 events
def s3_handler(s, event):
    s3 = boto3.client('s3')

    # Get the object from the event and show its content type
    bucket = event['Records'][0]['s3']['bucket']['name']
    key = urllib.unquote_plus(event['Records'][0]['s3']['object']['key']).decode('utf8')

    metadata[DD_SOURCE] = parse_event_source(event, key)

    # Extract the S3 object
    response = s3.get_object(Bucket=bucket, Key=key)
    body = response['Body']
    data = body.read()

    structured_logs = []

    # If the name has a .gz extension, then decompress the data
    if key[-3:] == '.gz':
        data = zlib.decompress(data, 16 + zlib.MAX_WBITS)

    if is_cloudtrail(str(key)):
        cloud_trail = json.loads(data)
        for event in cloud_trail['Records']:
            # Create structured object and send it
            structured_line = merge_dicts(event, {"aws": {"s3": {"bucket": bucket, "key": key}}})
            structured_logs.append(structured_line)
    else:
        # Send lines to Datadog
        for line in data.splitlines():
            # Create structured object and send it
            structured_line = {"aws": {"s3": {"bucket": bucket, "key": key}}, "message": line}
            structured_logs.append(structured_line)

    return structured_logs


# Handle CloudWatch events and logs
def awslogs_handler(s, event):
    # Get logs
    data = zlib.decompress(base64.b64decode(event["awslogs"]["data"]), 16 + zlib.MAX_WBITS)
    logs = json.loads(str(data))
    metadata[DD_SOURCE] = "cloudwatch"


    structured_logs = []

    # Send lines to Datadog
    for log in logs["logEvents"]:
        # Create structured object and send it
        structured_line = merge_dicts(log, {
            "aws": {
                "awslogs": {
                    "logGroup": logs["logGroup"],
                    "logStream": logs["logStream"],
                    "owner": logs["owner"]
                }
            }
        })
        structured_logs.append(structured_line)

    return structured_logs


def send_entry(s, log_entry):
    # The log_entry can only be a string or a dict
    if isinstance(log_entry, str):
        log_entry = {"message": log_entry}
    elif not isinstance(log_entry, dict):
        raise Exception(
            "Cannot send the entry as it must be either a string or a dict. Provided entry: " + str(log_entry)
        )

    # Merge with metadata
    log_entry = merge_dicts(log_entry, metadata)

    # Send to Datadog
    str_entry = json.dumps(log_entry)
    print(str_entry)
    prefix = "%s " % ddApiKey
    return s.send((prefix + str_entry + "\n").encode("UTF-8"))


def merge_dicts(a, b, path=None):
    if path is None:
        path = []
    for key in b:
        if key in a:
            if isinstance(a[key], dict) and isinstance(b[key], dict):
                merge_dicts(a[key], b[key], path + [str(key)])
            elif a[key] == b[key]:
                pass  # same leaf value
            else:
                raise Exception(
                    'Conflict while merging metadatas and the log entry at %s' % '.'.join(path + [str(key)])
                )
        else:
            a[key] = b[key]
    return a


def is_cloudtrail(key):
    match = cloudtrail_regex.search(key)
    return bool(match)

def parse_event_source(event, key):
    if "lambda" in event:
        return "lambda"
    if is_cloudtrail(str(key)):
        return "cloudtrail"
    if "elasticloadbalancing" in key:
        return "elb"
    if "redshift" in key:
        return "redshift"
    if "cloudfront" in key:
        return "cloudfront"
    if "s3" in event:
        return "s3"
    return "aws"
