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
import StringIO
import gzip
from base64 import b64decode

# Parameters
# ddApiKey: Datadog API Key
ddApiKey = "<your_api_key>"
try:
    ENCRYPTED = os.environ['DD_KMS_API_KEY']
    ddApiKey = boto3.client('kms').decrypt(CiphertextBlob=b64decode(ENCRYPTED))['Plaintext']
except Exception:
    try:
        ddApiKey = os.environ['DD_API_KEY']
    except Exception:
        pass

# metadata: Additional metadata to send with the logs
metadata = {
    "ddsourcecategory": "aws",
}

#Proxy
#Define the proxy endpoint to forward the logs to
host = os.getenv("DD_URL", default="lambda-intake.logs.datadoghq.com")

#Define the proxy port to forward the logs to 
try:
    ssl_port = os.environ['DD_PORT']
except Exception:
    ssl_port = 10516

#Scrubbing sensitive data
#Option to redact all pattern that looks like an ip address    
try:
    is_ipscrubbing = os.environ['REDACT_IP']
except Exception:
    is_ipscrubbing = False

# Pass custom tags as environment variable, ensure comma separated, no trailing comma in envvar!
DD_TAGS = ""
try:
    DD_TAGS = os.environ['DD_TAGS'] + ","
except Exception:
    pass

cloudtrail_regex = re.compile('\d+_CloudTrail_\w{2}-\w{4,9}-\d_\d{8}T\d{4}Z.+.json.gz$', re.I)
DD_SOURCE = "ddsource"
DD_CUSTOM_TAGS = "ddtags"
DD_SERVICE = "service"

def lambda_handler(event, context):
    # Check prerequisites
    if ddApiKey == "<your_api_key>" or ddApiKey == "":
        raise Exception(
            "You must configure your API key before starting this lambda function (see #Parameters section)"
        )

    # Attach Datadog's Socket
    s = connect_to_datadog(host, ssl_port)

    # Add the context to meta
    if "aws" not in metadata:
        metadata["aws"] = {}
    aws_meta = metadata["aws"]
    aws_meta["function_version"] = context.function_version
    aws_meta["invoked_function_arn"] = context.invoked_function_arn
    #Add custom tags here by adding new value with the following format "key1:value1, key2:value2"  - might be subject to modifications
    metadata[DD_CUSTOM_TAGS] = DD_TAGS + "forwardername:" + context.function_name.lower() + ",memorysize:" + context.memory_limit_in_mb

    try:
        logs = generate_logs(event,context)
        for log in logs:
            s = safe_submit_log(s, log)
    except Exception as e:
        print('Unexpected exception: {} for event {}'.format(str(e), event))
    finally:
        s.close()

def connect_to_datadog(host, port):
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s = ssl.wrap_socket(s)
    s.connect((host, port))
    return s

def generate_logs(event,context):
    try:
        # Route to the corresponding parser
        event_type = parse_event_type(event)
        if event_type == "s3":
            logs = s3_handler(event)
        elif event_type == "awslogs":
            logs = awslogs_handler(event,context)
        elif event_type == "events":
            logs = cwevent_handler(event)
        elif event_type == "sns":
            logs = sns_handler(event)
    except Exception as e:
        # Logs through the socket the error
        err_message = 'Error parsing the object. Exception: {} for event {}'.format(str(e), event)
        logs = [err_message]
    return logs

def safe_submit_log(s, log):
    try:
        send_entry(s, log)
    except Exception as e:
        # retry once
        s = connect_to_datadog(host, ssl_port)
        send_entry(s, log)
    return s

# Utility functions

def parse_event_type(event):
    if "Records" in event and len(event["Records"]) > 0:
        if "s3" in event["Records"][0]:
            return "s3"
        elif "Sns" in event["Records"][0]:
            return "sns"

    elif "awslogs" in event:
        return "awslogs"

    elif "detail" in event:
        return "events"
    raise Exception("Event type not supported (see #Event supported section)")


# Handle S3 events
def s3_handler(event):
    s3 = boto3.client('s3')

    # Get the object from the event and show its content type
    bucket = event['Records'][0]['s3']['bucket']['name']
    key = urllib.unquote_plus(event['Records'][0]['s3']['object']['key']).decode('utf8')

    metadata[DD_SOURCE] = parse_event_source(event, key)
    ##default service to source value
    metadata[DD_SERVICE] = metadata[DD_SOURCE]
    
    # Extract the S3 object
    response = s3.get_object(Bucket=bucket, Key=key)
    body = response['Body']
    data = body.read()

    structured_logs = []

    # If the name has a .gz extension, then decompress the data
    if key[-3:] == '.gz':
        with gzip.GzipFile(fileobj=StringIO.StringIO(data)) as decompress_stream:
            data = decompress_stream.read()

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


# Handle CloudWatch logs
def awslogs_handler(event,context):
    # Get logs
    with gzip.GzipFile(fileobj=StringIO.StringIO(base64.b64decode(event["awslogs"]["data"]))) as decompress_stream:
        data = decompress_stream.read()
    logs = json.loads(str(data))
    #Set the source on the logs
    source = logs.get("logGroup", "cloudwatch")
    metadata[DD_SOURCE] = parse_event_source(event, source)
    ##default service to source value
    metadata[DD_SERVICE] = metadata[DD_SOURCE]
    
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
        ## For Lambda logs, we want to extract the function name
        ## and we reconstruct the the arn of the monitored lambda
        # 1. we split the log group to get the function name
        if metadata[DD_SOURCE]=="lambda":
            loggroupsplit = logs["logGroup"].split("/lambda/")
            if len(loggroupsplit) > 0:
                functioname = loggroupsplit[1]
                # 2. We split the arn of the forwarder to extract the prefix
                arnsplit = context.invoked_function_arn.split("function:")
                if len(arnsplit) > 0:
                    arn_prefix = arnsplit[0]
                    # 3. We replace the function name in the arn
                    arn = arn_prefix + "function:"+functioname
                    # 4. We add the arn as a log attribute
                    structured_line = merge_dicts(log, {
                     "lambda": {"arn": arn }
                    })
                    # 5. We add the function name as tag
                    metadata[DD_CUSTOM_TAGS] = metadata[DD_CUSTOM_TAGS] +",functionname:"+functioname
        structured_logs.append(structured_line)

    return structured_logs

#Handle Cloudwatch Events
def cwevent_handler(event):

    data = event

    #Set the source on the log
    source = data.get("source", "cloudwatch")
    service = source.split(".")
    if len(service)>1:
        metadata[DD_SOURCE] = service[1]
    else:
        metadata[DD_SOURCE] = "cloudwatch"
    ##default service to source value
    metadata[DD_SERVICE] = metadata[DD_SOURCE]
    
    structured_logs = []
    structured_logs.append(data)

    return structured_logs

# Handle Sns events
def sns_handler(event):

    data = event
    # Set the source on the log
    metadata[DD_SOURCE] = parse_event_source(event, "sns")
    structured_logs = []

    for ev in data['Records']:
        # Create structured object and send it
        structured_line = ev
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
    
    #Scrub ip addresses if activated
    if is_ipscrubbing:
        try:
            str_entry = re.sub('\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}',"xxx.xxx.xxx.xx",str_entry)
        except Exception as e:
            print('Unexpected exception while scrubbing logs: {} for event {}'.format(str(e), str_entry))
            
    #For debugging purpose uncomment the following line
    #print(str_entry)
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
    for source in ["lambda", "redshift", "cloudfront", "kinesis", "mariadb", "mysql", "apigateway", "route53", "vpc", "rds", "sns"]:
        if source in key:
            return source
    if "elasticloadbalancing" in key:
        return "elb"
    if is_cloudtrail(str(key)):
        return "cloudtrail"
    if "awslogs" in event:
        return "cloudwatch"
    if "Records" in event and len(event["Records"]) > 0:
        if "s3" in event["Records"][0]:
            return "s3"
    return "aws"
