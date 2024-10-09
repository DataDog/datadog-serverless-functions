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


class AwsLogsHandler:
    def __init__(self, context, metadata, cache_layer):
        self.context = context
        self.metadata = metadata
        self.cache_layer = cache_layer
        self.aws_attributes = None

    def handle(self, event):
        # Get logs
        logs = self.extract_logs(event)
        # Build aws attributes
        self.aws_attributes = AwsAttributes(
            logs.get("logGroup"),
            logs.get("logStream"),
            logs.get("logEvents"),
            logs.get("owner"),
        )
        # Set account and region from lambda function ARN
        self.set_account_region()
        # Set the source on the logs
        self.set_source(event)
        # Add custom tags from cache
        self.add_cloudwatch_tags_from_cache()
        # Set service from custom tags, which may include the tags set on the log group
        # Returns DD_SOURCE by default
        add_service_tag(self.metadata)
        # Set host as log group where cloudwatch is source
        self.set_host()
        # For Lambda logs we want to extract the function name,
        # then rebuild the arn of the monitored lambda using that name.
        if self.metadata[DD_SOURCE] == str(AwsEventSource.LAMBDA):
            self.process_lambda_logs()
        # The EKS log group contains various sources from the K8S control plane.
        # In order to have these automatically trigger the correct pipelines they
        # need to send their events with the correct log source.
        if self.metadata[DD_SOURCE] == str(AwsEventSource.EKS):
            self.process_eks_logs()
        # Create and send structured logs to Datadog
        for log in logs["logEvents"]:
            yield merge_dicts(log, self.aws_attributes.to_dict())

    @staticmethod
    def extract_logs(event):
        with gzip.GzipFile(
            fileobj=BytesIO(base64.b64decode(event["awslogs"]["data"]))
        ) as decompress_stream:
            # Reading line by line avoid a bug where gzip would take a very long
            # time (>5min) for file around 60MB gzipped
            data = b"".join(BufferedReader(decompress_stream))
        return json.loads(data)

    def set_account_region(self):
        try:
            self.aws_attributes.set_account_region(self.context.invoked_function_arn)
        except Exception as e:
            logger.error(
                "Unable to set account and region from lambda function ARN: %s" % e
            )

    def set_source(self, event):
        log_group = self.aws_attributes.get_log_group()
        log_stream = self.aws_attributes.get_log_stream()
        source = log_group if log_group else str(AwsEventSource.CLOUDWATCH)
        # Use the logStream to identify if this is a CloudTrail, TransitGateway, or Bedrock event
        # i.e. 123456779121_CloudTrail_us-east-1
        if str(AwsCwEventSourcePrefix.CLOUDTRAIL) in log_stream:
            source = str(AwsEventSource.CLOUDTRAIL)
        if str(AwsCwEventSourcePrefix.TRANSITGATEWAY) in log_stream:
            source = str(AwsEventSource.TRANSITGATEWAY)
        if str(AwsCwEventSourcePrefix.BEDROCK) in log_stream:
            source = str(AwsEventSource.BEDROCK)
        self.metadata[DD_SOURCE] = parse_event_source(event, source)

        # Special handling for customized log group of Lambda functions
        # Multiple Lambda functions can share one single customized log group
        # Need to parse logStream name to determine whether it is a Lambda function
        if is_lambda_customized_log_group(log_stream):
            self.metadata[DD_SOURCE] = str(AwsEventSource.LAMBDA)

    def add_cloudwatch_tags_from_cache(self):
        log_group_arn = self.aws_attributes.get_log_group_arn()
        formatted_tags = self.cache_layer.get_cloudwatch_log_group_tags_cache().get(
            log_group_arn
        )
        if len(formatted_tags) > 0:
            self.metadata[DD_CUSTOM_TAGS] = (
                ",".join(formatted_tags)
                if not self.metadata[DD_CUSTOM_TAGS]
                else self.metadata[DD_CUSTOM_TAGS] + "," + ",".join(formatted_tags)
            )

    def set_host(self):
        if src := self.metadata.get(DD_SOURCE, None):
            metadata_source = AwsEventSource._value2member_map_.get(src)
        else:
            metadata_source = AwsEventSource.CLOUDWATCH
        metadata_host = self.metadata.get(DD_HOST, None)
        log_group = self.aws_attributes.get_log_group()

        if metadata_host is None:
            self.metadata[DD_HOST] = log_group

        match metadata_source:
            case AwsEventSource.CLOUDWATCH:
                self.metadata[DD_HOST] = log_group
            case AwsEventSource.APPSYNC:
                self.metadata[DD_HOST] = log_group.split("/")[-1]
            case AwsEventSource.VERIFIED_ACCESS:
                self.handle_verified_access_source()
            case AwsEventSource.STEPFUNCTION:
                self.handle_step_function_source()
            # When parsing rds logs, use the cloudwatch log group name to derive the
            # rds instance name, and add the log name of the stream ingested
            case (
                AwsEventSource.RDS
                | AwsEventSource.MYSQL
                | AwsEventSource.MARIADB
                | AwsEventSource.POSTGRESQL
            ):
                self.handle_rds_source()

    def handle_rds_source(self):
        match = RDS_REGEX.match(self.aws_attributes.get_log_group())
        if match is not None:
            self.metadata[DD_HOST] = match.group("host")
            self.metadata[DD_CUSTOM_TAGS] = (
                self.metadata[DD_CUSTOM_TAGS] + ",logname:" + match.group("name")
            )

    def handle_step_function_source(self):
        if not self.aws_attributes.get_log_stream().startswith("states/"):
            return

        state_machine_arn = self.get_state_machine_arn()
        if not state_machine_arn:
            return

        self.metadata[DD_HOST] = state_machine_arn
        formatted_stepfunctions_tags = (
            self.cache_layer.get_step_functions_tags_cache().get(state_machine_arn)
        )
        if len(formatted_stepfunctions_tags) > 0:
            self.metadata[DD_CUSTOM_TAGS] = (
                ",".join(formatted_stepfunctions_tags)
                if not self.metadata[DD_CUSTOM_TAGS]
                else self.metadata[DD_CUSTOM_TAGS]
                + ","
                + ",".join(formatted_stepfunctions_tags)
            )

        if os.environ.get("DD_STEP_FUNCTIONS_TRACE_ENABLED", "false").lower() == "true":
            self.metadata[DD_CUSTOM_TAGS] = ",".join(
                [self.metadata.get(DD_CUSTOM_TAGS, [])]
                + ["dd_step_functions_trace_enabled:true"]
            )

    def handle_verified_access_source(self):
        try:
            message = json.loads(self.aws_attributes.get_log_events()[0].get("message"))
            self.metadata[DD_HOST] = (
                message.get("http_request").get("url").get("hostname")
            )
        except Exception as e:
            logger.debug("Unable to set verified-access log host: %s" % e)

    def process_eks_logs(self):
        log_stream = self.aws_attributes.get_log_stream()
        if log_stream.startswith("kube-apiserver-audit-"):
            self.metadata[DD_SOURCE] = "kubernetes.audit"
        elif log_stream.startswith("kube-scheduler-"):
            self.metadata[DD_SOURCE] = "kube_scheduler"
        elif log_stream.startswith("kube-apiserver-"):
            self.metadata[DD_SOURCE] = "kube-apiserver"
        elif log_stream.startswith("kube-controller-manager-"):
            self.metadata[DD_SOURCE] = "kube-controller-manager"
        elif log_stream.startswith("authenticator-"):
            self.metadata[DD_SOURCE] = "aws-iam-authenticator"
        # In case the conditions above don't match we maintain eks as the source

    def get_state_machine_arn(self):
        try:
            message = json.loads(self.aws_attributes.get_log_events()[0].get("message"))
            if message.get("execution_arn") is not None:
                execution_arn = message["execution_arn"]
                arn_tokens = re.split(r"[:/\\]", execution_arn)
                arn_tokens[5] = "stateMachine"
                return ":".join(arn_tokens[:7])
        except Exception as e:
            logger.debug("Unable to get state_machine_arn: %s" % e)
        return ""

    # Lambda logs can be from either default or customized log group
    def process_lambda_logs(self):
        lower_cased_lambda_function_name = self.get_lower_cased_lambda_function_name()

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
            self.aws_attributes.set_lambda_arn(lower_cased_lambda_arn)
            env_tag_exists = (
                self.metadata[DD_CUSTOM_TAGS].startswith("env:")
                or ",env:" in self.metadata[DD_CUSTOM_TAGS]
            )
            # If there is no env specified, default to env:none
            if not env_tag_exists:
                self.metadata[DD_CUSTOM_TAGS] += ",env:none"

    # The lambda function name can be inferred from either a customized logstream name, or a loggroup name
    def get_lower_cased_lambda_function_name(self):
        # function name parsed from logstream is preferred for handling some edge cases
        function_name = get_lambda_function_name_from_logstream_name(
            self.aws_attributes.get_log_stream()
        )
        if function_name is None:
            log_group_parts = self.aws_attributes.get_log_group().split("/lambda/")
            if len(log_group_parts) > 1:
                function_name = log_group_parts[1]
            else:
                return None
        return function_name.lower()
