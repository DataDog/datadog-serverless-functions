# Unless explicitly stated otherwise all files in this repository are licensed
# under the Apache License Version 2.0.
# This product includes software developed at Datadog (https://www.datadoghq.com/).
# Copyright 2021 Datadog, Inc.
import os
import logging
import re
import datetime
from time import time

ENHANCED_METRICS_NAMESPACE_PREFIX = "aws.lambda.enhanced"

# Latest Lambda pricing per https://aws.amazon.com/lambda/pricing/
BASE_LAMBDA_INVOCATION_PRICE = 0.0000002
LAMBDA_PRICE_PER_GB_SECOND = 0.0000166667

ESTIMATED_COST_METRIC_NAME = "estimated_cost"


# Names to use for metrics and for the named regex groups
REQUEST_ID_FIELD_NAME = "request_id"
DURATION_METRIC_NAME = "duration"
BILLED_DURATION_METRIC_NAME = "billed_duration"
MEMORY_ALLOCATED_FIELD_NAME = "memorysize"
MAX_MEMORY_USED_METRIC_NAME = "max_memory_used"
INIT_DURATION_METRIC_NAME = "init_duration"
TIMEOUTS_METRIC_NAME = "timeouts"
OUT_OF_MEMORY_METRIC_NAME = "out_of_memory"

# Create named groups for each metric and tag so that we can
# access the values from the search result by name
REPORT_LOG_REGEX = re.compile(
    r"REPORT\s+"
    + r"RequestId:\s+(?P<{}>[\w-]+)\s+".format(REQUEST_ID_FIELD_NAME)
    + r"Duration:\s+(?P<{}>[\d\.]+)\s+ms\s+".format(DURATION_METRIC_NAME)
    + r"Billed\s+Duration:\s+(?P<{}>[\d\.]+)\s+ms\s+".format(
        BILLED_DURATION_METRIC_NAME
    )
    + r"Memory\s+Size:\s+(?P<{}>\d+)\s+MB\s+".format(MEMORY_ALLOCATED_FIELD_NAME)
    + r"Max\s+Memory\s+Used:\s+(?P<{}>\d+)\s+MB".format(MAX_MEMORY_USED_METRIC_NAME)
    + r"(\s+Init\s+Duration:\s+(?P<{}>[\d\.]+)\s+ms)?".format(INIT_DURATION_METRIC_NAME)
)

TIMED_OUT_REGEX = re.compile(
    r"Task\stimed\sout\safter\s+(?P<{}>[\d\.]+)\s+seconds".format(TIMEOUTS_METRIC_NAME)
)

OUT_OF_MEMORY_ERROR_STRINGS = [
    "fatal error: runtime: out of memory",  # Go
    "java.lang.OutOfMemoryError",  # Java
    "JavaScript heap out of memory",  # Node
    "MemoryError",  # Python
    "failed to allocate memory (NoMemoryError)",  # Ruby
]

METRICS_TO_PARSE_FROM_REPORT = [
    DURATION_METRIC_NAME,
    BILLED_DURATION_METRIC_NAME,
    MAX_MEMORY_USED_METRIC_NAME,
    INIT_DURATION_METRIC_NAME,
]

# Multiply the duration metrics by 1/1000 to convert ms to seconds
METRIC_ADJUSTMENT_FACTORS = {
    DURATION_METRIC_NAME: 0.001,
    BILLED_DURATION_METRIC_NAME: 0.001,
    INIT_DURATION_METRIC_NAME: 0.001,
}

logger = logging.getLogger()
logger.setLevel(logging.getLevelName(os.environ.get("DD_LOG_LEVEL", "INFO").upper()))

try:
    from datadog_lambda.metric import lambda_stats

    DD_SUBMIT_ENHANCED_METRICS = True
except ImportError:
    logger.debug(
        "Could not import from the Datadog Lambda layer so enhanced metrics won't be submitted. "
        "Add the Datadog Lambda layer to this function to submit enhanced metrics."
    )
    DD_SUBMIT_ENHANCED_METRICS = False


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
        self.tags = self.tags + tags

    def set_timestamp(self, timestamp):
        """Set the metric's timestamp

        Args:
            timestamp (int): Unix timestamp of this metric
        """
        self.timestamp = timestamp

    def submit_to_dd(self):
        """Submit this metric to the Datadog API"""
        timestamp = self.timestamp
        if not timestamp:
            timestamp = time()

        logger.debug(
            "Submitting metric {} {} {}".format(self.name, self.value, self.tags)
        )
        lambda_stats.distribution(
            self.name, self.value, timestamp=timestamp, tags=self.tags
        )


def get_last_modified_time(s3_file):
    last_modified_str = s3_file["ResponseMetadata"]["HTTPHeaders"]["last-modified"]
    last_modified_date = datetime.datetime.strptime(
        last_modified_str, "%a, %d %b %Y %H:%M:%S %Z"
    )
    last_modified_unix_time = int(last_modified_date.strftime("%s"))
    return last_modified_unix_time


def parse_and_submit_enhanced_metrics(logs, cache_layer):
    """Parses enhanced metrics from logs and submits them to DD with tags

    Args:
        logs (dict<str, str | dict | int>[]): the logs parsed from the event in the split method
            See docstring below for an example.
    """
    # If the Lambda layer is not present we can't submit enhanced metrics
    if not DD_SUBMIT_ENHANCED_METRICS:
        return

    for log in logs:
        try:
            enhanced_metrics = generate_enhanced_lambda_metrics(
                log, cache_layer.get_lambda_tags_cache()
            )
            for enhanced_metric in enhanced_metrics:
                enhanced_metric.submit_to_dd()
        except Exception:
            logger.exception(
                "Encountered an error while trying to parse and submit enhanced metrics for log %s",
                log,
            )


def generate_enhanced_lambda_metrics(log, tags_cache):
    """Parses a Lambda log for enhanced Lambda metrics and tags

    Args:
        log (dict<str, str | dict | int>): a log parsed from the event in the split method
            Ex: {
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
                }
        tags_cache (LambdaTagsCache): used to apply the Lambda's custom tags to the metrics

    Returns:
        DatadogMetricPoint[], where each metric has all of its tags
    """
    # Note: this arn attribute is always lowercased when it's created
    log_function_arn = log.get("lambda", {}).get("arn")
    log_message = log.get("message")
    timestamp = log.get("timestamp")

    is_lambda_log = all((log_function_arn, log_message, timestamp))
    if not is_lambda_log:
        return []

    # Check if this is a REPORT log
    parsed_metrics = parse_metrics_from_report_log(log_message)

    # Check if this is a timeout
    if not parsed_metrics:
        parsed_metrics = create_timeout_enhanced_metric(log_message)

    # Check if this is an out of memory error
    if not parsed_metrics:
        parsed_metrics = create_out_of_memory_enhanced_metric(log_message)

    # If none of the above, move on
    if not parsed_metrics:
        return []

    # Add the tags from ARN, custom tags cache, and env var
    tags_from_arn = parse_lambda_tags_from_arn(log_function_arn)
    lambda_custom_tags = tags_cache.get(log_function_arn)

    for parsed_metric in parsed_metrics:
        parsed_metric.add_tags(tags_from_arn + lambda_custom_tags)
        # Submit the metric with the timestamp of the log event
        parsed_metric.set_timestamp(int(timestamp))

    return parsed_metrics


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
        "region:{}".format(region),
        "account_id:{}".format(account_id),
        # Include the aws_account tag to match the aws.lambda CloudWatch metrics
        "aws_account:{}".format(account_id),
        "functionname:{}".format(function_name),
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

    regex_match = REPORT_LOG_REGEX.search(report_log_line)

    if not regex_match:
        return []

    metrics = []

    tags = ["memorysize:" + regex_match.group(MEMORY_ALLOCATED_FIELD_NAME)]
    if regex_match.group(INIT_DURATION_METRIC_NAME):
        tags.append("cold_start:true")
    else:
        tags.append("cold_start:false")

    for metric_name in METRICS_TO_PARSE_FROM_REPORT:
        # check whether the metric, e.g., init duration, is present in the REPORT log
        if not regex_match.group(metric_name):
            continue

        metric_point_value = float(regex_match.group(metric_name))
        # Multiply the duration metrics by 1/1000 to convert ms to seconds
        if metric_name in METRIC_ADJUSTMENT_FACTORS:
            metric_point_value *= METRIC_ADJUSTMENT_FACTORS[metric_name]

        dd_metric = DatadogMetricPoint(
            "{}.{}".format(ENHANCED_METRICS_NAMESPACE_PREFIX, metric_name),
            metric_point_value,
        )

        dd_metric.add_tags(tags)

        metrics.append(dd_metric)

    estimated_cost_metric_point = DatadogMetricPoint(
        "{}.{}".format(ENHANCED_METRICS_NAMESPACE_PREFIX, ESTIMATED_COST_METRIC_NAME),
        calculate_estimated_cost(
            float(regex_match.group(BILLED_DURATION_METRIC_NAME)),
            float(regex_match.group(MEMORY_ALLOCATED_FIELD_NAME)),
        ),
    )

    estimated_cost_metric_point.add_tags(tags)

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


def create_timeout_enhanced_metric(log_line):
    """Parses and returns a value of 1 if a timeout occurred for the function

    Args:
        log_line (str): The timed out task log
        EX: "2019-07-18T18:58:22.286Z b5264ab7-2056-4f5b-bb0f-a06a70f6205d \
             Task timed out after 30.03 seconds"

    Returns:
        DatadogMetricPoint[]
    """

    regex_match = TIMED_OUT_REGEX.search(log_line)
    if not regex_match:
        return []

    dd_metric = DatadogMetricPoint(
        f"{ENHANCED_METRICS_NAMESPACE_PREFIX}.{TIMEOUTS_METRIC_NAME}",
        1.0,
    )
    return [dd_metric]


def create_out_of_memory_enhanced_metric(log_line):
    """Parses and returns a value of 1 if an out of memory error occurred for the function

    Args:
        log_line (str): The out of memory task log

    Returns:
        DatadogMetricPoint[]
    """

    contains_out_of_memory_error = any(
        s in log_line for s in OUT_OF_MEMORY_ERROR_STRINGS
    )

    if not contains_out_of_memory_error:
        return []

    dd_metric = DatadogMetricPoint(
        f"{ENHANCED_METRICS_NAMESPACE_PREFIX}.{OUT_OF_MEMORY_METRIC_NAME}",
        1.0,
    )
    return [dd_metric]
