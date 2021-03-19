# Unless explicitly stated otherwise all files in this repository are licensed
# under the Apache License Version 2.0.
# This product includes software developed at Datadog (https://www.datadoghq.com/).
# Copyright 2021 Datadog, Inc.

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


def get_forwarder_telemetry_tags():
    return DD_FORWARDER_TELEMETRY_TAGS
