import re

REX_LAMBDA_CUSTOMIZE_LOG_STREAM_PATTERN = re.compile(
    "^20[0-9]{2}\\/[01][0-9]\\/[0-3][0-9]\\/[0-9a-zA-Z_.-]{1,75}\\[(?:\\$LATEST|[0-9A-Za-z_-]{1,129})\\][0-9a-f]{32}$"
)


def is_customized_log_group_for_lambda(logstream):
    return REX_LAMBDA_CUSTOMIZE_LOG_STREAM_PATTERN.fullmatch(logstream) is not None


def get_lambda_function_name_from_logstream(logstream):
    try:
        # Not match the pattern for customized Lambda log group
        if not is_customized_log_group_for_lambda(logstream):
            return None
        leftSquareBracketPos = logstream.index("[")
        lastForwardSlashPos = logstream.rindex("/")
        return logstream[lastForwardSlashPos + 1 : leftSquareBracketPos]
    except:
        return None
