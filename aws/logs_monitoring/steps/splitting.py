import logging
import json
import os
from settings import DD_CUSTOM_TAGS

logger = logging.getLogger()
logger.setLevel(logging.getLevelName(os.environ.get("DD_LOG_LEVEL", "INFO").upper()))


def split(events):
    """Split events into metrics, logs, and trace payloads"""
    metrics, logs, trace_payloads = [], [], []
    for event in events:
        try:
            parsed = json.loads(event["message"])
        except Exception:
            logs.append(event)
            continue

        metric = extract_metric(parsed, event)
        if metric:
            metrics.append(metric)
        elif is_trace(parsed):
            trace_payloads.append(
                {"message": event["message"], "tags": event[DD_CUSTOM_TAGS]}
            )
        else:
            logs.append(event)

    if logger.isEnabledFor(logging.DEBUG):
        logger.debug(
            f"Extracted {len(metrics)} metrics, {len(trace_payloads)} traces, and {len(logs)} logs"
        )

    return metrics, logs, trace_payloads


def extract_metric(parsed, event):
    """Extract metric from a parsed event message if it matches the metric schema"""
    try:
        required_attrs = {"m", "v", "e", "t"}
        if not all(attr in parsed for attr in required_attrs):
            return None
        if not isinstance(parsed["t"], list):
            return None
        if not isinstance(parsed["v"], (int, float)):
            return None

        lambda_log_arn = event.get("lambda", {}).get("arn")
        if lambda_log_arn:
            parsed["t"] += [f"function_arn:{lambda_log_arn.lower()}"]

        parsed["t"] += event[DD_CUSTOM_TAGS].split(",")
        return parsed
    except Exception:
        return None


def is_trace(parsed):
    """Check if a parsed message contains a valid Datadog trace payload"""
    try:
        traces = parsed.get("traces")
        if not isinstance(traces, list) or not traces or not traces[0]:
            return False
        # Verify this is a Datadog trace, not an unrelated "traces" array
        if traces[0][0].get("trace_id") is None:
            return False
        return True
    except Exception:
        return False
