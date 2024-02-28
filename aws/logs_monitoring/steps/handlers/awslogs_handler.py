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
from caching.cloudwatch_log_group_cache import CloudwatchLogGroupTagsCache
from caching.step_functions_cache import StepFunctionsTagsCache
from settings import (
    DD_SOURCE,
    DD_HOST,
    DD_CUSTOM_TAGS,
)

RDS_REGEX = re.compile("/aws/rds/(instance|cluster)/(?P<host>[^/]+)/(?P<name>[^/]+)")

# Store the cache in the global scope so that it will be reused as long as
# the log forwarder Lambda container is running
account_step_functions_tags_cache = StepFunctionsTagsCache()
account_cw_logs_tags_cache = CloudwatchLogGroupTagsCache()

logger = logging.getLogger()
logger.setLevel(logging.getLevelName(os.environ.get("DD_LOG_LEVEL", "INFO").upper()))


# Handle CloudWatch logs
def awslogs_handler(event, context, metadata):
    # Get logs
    logs = extract_logs(event)
    # Build aws attributes
    aws_attributes = init_attributes(logs)
    # Set the source on the logs
    set_source(event, metadata, logs)
    # Add custom tags from cache
    add_cloudwatch_tags_from_cache(metadata, logs)
    # Set service from custom tags, which may include the tags set on the log group
    # Returns DD_SOURCE by default
    add_service_tag(metadata)
    # Set host as log group where cloudwatch is source
    set_host(metadata, logs, aws_attributes)
    # For Lambda logs we want to extract the function name,
    # then rebuild the arn of the monitored lambda using that name.
    if metadata[DD_SOURCE] == "lambda":
        process_lambda_logs(logs, aws_attributes, context, metadata)
    # The EKS log group contains various sources from the K8S control plane.
    # In order to have these automatically trigger the correct pipelines they
    # need to send their events with the correct log source.
    if metadata[DD_SOURCE] == "eks":
        process_eks_logs(logs, metadata)

    # Create and send structured logs to Datadog
    for log in logs["logEvents"]:
        yield merge_dicts(log, aws_attributes)


def extract_logs(event):
    with gzip.GzipFile(
        fileobj=BytesIO(base64.b64decode(event["awslogs"]["data"]))
    ) as decompress_stream:
        # Reading line by line avoid a bug where gzip would take a very long
        # time (>5min) for file around 60MB gzipped
        data = b"".join(BufferedReader(decompress_stream))
    return json.loads(data)


def set_source(event, metadata, logs):
    source = logs.get("logGroup", "cloudwatch")
    # Use the logStream to identify if this is a CloudTrail, TransitGateway, or Bedrock event
    # i.e. 123456779121_CloudTrail_us-east-1
    if "_CloudTrail_" in logs["logStream"]:
        source = "cloudtrail"
    if "tgw-attach" in logs["logStream"]:
        source = "transitgateway"
    if logs["logStream"] == "aws/bedrock/modelinvocations":
        source = "bedrock"
    metadata[DD_SOURCE] = parse_event_source(event, source)

    # Special handling for customized log group of Lambda functions
    # Multiple Lambda functions can share one single customized log group
    # Need to parse logStream name to determine whether it is a Lambda function
    if is_lambda_customized_log_group(logs["logStream"]):
        metadata[DD_SOURCE] = "lambda"


def init_attributes(logs):
    return {
        "aws": {
            "awslogs": {
                "logGroup": logs["logGroup"],
                "logStream": logs["logStream"],
                "owner": logs["owner"],
            }
        }
    }


def add_cloudwatch_tags_from_cache(metadata, logs):
    formatted_tags = account_cw_logs_tags_cache.get(logs["logGroup"])
    if len(formatted_tags) > 0:
        metadata[DD_CUSTOM_TAGS] = (
            ",".join(formatted_tags)
            if not metadata[DD_CUSTOM_TAGS]
            else metadata[DD_CUSTOM_TAGS] + "," + ",".join(formatted_tags)
        )


def set_host(metadata, logs, aws_attributes):
    if metadata[DD_SOURCE] == "cloudwatch" or metadata.get(DD_HOST, None) == None:
        metadata[DD_HOST] = aws_attributes["aws"]["awslogs"]["logGroup"]

    if metadata[DD_SOURCE] == "appsync":
        metadata[DD_HOST] = aws_attributes["aws"]["awslogs"]["logGroup"].split("/")[-1]

    if metadata[DD_SOURCE] == "verified-access":
        try:
            message = json.loads(logs["logEvents"][0]["message"])
            metadata[DD_HOST] = message["http_request"]["url"]["hostname"]
        except Exception as e:
            logger.debug("Unable to set verified-access log host: %s" % e)

    if metadata[DD_SOURCE] == "stepfunction" and logs["logStream"].startswith(
        "states/"
    ):
        state_machine_arn = ""
        try:
            state_machine_arn = get_state_machine_arn(
                json.loads(logs["logEvents"][0]["message"])
            )
            if state_machine_arn:  # not empty
                metadata[DD_HOST] = state_machine_arn
        except Exception as e:
            logger.debug(
                "Unable to set stepfunction host or get state_machine_arn: %s" % e
            )

        formatted_stepfunctions_tags = account_step_functions_tags_cache.get(
            state_machine_arn
        )
        if len(formatted_stepfunctions_tags) > 0:
            metadata[DD_CUSTOM_TAGS] = (
                ",".join(formatted_stepfunctions_tags)
                if not metadata[DD_CUSTOM_TAGS]
                else metadata[DD_CUSTOM_TAGS]
                + ","
                + ",".join(formatted_stepfunctions_tags)
            )

    # When parsing rds logs, use the cloudwatch log group name to derive the
    # rds instance name, and add the log name of the stream ingested
    if metadata[DD_SOURCE] in ["rds", "mariadb", "mysql", "postgresql"]:
        match = RDS_REGEX.match(logs["logGroup"])
        if match is not None:
            metadata[DD_HOST] = match.group("host")
            metadata[DD_CUSTOM_TAGS] = (
                metadata[DD_CUSTOM_TAGS] + ",logname:" + match.group("name")
            )


def process_eks_logs(logs, metadata):
    if logs["logStream"].startswith("kube-apiserver-audit-"):
        metadata[DD_SOURCE] = "kubernetes.audit"
    elif logs["logStream"].startswith("kube-scheduler-"):
        metadata[DD_SOURCE] = "kube_scheduler"
    elif logs["logStream"].startswith("kube-apiserver-"):
        metadata[DD_SOURCE] = "kube-apiserver"
    elif logs["logStream"].startswith("kube-controller-manager-"):
        metadata[DD_SOURCE] = "kube-controller-manager"
    elif logs["logStream"].startswith("authenticator-"):
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
def process_lambda_logs(logs, aws_attributes, context, metadata):
    lower_cased_lambda_function_name = get_lower_cased_lambda_function_name(logs)
    if lower_cased_lambda_function_name is None:
        return
    # Split the arn of the forwarder to extract the prefix
    arn_parts = context.invoked_function_arn.split("function:")
    if len(arn_parts) > 0:
        arn_prefix = arn_parts[0]
        # Rebuild the arn with the lowercased function name
        lower_cased_lambda__arn = (
            arn_prefix + "function:" + lower_cased_lambda_function_name
        )
        # Add the lowe_rcased arn as a log attribute
        arn_attributes = {"lambda": {"arn": lower_cased_lambda__arn}}
        aws_attributes = merge_dicts(aws_attributes, arn_attributes)
        env_tag_exists = (
            metadata[DD_CUSTOM_TAGS].startswith("env:")
            or ",env:" in metadata[DD_CUSTOM_TAGS]
        )
        # If there is no env specified, default to env:none
        if not env_tag_exists:
            metadata[DD_CUSTOM_TAGS] += ",env:none"


# The lambda function name can be inferred from either a customized logstream name, or a loggroup name
def get_lower_cased_lambda_function_name(logs):
    logstream_name = logs["logStream"]
    # function name parsed from logstream is preferred for handling some edge cases
    function_name = get_lambda_function_name_from_logstream_name(logstream_name)
    if function_name is None:
        log_group_parts = logs["logGroup"].split("/lambda/")
        if len(log_group_parts) > 1:
            function_name = log_group_parts[1]
        else:
            return None
    return function_name.lower()
