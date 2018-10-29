# Unless explicitly stated otherwise all files in this repository are licensed
# under the Apache License Version 2.0.
# This product includes software developed at Datadog (https://www.datadoghq.com/).
# Copyright 2018 Datadog, Inc.

from __future__ import print_function

import base64
import json
import urllib
import os
import socket
import ssl
import re
from io import BytesIO, BufferedReader
import gzip

import boto3

# Parameters
# metadata: Additional metadata to send with the logs
metadata = {"ddsourcecategory": "aws"}


# Proxy
# Define the proxy endpoint to forward the logs to
DD_URL = os.getenv("DD_URL", default="lambda-intake.logs.datadoghq.com")

# Define the proxy port to forward the logs to
DD_PORT = os.environ.get("DD_PORT", 10516)

# Scrubbing sensitive data
# Option to redact all pattern that looks like an ip address
try:
    is_ipscrubbing = os.environ["REDACT_IP"]
except Exception:
    is_ipscrubbing = False

# DD_API_KEY: Datadog API Key
DD_API_KEY = "<your_api_key>"
try:
    if "DD_KMS_API_KEY" in os.environ:
        ENCRYPTED = os.environ["DD_KMS_API_KEY"]
        DD_API_KEY = boto3.client("kms").decrypt(
            CiphertextBlob=base64.b64decode(ENCRYPTED)
        )["Plaintext"]
    elif "DD_API_KEY" in os.environ:
        DD_API_KEY = os.environ["DD_API_KEY"]
except Exception:
    pass

cloudtrail_regex = re.compile(
    "\d+_CloudTrail_\w{2}-\w{4,9}-\d_\d{8}T\d{4}Z.+.json.gz$", re.I
)
ip_regex = re.compile("\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}", re.I)
DD_SOURCE = "ddsource"
DD_CUSTOM_TAGS = "ddtags"
DD_SERVICE = "service"

# Pass custom tags as environment variable, ensure comma separated, no trailing comma in envvar!
DD_TAGS = os.environ.get("DD_TAGS", "")


class DatadogConnection(object):
    def __init__(self, host, port, ddApiKey):
        self.host = host
        self.port = port
        self.api_key = ddApiKey
        self._sock = None

    def _connect(self):
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s = ssl.wrap_socket(s)
        s.connect((self.host, self.port))
        return s

    def safe_submit_log(self, log):
        try:
            self.send_entry(log)
        except Exception as e:
            # retry once
            self._sock = self._connect()
            self.send_entry(log)
        return self

    def send_entry(self, log_entry):
        # The log_entry can only be a string or a dict
        if isinstance(log_entry, str):
            log_entry = {"message": log_entry}
        elif not isinstance(log_entry, dict):
            raise Exception(
                "Cannot send the entry as it must be either a string or a dict. Provided entry: "
                + str(log_entry)
            )

        # Merge with metadata
        log_entry = merge_dicts(log_entry, metadata)

        # Send to Datadog
        str_entry = json.dumps(log_entry)

        # Scrub ip addresses if activated
        if is_ipscrubbing:
            try:
                str_entry = ip_regex.sub("xxx.xxx.xxx.xx", str_entry)
            except Exception as e:
                print(
                    "Unexpected exception while scrubbing logs: {} for event {}".format(
                        str(e), str_entry
                    )
                )

        # For debugging purpose uncomment the following line
        # print(str_entry)
        prefix = "%s " % self.api_key
        return self._sock.send((prefix + str_entry + "\n").encode("UTF-8"))

    def __enter__(self):
        self._sock = self._connect()
        return self

    def __exit__(self, ex_type, ex_value, traceback):
        if self._sock:
            self._sock.close()
        if ex_type is not None:
            print("DatadogConnection exit: ", ex_type, ex_value, traceback)


def lambda_handler(event, context):
    # Check prerequisites
    if DD_API_KEY == "<your_api_key>" or DD_API_KEY == "":
        raise Exception(
            "You must configure your API key before starting this lambda function (see #Parameters section)"
        )

    # crete socket
    with DatadogConnection(DD_URL, DD_PORT, DD_API_KEY) as con:
        # Add the context to meta
        if "aws" not in metadata:
            metadata["aws"] = {}
        aws_meta = metadata["aws"]
        aws_meta["function_version"] = context.function_version
        aws_meta["invoked_function_arn"] = context.invoked_function_arn
        # Add custom tags here by adding new value with the following format "key1:value1, key2:value2"  - might be subject to modifications
        dd_custom_tags_data = {
            "forwardername": context.function_name.lower(),
            "memorysize": context.memory_limit_in_mb,
        }
        metadata[DD_CUSTOM_TAGS] = ",".join(
            filter(
                None,
                [
                    DD_TAGS,
                    ",".join(
                        [
                            "{}:{}".format(k, v)
                            for k, v in dd_custom_tags_data.iteritems()
                        ]
                    ),
                ],
            )
        )

        try:
            logs = generate_logs(event, context)
            for log in logs:
                con = con.safe_submit_log(log)
        except Exception as e:
            print("Unexpected exception: {} for event {}".format(str(e), event))


def generate_logs(event, context):
    try:
        # Route to the corresponding parser
        event_type = parse_event_type(event)
        if event_type == "s3":
            logs = s3_handler(event)
        elif event_type == "awslogs":
            logs = awslogs_handler(event, context)
        elif event_type == "events":
            logs = cwevent_handler(event)
        elif event_type == "sns":
            logs = sns_handler(event)
    except Exception as e:
        # Logs through the socket the error
        err_message = "Error parsing the object. Exception: {} for event {}".format(
            str(e), event
        )
        logs = [err_message]
    return logs


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
    s3 = boto3.client("s3")

    # Get the object from the event and show its content type
    bucket = event["Records"][0]["s3"]["bucket"]["name"]
    key = urllib.unquote_plus(event["Records"][0]["s3"]["object"]["key"]).decode("utf8")

    metadata[DD_SOURCE] = parse_event_source(event, key)
    ##default service to source value
    metadata[DD_SERVICE] = metadata[DD_SOURCE]

    # Extract the S3 object
    response = s3.get_object(Bucket=bucket, Key=key)
    body = response["Body"]
    data = body.read()

    # If the name has a .gz extension, then decompress the data
    if key[-3:] == ".gz":
        with gzip.GzipFile(fileobj=BytesIO(data)) as decompress_stream:
            # Reading line by line avoid a bug where gzip would take a very long time (>5min) for
            # file around 60MB gzipped
            data = "".join(BufferedReader(decompress_stream))

    if is_cloudtrail(str(key)):
        cloud_trail = json.loads(data)
        for event in cloud_trail["Records"]:
            # Create structured object and send it
            structured_line = merge_dicts(
                event, {"aws": {"s3": {"bucket": bucket, "key": key}}}
            )
            yield structured_line
    else:
        # Send lines to Datadog
        for line in data.splitlines():
            # Create structured object and send it
            structured_line = {
                "aws": {"s3": {"bucket": bucket, "key": key}},
                "message": line,
            }
            yield structured_line


# Handle CloudWatch logs
def awslogs_handler(event, context):
    # Get logs
    with gzip.GzipFile(
        fileobj=BytesIO(base64.b64decode(event["awslogs"]["data"]))
    ) as decompress_stream:
        # Reading line by line avoid a bug where gzip would take a very long time (>5min) for
        # file around 60MB gzipped
        data = "".join(BufferedReader(decompress_stream))
    logs = json.loads(str(data))
    # Set the source on the logs
    source = logs.get("logGroup", "cloudwatch")
    metadata[DD_SOURCE] = parse_event_source(event, source)
    ##default service to source value
    metadata[DD_SERVICE] = metadata[DD_SOURCE]

    # Send lines to Datadog
    for log in logs["logEvents"]:
        # Create structured object and send it
        structured_line = merge_dicts(
            log,
            {
                "aws": {
                    "awslogs": {
                        "logGroup": logs["logGroup"],
                        "logStream": logs["logStream"],
                        "owner": logs["owner"],
                    }
                }
            },
        )
        ## For Lambda logs, we want to extract the function name
        ## and we reconstruct the the arn of the monitored lambda
        # 1. we split the log group to get the function name
        if metadata[DD_SOURCE] == "lambda":
            loggroupsplit = logs["logGroup"].split("/lambda/")
            if len(loggroupsplit) > 0:
                functioname = loggroupsplit[1].lower()
                # 2. We split the arn of the forwarder to extract the prefix
                arnsplit = context.invoked_function_arn.split("function:")
                if len(arnsplit) > 0:
                    arn_prefix = arnsplit[0]
                    # 3. We replace the function name in the arn
                    arn = arn_prefix + "function:" + functioname
                    # 4. We add the arn as a log attribute
                    structured_line = merge_dicts(log, {"lambda": {"arn": arn}})
                    # 5. We add the function name as tag
                    metadata[DD_CUSTOM_TAGS] = (
                        metadata[DD_CUSTOM_TAGS] + ",functionname:" + functioname
                    )
        yield structured_line


# Handle Cloudwatch Events
def cwevent_handler(event):

    data = event

    # Set the source on the log
    source = data.get("source", "cloudwatch")
    service = source.split(".")
    if len(service) > 1:
        metadata[DD_SOURCE] = service[1]
    else:
        metadata[DD_SOURCE] = "cloudwatch"
    ##default service to source value
    metadata[DD_SERVICE] = metadata[DD_SOURCE]

    yield data


# Handle Sns events
def sns_handler(event):

    data = event
    # Set the source on the log
    metadata[DD_SOURCE] = parse_event_source(event, "sns")

    for ev in data["Records"]:
        # Create structured object and send it
        structured_line = ev
        yield structured_line


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
                    "Conflict while merging metadatas and the log entry at %s"
                    % ".".join(path + [str(key)])
                )
        else:
            a[key] = b[key]
    return a


def is_cloudtrail(key):
    match = cloudtrail_regex.search(key)
    return bool(match)


def parse_event_source(event, key):
    for source in [
        "lambda",
        "redshift",
        "cloudfront",
        "kinesis",
        "mariadb",
        "mysql",
        "apigateway",
        "route53",
        "vpc",
        "rds",
        "sns",
    ]:
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
