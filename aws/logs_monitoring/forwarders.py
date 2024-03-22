import logging
import json
import os

from telemetry import send_event_metric, send_log_metric
from trace_forwarder.connection import TraceConnection
from logs.logs import (
    DatadogScrubber,
    DatadogBatcher,
    DatadogClient,
    DatadogHTTPClient,
    DatadogTCPClient,
)
from logs.logs_helpers import filter_logs
from settings import (
    DD_API_KEY,
    DD_USE_TCP,
    DD_NO_SSL,
    DD_SKIP_SSL_VALIDATION,
    DD_URL,
    DD_PORT,
    SCRUBBING_RULE_CONFIGS,
    INCLUDE_AT_MATCH,
    EXCLUDE_AT_MATCH,
    DD_TRACE_INTAKE_URL,
)

logger = logging.getLogger()
logger.setLevel(logging.getLevelName(os.environ.get("DD_LOG_LEVEL", "INFO").upper()))
trace_connection = TraceConnection(
    DD_TRACE_INTAKE_URL, DD_API_KEY, DD_SKIP_SSL_VALIDATION
)


def forward_logs(logs):
    """Forward logs to Datadog"""
    if logger.isEnabledFor(logging.DEBUG):
        logger.debug(f"Forwarding {len(logs)} logs")
    logs_to_forward = filter_logs(
        [json.dumps(log, ensure_ascii=False) for log in logs],
        include_pattern=INCLUDE_AT_MATCH,
        exclude_pattern=EXCLUDE_AT_MATCH,
    )
    scrubber = DatadogScrubber(SCRUBBING_RULE_CONFIGS)
    if DD_USE_TCP:
        batcher = DatadogBatcher(256 * 1000, 256 * 1000, 1)
        cli = DatadogTCPClient(DD_URL, DD_PORT, DD_NO_SSL, DD_API_KEY, scrubber)
    else:
        batcher = DatadogBatcher(512 * 1000, 4 * 1000 * 1000, 400)
        cli = DatadogHTTPClient(
            DD_URL, DD_PORT, DD_NO_SSL, DD_SKIP_SSL_VALIDATION, DD_API_KEY, scrubber
        )

    with DatadogClient(cli) as client:
        for batch in batcher.batch(logs_to_forward):
            try:
                client.send(batch)
            except Exception:
                logger.exception(f"Exception while forwarding log batch {batch}")
            else:
                if logger.isEnabledFor(logging.DEBUG):
                    logger.debug(f"Forwarded log batch: {json.dumps(batch)}")

    send_event_metric("logs_forwarded", len(logs_to_forward))


def forward_metrics(metrics):
    """
    Forward custom metrics submitted via logs to Datadog in a background thread
    using `lambda_stats` that is provided by the Datadog Python Lambda Layer.
    """
    if logger.isEnabledFor(logging.DEBUG):
        logger.debug(f"Forwarding {len(metrics)} metrics")

    for metric in metrics:
        try:
            send_log_metric(metric)
        except Exception:
            logger.exception(f"Exception while forwarding metric {json.dumps(metric)}")
        else:
            if logger.isEnabledFor(logging.DEBUG):
                logger.debug(f"Forwarded metric: {json.dumps(metric)}")

    send_event_metric("metrics_forwarded", len(metrics))


def forward_traces(trace_payloads):
    if logger.isEnabledFor(logging.DEBUG):
        logger.debug(f"Forwarding {len(trace_payloads)} traces")

    try:
        trace_connection.send_traces(trace_payloads)
    except Exception:
        logger.exception(
            f"Exception while forwarding traces {json.dumps(trace_payloads)}"
        )
    else:
        if logger.isEnabledFor(logging.DEBUG):
            logger.debug(f"Forwarded traces: {json.dumps(trace_payloads)}")

    send_event_metric("traces_forwarded", len(trace_payloads))
