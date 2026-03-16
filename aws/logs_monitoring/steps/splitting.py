import logging
import json
import os
from settings import DD_CUSTOM_TAGS

logger = logging.getLogger()
logger.setLevel(logging.getLevelName(os.environ.get("DD_LOG_LEVEL", "INFO").upper()))


_PARSE_FAILED = object()


def _try_parse_message(event):
    """Parse event message JSON once. Returns parsed object or _PARSE_FAILED sentinel."""
    try:
        return json.loads(event["message"])
    except Exception:
        return _PARSE_FAILED


def split(events):
    """Split events into metrics, logs, and trace payloads"""
    metrics, logs, trace_payloads = [], [], []
    for event in events:
        parsed = _try_parse_message(event)
        metric = extract_metric(event, parsed_message=parsed)
        if metric:
            metrics.append(metric)
            continue
        trace_payload = extract_trace_payload(event, parsed_message=parsed)
        if trace_payload:
            trace_payloads.append(trace_payload)
        else:
            logs.append(event)

    if logger.isEnabledFor(logging.DEBUG):
        logger.debug(
            f"Extracted {len(metrics)} metrics, {len(trace_payloads)} traces, and {len(logs)} logs"
        )

    return metrics, logs, trace_payloads


def extract_metric(event, parsed_message=None):
    """Extract metric from an event if possible"""
    try:
        if parsed_message is _PARSE_FAILED:
            return None
        metric = (
            parsed_message
            if parsed_message is not None
            else json.loads(event["message"])
        )

        required_attrs = {"m", "v", "e", "t"}
        if not all(attr in metric for attr in required_attrs):
            return None
        if not isinstance(metric["t"], list):
            return None
        if not isinstance(metric["v"], (int, float)):
            return None

        lambda_log_arn = event.get("lambda", {}).get("arn")
        if lambda_log_arn:
            metric["t"] += [f"function_arn:{lambda_log_arn.lower()}"]

        metric["t"] += event[DD_CUSTOM_TAGS].split(",")
        return metric
    except Exception:
        return None


def extract_trace_payload(event, parsed_message=None):
    """Extract trace payload from an event if possible"""
    try:
        if parsed_message is _PARSE_FAILED:
            return None
        obj = (
            parsed_message
            if parsed_message is not None
            else json.loads(event["message"])
        )

        traces = obj.get("traces")
        if not isinstance(traces, list) or not traces or not traces[0]:
            return None
        # Verify this is a Datadog trace, not an unrelated "traces" array
        if traces[0][0].get("trace_id") is None:
            return None

        return {"message": event["message"], "tags": event[DD_CUSTOM_TAGS]}
    except Exception:
        return None
