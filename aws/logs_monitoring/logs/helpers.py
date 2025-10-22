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

logger = logging.getLogger()
logger.setLevel(logging.getLevelName(os.environ.get("DD_LOG_LEVEL", "INFO").upper()))


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
            f"Empty pattern for {rule}. Set a valid regex pattern or remove the {rule} environment variable."
        )
    try:
        return re.compile(pattern)
    except re.error as e:
        raise Exception(
            f"Invalid regex pattern for {rule}: '{pattern}'. Regex error: {e}"
        )
    except Exception as e:
        raise Exception(f"Failed to compile {rule} regex pattern '{pattern}': {e}")


def add_retry_tag(log):
    try:
        log = json.loads(log)
        log[DD_CUSTOM_TAGS] = log.get(DD_CUSTOM_TAGS, "") + f",{DD_RETRY_KEYWORD}:true"
    except Exception:
        logger.warning(f"cannot add retry tag for log {log}")

    return log
