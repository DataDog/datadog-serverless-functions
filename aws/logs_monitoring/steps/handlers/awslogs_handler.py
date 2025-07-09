import base64
import gzip
import json
import logging
import os
import re
from io import BufferedReader, BytesIO

from customized_log_group import (
    get_lambda_function_name_from_logstream_name,
    is_lambda_customized_log_group,
    is_step_functions_log_group,
)
from settings import DD_CUSTOM_TAGS, DD_HOST, DD_SOURCE
from steps.common import (
    add_service_tag,
    generate_metadata,
    merge_dicts,
    parse_event_source,
)
from steps.enums import AwsCwEventSourcePrefix, AwsEventSource
from steps.handlers.aws_attributes import AwsAttributes

logger = logging.getLogger()
logger.setLevel(logging.getLevelName(os.environ.get("DD_LOG_LEVEL", "INFO").upper()))


class AwsLogsHandler:
    def __init__(self, context, cache_layer):
        self.context = context
        self.cache_layer = cache_layer

    def handle(self, event):
        # Generate metadata
        metadata = generate_metadata(self.context)
        # Get logs
        logs = self.extract_logs(event)
        # Build aws attributes
        aws_attributes = AwsAttributes(
            self.context,
            logs.get("logGroup"),
            logs.get("logStream"),
            logs.get("logEvents"),
            logs.get("owner"),
        )
        # Set account and region from lambda function ARN
        self.set_account_region(aws_attributes)
        # Set the source on the logs
        if metadata.get(DD_SOURCE) is None:
            self.set_source(event, metadata, aws_attributes)

        # Add custom tags from cache
        self.add_cloudwatch_tags_from_cache(metadata, aws_attributes)
        # Set service from custom tags, which may include the tags set on the log group
        # Returns DD_SOURCE by default
        add_service_tag(metadata)
        # Set host as log group where cloudwatch is source
        self.set_host(metadata, aws_attributes)
        # For Lambda logs we want to extract the function name,
        # then rebuild the arn of the monitored lambda using that name.
        if metadata[DD_SOURCE] == str(AwsEventSource.LAMBDA):
            self.process_lambda_logs(metadata, aws_attributes)
        # Create and send structured logs to Datadog
        for log in logs["logEvents"]:
            merged = merge_dicts(log, aws_attributes.to_dict())
            yield merge_dicts(merged, metadata)

    @staticmethod
    def extract_logs(event):
        with gzip.GzipFile(
            fileobj=BytesIO(base64.b64decode(event["awslogs"]["data"]))
        ) as decompress_stream:
            # Reading line by line avoid a bug where gzip would take a very long
            # time (>5min) for file around 60MB gzipped
            data = b"".join(BufferedReader(decompress_stream))
        return json.loads(data)

    def set_account_region(self, aws_attributes):
        try:
            aws_attributes.set_account_region(self.context.invoked_function_arn)
        except Exception as e:
            logger.error(
                "Unable to set account and region from lambda function ARN: %s" % e
            )

    def set_source(self, event, metadata, aws_attributes):
        log_group = aws_attributes.get_log_group()
        log_stream = aws_attributes.get_log_stream()
        source = log_group if log_group else str(AwsEventSource.CLOUDWATCH)
        # Use the logStream to identify if this is a CloudTrail event
        # i.e. 123456779121_CloudTrail_us-east-1
        if str(AwsCwEventSourcePrefix.CLOUDTRAIL) in log_stream:
            source = str(AwsEventSource.CLOUDTRAIL)
        metadata[DD_SOURCE] = parse_event_source(event, source)

        # Special handling for customized log group of Lambda Functions and Step Functions
        # Multiple functions can share one single customized log group. Need to parse logStream name to determine
        # Need to place the handling of customized log group at the bottom so that it can correct the source for some edge cases
        if is_lambda_customized_log_group(log_stream):
            metadata[DD_SOURCE] = str(AwsEventSource.LAMBDA)
        # Regardless of whether the log group is customized, the corresponding log stream starts with 'states/'."
        if is_step_functions_log_group(log_stream):
            metadata[DD_SOURCE] = str(AwsEventSource.STEPFUNCTION)

    def add_cloudwatch_tags_from_cache(self, metadata, aws_attributes):
        log_group_arn = aws_attributes.get_log_group_arn()
        formatted_tags = self.cache_layer.get_cloudwatch_log_group_tags_cache().get(
            log_group_arn
        )
        if len(formatted_tags) > 0:
            metadata[DD_CUSTOM_TAGS] = (
                ",".join(formatted_tags)
                if not metadata[DD_CUSTOM_TAGS]
                else metadata[DD_CUSTOM_TAGS] + "," + ",".join(formatted_tags)
            )

    def set_host(self, metadata, aws_attributes):
        if src := metadata.get(DD_SOURCE, None):
            metadata_source = AwsEventSource._value2member_map_.get(src)
        else:
            metadata_source = AwsEventSource.CLOUDWATCH
        metadata_host = metadata.get(DD_HOST, None)
        log_group = aws_attributes.get_log_group()

        if metadata_host is None:
            metadata[DD_HOST] = log_group

        match metadata_source:
            case AwsEventSource.CLOUDWATCH:
                metadata[DD_HOST] = log_group
            case AwsEventSource.STEPFUNCTION:
                self.handle_step_function_source(metadata, aws_attributes)

    def handle_verified_access_source(self, metadata, aws_attributes):
        try:
            message = json.loads(aws_attributes.get_log_events()[0].get("message"))
            metadata[DD_HOST] = message.get("http_request").get("url").get("hostname")
        except Exception as e:
            logger.debug("Unable to set verified-access log host: %s" % e)

    def handle_step_function_source(self, metadata, aws_attributes):
        state_machine_arn = self.get_state_machine_arn(aws_attributes)
        if not state_machine_arn:
            return

        metadata[DD_HOST] = state_machine_arn
        formatted_stepfunctions_tags = (
            self.cache_layer.get_step_functions_tags_cache().get(state_machine_arn)
        )
        if len(formatted_stepfunctions_tags) > 0:
            metadata[DD_CUSTOM_TAGS] = (
                ",".join(formatted_stepfunctions_tags)
                if not metadata[DD_CUSTOM_TAGS]
                else metadata[DD_CUSTOM_TAGS]
                + ","
                + ",".join(formatted_stepfunctions_tags)
            )

        if os.environ.get("DD_STEP_FUNCTIONS_TRACE_ENABLED", "false").lower() == "true":
            metadata[DD_CUSTOM_TAGS] = ",".join(
                [metadata.get(DD_CUSTOM_TAGS, [])]
                + ["dd_step_functions_trace_enabled:true"]
            )

    def get_state_machine_arn(self, aws_attributes):
        try:
            message = json.loads(aws_attributes.get_log_events()[0].get("message"))
            if message.get("execution_arn") is not None:
                execution_arn = message["execution_arn"]
                arn_tokens = re.split(r"[:/\\]", execution_arn)
                arn_tokens[5] = "stateMachine"
                return ":".join(arn_tokens[:7])
        except Exception as e:
            logger.debug("Unable to get state_machine_arn: %s" % e)
        return ""

    # Lambda logs can be from either default or customized log group
    def process_lambda_logs(self, metadata, aws_attributes):
        lower_cased_lambda_function_name = self.get_lower_cased_lambda_function_name(
            aws_attributes
        )

        if lower_cased_lambda_function_name is None:
            return

        # Split the arn of the forwarder to extract the prefix
        arn_parts = self.context.invoked_function_arn.split("function:")
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
    def get_lower_cased_lambda_function_name(self, aws_attributes):
        # function name parsed from logstream is preferred for handling some edge cases
        function_name = get_lambda_function_name_from_logstream_name(
            aws_attributes.get_log_stream()
        )
        if function_name is None:
            log_group_parts = aws_attributes.get_log_group().split("/lambda/")
            if len(log_group_parts) > 1:
                function_name = log_group_parts[1]
            else:
                return None
        return function_name.lower()
