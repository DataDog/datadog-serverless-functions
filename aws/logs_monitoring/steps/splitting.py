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
        metric = extract_metric(event)
        trace_payload = extract_trace_payload(event)
        if metric:
            metrics.append(metric)
        elif trace_payload:
            trace_payloads.append(trace_payload)
        else:
            logs.append(event)

    if logger.isEnabledFor(logging.DEBUG):
        logger.debug(
            f"Extracted {len(metrics)} metrics, {len(trace_payloads)} traces, and {len(logs)} logs"
        )

    return metrics, logs, trace_payloads


def extract_metric(event):
    """Extract metric from an event if possible"""
    try:
        metric = json.loads(event["message"])
        required_attrs = {"m", "v", "e", "t"}
        if not all(attr in metric for attr in required_attrs):
            return None
        if not isinstance(metric["t"], list):
            return None
        if not (isinstance(metric["v"], int) or isinstance(metric["v"], float)):
            return None

        lambda_log_metadata = event.get("lambda", {})
        lambda_log_arn = lambda_log_metadata.get("arn")

        if lambda_log_arn:
            metric["t"] += [f"function_arn:{lambda_log_arn.lower()}"]

        metric["t"] += event[DD_CUSTOM_TAGS].split(",")
        return metric
    except Exception:
        return None


def extract_trace_payload(event):
    """Extract trace payload from an event if possible"""
    try:
        message = event["message"]
        obj = json.loads(event["message"])

        obj_has_traces = "traces" in obj
        traces_is_a_list = isinstance(obj["traces"], list)
        # check that the log is not containing a trace array unrelated to Datadog
        trace_id_found = (
            len(obj["traces"]) > 0
            and len(obj["traces"][0]) > 0
            and obj["traces"][0][0]["trace_id"] is not None
        )

        if obj_has_traces and traces_is_a_list and trace_id_found:
            return {"message": message, "tags": event[DD_CUSTOM_TAGS]}
        return None
    except Exception:
        return None
