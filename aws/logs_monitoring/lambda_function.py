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
from botocore.vendored import requests
import time
import ssl
import re
from io import BytesIO, BufferedReader
import gzip

import boto3


# Change this value to change the underlying network client (HTTP or TCP),
# by default, use the HTTP client.
DD_USE_TCP = os.getenv("DD_USE_TCP", default="false").lower() == "true"


# Define the destination endpoint to send logs to
DD_SITE = os.getenv("DD_SITE", default="datadoghq.com")
if DD_USE_TCP:
    DD_URL = os.getenv("DD_URL", default="lambda-intake.logs." + DD_SITE)
    try:
        if "DD_SITE" in os.environ and DD_SITE == "datadoghq.eu":
            DD_PORT = int(os.environ.get("DD_PORT", 443))
        else:
            DD_PORT = int(os.environ.get("DD_PORT", 10516))
    except Exception:
        DD_PORT = 10516
else:
    DD_URL = os.getenv("DD_URL", default="lambda-http-intake.logs." + DD_SITE)


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

# Strip any trailing and leading whitespace from the API key
DD_API_KEY = DD_API_KEY.strip()

DD_SOURCE = "ddsource"
DD_CUSTOM_TAGS = "ddtags"
DD_SERVICE = "service"
DD_HOST = "host"
DD_FORWARDER_VERSION = "1.3.0"

# Pass custom tags as environment variable, ensure comma separated, no trailing comma in envvar!
DD_TAGS = os.environ.get("DD_TAGS", "")


class RetriableException(Exception):
    pass


class ScrubbingException(Exception):
    pass


class DatadogClient(object):
    """
    Client that implements a linear retrying logic to send a batch of logs.
    """

    def __init__(self, client, max_retries=3, backoff=1):
        self._client = client
        self._max_retries = max_retries
        self._backoff = backoff

    def send(self, logs, metadata):
        retry = 0
        while retry <= self._max_retries:
            if retry > 0:
                time.sleep(self._backoff)
            try:
                self._client.send(logs, metadata)
            except RetriableException as e:
                retry += 1
                continue
            return
        raise Exception("max number of retries reached: {}".format(self._max_retries))

    def __enter__(self):
        self._client.__enter__()
        return self

    def __exit__(self, ex_type, ex_value, traceback):
        self._client.__exit__(ex_type, ex_value, traceback)


class DatadogTCPClient(object):
    """
    Client that sends a batch of logs over TCP.
    """

    def __init__(self, host, port, api_key, scrubber):
        self.host = host
        self.port = port
        self._api_key = api_key
        self._scrubber = scrubber
        self._sock = None

    def _connect(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock = ssl.wrap_socket(sock)
        sock.connect((self.host, self.port))
        self._sock = sock

    def _close(self):
        if self._sock:
            self._sock.close()

    def _reset(self):
        self._close()
        self._connect()

    def send(self, logs, metadata):
        try:
            frame = self._scrubber.scrub(
                "".join(
                    [
                        "{} {}\n".format(
                            self._api_key, json.dumps(merge_dicts(log, metadata))
                        )
                        for log in logs
                    ]
                )
            )
            self._sock.send(frame.encode("UTF-8"))
        except ScrubbingException as e:
            raise Exception("could not scrub the payload")
        except Exception as e:
            # most likely a network error, reset the connection
            self._reset()
            raise RetriableException()

    def __enter__(self):
        self._connect()
        return self

    def __exit__(self, ex_type, ex_value, traceback):
        self._close()


class DatadogHTTPClient(object):
    """
    Client that sends a batch of logs over HTTP.
    """

    _POST = "POST"
    _HEADERS = {"Content-type": "application/json"}

    def __init__(self, host, api_key, scrubber, timeout=10):
        self._url = "https://{}/v1/input/{}".format(host, api_key)
        self._scrubber = scrubber
        self._timeout = timeout
        self._session = None

    def _connect(self):
        self._session = requests.Session()
        self._session.headers.update(self._HEADERS)

    def _close(self):
        self._session.close()

    def send(self, logs, metadata):
        """
        Sends a batch of log, only retry on server and network errors.
        """
        try:
            resp = self._session.post(
                self._url,
                data=self._scrubber.scrub(json.dumps(logs)),
                params=metadata,
                timeout=self._timeout,
            )
        except ScrubbingException as e:
            raise Exception("could not scrub the payload")
        except Exception as e:
            # most likely a network error
            raise RetriableException()
        if resp.status_code >= 500:
            # server error
            raise RetriableException()
        elif resp.status_code >= 400:
            # client error
            raise Exception(
                "client error, status: {}, reason {}".format(
                    resp.status_code, resp.reason
                )
            )
        else:
            # success
            return

    def __enter__(self):
        self._connect()
        return self

    def __exit__(self, ex_type, ex_value, traceback):
        self._close()


class DatadogBatcher(object):
    def __init__(self, max_log_size_bytes, max_size_bytes, max_size_count):
        self._max_log_size_bytes = max_log_size_bytes
        self._max_size_bytes = max_size_bytes
        self._max_size_count = max_size_count

    def _sizeof_bytes(self, log):
        return len(json.dumps(log).encode("UTF-8"))

    def batch(self, logs):
        """
        Returns an array of batches.
        Each batch contains at most max_size_count logs and
        is not strictly greater than max_size_bytes.
        All logs strictly greater than max_log_size_bytes are dropped.
        """
        batches = []
        batch = []
        size_bytes = 0
        size_count = 0
        for log in logs:
            log_size_bytes = self._sizeof_bytes(log)
            if size_count > 0 and (
                size_count >= self._max_size_count
                or size_bytes + log_size_bytes > self._max_size_bytes
            ):
                batches.append(batch)
                batch = []
                size_bytes = 0
                size_count = 0
            if log_size_bytes <= self._max_log_size_bytes:
                # all logs exceeding max_log_size_bytes are dropped here
                batch.append(log)
                size_bytes += log_size_bytes
                size_count += 1
        if size_count > 0:
            batches.append(batch)
        return batches


class DatadogScrubber(object):
    def __init__(self, shouldScrubIPs):
        self._ip_regex = (
            re.compile("\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}", re.I)
            if shouldScrubIPs
            else None
        )

    def scrub(self, payload):
        if self._ip_regex is not None:
            try:
                return self._ip_regex.sub("xxx.xxx.xxx.xxx", payload)
            except Exception as e:
                raise ScrubbingException()
        return payload


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

    metadata = generate_metadata(context)
    logs = generate_logs(event, context, metadata)

    scrubber = DatadogScrubber(is_ipscrubbing)
    if DD_USE_TCP:
        batcher = DatadogBatcher(256 * 1000, 256 * 1000, 1)
        cli = DatadogTCPClient(DD_URL, DD_PORT, DD_API_KEY, scrubber)
    else:
        batcher = DatadogBatcher(128 * 1000, 1 * 1000 * 1000, 25)
        cli = DatadogHTTPClient(DD_URL, DD_API_KEY, scrubber)

    with DatadogClient(cli) as client:
        for batch in batcher.batch(logs):
            try:
                client.send(batch, metadata)
            except Exception as e:
                print("Unexpected exception: {}, event: {}".format(str(e), event))


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
    return normalize_logs(logs)


def generate_metadata(context):
    metadata = {
        "ddsourcecategory": "aws",
        "aws": {
            "function_version": context.function_version,
            "invoked_function_arn": context.invoked_function_arn,
        },
    }
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
                    ["{}:{}".format(k, v) for k, v in dd_custom_tags_data.iteritems()]
                ),
            ],
        )
    )

    return metadata


# Utility functions


def normalize_logs(logs):
    normalized = []
    for log in logs:
        if isinstance(log, dict):
            normalized.append(log)
        elif isinstance(log, str):
            normalized.append({"message": log})
        else:
            # drop this log
            continue
    return normalized


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
                    arn = "{}function:{}".format(arn_prefix, functioname)
                    # 4. We add the arn as a log attribute
                    structured_line = merge_dicts(log, {"lambda": {"arn": arn}})
                    # 5. We add the function name as tag
                    metadata[DD_CUSTOM_TAGS] = "{},functionname:{}".format(
                        metadata[DD_CUSTOM_TAGS], functioname
                    )
                    # 6 we set the arn as the hostname
                    metadata[DD_HOST] = arn
        yield structured_line


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


cloudtrail_regex = re.compile(
    "\d+_CloudTrail_\w{2}-\w{4,9}-\d_\d{8}T\d{4}Z.+.json.gz$", re.I
)


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
        # For ELB logs we parse the filename to extract parameters in order to rebuild the ARN
        # 1. We extract the region from the filename
        # 2. We extract the loadbalancer name and replace the "." by "/" to match the ARN format
        # 3. We extract the id of the loadbalancer
        # 4. We build the arn
        keysplit = key.split("_")
        idsplit = key.split("/")
        if len(keysplit) > 3:
            region = keysplit[2].lower()
            name = keysplit[3].lower()
            elbname = name.replace(".", "/")
            if len(idsplit) > 1:
                idvalue = idsplit[1]
                return "arn:aws:elasticloadbalancing:{}:{}:loadbalancer/{}".format(
                    region, idvalue, elbname
                )
    if source == "s3":
        # For S3 access logs we use the bucket name to rebuild the arn
        if bucket:
            return "arn:aws:s3:::{}".format(bucket)
    if source == "cloudfront":
        # For Cloudfront logs we need to get the account and distribution id from the lambda arn and the filename
        # 1. We extract the cloudfront id  from the filename
        # 2. We extract the AWS account id from the lambda arn
        # 3. We build the arn
        namesplit = key.split("/")
        if len(namesplit) > 0:
            filename = namesplit[len(namesplit) - 1]
            # (distribution-ID.YYYY-MM-DD-HH.unique-ID.gz)
            filenamesplit = filename.split(".")
            if len(filenamesplit) > 3:
                distributionID = filenamesplit[len(filenamesplit) - 4].lower()
                arn = context.invoked_function_arn
                arnsplit = arn.split(":")
                if len(arnsplit) == 7:
                    awsaccountID = arnsplit[4].lower()
                    return "arn:aws:cloudfront::{}:distribution/{}".format(
                        awsaccountID, distributionID
                    )
    if source == "redshift":
        # For redshift logs we leverage the filename to extract the relevant information
        # 1. We extract the region from the filename
        # 2. We extract the account-id from the filename
        # 3. We extract the name of the cluster
        # 4. We build the arn: arn:aws:redshift:region:account-id:cluster:cluster-name
        namesplit = key.split("/")
        if len(namesplit) == 8:
            region = namesplit[3].lower()
            accountID = namesplit[1].lower()
            filename = namesplit[7]
            filesplit = filename.split("_")
            if len(filesplit) == 6:
                clustername = filesplit[3]
                return "arn:aws:redshift:{}:{}:cluster:{}:".format(
                    region, accountID, clustername
                )
    return
