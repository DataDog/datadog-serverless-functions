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
    generate_metadata,
    get_service_from_tags_and_remove_duplicates,
    merge_dicts,
)
from steps.enums import AwsEventType, AwsEventTypeKeyword, AwsEventSource
from settings import (
    DD_SOURCE,
    DD_SERVICE,
)

logger = logging.getLogger()
logger.setLevel(logging.getLevelName(os.environ.get("DD_LOG_LEVEL", "INFO").upper()))


def parse(event, context, cache_layer):
    """Parse Lambda input to normalized events"""
    metadata = generate_metadata(context)
    try:
        event_type = parse_event_type(event)
        if logger.isEnabledFor(logging.DEBUG):
            logger.debug(f"Parsed event type: {event_type}")
        set_forwarder_telemetry_tags(context, event_type)
        match event_type:
            case AwsEventType.AWSLOGS:
                aws_handler = AwsLogsHandler(context, cache_layer)
                events = aws_handler.handle(event)
                return collect_and_count(events)
            case AwsEventType.S3:
                s3_handler = S3EventHandler(context, metadata, cache_layer)
                events = s3_handler.handle(event)
            case AwsEventType.EVENTS:
                events = cwevent_handler(event, metadata)
            case AwsEventType.SNS:
                events = sns_handler(event, metadata)
            case AwsEventType.KINESIS:
                events = kinesis_awslogs_handler(event, context, cache_layer)
            case _:
                events = ["Parsing: Unsupported event type"]
    except Exception as e:
        # Logs through the socket the error
        err_message = "Error parsing the object. Exception: {} for event {}".format(
            str(e), event
        )
        events = [err_message]

    return normalize_events(events, metadata)


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
def kinesis_awslogs_handler(event, context, cache_layer):
    def reformat_record(record):
        return {"awslogs": {"data": record["kinesis"]["data"]}}

    awslogs_handler = AwsLogsHandler(context, cache_layer)
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


def collect_and_count(events):
    collected = []
    counter = 0
    for event in events:
        counter += 1
        collected.append(event)

    send_event_metric("incoming_events", counter)

    return collected
