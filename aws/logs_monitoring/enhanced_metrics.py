import re
import os
import logging

from collections import defaultdict
from time import time


import boto3
from botocore.exceptions import ClientError

from datadog_lambda.metric import lambda_metric


ILLEGAL_TAG_CHARACTERS = {":", "/", "-"}
REPLACEMENT_CHARACTER = "_"
ENHANCED_METRICS_NAMESPACE_PREFIX = "aws.lambda.enhanced"

# Latest Lambda pricing per https://aws.amazon.com/lambda/pricing/
BASE_LAMBDA_INVOCATION_PRICE = 0.0000002
LAMBDA_PRICE_PER_GB_SECOND = 0.0000166667

ESTIMATED_COST_METRIC_NAME = "estimated_cost"

GET_RESOURCES_LAMBDA_FILTER = "lambda"

FETCH_CUSTOM_TAGS_ENV_VAR_NAME = "DD_FETCH_CUSTOM_TAGS"
LOG_LEVEL_ENV_VAR_NAME = "DD_LOG_LEVEL"

resource_tagging_client = boto3.client("resourcegroupstaggingapi")

log = logging.getLogger()
log.setLevel(logging.INFO)

def set_log_level_to_env_var:
    """Reads the log level env var and sets the log level according to its value

    Defaults to INFO level
    """
    env_var_log_level = os.environ.get(LOG_LEVEL_ENV_VAR_NAME, "").lower()
    if env_var_log_level == "debug":
        log.setLevel(logging.DEBUG)
    if env_var_log_level == "error":
        log.setLevel(logging.ERROR)
    if env_var_log_level == "warn" or env_var_log_level == "warning":
        log.setLevel(logging.WARN)

set_log_level_to_env_var()


def should_fetch_custom_tags():
    """Checks the env var to determine if the customer has opted-in to fetching custom tags
    """
    env_var_value = os.environ.get(FETCH_CUSTOM_TAGS_ENV_VAR_NAME)
    return env_var_value and env_var_value.lower() == "true"


def sanitize_aws_tag_string(raw_string):
    """Convert banned characters to underscores
    """
    sanitized_string = ""
    for character in raw_string:
        if character in ILLEGAL_TAG_CHARACTERS:
            sanitized_string += REPLACEMENT_CHARACTER
            continue
        sanitized_string += character
    return sanitized_string


def get_dd_tag_string_from_aws_dict(aws_key_value_tag_dict):
    """Converts the AWS dict tag format to the dd key:value string format

    Args:
        aws_key_value_tag_dict (dict): the dict the GetResources endpoint returns for a tag
            ex: { "Key": "creator", "Value": "swf"}

    Returns:
        key:value colon-separated string built from the dict
            ex: "creator:swf"
    """
    key = sanitize_aws_tag_string(aws_key_value_tag_dict["Key"])
    value = sanitize_aws_tag_string(aws_key_value_tag_dict["Value"])
    return "{}:{}".format(key, value)


def parse_get_resources_response_for_tags_by_arn(get_resources_page):
    """Parses a page of GetResources response for the mapping from ARN to tags


    """
    tags_by_arn = defaultdict(list)

    aws_resouce_tag_mappings = get_resources_page["ResourceTagMappingList"]
    for aws_resource_tag_mapping in aws_resouce_tag_mappings:
        function_arn = aws_resource_tag_mapping["ResourceARN"]
        raw_aws_tags = aws_resource_tag_mapping["Tags"]
        tags = map(get_dd_tag_string_from_aws_dict, raw_aws_tags)

        tags_by_arn[function_arn] += tags

    return tags_by_arn


def build_tags_by_arn_cache():
    """Makes API calls to GetResources to get the live tags of the account's Lambda functions

    Returns an empty dict instead of fetching custom tags if the tag fetch env variable is not set to true

    Returns:
        tags_by_arn_cache (dict<str, str[]>): each Lambda's tags in a dict keyed by ARN
    """
    # If the custom tag fetch env var is not set to true do not fetch; return an empty dict
    if not should_fetch_custom_tags():
        log.debug(
            "Not fetching custom tags because the environment variable %s is not set to true",
            FETCH_CUSTOM_TAGS_ENV_VAR_NAME,
        )
        return {}

    tags_by_arn_cache = {}
    get_resources_paginator = resource_tagging_client.get_paginator("get_resources")

    try:
        for page in get_resources_paginator.paginate(
            ResourceTypeFilters=[GET_RESOURCES_LAMBDA_FILTER], ResourcesPerPage=100
        ):
            lambda_metric(
                "{}.get_resources_api_calls".format(ENHANCED_METRICS_NAMESPACE_PREFIX),
                1,
            )
            page_tags_by_arn = parse_get_resources_response_for_tags_by_arn(page)
            tags_by_arn_cache.update(page_tags_by_arn)

    except ClientError:
        log.exception(
            "Encountered a ClientError when trying to fetch tags. You may need to give "
            "this Lambda's role permission to use the Resource Groups Tagging API GetResources method"
        )

    log.debug(
        "Built this tags cache from GetResources API calls: %s", tags_by_arn_cache
    )

    return tags_by_arn_cache


class LambdaTagsCache(object):
    def __init__(self, tags_ttl_seconds=3600):
        self.tags_ttl_seconds = tags_ttl_seconds

        self.tags_by_arn = {}
        self.last_tags_fetch_time = 0

    def _fetch_tags(self):
        """Populate the tags in the cache by making calls to GetResources
        """
        self.tags_by_arn = build_tags_by_arn_cache()
        self.last_tags_fetch_time = time()

    def _are_tags_out_of_date(self):
        """Returns bool for whether the tag fetch TTL has expired
        """
        earliest_time_to_refetch_tags = (
            self.last_tags_fetch_time + self.tags_ttl_seconds
        )
        return time() > earliest_time_to_refetch_tags

    def get_lambda_tags(self, resource_arn):
        """Get the tags for the Lambda function from the cache

        Will refetch the tags if they are out of date

        Returns:
            lambda_tags (str[]): the list of "key:value" Datadog tag strings
        """
        if self._are_tags_out_of_date():
            self._fetch_tags()

        function_tags = self.tags_by_arn.get(resource_arn, [])

        return function_tags

# Store the cache in the global scope so that it will be reused as long as
# the log forwarder Lambda container is running
account_lambda_tags_cache = LambdaTagsCache()


class DatadogMetricPoint(object):
    """Holds a datapoint's data so that it can be prepared for submission to DD

    Properties:
        name (str): metric name, with namespace
        value (int | float): the datapoint's value

    """

    def __init__(self, name, value, timestamp=None, tags=[]):
        self.name = name
        self.value = value
        self.tags = tags
        self.timestamp = timestamp

    def add_tags(self, tags):
        """Add tags to this metric

        Args:
            tags (str[]): list of tags to add to this metric
        """
        self.tags += tags

    def set_timestamp(self, timestamp):
        """Set the metric's timestamp

        Args:
            timestamp (int): Unix timestamp of this metric
        """
        self.timestamp = timestamp

    def submit_to_dd(self):
        """Submit this metric to the Datadog API
        """
        timestamp = self.timestamp
        if not timestamp:
            timestamp = time()

        log.debug("Submitting metric {} {} {}".format(self.name, self.value, self.tags))
        lambda_metric(self.name, self.value, timestamp=timestamp, tags=self.tags)


def parse_and_submit_enhanced_metrics(logs):
    """Parses enhanced metrics from REPORT logs and submits them to DD with tags

    Args:
        logs (dict<str, multiple types>[]): the logs parsed from the event in the split method
            See docstring below for an example.
    """
    # Wrap everything in try/catch to prevent failing the Lambda on enhanced metrics
    try:
        enhanced_metrics = generate_enhanced_lambda_metrics(logs, account_lambda_tags_cache)
        for enhanced_metric in enhanced_metrics:
            enhanced_metric.submit_to_dd()
    except Exception:
        log.exception("Encountered an error while trying to parse and submit enhanced metrics")


def generate_enhanced_lambda_metrics(logs, tags_cache):
    """Parses Lambda logs for enhanced Lambda metrics and tags

    Args:
        logs (dict<str, multiple types>[]): the logs parsed from the event in the split method
            Ex: [{
                    "id": "34988208851106313984209006125707332605649155257376768001",
                    "timestamp": 1568925546641,
                    "message": "END RequestId: 2f676573-c16b-4207-993a-51fb960d73e2\\n",
                    "aws": {
                        "awslogs": {
                            "logGroup": "/aws/lambda/function_log_generator",
                            "logStream": "2019/09/19/[$LATEST]0225597e48f74a659916f0e482df5b92",
                            "owner": "172597598159"
                        },
                        "function_version": "$LATEST",
                        "invoked_function_arn": "arn:aws:lambda:us-east-1:172597598159:function:collect_logs_datadog_demo"
                    },
                    "lambda": {
                        "arn": "arn:aws:lambda:us-east-1:172597598159:function:function_log_generator"
                    },
                    "ddsourcecategory": "aws",
                    "ddtags": "env:demo,python_version:3.6,role:lambda,forwardername:collect_logs_datadog_demo,memorysize:128,forwarder_version:2.0.0,functionname:function_log_generator,env:none",
                    "ddsource": "lambda",
                    "service": "function_log_generator",
                    "host": "arn:aws:lambda:us-east-1:172597598159:function:function_log_generator"
                }]
        tags_cache (LambdaTagsCache): used to apply the Lambda's custom tags to the metrics

    Returns:
        DatadogMetricPoint[], where each metric has all of its tags
    """
    enhanced_metrics = []
    for log in logs:
        log_function_arn = log.get("lambda", {}).get("arn")
        log_message = log.get("message")
        timestamp = log.get("timestamp")

        # If the log dict is missing any of this data it's not a Lambda REPORT log and we move on
        if not all(
            (
                log_function_arn,
                log_message,
                timestamp,
                log_message.startswith("REPORT"),
            )
        ):
            continue

        parsed_metrics = parse_metrics_from_report_log(log_message)
        if not parsed_metrics:
            continue

        # Add the tags from ARN, custom tags cache, and env var
        tags_from_arn = parse_lambda_tags_from_arn(log_function_arn)
        lambda_custom_tags = tags_cache.get_lambda_tags(log_function_arn)
        # "ddtags" is the name of the key in the log event dict
        tags_from_env_var = log.get("ddtags").split(",") if log.get("ddtags") else []

        for parsed_metric in parsed_metrics:
            parsed_metric.add_tags(
                tags_from_arn + lambda_custom_tags + tags_from_env_var
            )
            # Submit the metric with the timestamp of the log event
            parsed_metric.set_timestamp(int(timestamp))

        enhanced_metrics += parsed_metrics

    return enhanced_metrics

# Names to use for metrics and for the named regex groups
REQUEST_ID_FIELD_NAME = "request_id"
DURATION_METRIC_NAME = "duration"
BILLED_DURATION_METRIC_NAME = "billed_duration"
MEMORY_ALLOCATED_FIELD_NAME = "memorysize"
MAX_MEMORY_USED_METRIC_NAME = "max_memory_used"

# Create named groups for each metric and tag so that we can access from the search result by name
REPORT_LOG_REGEX_SEARCH = (
    r"REPORT\s+"
    + r"RequestId:\s+(?P<{}>[\w-]+)\s+".format(REQUEST_ID_FIELD_NAME)
    + r"Duration:\s+(?P<{}>[\d\.]+)\s+ms\s+".format(DURATION_METRIC_NAME)
    + r"Billed\s+Duration:\s+(?P<{}>[\d\.]+)\s+ms\s+".format(
        BILLED_DURATION_METRIC_NAME
    )
    + r"Memory\s+Size:\s+(?P<{}>\d+)\s+MB\s+".format(MEMORY_ALLOCATED_FIELD_NAME)
    + r"Max\s+Memory\s+Used:\s+(?P<{}>\d+)\s+MB".format(MAX_MEMORY_USED_METRIC_NAME)
)

METRICS_TO_PARSE_FROM_REPORT = [
    DURATION_METRIC_NAME,
    BILLED_DURATION_METRIC_NAME,
    MAX_MEMORY_USED_METRIC_NAME,
]

TAGS_TO_PARSE_FROM_REPORT = [MEMORY_ALLOCATED_FIELD_NAME]

# Multiply the duration metrics by 1/1000 to convert ms to seconds
METRIC_ADJUSTMENT_FACTORS = {
    DURATION_METRIC_NAME: 0.001,
    BILLED_DURATION_METRIC_NAME: 0.001,
}


def parse_lambda_tags_from_arn(arn):
    """Generate the list of lambda tags based on the data in the arn

    Args:
        arn (str): Lambda ARN.
            ex: arn:aws:lambda:us-east-1:172597598159:function:my-lambda[:optional-version]
    """
    # Cap the number of times to split
    split_arn = arn.split(":")

    # If ARN includes version / alias at the end, drop it
    if len(split_arn) > 7:
        split_arn = split_arn[:7]

    _, _, _, region, account_id, _, function_name = split_arn

    return [
        "functionname:{}".format(function_name),
        "account_id:{}".format(account_id),
        "region:{}".format(region),
    ]


def parse_metrics_from_report_log(report_log_line):
    """Parses and returns metrics from the REPORT Lambda log

    Args:
        report_log_line (str): The REPORT log generated by Lambda
        EX: "REPORT RequestId: 814ba7cb-071e-4181-9a09-fa41db5bccad	Duration: 1711.87 ms	\
            Billed Duration: 1800 ms	Memory Size: 128 MB	Max Memory Used: 98 MB	\
            XRAY TraceId: 1-5d83c0ad-b8eb33a0b1de97d804fac890	SegmentId: 31255c3b19bd3637	Sampled: true"

    Returns:
        metrics - DatadogMetricPoint[]
    """
    regex_search = re.compile(REPORT_LOG_REGEX_SEARCH)
    regex_match = regex_search.search(report_log_line)

    if not regex_match:
        return []

    metric_tags = []

    for tag_key in TAGS_TO_PARSE_FROM_REPORT:
        metric_tags.append("{}:{}".format(tag_key, regex_match.group(tag_key)))

    metrics = []

    for metric_name in METRICS_TO_PARSE_FROM_REPORT:
        metric_point_value = float(regex_match.group(metric_name))
        # Multiply the duration metrics by 1/1000 to convert ms to seconds
        if metric_name in METRIC_ADJUSTMENT_FACTORS:
            metric_point_value *= METRIC_ADJUSTMENT_FACTORS[metric_name]

        dd_metric = DatadogMetricPoint(
            "{}.{}".format(ENHANCED_METRICS_NAMESPACE_PREFIX, metric_name),
            metric_point_value,
            tags=metric_tags[:],
        )
        metrics.append(dd_metric)

    estimated_cost_metric_point = DatadogMetricPoint(
        "{}.{}".format(ENHANCED_METRICS_NAMESPACE_PREFIX, ESTIMATED_COST_METRIC_NAME),
        calculate_estimated_cost(
            float(regex_match.group(BILLED_DURATION_METRIC_NAME)),
            float(regex_match.group(MEMORY_ALLOCATED_FIELD_NAME)),
        ),
        tags=metric_tags[:],
    )
    metrics.append(estimated_cost_metric_point)

    return metrics


def calculate_estimated_cost(billed_duration_ms, memory_allocated):
    """Returns the estimated cost in USD of a Lambda invocation

    Args:
        billed_duration (float | int): number of milliseconds this invocation is billed for
        memory_allocated (float | int): amount of memory in MB allocated to the function execution

    See https://aws.amazon.com/lambda/pricing/ for latest pricing
    """
    # Divide milliseconds by 1000 to get seconds
    gb_seconds = (billed_duration_ms / 1000.0) * (memory_allocated / 1024.0)

    return BASE_LAMBDA_INVOCATION_PRICE + gb_seconds * LAMBDA_PRICE_PER_GB_SECOND
