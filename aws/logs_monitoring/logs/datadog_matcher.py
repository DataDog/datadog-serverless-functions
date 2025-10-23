# Unless explicitly stated otherwise all files in this repository are licensed
# under the Apache License Version 2.0.
# This product includes software developed at Datadog (https://www.datadoghq.com/).
# Copyright 2021 Datadog, Inc.


import logging
import os
import re

from logs.exceptions import ScrubbingException
from logs.helpers import compileRegex

logger = logging.getLogger()
logger.setLevel(logging.getLevelName(os.environ.get("DD_LOG_LEVEL", "INFO").upper()))


class DatadogMatcher(object):
    def __init__(self, include_pattern=None, exclude_pattern=None):
        self._include_regex = None
        self._exclude_regex = None

        if include_pattern is not None:
            logger.debug(f"Applying include pattern: {include_pattern}")
            self._include_regex = compileRegex("INCLUDE_AT_MATCH", include_pattern)

        if exclude_pattern is not None:
            logger.debug(f"Applying exclude pattern: {exclude_pattern}")
            self._exclude_regex = compileRegex("EXCLUDE_AT_MATCH", exclude_pattern)

    def match(self, log):
        try:
            if self._exclude_regex is not None and re.search(
                self._exclude_regex, str(log)
            ):
                logger.debug("Exclude pattern matched, excluding log event")
                return False

            if self._include_regex is not None and not re.search(
                self._include_regex, str(log)
            ):
                logger.debug("Include pattern did not match, excluding log event")
                return False

            return True

        except ScrubbingException as e:
            raise Exception(f"Failed to filter log: {e}")

        except Exception as e:
            raise Exception(f"Failed to filter log: {e}")
