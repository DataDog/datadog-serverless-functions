import json
import logging
import os
import re

from enhanced_lambda_metrics import parse_lambda_tags_from_arn
from settings import DD_CUSTOM_TAGS, DD_HOST, DD_SERVICE, DD_SOURCE
from steps.enums import AwsEventSource

HOST_IDENTITY_REGEXP = re.compile(
    r"^arn:aws:sts::.*?:assumed-role\/(?P<role>.*?)/(?P<host>i-([0-9a-f]{8}|[0-9a-f]{17}))$"
)

logger = logging.getLogger()
logger.setLevel(logging.getLevelName(os.environ.get("DD_LOG_LEVEL", "INFO").upper()))


def enrich(events, cache_layer):
    """Adds event-specific tags and attributes to each event

    Args:
        events (dict[]): the list of event dicts we want to enrich
    """
    for event in events:
        add_metadata_to_lambda_log(event, cache_layer)
        extract_ddtags_from_message(event)
        extract_host_from_cloudtrails(event)

    return events


def add_metadata_to_lambda_log(event, cache_layer):
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

    # Function name is the seventh piece of the ARN
    try:
        function_name = lambda_log_arn.split(":")[6]
    except IndexError:
        logger.error(f"Failed to extract function name from ARN: {lambda_log_arn}")
        return

    # Set Lambda ARN to "host"
    event[DD_HOST] = lambda_log_arn

    tags = [f"functionname:{function_name}"]

    # Get custom tags of the Lambda function
    custom_lambda_tags = get_enriched_lambda_log_tags(event, cache_layer)

    # If not set during parsing or has a default value
    # then set the service tag from lambda tags cache or using the function name
    # otherwise, remove the service tag from the custom lambda tags if exists to avoid duplication
    if not event.get(DD_SERVICE) or event.get(DD_SERVICE) == event.get(DD_SOURCE):
        service_tag = next(
            (tag for tag in custom_lambda_tags if tag.startswith("service:")),
            f"service:{function_name}",
        )
        if service_tag:
            tags.append(service_tag)
            event[DD_SERVICE] = service_tag.split(":")[1]
    else:
        custom_lambda_tags = [
            tag for tag in custom_lambda_tags if not tag.startswith("service:")
        ]

    # Check if one of the Lambda's custom tags is env
    # If an env tag exists, remove the env:none placeholder
    custom_env_tag = next(
        (tag for tag in custom_lambda_tags if tag.startswith("env:")), None
    )
    if custom_env_tag:
        event[DD_CUSTOM_TAGS] = ",".join(
            [t for t in event.get(DD_CUSTOM_TAGS, "").split(",") if t != "env:none"]
        )

    tags.extend(custom_lambda_tags)

    # Dedup tags, so we don't end up with functionname twice
    tags = list(set(tags))
    tags.sort()  # Keep order deterministic

    if custom_tags := event.get(DD_CUSTOM_TAGS):
        event[DD_CUSTOM_TAGS] = ",".join([custom_tags] + tags)
    else:
        event[DD_CUSTOM_TAGS] = ",".join(tags)


def get_enriched_lambda_log_tags(log_event, cache_layer):
    """Retrieves extra tags from lambda, either read from the function arn, or by fetching lambda tags from the function itself.

    Args:
        log_event (dict<str, str | dict | int>): a log parsed from the event in the split method
    """
    # Note that this arn attribute has been lowercased already
    log_function_arn = log_event.get("lambda", {}).get("arn")

    if not log_function_arn:
        return []
    tags_from_arn = parse_lambda_tags_from_arn(log_function_arn)
    lambda_custom_tags = cache_layer.get_lambda_tags_cache().get(log_function_arn)

    # Combine and dedup tags
    tags = list(set(tags_from_arn + lambda_custom_tags))
    return tags


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
            except Exception as e:
                if logger.isEnabledFor(logging.DEBUG):
                    logger.debug(f"Failed to extract ddtags from: {event}: {e}")
                return

        # strip and cleanup spaces from extracted tags:
        extracted_ddtags = extracted_ddtags.replace(" ", "")

        # Extract service tag from message.ddtags if exists
        service_tags = [
            tag for tag in extracted_ddtags.split(",") if tag.startswith("service:")
        ]
        if service_tags:
            event[DD_SERVICE] = service_tags[0][8:]
            event[DD_CUSTOM_TAGS] = ",".join(
                [
                    tag
                    for tag in event[DD_CUSTOM_TAGS].split(",")
                    if not tag.startswith("service:") and not tag == ""
                ]
            )

        event[DD_CUSTOM_TAGS] = f"{event[DD_CUSTOM_TAGS]},{extracted_ddtags}"


def extract_host_from_cloudtrails(event):
    """Extract the hostname from cloudtrail events userIdentity.arn field if it
    matches AWS hostnames.

    In case of s3 events the fields of the event are not encoded in the
    "message" field, but in the event object itself.
    """

    if event is not None and event.get(DD_SOURCE) == str(AwsEventSource.CLOUDTRAIL):
        message = event.get("message", {})
        if isinstance(message, str):
            try:
                message = json.loads(message)
            except json.JSONDecodeError as e:
                logger.debug(f"Failed to decode cloudtrail message: {e}")
                return

        # deal with s3 input type events
        if not message:
            message = event

        if isinstance(message, dict):
            arn = message.get("userIdentity", {}).get("arn")
            if arn is not None:
                match = HOST_IDENTITY_REGEXP.match(arn)
                if match is not None:
                    event[DD_HOST] = match.group("host")
