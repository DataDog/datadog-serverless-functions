# Unless explicitly stated otherwise all files in this repository are licensed
# under the Apache License Version 2.0.
# This product includes software developed at Datadog (https://www.datadoghq.com/).
# Copyright 2021 Datadog, Inc.

try:
    from datadog_lambda.metric import lambda_stats

    DD_SUBMIT_ENHANCED_METRICS = True
except ImportError:
    DD_SUBMIT_ENHANCED_METRICS = False

from settings import DD_FORWARDER_VERSION

DD_FORWARDER_TELEMETRY_NAMESPACE_PREFIX = "aws.dd_forwarder"
DD_FORWARDER_TELEMETRY_TAGS = []


def set_forwarder_telemetry_tags(context, event_type):
    """Helper function to set tags on telemetry metrics
    Do not submit telemetry metrics before this helper function is invoked
    """
    global DD_FORWARDER_TELEMETRY_TAGS
    DD_FORWARDER_TELEMETRY_TAGS = [
        f"forwardername:{context.function_name.lower()}",
        f"forwarder_memorysize:{context.memory_limit_in_mb}",
        f"forwarder_version:{DD_FORWARDER_VERSION}",
        f"event_type:{event_type}",
    ]


def send_forwarder_internal_metrics(name, additional_tags=[]):
    if not DD_SUBMIT_ENHANCED_METRICS:
        return

    """Send forwarder's internal metrics to DD"""
    lambda_stats.distribution(
        "{}.{}".format(DD_FORWARDER_TELEMETRY_NAMESPACE_PREFIX, name),
        1,
        tags=DD_FORWARDER_TELEMETRY_TAGS + additional_tags,
    )


def send_event_metric(metric_name, metric_value):
    if not DD_SUBMIT_ENHANCED_METRICS:
        return

    lambda_stats.distribution(
        "{}.{}".format(DD_FORWARDER_TELEMETRY_NAMESPACE_PREFIX, metric_name),
        metric_value,
        tags=DD_FORWARDER_TELEMETRY_TAGS,
    )


def send_log_metric(metric):
    if not DD_SUBMIT_ENHANCED_METRICS:
        return

    lambda_stats.distribution(
        metric["m"], metric["v"], timestamp=metric["e"], tags=metric["t"]
    )
