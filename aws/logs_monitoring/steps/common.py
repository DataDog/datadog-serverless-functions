import re
from steps.enums import (
    AwsEventSource,
    AwsEventType,
    AwsEventTypeKeyword,
    AwsCwEventSourcePrefix,
    AwsS3EventSourceKeyword,
)
from settings import DD_CUSTOM_TAGS, DD_SERVICE, DD_SOURCE

CLOUDTRAIL_REGEX = re.compile(
    "\d+_CloudTrail(|-Digest|-Insight)_\w{2}(|-gov|-cn)-\w{4,9}-\d_(|.+)\d{8}T\d{4,6}Z(|.+).json.gz$",
    re.I,
)


def parse_event_source(event, override):
    """Parse out the source that will be assigned to the log in Datadog
    Args:
        event (dict): The AWS-formatted log event that the forwarder was triggered with
        key (string): The S3 object key if the event is from S3 or the CW Log Group if the event is from CW Logs
    """
    lowercased = str(override).lower()

    # Determines if the key matches any known sources for Cloudwatch logs
    if event.get(str(AwsEventType.AWSLOGS), None):
        return find_cloudwatch_source(lowercased)

    # Determines if the key matches any known sources for S3 logs
    if records := event.get(str(AwsEventTypeKeyword.RECORDS), None):
        if len(records) > 0 and str(AwsEventSource.S3) in records[0]:
            if is_cloudtrail(lowercased):
                return str(AwsEventSource.CLOUDTRAIL)

            return find_s3_source(lowercased)

    return str(AwsEventSource.AWS)


def is_cloudtrail(key):
    match = CLOUDTRAIL_REGEX.search(key)
    return bool(match)


def find_cloudwatch_source(log_group):
    for prefix in AwsCwEventSourcePrefix:
        if log_group.startswith(str(prefix)):
            if prefix == AwsCwEventSourcePrefix.RDS:
                return find_rds_source(log_group)

            return str(prefix.event_source)

    # directly look for the source in the log group
    for source in AwsEventSource.cloudwatch_sources():
        if str(source) in log_group:
            return str(source)

    return str(AwsEventSource.CLOUDWATCH)


def find_rds_source(log_group):
    for engine in AwsEventSource.rds_sources():
        if str(engine) in log_group:
            return str(engine)

    return str(AwsEventSource.RDS)


def find_s3_source(key):
    for keyword in AwsS3EventSourceKeyword:
        keyword_str = str(keyword)
        if keyword_str in key:
            return str(keyword.event_source)

    return str(AwsEventSource.S3)


def add_service_tag(metadata):
    metadata[DD_SERVICE] = get_service_from_tags_and_remove_duplicates(metadata)


def get_service_from_tags_and_remove_duplicates(metadata):
    service = ""
    tagsplit = metadata[DD_CUSTOM_TAGS].split(",")
    for i, tag in enumerate(tagsplit):
        if tag.startswith("service:"):
            if service:
                # remove duplicate entry from the tags
                del tagsplit[i]
            else:
                service = tag[8:]
    metadata[DD_CUSTOM_TAGS] = ",".join(tagsplit)

    # Default service to source value
    return service if service else metadata[DD_SOURCE]


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
