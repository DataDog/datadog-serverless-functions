# Unless explicitly stated otherwise all files in this repository are licensed
# under the Apache License Version 2.0.
# This product includes software developed at Datadog (https://www.datadoghq.com/).
# Copyright 2021 Datadog, Inc.


import re

"""
Customized log group is a log group shared by multiple applications of the same type. Based on the feedback from AWS, 
customers may name the log group arbitrarily. E.g they can name a lambda log group as "/aws/vendedlogs/states/**", which is typically used for Stepfunctions
In addition, potentially, not just Lambda, any other AWS services can use a customized log group.
The workaround is to parse the logstream_name to get the source of logs.
"""

# Example: "2023/11/06/test-customized-log-group1[$LATEST]13e304cba4b9446eb7ef082a00038990"
REX_LAMBDA_CUSTOMIZE_LOGSTREAM_NAME_PATTERN = re.compile(
    "^[0-9]{4}\\/[01][0-9]\\/[0-3][0-9]\\/[0-9a-zA-Z_.-]{1,75}\\[(?:\\$LATEST|[0-9A-Za-z_-]{1,129})\\][0-9a-f]{32}$"
)


def is_lambda_customized_log_group(logstream_name):
    return (
        REX_LAMBDA_CUSTOMIZE_LOGSTREAM_NAME_PATTERN.fullmatch(logstream_name)
        is not None
    )


def get_lambda_function_name_from_logstream_name(logstream_name):
    try:
        # Not match the pattern for customized Lambda log group
        if not is_lambda_customized_log_group(logstream_name):
            return None
        leftSquareBracketPos = logstream_name.index("[")
        lastForwardSlashPos = logstream_name.rindex("/")
        return logstream_name[lastForwardSlashPos + 1 : leftSquareBracketPos]
    except:
        return None
