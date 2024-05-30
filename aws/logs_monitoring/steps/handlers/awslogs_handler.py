import base64
import gzip
import json
import logging
import os
import re
from io import BufferedReader, BytesIO

from steps.common import (
    add_service_tag,
    merge_dicts,
    parse_event_source,
)
from customized_log_group import (
    is_lambda_customized_log_group,
    get_lambda_function_name_from_logstream_name,
)
from steps.handlers.aws_attributes import AwsAttributes
from steps.enums import AwsEventSource, AwsCwEventSourcePrefix
from settings import (
    DD_SOURCE,
    DD_HOST,
    DD_CUSTOM_TAGS,
)

RDS_REGEX = re.compile("/aws/rds/(instance|cluster)/(?P<host>[^/]+)/(?P<name>[^/]+)")

logger = logging.getLogger()
logger.setLevel(logging.getLevelName(os.environ.get("DD_LOG_LEVEL", "INFO").upper()))


# Handle CloudWatch logs
def awslogs_handler(event, context, metadata, cache_layer):
    # Get logs
    logs = extract_logs(event)
    # Build aws attributes
    aws_attributes = AwsAttributes(
        logs.get("logGroup"),
        logs.get("logStream"),
        logs.get("logEvents"),
        logs.get("owner"),
    )
    # Set account and region from lambda function ARN
    set_account_region(context, aws_attributes)
    # Set the source on the logs
    set_source(event, metadata, aws_attributes)
    # Add custom tags from cache
    add_cloudwatch_tags_from_cache(metadata, aws_attributes, cache_layer)
    # Set service from custom tags, which may include the tags set on the log group
    # Returns DD_SOURCE by default
    add_service_tag(metadata)
    # Set host as log group where cloudwatch is source
    set_host(metadata, aws_attributes, cache_layer)
    # For Lambda logs we want to extract the function name,
    # then rebuild the arn of the monitored lambda using that name.
    if metadata[DD_SOURCE] == str(AwsEventSource.LAMBDA):
        process_lambda_logs(aws_attributes, context, metadata)
    # The EKS log group contains various sources from the K8S control plane.
    # In order to have these automatically trigger the correct pipelines they
    # need to send their events with the correct log source.
    if metadata[DD_SOURCE] == str(AwsEventSource.EKS):
        process_eks_logs(aws_attributes, metadata)

    # Create and send structured logs to Datadog
    for log in logs["logEvents"]:
        yield merge_dicts(log, aws_attributes.to_dict())


def extract_logs(event):
    with gzip.GzipFile(
        fileobj=BytesIO(base64.b64decode(event["awslogs"]["data"]))
    ) as decompress_stream:
        # Reading line by line avoid a bug where gzip would take a very long
        # time (>5min) for file around 60MB gzipped
        data = b"".join(BufferedReader(decompress_stream))
    return json.loads(data)


def set_account_region(context, aws_attributes):
    try:
        aws_attributes.set_account_region(context.invoked_function_arn)
    except Exception as e:
        logger.error(
            "Unable to set account and region from lambda function ARN: %s" % e
        )


def set_source(event, metadata, aws_attributes):
    log_group = aws_attributes.get_log_group()
    log_stream = aws_attributes.get_log_stream()
    source = log_group if log_group else str(AwsEventSource.CLOUDWATCH)
    # Use the logStream to identify if this is a CloudTrail, TransitGateway, or Bedrock event
    # i.e. 123456779121_CloudTrail_us-east-1
    if str(AwsCwEventSourcePrefix.CLOUDTRAIL) in log_stream:
        source = str(AwsEventSource.CLOUDTRAIL)
    if str(AwsCwEventSourcePrefix.TRANSITGATEWAY) in log_stream:
        source = str(AwsEventSource.TRANSITGATEWAY)
    if str(AwsCwEventSourcePrefix.BEDROCK) in log_stream:
        source = str(AwsEventSource.BEDROCK)
    metadata[DD_SOURCE] = parse_event_source(event, source)

    # Special handling for customized log group of Lambda functions
    # Multiple Lambda functions can share one single customized log group
    # Need to parse logStream name to determine whether it is a Lambda function
    if is_lambda_customized_log_group(log_stream):
        metadata[DD_SOURCE] = str(AwsEventSource.LAMBDA)


def add_cloudwatch_tags_from_cache(metadata, aws_attributes, cache_layer):
    log_group_arn = aws_attributes.get_log_group_arn()
    formatted_tags = cache_layer.get_cloudwatch_log_group_tags_cache().get(
        log_group_arn
    )
    if len(formatted_tags) > 0:
        metadata[DD_CUSTOM_TAGS] = (
            ",".join(formatted_tags)
            if not metadata[DD_CUSTOM_TAGS]
            else metadata[DD_CUSTOM_TAGS] + "," + ",".join(formatted_tags)
        )


def set_host(metadata, aws_attributes, cache_layer):
    if src := metadata.get(DD_SOURCE, None):
        metadata_source = AwsEventSource._value2member_map_.get(src)
    else:
        metadata_source = AwsEventSource.CLOUDWATCH
    metadata_host = metadata.get(DD_HOST, None)
    log_group = aws_attributes.get_log_group()
    log_stream = aws_attributes.get_log_stream()
    log_events = aws_attributes.get_log_events()

    if metadata_host is None:
        metadata[DD_HOST] = log_group

    match metadata_source:
        case AwsEventSource.CLOUDWATCH:
            metadata[DD_HOST] = log_group
        case AwsEventSource.APPSYNC:
            metadata[DD_HOST] = log_group.split("/")[-1]
        case AwsEventSource.VERIFIED_ACCESS:
            handle_verified_access_source(metadata, log_events)
        case AwsEventSource.STEPFUNCTION:
            handle_step_function_source(metadata, log_events, log_stream, cache_layer)
        # When parsing rds logs, use the cloudwatch log group name to derive the
        # rds instance name, and add the log name of the stream ingested
        case (
            AwsEventSource.RDS
            | AwsEventSource.MYSQL
            | AwsEventSource.MARIADB
            | AwsEventSource.POSTGRESQL
        ):
            handle_rds_source(metadata, log_group)


def handle_rds_source(metadata, log_group):
    match = RDS_REGEX.match(log_group)
    if match is not None:
        metadata[DD_HOST] = match.group("host")
        metadata[DD_CUSTOM_TAGS] = (
            metadata[DD_CUSTOM_TAGS] + ",logname:" + match.group("name")
        )


def handle_step_function_source(metadata, log_events, log_stream, cache_layer):
    if not log_stream.startswith("states/"):
        pass
    state_machine_arn = ""

    try:
        state_machine_arn = get_state_machine_arn(
            json.loads(log_events[0].get("message"))
        )
        if state_machine_arn:  # not empty
            metadata[DD_HOST] = state_machine_arn
    except Exception as e:
        logger.debug("Unable to set stepfunction host or get state_machine_arn: %s" % e)

    formatted_stepfunctions_tags = cache_layer.get_step_functions_tags_cache().get(
        state_machine_arn
    )
    if len(formatted_stepfunctions_tags) > 0:
        metadata[DD_CUSTOM_TAGS] = (
            ",".join(formatted_stepfunctions_tags)
            if not metadata[DD_CUSTOM_TAGS]
            else metadata[DD_CUSTOM_TAGS] + "," + ",".join(formatted_stepfunctions_tags)
        )


def handle_verified_access_source(metadata, log_events):
    try:
        message = json.loads(log_events[0].get("message"))
        metadata[DD_HOST] = message.get("http_request").get("url").get("hostname")
    except Exception as e:
        logger.debug("Unable to set verified-access log host: %s" % e)


def process_eks_logs(aws_attributes, metadata):
    log_stream = aws_attributes.get_log_stream()
    if log_stream.startswith("kube-apiserver-audit-"):
        metadata[DD_SOURCE] = "kubernetes.audit"
    elif log_stream.startswith("kube-scheduler-"):
        metadata[DD_SOURCE] = "kube_scheduler"
    elif log_stream.startswith("kube-apiserver-"):
        metadata[DD_SOURCE] = "kube-apiserver"
    elif log_stream.startswith("kube-controller-manager-"):
        metadata[DD_SOURCE] = "kube-controller-manager"
    elif log_stream.startswith("authenticator-"):
        metadata[DD_SOURCE] = "aws-iam-authenticator"
    # In case the conditions above don't match we maintain eks as the source


def get_state_machine_arn(message):
    if message.get("execution_arn") is not None:
        execution_arn = message["execution_arn"]
        arn_tokens = re.split(r"[:/\\]", execution_arn)
        arn_tokens[5] = "stateMachine"
        return ":".join(arn_tokens[:7])
    return ""


# Lambda logs can be from either default or customized log group
def process_lambda_logs(aws_attributes, context, metadata):
    log_group = aws_attributes.get_log_group()
    log_stream = aws_attributes.get_log_stream()

    lower_cased_lambda_function_name = get_lower_cased_lambda_function_name(
        log_stream, log_group
    )

    if lower_cased_lambda_function_name is None:
        return

    # Split the arn of the forwarder to extract the prefix
    arn_parts = context.invoked_function_arn.split("function:")
    if len(arn_parts) > 0:
        arn_prefix = arn_parts[0]
        # Rebuild the arn with the lowercased function name
        lower_cased_lambda_arn = (
            arn_prefix + "function:" + lower_cased_lambda_function_name
        )
        # Add the lowe_rcased arn as a log attribute
        aws_attributes.set_lambda_arn(lower_cased_lambda_arn)
        env_tag_exists = (
            metadata[DD_CUSTOM_TAGS].startswith("env:")
            or ",env:" in metadata[DD_CUSTOM_TAGS]
        )
        # If there is no env specified, default to env:none
        if not env_tag_exists:
            metadata[DD_CUSTOM_TAGS] += ",env:none"


# The lambda function name can be inferred from either a customized logstream name, or a loggroup name
def get_lower_cased_lambda_function_name(log_stream, log_group):
    # function name parsed from logstream is preferred for handling some edge cases
    function_name = get_lambda_function_name_from_logstream_name(log_stream)
    if function_name is None:
        log_group_parts = log_group.split("/lambda/")
        if len(log_group_parts) > 1:
            function_name = log_group_parts[1]
        else:
            return None
    return function_name.lower()
