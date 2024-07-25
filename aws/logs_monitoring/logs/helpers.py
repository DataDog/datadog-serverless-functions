# Unless explicitly stated otherwise all files in this repository are licensed
# under the Apache License Version 2.0.
# This product includes software developed at Datadog (https://www.datadoghq.com/).
# Copyright 2021 Datadog, Inc.


import gzip
import json
import logging
import os
import re

from settings import DD_CUSTOM_TAGS, DD_RETRY_KEYWORD

from logs.exceptions import ScrubbingException

logger = logging.getLogger()
logger.setLevel(logging.getLevelName(os.environ.get("DD_LOG_LEVEL", "INFO").upper()))


def filter_logs(logs, include_pattern=None, exclude_pattern=None):
    """
    Applies log filtering rules.
    If no filtering rules exist, return all the logs.
    """
    if include_pattern is None and exclude_pattern is None:
        return logs

    logger.debug(f"Applying exclude pattern: {exclude_pattern}")
    exclude_regex = compileRegex("EXCLUDE_AT_MATCH", exclude_pattern)

    logger.debug(f"Applying include pattern: {include_pattern}")
    include_regex = compileRegex("INCLUDE_AT_MATCH", include_pattern)

    # Add logs that should be sent to logs_to_send
    logs_to_send = []

    for log in logs:
        try:
            if exclude_regex is not None and re.search(exclude_regex, log):
                logger.debug("Exclude pattern matched, excluding log event")
                continue

            if include_regex is not None and not re.search(include_regex, log):
                logger.debug("Include pattern did not match, excluding log event")
                continue

            logs_to_send.append(log)

        except ScrubbingException:
            raise Exception("could not filter the payload")

    return logs_to_send


def compress_logs(batch, level):
    if level < 0:
        compression_level = 0
    elif level > 9:
        compression_level = 9
    else:
        compression_level = level

    return gzip.compress(bytes(batch, "utf-8"), compression_level)


def compileRegex(rule, pattern):
    if pattern is None:
        return

    if pattern == "":
        # If pattern is an empty string, raise exception
        raise Exception(
            "No pattern provided:\nAdd pattern or remove {} environment variable".format(
                rule
            )
        )
    try:
        return re.compile(pattern)
    except Exception:
        raise Exception(
            "could not compile {} regex with pattern: {}".format(rule, pattern)
        )


def add_retry_tag(log):
    try:
        log = json.loads(log)
        log[DD_CUSTOM_TAGS] = log.get(DD_CUSTOM_TAGS, "") + f",{DD_RETRY_KEYWORD}:true"
    except Exception:
        logger.warning(f"cannot add retry tag for log {log}")

    return log
