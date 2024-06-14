# Unless explicitly stated otherwise all files in this repository are licensed
# under the Apache License Version 2.0.
# This product includes software developed at Datadog (https://www.datadoghq.com/).
# Copyright 2021 Datadog, Inc.

import json
import os
import itertools
import logging
from telemetry import set_forwarder_telemetry_tags, send_event_metric
from steps.handlers.awslogs_handler import AwsLogsHandler
from steps.handlers.s3_handler import S3EventHandler
from steps.common import (
    merge_dicts,
    get_service_from_tags_and_remove_duplicates,
)
from steps.enums import AwsEventType, AwsEventTypeKeyword, AwsEventSource
from settings import (
    AWS_STRING,
    FUNCTIONVERSION_STRING,
    INVOKEDFUNCTIONARN_STRING,
    SOURCECATEGORY_STRING,
    FORWARDERNAME_STRING,
    FORWARDERMEMSIZE_STRING,
    FORWARDERVERSION_STRING,
    DD_TAGS,
    DD_SOURCE,
    DD_CUSTOM_TAGS,
    DD_SERVICE,
    DD_FORWARDER_VERSION,
)

logger = logging.getLogger()
logger.setLevel(logging.getLevelName(os.environ.get("DD_LOG_LEVEL", "INFO").upper()))


def parse(event, context, cache_layer):
    """Parse Lambda input to normalized events"""
    metadata = generate_metadata(context)
    event_type = AwsEventType.UNKNOWN
    try:
        # Route to the corresponding parser
        event_type = parse_event_type(event)
        if logger.isEnabledFor(logging.DEBUG):
            logger.debug(f"Parsed event type: {event_type}")
        match event_type:
            case AwsEventType.S3:
                s3_handler = S3EventHandler(context, metadata, cache_layer)
                events = s3_handler.handle(event)
            case AwsEventType.AWSLOGS:
                aws_handler = AwsLogsHandler(context, metadata, cache_layer)
                events = aws_handler.handle(event)
            case AwsEventType.EVENTS:
                events = cwevent_handler(event, metadata)
            case AwsEventType.SNS:
                events = sns_handler(event, metadata)
            case AwsEventType.KINESIS:
                events = kinesis_awslogs_handler(event, context, metadata, cache_layer)
            case _:
                events = ["Parsing: Unsupported event type"]
    except Exception as e:
        # Logs through the socket the error
        err_message = "Error parsing the object. Exception: {} for event {}".format(
            str(e), event
        )
        events = [err_message]

    set_forwarder_telemetry_tags(context, event_type)

    return normalize_events(events, metadata)


def generate_metadata(context):
    metadata = {
        SOURCECATEGORY_STRING: AWS_STRING,
        AWS_STRING: {
            FUNCTIONVERSION_STRING: context.function_version,
            INVOKEDFUNCTIONARN_STRING: context.invoked_function_arn,
        },
    }
    # Add custom tags here by adding new value with the following format "key1:value1, key2:value2"  - might be subject to modifications
    dd_custom_tags_data = generate_custom_tags(context)
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


def generate_custom_tags(context):
    dd_custom_tags_data = {
        FORWARDERNAME_STRING: context.function_name.lower(),
        FORWARDERMEMSIZE_STRING: context.memory_limit_in_mb,
        FORWARDERVERSION_STRING: DD_FORWARDER_VERSION,
    }

    return dd_custom_tags_data


def parse_event_type(event):
    if records := event.get(str(AwsEventTypeKeyword.RECORDS), None):
        record = records[0]
        if record.get(str(AwsEventType.S3), None):
            return AwsEventType.S3
        elif sns_record := record.get(str(AwsEventTypeKeyword.SNS), None):
            sns_msg = sns_record.get(str(AwsEventTypeKeyword.MESSAGE), None)
            try:
                sns_msg_dict = json.loads(sns_msg)
                if inner_records := sns_msg_dict.get(
                    str(AwsEventTypeKeyword.RECORDS), None
                ):
                    if inner_records[0].get(str(AwsEventType.S3)):
                        return AwsEventType.S3
            except Exception:
                if logger.isEnabledFor(logging.DEBUG):
                    logger.debug(f"No s3 event detected from SNS message: {sns_msg}")
            return AwsEventType.SNS
        elif str(AwsEventType.KINESIS) in record:
            return AwsEventType.KINESIS
    elif str(AwsEventType.AWSLOGS) in event:
        return AwsEventType.AWSLOGS
    elif "detail" in event:
        return AwsEventType.EVENTS
    raise Exception("Event type not supported (see #Event supported section)")


# Handle Cloudwatch Events
def cwevent_handler(event, metadata):
    # Set the source on the log
    source = event.get("source", str(AwsEventSource.CLOUDWATCH))
    service = source.split(".")
    if len(service) > 1:
        metadata[DD_SOURCE] = service[1]
    else:
        metadata[DD_SOURCE] = str(AwsEventSource.CLOUDWATCH)
    metadata[DD_SERVICE] = get_service_from_tags_and_remove_duplicates(metadata)

    yield event


# Handle Sns events
def sns_handler(event, metadata):
    # Set the source on the log
    metadata[DD_SOURCE] = str(AwsEventSource.SNS)
    for ev in event["Records"]:
        yield ev


# Handle CloudWatch logs from Kinesis
def kinesis_awslogs_handler(event, context, metadata, cache_layer):
    def reformat_record(record):
        return {"awslogs": {"data": record["kinesis"]["data"]}}

    awslogs_handler = AwsLogsHandler(context, metadata, cache_layer)
    return itertools.chain.from_iterable(
        awslogs_handler.handle(reformat_record(r)) for r in event["Records"]
    )


def normalize_events(events, metadata):
    normalized = []
    events_counter = 0

    for event in events:
        events_counter += 1
        if isinstance(event, dict):
            normalized.append(merge_dicts(event, metadata))
        elif isinstance(event, str):
            normalized.append(merge_dicts({"message": event}, metadata))
        else:
            # drop this log
            continue

    """Submit count of total events"""
    send_event_metric("incoming_events", events_counter)

    return normalized
