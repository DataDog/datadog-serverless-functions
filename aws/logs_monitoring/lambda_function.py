# Unless explicitly stated otherwise all files in this repository are licensed
# under the Apache License Version 2.0.
# This product includes software developed at Datadog (https://www.datadoghq.com/).
# Copyright 2018 Datadog, Inc.

from __future__ import print_function

import base64
import gzip
import json
import os
import re
import socket
import ssl
import urllib
from io import BytesIO, BufferedReader

import boto3

# Proxy
# Define the proxy endpoint to forward the logs to
DD_SITE = os.getenv("DD_SITE", default="datadoghq.com")
DD_URL = os.getenv("DD_URL", default="lambda-intake.logs." + DD_SITE)

# Define the proxy port to forward the logs to
try:
    if "DD_SITE" in os.environ and DD_SITE == "datadoghq.eu":
        DD_PORT = int(os.environ.get("DD_PORT", 443))
    else:
        DD_PORT = int(os.environ.get("DD_PORT", 10516))
except Exception:
    DD_PORT = 10516

# Scrubbing sensitive data
# Option to redact all pattern that looks like an ip address / email address
try:
    is_ipscrubbing = os.environ["REDACT_IP"]
except Exception:
    is_ipscrubbing = False
try:
    is_emailscrubbing = os.environ["REDACT_EMAIL"]
except Exception:
    is_emailscrubbing = False

# DD_API_KEY: Datadog API Key
DD_API_KEY = "<your_api_key>"
if "DD_KMS_API_KEY" in os.environ:
    ENCRYPTED = os.environ["DD_KMS_API_KEY"]
    DD_API_KEY = boto3.client("kms").decrypt(
        CiphertextBlob=base64.b64decode(ENCRYPTED)
    )["Plaintext"]
elif "DD_API_KEY" in os.environ:
    DD_API_KEY = os.environ["DD_API_KEY"]

# Strip any trailing and leading whitespace from the API key
DD_API_KEY = DD_API_KEY.strip()

cloudtrail_regex = re.compile(
    "\d+_CloudTrail_\w{2}-\w{4,9}-\d_\d{8}T\d{4}Z.+.json.gz$", re.I
)
ip_regex = re.compile("\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}", re.I)
email_regex = re.compile("[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+", re.I)

DD_SOURCE = "ddsource"
DD_CUSTOM_TAGS = "ddtags"
DD_SERVICE = "service"
DD_HOST = "host"
DD_FORWARDER_VERSION = "1.2.3"

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

    def safe_submit_log(self, log, metadata):
        try:
            self.send_entry(log, metadata)
        except Exception as e:
            # retry once
            if self._sock:
                # make sure we don't keep old connections open
                self._sock.close()
            self._sock = self._connect()
            self.send_entry(log, metadata)
        return self

    def send_entry(self, log_entry, metadata):
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
        # Scrub email addresses if activated
        if is_emailscrubbing:
            try:
                str_entry = email_regex.sub("xxxxx@xxxxx.com", str_entry)
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
    # Check if the API key is the correct number of characters
    if len(DD_API_KEY) != 32:
        raise Exception(
            "The API key is not the expected length. Please confirm that your API key is correct"
        )

    metadata = {"ddsourcecategory": "aws"}

    # create socket
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
            "forwarder_version": DD_FORWARDER_VERSION,
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
            logs = generate_logs(event, context, metadata)
            for log in logs:
                con = con.safe_submit_log(log, metadata)
        except Exception as e:
            print("Unexpected exception: {} for event {}".format(str(e), event))


def generate_logs(event, context, metadata):
    try:
        # Route to the corresponding parser
        event_type = parse_event_type(event)
        if event_type == "s3":
            logs = s3_handler(event, context, metadata)
        elif event_type == "awslogs":
            logs = awslogs_handler(event, context, metadata)
        elif event_type == "events":
            logs = cwevent_handler(event, metadata)
        elif event_type == "sns":
            logs = sns_handler(event, metadata)
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
def s3_handler(event, context, metadata):
    s3 = boto3.client("s3")

    # Get the object from the event and show its content type
    bucket = event["Records"][0]["s3"]["bucket"]["name"]
    key = urllib.unquote_plus(event["Records"][0]["s3"]["object"]["key"]).decode("utf8")

    source = parse_event_source(event, key)
    metadata[DD_SOURCE] = source
    ##default service to source value
    metadata[DD_SERVICE] = source
    ##Get the ARN of the service and set it as the hostname
    hostname = parse_service_arn(source, key, bucket, context)
    if hostname:
        metadata[DD_HOST] = hostname

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
def awslogs_handler(event, context, metadata):
    # Get logs
    with gzip.GzipFile(
        fileobj=BytesIO(base64.b64decode(event["awslogs"]["data"]))
    ) as decompress_stream:
        # Reading line by line avoid a bug where gzip would take a very long
        # time (>5min) for file around 60MB gzipped
        data = "".join(BufferedReader(decompress_stream))
    logs = json.loads(str(data))

    # Set the source on the logs
    source = logs.get("logGroup", "cloudwatch")
    metadata[DD_SOURCE] = parse_event_source(event, source)

    # Default service to source value
    metadata[DD_SERVICE] = metadata[DD_SOURCE]

    # Build aws attributes
    aws_attributes = {
        "aws": {
            "awslogs": {
                "logGroup": logs["logGroup"],
                "logStream": logs["logStream"],
                "owner": logs["owner"],
            }
        }
    }

    # For Lambda logs we want to extract the function name,
    # then rebuild the arn of the monitored lambda using that name.
    # Start by splitting the log group to get the function name
    if metadata[DD_SOURCE] == "lambda":
        log_group_parts = logs["logGroup"].split("/lambda/")
        if len(log_group_parts) > 0:
            function_name = log_group_parts[1].lower()
            # Split the arn of the forwarder to extract the prefix
            arn_parts = context.invoked_function_arn.split("function:")
            if len(arn_parts) > 0:
                arn_prefix = arn_parts[0]
                # Rebuild the arn by replacing the function name
                arn = arn_prefix + "function:" + function_name
                # Add the arn as a log attribute
                arn_attributes = {"lambda": {"arn": arn}}
                aws_attributes = merge_dicts(aws_attributes, arn_attributes)
                # Add the function name as tag
                metadata[DD_CUSTOM_TAGS] += ",functionname:" + function_name
                # Set the arn as the hostname
                metadata[DD_HOST] = arn

    # Create and send structured logs to Datadog
    for log in logs["logEvents"]:
        yield merge_dicts(log, aws_attributes)


# Handle Cloudwatch Events
def cwevent_handler(event, metadata):

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
def sns_handler(event, metadata):

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
    if "elasticloadbalancing" in key:
        return "elb"
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
        "waf",
        "docdb",
    ]:
        if source in key:
            return source
    if "API-Gateway" in key:
        return "apigateway"
    if is_cloudtrail(str(key)):
        return "cloudtrail"
    if "awslogs" in event:
        return "cloudwatch"
    if "Records" in event and len(event["Records"]) > 0:
        if "s3" in event["Records"][0]:
            return "s3"
    return "aws"

def parse_service_arn(source, key, bucket, context):
    if source == "elb":
        #For ELB logs we parse the filename to extract parameters in order to rebuild the ARN
        #1. We extract the region from the filename
        #2. We extract the loadbalancer name and replace the "." by "/" to match the ARN format
        #3. We extract the id of the loadbalancer
        #4. We build the arn
        keysplit = key.split("_")
        idsplit = key.split("/")
        if len(keysplit) > 3:
            region = keysplit[2].lower()
            name = keysplit[3]
            elbname = name.replace(".", "/")
            if len(idsplit) > 1:
                idvalue = idsplit[1]
                return "arn:aws:elasticloadbalancing:" + region + ":" + idvalue + ":loadbalancer/" + elbname
    if source == "s3":
        #For S3 access logs we use the bucket name to rebuild the arn
        if bucket:
            return "arn:aws:s3:::" + bucket
    if source == "cloudfront":
        #For Cloudfront logs we need to get the account and distribution id from the lambda arn and the filename
        #1. We extract the cloudfront id  from the filename
        #2. We extract the AWS account id from the lambda arn
        #3. We build the arn
        namesplit = key.split("/")
        if len(namesplit) > 0:
            filename = namesplit[len(namesplit)-1] 
            #(distribution-ID.YYYY-MM-DD-HH.unique-ID.gz)
            filenamesplit = filename.split(".")
            if len(filenamesplit) > 3:
                distributionID = filenamesplit[len(filenamesplit)-4].lower()
                arn = context.invoked_function_arn
                arnsplit = arn.split(":")
                if len(arnsplit) == 7:
                    awsaccountID = arnsplit[4].lower()
                    return "arn:aws:cloudfront::" + awsaccountID+":distribution/" + distributionID
    if source == "redshift":
        #For redshift logs we leverage the filename to extract the relevant information
        #1. We extract the region from the filename
        #2. We extract the account-id from the filename
        #3. We extract the name of the cluster
        #4. We build the arn: arn:aws:redshift:region:account-id:cluster:cluster-name
        namesplit = key.split("/")
        if len(namesplit) == 8:
            region = namesplit[3].lower()
            accountID = namesplit[1].lower()
            filename = namesplit[7]
            filesplit = filename.split("_")
            if len(filesplit) == 6:
                clustername = filesplit[3]
                return "arn:aws:redshift:" + region + ":" + accountID + ":cluster:" + clustername
    return
