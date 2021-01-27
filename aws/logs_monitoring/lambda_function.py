# Unless explicitly stated otherwise all files in this repository are licensed
# under the Apache License Version 2.0.
# This product includes software developed at Datadog (https://www.datadoghq.com/).
# Copyright 2020 Datadog, Inc.

import base64
import gzip
import json
import os
from collections import defaultdict
from concurrent.futures import as_completed

import boto3
import botocore
import itertools
import re
import urllib
import socket
import ssl
import logging
from io import BytesIO, BufferedReader
import time
import requests
from requests_futures.sessions import FuturesSession

from datadog_lambda.wrapper import datadog_lambda_wrapper
from datadog_lambda.metric import lambda_stats
from datadog import api
from trace_forwarder.connection import TraceConnection
from enhanced_lambda_metrics import (
    get_enriched_lambda_log_tags,
    parse_and_submit_enhanced_metrics,
)
from settings import (
    DD_API_KEY,
    DD_FORWARD_LOG,
    DD_USE_TCP,
    DD_USE_COMPRESSION,
    DD_COMPRESSION_LEVEL,
    DD_NO_SSL,
    DD_SKIP_SSL_VALIDATION,
    DD_SITE,
    DD_TAGS,
    DD_API_URL,
    DD_TRACE_INTAKE_URL,
    DD_URL,
    DD_PORT,
    SCRUBBING_RULE_CONFIGS,
    INCLUDE_AT_MATCH,
    EXCLUDE_AT_MATCH,
    DD_MULTILINE_LOG_REGEX_PATTERN,
    DD_SOURCE,
    DD_CUSTOM_TAGS,
    DD_SERVICE,
    DD_HOST,
    DD_FORWARDER_VERSION,
    DD_ADDITIONAL_TARGET_LAMBDAS,
    DD_USE_VPC,
    DD_MAX_WORKERS,
)


logger = logging.getLogger()
logger.setLevel(logging.getLevelName(os.environ.get("DD_LOG_LEVEL", "INFO").upper()))


# DD_API_KEY must be set
if DD_API_KEY == "<YOUR_DATADOG_API_KEY>" or DD_API_KEY == "":
    raise Exception("Missing Datadog API key")
# Check if the API key is the correct number of characters
if len(DD_API_KEY) != 32:
    raise Exception(
        "The API key is not the expected length. "
        "Please confirm that your API key is correct"
    )
# Validate the API key
logger.debug("Validating the Datadog API key")
validation_res = requests.get(
    "{}/api/v1/validate?api_key={}".format(DD_API_URL, DD_API_KEY),
    verify=(not DD_SKIP_SSL_VALIDATION),
    timeout=10,
)
if not validation_res.ok:
    raise Exception("The API key is not valid.")

# Force the layer to use the exact same API key and host as the forwarder
api._api_key = DD_API_KEY
api._api_host = DD_API_URL
api._cacert = not DD_SKIP_SSL_VALIDATION

trace_connection = TraceConnection(
    DD_TRACE_INTAKE_URL, DD_API_KEY, DD_SKIP_SSL_VALIDATION
)

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


include_regex = compileRegex("INCLUDE_AT_MATCH", INCLUDE_AT_MATCH)

exclude_regex = compileRegex("EXCLUDE_AT_MATCH", EXCLUDE_AT_MATCH)

rds_regex = re.compile("/aws/rds/(instance|cluster)/(?P<host>[^/]+)/(?P<name>[^/]+)")

HOST_IDENTITY_REGEXP = re.compile(
    r"^arn:aws:sts::.*?:assumed-role\/(?P<role>.*?)/(?P<host>i-[0-9a-f]{17})$"
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

# Used to build and pass aws.dd_forwarder.* telemetry tags
DD_FORWARDER_TELEMETRY_TAGS = []
DD_FORWARDER_TELEMETRY_NAMESPACE_PREFIX = "aws.dd_forwarder"


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
        if logger.isEnabledFor(logging.DEBUG):
            logger.debug(
                f"Initialized tcp client for logs intake: "
                f"<host: {host}, port: {port}, no_ssl: {no_ssl}>"
            )

    def _connect(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        if self._use_ssl:
            sock = ssl.create_default_context().wrap_socket(
                sock, server_hostname=self.host
            )
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

    def __init__(
        self, host, port, no_ssl, skip_ssl_validation, api_key, scrubber, timeout=10
    ):
        protocol = "http" if no_ssl else "https"
        self._url = "{}://{}:{}/v1/input/{}".format(protocol, host, port, api_key)
        self._scrubber = scrubber
        self._timeout = timeout
        self._session = None
        self._ssl_validation = not skip_ssl_validation
        self._futures = []
        if logger.isEnabledFor(logging.DEBUG):
            logger.debug(
                f"Initialized http client for logs intake: "
                f"<host: {host}, port: {port}, url: {self._url}, no_ssl: {no_ssl}, "
                f"skip_ssl_validation: {skip_ssl_validation}, timeout: {timeout}>"
            )

    def _connect(self):
        self._session = FuturesSession(max_workers=DD_MAX_WORKERS)
        self._session.headers.update(self._HEADERS)

    def _close(self):
        # Resolve all the futures and log exceptions if any
        for future in as_completed(self._futures):
            try:
                future.result()
            except Exception:
                logger.exception("Exception while forwarding logs")

        self._session.close()

    def send(self, logs):
        """
        Sends a batch of log, only retry on server and network errors.
        """
        try:
            data = self._scrubber.scrub("[{}]".format(",".join(logs)))
        except ScrubbingException:
            raise Exception("could not scrub the payload")
        if DD_USE_COMPRESSION:
            data = compress_logs(data, DD_COMPRESSION_LEVEL)

        # FuturesSession returns immediately with a future object
        future = self._session.post(
            self._url, data, timeout=self._timeout, verify=self._ssl_validation
        )
        self._futures.append(future)

    def __enter__(self):
        self._connect()
        return self

    def __exit__(self, ex_type, ex_value, traceback):
        self._close()


class DatadogBatcher(object):
    def __init__(self, max_item_size_bytes, max_batch_size_bytes, max_items_count):
        self._max_item_size_bytes = max_item_size_bytes
        self._max_batch_size_bytes = max_batch_size_bytes
        self._max_items_count = max_items_count

    def _sizeof_bytes(self, item):
        return len(str(item).encode("UTF-8"))

    def batch(self, items):
        """
        Returns an array of batches.
        Each batch contains at most max_items_count items and
        is not strictly greater than max_batch_size_bytes.
        All items strictly greater than max_item_size_bytes are dropped.
        """
        batches = []
        batch = []
        size_bytes = 0
        size_count = 0
        for item in items:
            item_size_bytes = self._sizeof_bytes(item)
            if size_count > 0 and (
                size_count >= self._max_items_count
                or size_bytes + item_size_bytes > self._max_batch_size_bytes
            ):
                batches.append(batch)
                batch = []
                size_bytes = 0
                size_count = 0
            # all items exceeding max_item_size_bytes are dropped here
            if item_size_bytes <= self._max_item_size_bytes:
                batch.append(item)
                size_bytes += item_size_bytes
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

    return gzip.compress(bytes(batch, "utf-8"), compression_level)


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
    if logger.isEnabledFor(logging.DEBUG):
        logger.debug(f"Received Event:{json.dumps(event)}")
        logger.debug(f"Forwarder version: {DD_FORWARDER_VERSION}")

    if DD_ADDITIONAL_TARGET_LAMBDAS:
        invoke_additional_target_lambdas(event)

    metrics, logs, trace_payloads = split(enrich(parse(event, context)))

    if DD_FORWARD_LOG:
        forward_logs(logs)

    forward_metrics(metrics)

    if len(trace_payloads) > 0:
        forward_traces(trace_payloads)

    parse_and_submit_enhanced_metrics(logs)


lambda_handler = datadog_lambda_wrapper(datadog_forwarder)


def forward_logs(logs):
    """Forward logs to Datadog"""
    if logger.isEnabledFor(logging.DEBUG):
        logger.debug(f"Forwarding {len(logs)} logs")
    logs_to_forward = filter_logs(list(map(json.dumps, logs)))
    scrubber = DatadogScrubber(SCRUBBING_RULE_CONFIGS)
    if DD_USE_TCP:
        batcher = DatadogBatcher(256 * 1000, 256 * 1000, 1)
        cli = DatadogTCPClient(DD_URL, DD_PORT, DD_NO_SSL, DD_API_KEY, scrubber)
    else:
        batcher = DatadogBatcher(256 * 1000, 4 * 1000 * 1000, 400)
        cli = DatadogHTTPClient(
            DD_URL, DD_PORT, DD_NO_SSL, DD_SKIP_SSL_VALIDATION, DD_API_KEY, scrubber
        )

    with DatadogClient(cli) as client:
        for batch in batcher.batch(logs_to_forward):
            try:
                client.send(batch)
            except Exception:
                logger.exception(f"Exception while forwarding log batch {batch}")
            else:
                if logger.isEnabledFor(logging.DEBUG):
                    logger.debug(f"Forwarded log batch: {json.dumps(batch)}")

    lambda_stats.distribution(
        "{}.logs_forwarded".format(DD_FORWARDER_TELEMETRY_NAMESPACE_PREFIX),
        len(logs_to_forward),
        tags=DD_FORWARDER_TELEMETRY_TAGS,
    )


def parse(event, context):
    """Parse Lambda input to normalized events"""
    metadata = generate_metadata(context)
    event_type = "unknown"
    try:
        # Route to the corresponding parser
        event_type = parse_event_type(event)
        if logger.isEnabledFor(logging.DEBUG):
            logger.debug(f"Parsed event type: {event_type}")
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

    set_forwarder_telemetry_tags(context, event_type)

    return normalize_events(events, metadata)


def set_forwarder_telemetry_tags(context, event_type):
    """Helper function to set tags on telemetry metrics
    Do not submit telemetry metrics before this helper function is invoked
    """
    global DD_FORWARDER_TELEMETRY_TAGS

    DD_FORWARDER_TELEMETRY_TAGS = [
        f"forwardername:{context.function_name.lower()}",
        f"forwarder_memorysize:{context.memory_limit_in_mb}",
        f"forwarder_version:{DD_FORWARDER_VERSION}",
        f"event_type:{event_type}",
    ]


def enrich(events):
    """Adds event-specific tags and attributes to each event

    Args:
        events (dict[]): the list of event dicts we want to enrich
    """
    for event in events:
        add_metadata_to_lambda_log(event)
        extract_ddtags_from_message(event)

    return events


def extract_ddtags_from_message(event):
    """When the logs intake pipeline detects a `message` field with a
    JSON content, it extracts the content to the top-level. The fields
    of same name from the top-level will be overridden.

    E.g. the application adds some tags to the log, which appear in the
    `message.ddtags` field, and the forwarder adds some common tags, such
    as `aws_account`, which appear in the top-level `ddtags` field:

    {
        "message": {
            "ddtags": "mytag:value", # tags added by the application
            ...
        },
        "ddtags": "env:xxx,aws_account", # tags added by the forwarder
        ...
    }

    Only the custom tags added by the application will be kept.

    We might want to change the intake pipeline to "merge" the conflicting
    fields rather than "overridding" in the future, but for now we should
    extract `message.ddtags` and merge it with the top-level `ddtags` field.
    """
    if "message" in event and DD_CUSTOM_TAGS in event["message"]:
        if isinstance(event["message"], dict):
            extracted_ddtags = event["message"].pop(DD_CUSTOM_TAGS)
        if isinstance(event["message"], str):
            try:
                message_dict = json.loads(event["message"])
                extracted_ddtags = message_dict.pop(DD_CUSTOM_TAGS)
                event["message"] = json.dumps(message_dict)
            except Exception:
                if logger.isEnabledFor(logging.DEBUG):
                    logger.debug(f"Failed to extract ddtags from: {event}")
                return
        event[DD_CUSTOM_TAGS] = f"{event[DD_CUSTOM_TAGS]},{extracted_ddtags}"


def extract_arn_hostname(message):
    """Extract the hostname from userIdentity.arn field if it matches AWS hostnames

    >>> extract_arn_hostname(json.dumps(
    >>> {"usertIdentity": {"arn": "arn:aws:sts::123456789123:assumed-role/DatadogAWSIntegrationRole/i-08014e4f62ccf762d"}})
    >>> )
    i-0123456789abcdef0
    >>> extract_arn_hostname({"message": "test"})
    None
    """
    if message is not None:
        if isinstance(message, str):
            try:
                message = json.loads(message)
            except json.JSONDecodeError:
                return None
        useridentify_arn = message.get("userIdentity", {}).get("arn")
        if useridentify_arn is not None:
            match = HOST_IDENTITY_REGEXP.match(useridentify_arn)
            if match is not None:
                return match.group("host")
    return None


def add_metadata_to_lambda_log(event):
    """Mutate log dict to add tags, host, and service metadata

    * tags for functionname, aws_account, region
    * host from the Lambda ARN
    * service from the Lambda name

    If the event arg is not a Lambda log then this returns without doing anything

    Args:
        event (dict): the event we are adding Lambda metadata to
    """
    lambda_log_metadata = event.get("lambda", {})
    lambda_log_arn = lambda_log_metadata.get("arn")

    # Do not mutate the event if it's not from Lambda
    if not lambda_log_arn:
        return

    # Set Lambda ARN to "host"
    event[DD_HOST] = lambda_log_arn

    # Function name is the seventh piece of the ARN
    function_name = lambda_log_arn.split(":")[6]
    tags = [f"functionname:{function_name}"]

    # Get custom tags of the Lambda function
    custom_lambda_tags = get_enriched_lambda_log_tags(event)

    # Set the `service` tag and metadata field. If the Lambda function is
    # tagged with a `service` tag, use it, otherwise use the function name.
    service_tag = next(
        (tag for tag in custom_lambda_tags if tag.startswith("service:")),
        f"service:{function_name}",
    )
    tags.append(service_tag)
    event[DD_SERVICE] = service_tag.split(":")[1]

    # Check if one of the Lambda's custom tags is env
    # If an env tag exists, remove the env:none placeholder
    custom_env_tag = next(
        (tag for tag in custom_lambda_tags if tag.startswith("env:")), None
    )
    if custom_env_tag is not None:
        event[DD_CUSTOM_TAGS] = event[DD_CUSTOM_TAGS].replace("env:none", "")

    tags += custom_lambda_tags

    # Dedup tags, so we don't end up with functionname twice
    tags = list(set(tags))
    tags.sort()  # Keep order deterministic

    event[DD_CUSTOM_TAGS] = ",".join([event[DD_CUSTOM_TAGS]] + tags)


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
        "forwarder_memorysize": context.memory_limit_in_mb,
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


def extract_trace_payload(event):
    """Extract trace payload from an event if possible"""
    try:
        message = event["message"]
        obj = json.loads(event["message"])
        if not "traces" in obj or not isinstance(obj["traces"], list):
            return None
        return {"message": message, "tags": event[DD_CUSTOM_TAGS]}
    except Exception:
        return None


def extract_metric(event):
    """Extract metric from an event if possible"""
    try:
        metric = json.loads(event["message"])
        required_attrs = {"m", "v", "e", "t"}
        if not all(attr in metric for attr in required_attrs):
            return None
        if not isinstance(metric["t"], list):
            return None
        if not (isinstance(metric["v"], int) or isinstance(metric["v"], float)):
            return None

        lambda_log_metadata = event.get("lambda", {})
        lambda_log_arn = lambda_log_metadata.get("arn")

        if lambda_log_arn:
            metric["t"] += [f"function_arn:{lambda_log_arn.lower()}"]

        metric["t"] += event[DD_CUSTOM_TAGS].split(",")
        return metric
    except Exception:
        return None


def split(events):
    """Split events into metrics, logs, and trace payloads"""
    metrics, logs, trace_payloads = [], [], []
    for event in events:
        metric = extract_metric(event)
        trace_payload = extract_trace_payload(event)
        if metric:
            metrics.append(metric)
        elif trace_payload:
            trace_payloads.append(trace_payload)
        else:
            logs.append(event)

    if logger.isEnabledFor(logging.DEBUG):
        logger.debug(
            f"Extracted {len(metrics)} metrics, {len(trace_payloads)} traces, and {len(logs)} logs"
        )

    return metrics, logs, trace_payloads


# should only be called when INCLUDE_AT_MATCH and/or EXCLUDE_AT_MATCH exist
def filter_logs(logs):
    """
    Applies log filtering rules.
    If no filtering rules exist, return all the logs.
    """
    if INCLUDE_AT_MATCH is None and EXCLUDE_AT_MATCH is None:
        return logs
    # Add logs that should be sent to logs_to_send
    logs_to_send = []
    for log in logs:
        if EXCLUDE_AT_MATCH is not None or INCLUDE_AT_MATCH is not None:
            logger.debug("Filtering log event:")
            logger.debug(log)
        try:
            if EXCLUDE_AT_MATCH is not None:
                # if an exclude match is found, do not add log to logs_to_send
                logger.debug(f"Applying EXCLUDE_AT_MATCH: {EXCLUDE_AT_MATCH}")
                if re.search(exclude_regex, log):
                    logger.debug("Exclude regex matched, excluding log event")
                    continue
            if INCLUDE_AT_MATCH is not None:
                # if no include match is found, do not add log to logs_to_send
                logger.debug(f"Applying INCLUDE_AT_MATCH: {INCLUDE_AT_MATCH}")
                if not re.search(include_regex, log):
                    logger.debug("Include regex did not match, excluding log event")
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
    if logger.isEnabledFor(logging.DEBUG):
        logger.debug(f"Forwarding {len(metrics)} metrics")

    for metric in metrics:
        try:
            lambda_stats.distribution(
                metric["m"], metric["v"], timestamp=metric["e"], tags=metric["t"]
            )
        except Exception:
            logger.exception(f"Exception while forwarding metric {json.dumps(metric)}")
        else:
            if logger.isEnabledFor(logging.DEBUG):
                logger.debug(f"Forwarded metric: {json.dumps(metric)}")

    lambda_stats.distribution(
        "{}.metrics_forwarded".format(DD_FORWARDER_TELEMETRY_NAMESPACE_PREFIX),
        len(metrics),
        tags=DD_FORWARDER_TELEMETRY_TAGS,
    )


def forward_traces(trace_payloads):
    if logger.isEnabledFor(logging.DEBUG):
        logger.debug(f"Forwarding {len(trace_payloads)} traces")

    try:
        trace_connection.send_traces(trace_payloads)
    except Exception:
        logger.exception(
            f"Exception while forwarding traces {json.dumps(trace_payloads)}"
        )
    else:
        if logger.isEnabledFor(logging.DEBUG):
            logger.debug(f"Forwarded traces: {json.dumps(trace_payloads)}")

    lambda_stats.distribution(
        "{}.traces_forwarded".format(DD_FORWARDER_TELEMETRY_NAMESPACE_PREFIX),
        len(trace_payloads),
        tags=DD_FORWARDER_TELEMETRY_TAGS,
    )


# Utility functions


def normalize_events(events, metadata):
    normalized = []
    events_counter = 0

    for event in events:
        events_counter += 1
        if isinstance(event, dict):
            normalized_event = merge_dicts(event, metadata)
        elif isinstance(event, str):
            normalized_event = merge_dicts({"message": event}, metadata)
        else:
            # drop this log
            continue

        # in case it's a cloudtrail event replace the hostname with the
        # hostname in the ARN if available.
        if normalized_event.get(DD_SOURCE) == "cloudtrail":
            extracted_arn_hostname = extract_arn_hostname(normalized_event["message"])
            if extracted_arn_hostname is not None:
                normalized_event[DD_HOST] = extracted_arn_hostname

        normalized.append(normalized_event)

    """Submit count of total events"""
    lambda_stats.distribution(
        "{}.incoming_events".format(DD_FORWARDER_TELEMETRY_NAMESPACE_PREFIX),
        events_counter,
        tags=DD_FORWARDER_TELEMETRY_TAGS,
    )

    return normalized


def parse_event_type(event):
    if "Records" in event and len(event["Records"]) > 0:
        if "s3" in event["Records"][0]:
            return "s3"
        elif "Sns" in event["Records"][0]:
            # it's not uncommon to fan out s3 notifications through SNS,
            # should treat it as an s3 event rather than sns event.
            sns_msg = event["Records"][0]["Sns"]["Message"]
            try:
                sns_msg_dict = json.loads(sns_msg)
                if "Records" in sns_msg_dict and "s3" in sns_msg_dict["Records"][0]:
                    return "s3"
            except Exception:
                if logger.isEnabledFor(logging.DEBUG):
                    logger.debug(f"No s3 event detected from SNS message: {sns_msg}")
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
    # Need to use path style to access s3 via VPC Endpoints
    # https://github.com/gford1000-aws/lambda_s3_access_using_vpc_endpoint#boto3-specific-notes
    if DD_USE_VPC:
        s3 = boto3.client(
            "s3",
            os.environ["AWS_REGION"],
            config=botocore.config.Config(s3={"addressing_style": "path"}),
        )
    else:
        s3 = boto3.client("s3")
    # if this is a S3 event carried in a SNS message, extract it and override the event
    if "Sns" in event["Records"][0]:
        event = json.loads(event["Records"][0]["Sns"]["Message"])

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

    # Use the logStream to identify if this is a CloudTrail event
    # i.e. 123456779121_CloudTrail_us-east-1
    if "_CloudTrail_" in logs["logStream"]:
        source = "cloudtrail"
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
    if metadata[DD_SOURCE] == "cloudwatch" or metadata.get(DD_HOST, None) == None:
        metadata[DD_HOST] = aws_attributes["aws"]["awslogs"]["logGroup"]

    # When parsing rds logs, use the cloudwatch log group name to derive the
    # rds instance name, and add the log name of the stream ingested
    if metadata[DD_SOURCE] in ["rds", "mariadb", "mysql"]:
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
            lowercase_function_name = log_group_parts[1].lower()
            # Split the arn of the forwarder to extract the prefix
            arn_parts = context.invoked_function_arn.split("function:")
            if len(arn_parts) > 0:
                arn_prefix = arn_parts[0]
                # Rebuild the arn with the lowercased function name
                lowercase_arn = arn_prefix + "function:" + lowercase_function_name
                # Add the lowercased arn as a log attribute
                arn_attributes = {"lambda": {"arn": lowercase_arn}}
                aws_attributes = merge_dicts(aws_attributes, arn_attributes)

                env_tag_exists = (
                    metadata[DD_CUSTOM_TAGS].startswith("env:")
                    or ",env:" in metadata[DD_CUSTOM_TAGS]
                )
                # If there is no env specified, default to env:none
                if not env_tag_exists:
                    metadata[DD_CUSTOM_TAGS] += ",env:none"

    # The EKS log group contains various sources from the K8S control plane.
    # In order to have these automatically trigger the correct pipelines they
    # need to send their events with the correct log source.
    if metadata[DD_SOURCE] == "eks":
        if logs["logStream"].startswith("kube-apiserver-audit-"):
            metadata[DD_SOURCE] = "kubernetes.audit"
        elif logs["logStream"].startswith("kube-scheduler-"):
            metadata[DD_SOURCE] = "kube_scheduler"
        # In case the conditions above don't match we maintain eks as the source

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
    metadata[DD_SOURCE] = "sns"

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


def find_cloudwatch_source(log_group):
    # e.g. /aws/rds/instance/my-mariadb/error
    if log_group.startswith("/aws/rds"):
        for engine in ["mariadb", "mysql"]:
            if engine in log_group:
                return engine
        return "rds"

    # e.g. Api-Gateway-Execution-Logs_xxxxxx/dev
    if log_group.startswith("api-gateway"):
        return "apigateway"

    # e.g. dms-tasks-test-instance
    if log_group.startswith("dms-tasks"):
        return "dms"

    # e.g. sns/us-east-1/123456779121/SnsTopicX
    if log_group.startswith("sns/"):
        return "sns"

    for source in [
        "/aws/lambda",  # e.g. /aws/lambda/helloDatadog
        "/aws/codebuild",  # e.g. /aws/codebuild/my-project
        "/aws/kinesis",  # e.g. /aws/kinesisfirehose/dev
        "/aws/docdb",  # e.g. /aws/docdb/yourClusterName/profile
        "/aws/eks",  # e.g. /aws/eks/yourClusterName/profile
    ]:
        if log_group.startswith(source):
            return source.replace("/aws/", "")

    # the below substrings must be in your log group to be detected
    for source in [
        "network-firewall",
        "route53",
        "vpc",
        "fargate",
        "cloudtrail",
        "msk",
    ]:
        if source in log_group:
            return source

    return "cloudwatch"


def find_s3_source(key):
    # e.g. AWSLogs/123456779121/elasticloadbalancing/us-east-1/2020/10/02/123456779121_elasticloadbalancing_us-east-1_app.alb.xxxxx.xx.xxx.xxx_x.log.gz
    if "elasticloadbalancing" in key:
        return "elb"

    # e.g. AWSLogs/123456779121/vpcflowlogs/us-east-1/2020/10/02/123456779121_vpcflowlogs_us-east-1_fl-xxxxx.log.gz
    if "vpcflowlogs" in key:
        return "vpc"

    # e.g. 2020/10/02/21/aws-waf-logs-testing-1-2020-10-02-21-25-30-x123x-x456x
    if "aws-waf-logs" in key:
        return "waf"

    # e.g. AWSLogs/123456779121/redshift/us-east-1/2020/10/21/123456779121_redshift_us-east-1_mycluster_userlog_2020-10-21T18:01.gz
    if "_redshift_" in key:
        return "redshift"

    # this substring must be in your target prefix to be detected
    if "amazon_documentdb" in key:
        return "docdb"

    # the below substrings must be in your target prefix to be detected
    for source in [
        "amazon_codebuild",
        "amazon_kinesis",
        "amazon_dms",
        "amazon_msk",
        "network-firewall",
        "cloudfront",
    ]:
        if source in key:
            return source.replace("amazon_", "")

    return "s3"


def parse_event_source(event, key):
    """Parse out the source that will be assigned to the log in Datadog
    Args:
        event (dict): The AWS-formatted log event that the forwarder was triggered with
        key (string): The S3 object key if the event is from S3 or the CW Log Group if the event is from CW Logs
    """
    lowercase_key = str(key).lower()

    # Determines if the key matches any known sources for Cloudwatch logs
    if "awslogs" in event:
        return find_cloudwatch_source(lowercase_key)

    # Determines if the key matches any known sources for S3 logs
    if "Records" in event and len(event["Records"]) > 0:
        if "s3" in event["Records"][0]:
            if is_cloudtrail(str(key)):
                return "cloudtrail"

            return find_s3_source(lowercase_key)

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


def invoke_additional_target_lambdas(event):
    lambda_client = boto3.client("lambda")
    lambda_arns = DD_ADDITIONAL_TARGET_LAMBDAS.split(",")
    lambda_payload = json.dumps(event)

    for lambda_arn in lambda_arns:
        try:
            lambda_client.invoke(
                FunctionName=lambda_arn,
                InvocationType="Event",
                Payload=lambda_payload,
            )
        except Exception as e:
            logger.exception(
                f"Failed to invoke additional target lambda {lambda_arn} due to {e}"
            )

    return
