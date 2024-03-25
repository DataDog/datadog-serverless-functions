import logging
import re
import gzip
import os
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
    # Add logs that should be sent to logs_to_send
    logs_to_send = []
    for log in logs:
        if exclude_pattern is not None or include_pattern is not None:
            logger.debug("Filtering log event:")
            logger.debug(log)
        try:
            if exclude_pattern is not None:
                # if an exclude match is found, do not add log to logs_to_send
                logger.debug(f"Applying exclude pattern: {exclude_pattern}")
                exclude_regex = compileRegex("EXCLUDE_AT_MATCH", exclude_pattern)
                if re.search(exclude_regex, log):
                    logger.debug("Exclude pattern matched, excluding log event")
                    continue
            if include_pattern is not None:
                # if no include match is found, do not add log to logs_to_send
                logger.debug(f"Applying include pattern: {include_pattern}")
                include_regex = compileRegex("INCLUDE_AT_MATCH", include_pattern)
                if not re.search(include_regex, log):
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
    if pattern is not None:
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
