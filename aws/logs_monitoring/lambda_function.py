# Unless explicitly stated otherwise all files in this repository are licensed
# under the Apache License Version 2.0.
# This product includes software developed at Datadog (https://www.datadoghq.com/).
# Copyright 2018 Datadog, Inc.

from __future__ import print_function

import base64
import gzip
import json
import os

import boto3
import itertools
import re
import six.moves.urllib as urllib  # for for Python 2.7 urllib.unquote_plus
import socket
import ssl
import logging
from io import BytesIO, BufferedReader
import time

log = logging.getLogger()
log.setLevel(logging.getLevelName(os.environ.get("DD_LOG_LEVEL", "INFO").upper()))

try:
    import requests
except ImportError:
    log.error(
        "Could not import the 'requests' package, please ensure the Datadog "
        "Lambda Layer is installed. https://dtdg.co/forwarder-layer"
    )
    # Fallback to the botocore vendored version of requests, while ensuring
    # customers have the Datadog Lambda Layer installed. The vendored version
    # of requests is removed in botocore 1.13.x.
    from botocore.vendored import requests

try:
    from enhanced_lambda_metrics import parse_and_submit_enhanced_metrics
    DD_ENHANCED_LAMBDA_METRICS = True
except ImportError:
    DD_ENHANCED_LAMBDA_METRICS = False
    log.warn(
        "Could not import from enhanced_lambda_metrics so enhanced metrics "
        "will not be submitted. Ensure you've included the enhanced_lambda_metrics "
        "file in your Lambda project."
    )
finally:
    log.debug(f"DD_ENHANCED_LAMBDA_METRICS: {DD_ENHANCED_LAMBDA_METRICS}")


try:
    # Datadog Lambda layer is required to forward metrics
    from datadog_lambda.wrapper import datadog_lambda_wrapper
    from datadog_lambda.metric import lambda_stats
    DD_FORWARD_METRIC = True
except ImportError:
    log.debug(
        "Could not import from the Datadog Lambda layer, metrics can't be forwarded"
    )
    # For backward-compatibility
    DD_FORWARD_METRIC = False
finally:
    log.debug(f"DD_FORWARD_METRIC: {DD_FORWARD_METRIC}")

try:
    # Datadog Trace Layer is required to forward traces
    from trace_forwarder.connection import TraceConnection
    DD_FORWARD_TRACES = True
except ImportError:
    # For backward-compatibility
    DD_FORWARD_TRACES = False
finally:
    log.debug(f"DD_FORWARD_TRACES: {DD_FORWARD_TRACES}")


def get_env_var(envvar, default, boolean=False):
    """
        Return the value of the given environment variable with debug logging.
        When boolean=True, parse the value as a boolean case-insensitively.
    """
    value = os.getenv(envvar, default=default)
    if boolean:
        value = value.lower() == "true"
    log.debug(f"{envvar}: {value}")
    return value

#####################################
############# PARAMETERS ############
#####################################

## @param DD_API_KEY - String - required - default: none
## The Datadog API key associated with your Datadog Account
## It can be found here:
##
##   * Datadog US Site: https://app.datadoghq.com/account/settings#api
##   * Datadog EU Site: https://app.datadoghq.eu/account/settings#api
#
DD_API_KEY = "<YOUR_DATADOG_API_KEY>"

## @param DD_FORWARD_LOG - boolean - optional - default: true
## Set this variable to `False` to disable log forwarding.
## E.g., when you only want to forward metrics from logs.
#
DD_FORWARD_LOG = get_env_var("DD_FORWARD_LOG", "true", boolean=True)

## @param DD_USE_TCP - boolean - optional -default: false
## Change this value to `true` to send your logs and metrics using the TCP network client
## By default, it uses the HTTP client.
#
DD_USE_TCP = get_env_var("DD_USE_TCP", "false", boolean=True)

## @param DD_USE_COMPRESSION - boolean - optional -default: true
## Only valid when sending logs over HTTP
## Change this value to `false` to send your logs without any compression applied
## By default, compression is enabled.
#
DD_USE_COMPRESSION = get_env_var("DD_USE_COMPRESSION", "true", boolean=True)

## @param DD_USE_COMPRESSION - integer - optional -default: 6
## Change this value to set the compression level.
## Values range from 0 (no compression) to 9 (best compression).
## By default, compression is set to level 6.
#
DD_COMPRESSION_LEVEL = int(os.getenv("DD_COMPRESSION_LEVEL", 6))

## @param DD_USE_SSL - boolean - optional -default: false
## Change this value to `true` to disable SSL
## Useful when you are forwarding your logs to a proxy.
#
DD_NO_SSL = get_env_var("DD_NO_SSL", "false", boolean=True)

## @param DD_SKIP_SSL_VALIDATION - boolean - optional -default: false
## Disable SSL certificate validation when forwarding logs via HTTP.
#
DD_SKIP_SSL_VALIDATION = get_env_var(
    "DD_SKIP_SSL_VALIDATION", "false", boolean=True
)

## @param DD_SITE - String - optional -default: datadoghq.com
## Define the Datadog Site to send your logs and metrics to.
## Set it to `datadoghq.eu` to send your logs and metrics to Datadog EU site.
#
DD_SITE = get_env_var("DD_SITE", default="datadoghq.com")

## @param DD_TAGS - list of comma separated strings - optional -default: none
## Pass custom tags as environment variable or through this variable.
## Ensure your tags are a comma separated list of strings with no trailing comma in the envvar!
#
DD_TAGS = get_env_var("DD_TAGS", "")

if DD_USE_TCP:
    DD_URL = get_env_var("DD_URL", default="lambda-intake.logs." + DD_SITE)
    try:
        if "DD_SITE" in os.environ and DD_SITE == "datadoghq.eu":
            DD_PORT = int(get_env_var("DD_PORT", default="443"))
        else:
            DD_PORT = int(get_env_var("DD_PORT", default="10516"))
    except Exception:
        DD_PORT = 10516
else:
    DD_URL = get_env_var("DD_URL", default="lambda-http-intake.logs." + DD_SITE)
    DD_PORT = int(get_env_var("DD_PORT", default="443"))


class ScrubbingRuleConfig(object):
    def __init__(self, name, pattern, placeholder):
        self.name = name
        self.pattern = pattern
        self.placeholder = placeholder


# Scrubbing sensitive data
# Option to redact all pattern that looks like an ip address / email address / custom pattern
SCRUBBING_RULE_CONFIGS = [
    ScrubbingRuleConfig(
        "REDACT_IP", "\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}", "xxx.xxx.xxx.xxx"
    ),
    ScrubbingRuleConfig(
        "REDACT_EMAIL",
        "[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+",
        "xxxxx@xxxxx.com",
    ),
    ScrubbingRuleConfig(
        "DD_SCRUBBING_RULE",
        get_env_var("DD_SCRUBBING_RULE", default=None),
        get_env_var("DD_SCRUBBING_RULE_REPLACEMENT", default="xxxxx"),
    ),
]


# Use for include, exclude, and scrubbing rules
def compileRegex(rule, pattern):
    if pattern is not None:
        if pattern == "":
            # If pattern is an empty string, raise exception
            raise Exception(
                "No pattern provided:\nAdd pattern or remove {} environment variable".format(
                    rule
                )
            )
        try:
            return re.compile(pattern)
        except Exception:
            raise Exception(
                "could not compile {} regex with pattern: {}".format(rule, pattern)
            )


# Filtering logs
# Option to include or exclude logs based on a pattern match
INCLUDE_AT_MATCH = get_env_var("INCLUDE_AT_MATCH", default=None)
include_regex = compileRegex("INCLUDE_AT_MATCH", INCLUDE_AT_MATCH)

EXCLUDE_AT_MATCH = get_env_var("EXCLUDE_AT_MATCH", default=None)
exclude_regex = compileRegex("EXCLUDE_AT_MATCH", EXCLUDE_AT_MATCH)

if "DD_API_KEY_SECRET_ARN" in os.environ:
    SECRET_ARN = os.environ["DD_API_KEY_SECRET_ARN"]
    DD_API_KEY = boto3.client("secretsmanager").get_secret_value(
        SecretId=SECRET_ARN
    )["SecretString"]
elif "DD_KMS_API_KEY" in os.environ:
    ENCRYPTED = os.environ["DD_KMS_API_KEY"]
    DD_API_KEY = boto3.client("kms").decrypt(
        CiphertextBlob=base64.b64decode(ENCRYPTED)
    )["Plaintext"]
    if type(DD_API_KEY) is bytes:
        DD_API_KEY = DD_API_KEY.decode("utf-8")
elif "DD_API_KEY" in os.environ:
    DD_API_KEY = os.environ["DD_API_KEY"]

# Strip any trailing and leading whitespace from the API key
DD_API_KEY = DD_API_KEY.strip()

# DD_API_KEY must be set
if DD_API_KEY == "<YOUR_DATADOG_API_KEY>" or DD_API_KEY == "":
    raise Exception(
        "Missing Datadog API key"
    )
# Check if the API key is the correct number of characters
if len(DD_API_KEY) != 32:
    raise Exception(
        "The API key is not the expected length. "
        "Please confirm that your API key is correct"
    )
# Validate the API key
validation_res = requests.get(
    "https://api.{}/api/v1/validate?api_key={}".format(DD_SITE, DD_API_KEY)
)
if not validation_res.ok:
    raise Exception("The API key is not valid.")

trace_connection = None
if DD_FORWARD_TRACES:
    trace_connection = TraceConnection(
        "https://trace.agent.{}".format(DD_SITE), DD_API_KEY
    )

# DD_MULTILINE_LOG_REGEX_PATTERN: Multiline Log Regular Expression Pattern
DD_MULTILINE_LOG_REGEX_PATTERN = get_env_var(
    "DD_MULTILINE_LOG_REGEX_PATTERN", default=None
)
if DD_MULTILINE_LOG_REGEX_PATTERN:
    try:
        multiline_regex = re.compile(
            "[\n\r\f]+(?={})".format(DD_MULTILINE_LOG_REGEX_PATTERN)
        )
    except Exception:
        raise Exception(
            "could not compile multiline regex with pattern: {}".format(
                DD_MULTILINE_LOG_REGEX_PATTERN
            )
        )
    multiline_regex_start_pattern = re.compile(
        "^{}".format(DD_MULTILINE_LOG_REGEX_PATTERN)
    )

rds_regex = re.compile("/aws/rds/(instance|cluster)/(?P<host>[^/]+)/(?P<name>[^/]+)")

DD_SOURCE = "ddsource"
DD_CUSTOM_TAGS = "ddtags"
DD_SERVICE = "service"
DD_HOST = "host"
DD_FORWARDER_VERSION = "3.0.0"

class RetriableException(Exception):
    pass


class ScrubbingException(Exception):
    pass


class DatadogClient(object):
    """
    Client that implements a exponential retrying logic to send a batch of logs.
    """

    def __init__(self, client, max_backoff=30):
        self._client = client
        self._max_backoff = max_backoff

    def send(self, logs):
        backoff = 1
        while True:
            try:
                self._client.send(logs)
                return
            except RetriableException:
                time.sleep(backoff)
                if backoff < self._max_backoff:
                    backoff *= 2
                continue

    def __enter__(self):
        self._client.__enter__()
        return self

    def __exit__(self, ex_type, ex_value, traceback):
        self._client.__exit__(ex_type, ex_value, traceback)


class DatadogTCPClient(object):
    """
    Client that sends a batch of logs over TCP.
    """

    def __init__(self, host, port, no_ssl, api_key, scrubber):
        self.host = host
        self.port = port
        self._use_ssl = not no_ssl
        self._api_key = api_key
        self._scrubber = scrubber
        self._sock = None

    def _connect(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        if self._use_ssl:
            sock = ssl.wrap_socket(sock)
        sock.connect((self.host, self.port))
        self._sock = sock

    def _close(self):
        if self._sock:
            self._sock.close()

    def _reset(self):
        self._close()
        self._connect()

    def send(self, logs):
        try:
            frame = self._scrubber.scrub(
                "".join(["{} {}\n".format(self._api_key, log) for log in logs])
            )
            self._sock.sendall(frame.encode("UTF-8"))
        except ScrubbingException:
            raise Exception("could not scrub the payload")
        except Exception:
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
    if DD_USE_COMPRESSION:
        _HEADERS = {"Content-type": "application/json", "Content-Encoding": "gzip"}
    else:
        _HEADERS = {"Content-type": "application/json"}

    def __init__(self, host, port, no_ssl, skip_ssl_validation, api_key, scrubber, timeout=10):
        protocol = "http" if no_ssl else "https"
        self._url = "{}://{}:{}/v1/input/{}".format(protocol, host, port, api_key)
        self._scrubber = scrubber
        self._timeout = timeout
        self._session = None
        self._ssl_validation = not skip_ssl_validation

    def _connect(self):
        self._session = requests.Session()
        self._session.headers.update(self._HEADERS)

    def _close(self):
        self._session.close()

    def send(self, logs):
        """
        Sends a batch of log, only retry on server and network errors.
        """
        try:
            data=self._scrubber.scrub("[{}]".format(",".join(logs)))
        except ScrubbingException:
            raise Exception("could not scrub the payload")
        if DD_USE_COMPRESSION:
            data = compress_logs(data, DD_COMPRESSION_LEVEL)
        try:
            resp = self._session.post(
                self._url,
                data,
                timeout=self._timeout,
                verify=self._ssl_validation
            )
        except Exception:
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
        return len(log.encode("UTF-8"))

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
            # all logs exceeding max_log_size_bytes are dropped here
            if log_size_bytes <= self._max_log_size_bytes:
                batch.append(log)
                size_bytes += log_size_bytes
                size_count += 1
        if size_count > 0:
            batches.append(batch)
        return batches


def compress_logs(batch, level):
    if level < 0:
        compression_level = 0
    elif level > 9:
        compression_level = 9
    else:
        compression_level = level

    return gzip.compress(bytes(batch, 'utf-8'), compression_level)

class ScrubbingRule(object):
    def __init__(self, regex, placeholder):
        self.regex = regex
        self.placeholder = placeholder


class DatadogScrubber(object):
    def __init__(self, configs):
        rules = []
        for config in configs:
            if config.name in os.environ:
                rules.append(
                    ScrubbingRule(
                        compileRegex(config.name, config.pattern), config.placeholder
                    )
                )
        self._rules = rules

    def scrub(self, payload):
        for rule in self._rules:
            try:
                payload = rule.regex.sub(rule.placeholder, payload)
            except Exception:
                raise ScrubbingException()
        return payload


def datadog_forwarder(event, context):
    """The actual lambda function entry point"""
    metrics, logs, traces = split(enrich(parse(event, context)))

    if DD_FORWARD_LOG:
        forward_logs(filter_logs(map(json.dumps, logs)))

    if DD_FORWARD_METRIC:
        forward_metrics(metrics)

    if DD_FORWARD_TRACES and len(traces) > 0:
        forward_traces(traces)

    if DD_ENHANCED_LAMBDA_METRICS:
        report_logs = filter(
            lambda log: log.get("message", "").startswith("REPORT"), logs
        )
        parse_and_submit_enhanced_metrics(report_logs)


if DD_FORWARD_METRIC or DD_FORWARD_TRACES:
    # Datadog Lambda layer is required to forward metrics
    lambda_handler = datadog_lambda_wrapper(datadog_forwarder)
else:
    lambda_handler = datadog_forwarder


def forward_logs(logs):
    """Forward logs to Datadog"""
    scrubber = DatadogScrubber(SCRUBBING_RULE_CONFIGS)
    if DD_USE_TCP:
        batcher = DatadogBatcher(256 * 1000, 256 * 1000, 1)
        cli = DatadogTCPClient(
            DD_URL, DD_PORT, DD_NO_SSL, DD_API_KEY, scrubber)
    else:
        batcher = DatadogBatcher(256 * 1000, 2 * 1000 * 1000, 200)
        cli = DatadogHTTPClient(
            DD_URL, DD_PORT, DD_NO_SSL,
            DD_SKIP_SSL_VALIDATION, DD_API_KEY, scrubber)

    with DatadogClient(cli) as client:
        for batch in batcher.batch(logs):
            try:
                client.send(batch)
            except Exception:
                log.exception(f"Exception while forwarding log batch {batch}")
            else:
                log.debug(f"Forwarded {len(batch)} logs")


def parse(event, context):
    """Parse Lambda input to normalized events"""
    metadata = generate_metadata(context)
    try:
        # Route to the corresponding parser
        event_type = parse_event_type(event)
        if event_type == "s3":
            events = s3_handler(event, context, metadata)
        elif event_type == "awslogs":
            events = awslogs_handler(event, context, metadata)
        elif event_type == "events":
            events = cwevent_handler(event, metadata)
        elif event_type == "sns":
            events = sns_handler(event, metadata)
        elif event_type == "kinesis":
            events = kinesis_awslogs_handler(event, context, metadata)
    except Exception as e:
        # Logs through the socket the error
        err_message = "Error parsing the object. Exception: {} for event {}".format(
            str(e), event
        )
        events = [err_message]

    return normalize_events(events, metadata)


def enrich(events):
    """Adds event-specific tags and attributes to each event

    Args:
        events (dict[]): the list of event dicts we want to enrich
    """
    for event in events:
        add_metadata_to_lambda_log(event)

    return events


def add_metadata_to_lambda_log(event):
    """Mutate log dict to add functionname tag, host, and service from the existing Lambda attribute

    If the event arg is not a Lambda log then this returns without doing anything

    Args:
        event (dict): the event we are adding Lambda metadata to
    """
    lambda_log_metadata = event.get('lambda', {})
    lambda_log_arn = lambda_log_metadata.get('arn')

    # Do not mutate the event if it's not from Lambda
    if not lambda_log_arn:
        return

    # Function name is the sixth piece of the ARN
    function_name = lambda_log_arn.split(':')[6]

    event[DD_HOST] = lambda_log_arn
    event[DD_CUSTOM_TAGS] = "{},functionname:{}".format(event[DD_CUSTOM_TAGS], function_name)
    event[DD_SERVICE] = function_name


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
                    ["{}:{}".format(k, v) for k, v in dd_custom_tags_data.items()]
                ),
            ],
        )
    )

    return metadata


def extract_trace(event):
    """Extract traces from an event if possible"""
    try:
        message = event["message"]
        obj = json.loads(event["message"])
        if not "traces" in obj or not isinstance(obj["traces"], list):
            return None
        return message
    except Exception:
        return None


def extract_metric(event):
    """Extract metric from an event if possible"""
    try:
        metric = json.loads(event["message"])
        required_attrs = {"m", "v", "e", "t"}
        if all(attr in metric for attr in required_attrs):
            return metric
        else:
            return None
    except Exception:
        return None


def split(events):
    """Split events into metrics, logs, and traces
    """
    metrics, logs, traces = [], [], []
    for event in events:
        metric = extract_metric(event)
        trace = extract_trace(event)
        if metric and DD_FORWARD_METRIC:
            metrics.append(metric)
        elif trace and DD_FORWARD_TRACES:
            traces.append(trace)
        else:
            logs.append(event)
    return metrics, logs, traces



# should only be called when INCLUDE_AT_MATCH and/or EXCLUDE_AT_MATCH exist
def filter_logs(logs):
    """
    Applies log filtering rules.
    If no filtering rules exist, return all the logs.
    """
    if INCLUDE_AT_MATCH is None and EXCLUDE_AT_MATCH is None:
        # convert to strings
        return logs
    # Add logs that should be sent to logs_to_send
    logs_to_send = []
    # Test each log for exclusion and inclusion, if the criteria exist
    for log in logs:
        try:
            if EXCLUDE_AT_MATCH is not None:
                # if an exclude match is found, do not add log to logs_to_send
                if re.search(exclude_regex, log):
                    continue
            if INCLUDE_AT_MATCH is not None:
                # if no include match is found, do not add log to logs_to_send
                if not re.search(include_regex, log):
                    continue
            logs_to_send.append(log)
        except ScrubbingException:
            raise Exception("could not filter the payload")
    return logs_to_send


def forward_metrics(metrics):
    """
    Forward custom metrics submitted via logs to Datadog in a background thread
    using `lambda_stats` that is provided by the Datadog Python Lambda Layer.
    """
    for metric in metrics:
        try:
            lambda_stats.distribution(
                metric["m"], metric["v"], timestamp=metric["e"], tags=metric["t"]
            )
        except Exception:
            log.exception(f"Exception while forwarding metric {metric}")
        else:
            log.debug(f"Forwarded metric: {metric}")


def forward_traces(traces):
    for trace in traces:
        try:   
            trace_connection.send_trace(trace)
        except Exception:
            log.exception(f"Exception while forwarding trace {trace}")
        else:
            log.debug(f"Forwarded trace: {trace}")


# Utility functions


def normalize_events(events, metadata):
    normalized = []
    for event in events:
        if isinstance(event, dict):
            normalized.append(merge_dicts(event, metadata))
        elif isinstance(event, str):
            normalized.append(merge_dicts({"message": event}, metadata))
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
        elif "kinesis" in event["Records"][0]:
            return "kinesis"

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
    key = urllib.parse.unquote_plus(event["Records"][0]["s3"]["object"]["key"])

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

    # Decompress data that has a .gz extension or magic header http://www.onicos.com/staff/iz/formats/gzip.html
    if key[-3:] == ".gz" or data[:2] == b"\x1f\x8b":
        with gzip.GzipFile(fileobj=BytesIO(data)) as decompress_stream:
            # Reading line by line avoid a bug where gzip would take a very long time (>5min) for
            # file around 60MB gzipped
            data = b"".join(BufferedReader(decompress_stream))

    if is_cloudtrail(str(key)):
        cloud_trail = json.loads(data)
        for event in cloud_trail["Records"]:
            # Create structured object and send it
            structured_line = merge_dicts(
                event, {"aws": {"s3": {"bucket": bucket, "key": key}}}
            )
            yield structured_line
    else:
        # Check if using multiline log regex pattern
        # and determine whether line or pattern separated logs
        data = data.decode("utf-8")
        if DD_MULTILINE_LOG_REGEX_PATTERN and multiline_regex_start_pattern.match(data):
            split_data = multiline_regex.split(data)
        else:
            split_data = data.splitlines()

        # Send lines to Datadog
        for line in split_data:
            # Create structured object and send it
            structured_line = {
                "aws": {"s3": {"bucket": bucket, "key": key}},
                "message": line,
            }
            yield structured_line


# Handle CloudWatch logs from Kinesis
def kinesis_awslogs_handler(event, context, metadata):
    def reformat_record(record):
        return {"awslogs": {"data": record["kinesis"]["data"]}}

    return itertools.chain.from_iterable(
        awslogs_handler(reformat_record(r), context, metadata) for r in event["Records"]
    )


# Handle CloudWatch logs
def awslogs_handler(event, context, metadata):
    # Get logs
    with gzip.GzipFile(
            fileobj=BytesIO(base64.b64decode(event["awslogs"]["data"]))
    ) as decompress_stream:
        # Reading line by line avoid a bug where gzip would take a very long
        # time (>5min) for file around 60MB gzipped
        data = b"".join(BufferedReader(decompress_stream))
    logs = json.loads(data)

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

    # Set host as log group where cloudwatch is source
    if metadata[DD_SOURCE] == "cloudwatch":
        metadata[DD_HOST] = aws_attributes["aws"]["awslogs"]["logGroup"]

    # When parsing rds logs, use the cloudwatch log group name to derive the
    # rds instance name, and add the log name of the stream ingested
    if metadata[DD_SOURCE] == "rds":
        match = rds_regex.match(logs["logGroup"])
        if match is not None:
            metadata[DD_HOST] = match.group("host")
            metadata[DD_CUSTOM_TAGS] = (
                metadata[DD_CUSTOM_TAGS] + ",logname:" + match.group("name")
            )
            # We can intuit the sourcecategory in some cases
            if match.group("name") == "postgresql":
                metadata[DD_CUSTOM_TAGS] + ",sourcecategory:" + match.group("name")

    # For Lambda logs we want to extract the function name,
    # then rebuild the arn of the monitored lambda using that name.
    # Start by splitting the log group to get the function name
    if metadata[DD_SOURCE] == "lambda":
        log_group_parts = logs["logGroup"].split("/lambda/")
        if len(log_group_parts) > 1:
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

                env_tag_exists = metadata[DD_CUSTOM_TAGS].startswith('env:') or ',env:' in metadata[DD_CUSTOM_TAGS]
                # If there is no env specified, default to env:none
                if not env_tag_exists:
                    metadata[DD_CUSTOM_TAGS] += ",env:none"

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
        "/aws/rds",
        "sns",
        "waf",
        "docdb",
        "fargate",
    ]:
        if source in key:
            return source.replace("/aws/", "")
    if "API-Gateway" in key or "ApiGateway" in key:
        return "apigateway"
    if is_cloudtrail(str(key)) or (
        "logGroup" in event and event["logGroup"] == "CloudTrail"
    ):
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
        idsplit = key.split("/")
        # If there is a prefix on the S3 bucket, idsplit[1] will be "AWSLogs"
        # Remove the prefix before splitting they key
        if len(idsplit) > 1 and idsplit[1] == "AWSLogs":
            idsplit = idsplit[1:]
            keysplit = "/".join(idsplit).split("_")
        # If no prefix, split the key
        else:
            keysplit = key.split("_")
        if len(keysplit) > 3:
            region = keysplit[2].lower()
            name = keysplit[3]
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
