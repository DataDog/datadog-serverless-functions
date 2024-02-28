# Unless explicitly stated otherwise all files in this repository are licensed
# under the Apache License Version 2.0.
# This product includes software developed at Datadog (https://www.datadoghq.com/).
# Copyright 2021 Datadog, Inc.

import json
import os
import itertools
import logging
from datadog_lambda.metric import lambda_stats
from telemetry import (
    DD_FORWARDER_TELEMETRY_NAMESPACE_PREFIX,
    get_forwarder_telemetry_tags,
    set_forwarder_telemetry_tags,
)
from steps.handlers.awslogs_handler import awslogs_handler
from steps.handlers.s3_handler import s3_handler
from steps.common import (
    merge_dicts,
    get_service_from_tags_and_remove_duplicates,
)
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


def parse(event, context):
    """Parse Lambda input to normalized events"""
    metadata = generate_metadata(context)
    event_type = "unknown"
    try:
        # Route to the corresponding parser
        event_type = parse_event_type(event)
        if logger.isEnabledFor(logging.DEBUG):
            logger.debug(f"Parsed event type: {event_type}")
        match event_type:
            case "s3":
                events = s3_handler(event, context, metadata)
            case "awslogs":
                events = awslogs_handler(event, context, metadata)
            case "events":
                events = cwevent_handler(event, metadata)
            case "sns":
                events = sns_handler(event, metadata)
            case "kinesis":
                events = kinesis_awslogs_handler(event, context, metadata)
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
    if "Records" in event and event["Records"]:
        record = event["Records"][0]
        if "s3" in record:
            return "s3"
        elif "Sns" in record:
            sns_msg = record["Sns"]["Message"]
            try:
                sns_msg_dict = json.loads(sns_msg)
                if "Records" in sns_msg_dict and "s3" in sns_msg_dict["Records"][0]:
                    return "s3"
            except Exception:
                if logger.isEnabledFor(logging.DEBUG):
                    logger.debug(f"No s3 event detected from SNS message: {sns_msg}")
            return "sns"
        elif "kinesis" in record:
            return "kinesis"
    elif "awslogs" in event:
        return "awslogs"
    elif "detail" in event:
        return "events"
    raise Exception("Event type not supported (see #Event supported section)")


# Handle Cloudwatch Events
def cwevent_handler(event, metadata):
    # Set the source on the log
    source = event.get("source", "cloudwatch")
    service = source.split(".")
    if len(service) > 1:
        metadata[DD_SOURCE] = service[1]
    else:
        metadata[DD_SOURCE] = "cloudwatch"
    metadata[DD_SERVICE] = get_service_from_tags_and_remove_duplicates(metadata)

    yield event


# Handle Sns events
def sns_handler(event, metadata):
    # Set the source on the log
    metadata[DD_SOURCE] = "sns"
    for ev in event["Records"]:
        # Create structured object and send it
        structured_line = ev
        yield structured_line


# Handle CloudWatch logs from Kinesis
def kinesis_awslogs_handler(event, context, metadata):
    def reformat_record(record):
        return {"awslogs": {"data": record["kinesis"]["data"]}}

    return itertools.chain.from_iterable(
        awslogs_handler(reformat_record(r), context, metadata) for r in event["Records"]
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
    lambda_stats.distribution(
        "{}.incoming_events".format(DD_FORWARDER_TELEMETRY_NAMESPACE_PREFIX),
        events_counter,
        tags=get_forwarder_telemetry_tags(),
    )

    return normalized
