# Unless explicitly stated otherwise all files in this repository are licensed
# under the Apache License Version 2.0.
# This product includes software developed at Datadog (https://www.datadoghq.com/).
# Copyright 2021 Datadog, Inc.


import json
import logging
import os

from logs.datadog_batcher import DatadogBatcher
from logs.datadog_client import DatadogClient
from logs.datadog_http_client import DatadogHTTPClient
from logs.datadog_matcher import DatadogMatcher
from logs.datadog_scrubber import DatadogScrubber
from logs.helpers import add_retry_tag
from retry.enums import RetryPrefix
from retry.storage import Storage
from settings import (
    DD_API_KEY,
    DD_FORWARD_LOG,
    DD_NO_SSL,
    DD_PORT,
    DD_SKIP_SSL_VALIDATION,
    DD_STORE_FAILED_EVENTS,
    DD_TRACE_INTAKE_URL,
    DD_URL,
    EXCLUDE_AT_MATCH,
    INCLUDE_AT_MATCH,
    SCRUBBING_RULE_CONFIGS,
)
from telemetry import send_event_metric, send_log_metric
from trace_forwarder.connection import TraceConnection

logger = logging.getLogger()
logger.setLevel(logging.getLevelName(os.environ.get("DD_LOG_LEVEL", "INFO").upper()))


class Forwarder(object):
    def __init__(self, function_prefix):
        self.trace_connection = TraceConnection(
            DD_TRACE_INTAKE_URL, DD_API_KEY, DD_SKIP_SSL_VALIDATION
        )
        self.storage = Storage(function_prefix)

    def forward(self, logs, metrics, traces):
        """
        Forward logs, metrics, and traces to Datadog in a background thread.
        """
        if DD_FORWARD_LOG:
            self._forward_logs(logs)
        self._forward_metrics(metrics)
        self._forward_traces(traces)

    def retry(self):
        """
        Retry forwarding logs, metrics, and traces to Datadog.
        """
        for prefix in RetryPrefix:
            self._retry_prefix(prefix)

    def _retry_prefix(self, prefix):
        if logger.isEnabledFor(logging.DEBUG):
            logger.debug(f"Retrying {prefix} data")

        key_data = self.storage.get_data(prefix)

        for k, d in key_data.items():
            if d is None:
                continue
            match prefix:
                case RetryPrefix.LOGS:
                    self._forward_logs(d, key=k)
                case RetryPrefix.METRICS:
                    self._forward_metrics(d, key=k)
                case RetryPrefix.TRACES:
                    self._forward_traces(d, key=k)

    def _forward_logs(self, logs, key=None):
        """Forward logs to Datadog"""
        if logger.isEnabledFor(logging.DEBUG):
            logger.debug(f"Forwarding {len(logs)} logs")

        scrubber = DatadogScrubber(SCRUBBING_RULE_CONFIGS)
        matcher = DatadogMatcher(
            include_pattern=INCLUDE_AT_MATCH, exclude_pattern=EXCLUDE_AT_MATCH
        )

        logs_to_forward = []
        for log in logs:
            if key:
                log = add_retry_tag(log)

            evaluated_log = log
            to_forward = None

            # apply scrubbing rules to inner log message
            if isinstance(log, dict):
                if log.get("message"):
                    try:
                        log["message"] = scrubber.scrub(log["message"])
                        evaluated_log = log["message"]
                    except Exception as e:
                        logger.error(
                            f"Exception while scrubbing log message {log['message']}: {e}"
                        )
                else:
                    to_forward = dump_event(log)
                    evaluated_log = to_forward

            if matcher.match(evaluated_log):
                if to_forward is None:
                    logs_to_forward.append(dump_event(log))
                else:
                    logs_to_forward.append(to_forward)

        batcher = DatadogBatcher(512 * 1000, 4 * 1000 * 1000, 400)
        cli = DatadogHTTPClient(
            DD_URL, DD_PORT, DD_NO_SSL, DD_SKIP_SSL_VALIDATION, DD_API_KEY, scrubber
        )

        failed_logs = []
        with DatadogClient(cli) as client:
            for batch in batcher.batch(logs_to_forward):
                try:
                    client.send(batch)
                except Exception as e:
                    logger.error(f"Exception while forwarding log batch {batch}: {e}")
                    failed_logs.extend(batch)
                else:
                    if logger.isEnabledFor(logging.DEBUG):
                        logger.debug(f"Forwarded log batch: {batch}")
                    if key:
                        self.storage.delete_data(key)

        if DD_STORE_FAILED_EVENTS and len(failed_logs) > 0 and not key:
            self.storage.store_data(RetryPrefix.LOGS, failed_logs)

        if len(failed_logs) > 0:
            send_event_metric("logs_failed", failed_logs)

        send_event_metric("logs_forwarded", len(logs_to_forward) - len(failed_logs))

    def _forward_metrics(self, metrics, key=None):
        """
        Forward custom metrics submitted via logs to Datadog in a background thread
        using `lambda_stats` that is provided by the Datadog Python Lambda Layer.
        """
        if logger.isEnabledFor(logging.DEBUG):
            logger.debug(f"Forwarding {len(metrics)} metrics")

        failed_metrics = []
        for metric in metrics:
            try:
                send_log_metric(metric)
            except Exception as e:
                logger.error(
                    f"Exception while forwarding metric {json.dumps(metric)}: {e}"
                )
                failed_metrics.append(metric)
            else:
                if logger.isEnabledFor(logging.DEBUG):
                    logger.debug(f"Forwarded metric: {json.dumps(metric)}")
                if key:
                    self.storage.delete_data(key)

        if DD_STORE_FAILED_EVENTS and len(failed_metrics) > 0 and not key:
            self.storage.store_data(RetryPrefix.METRICS, failed_metrics)

        if len(failed_metrics) > 0:
            send_event_metric("metrics_failed", failed_metrics)

        send_event_metric("metrics_forwarded", len(metrics) - len(failed_metrics))

    def _forward_traces(self, traces, key=None):
        if not len(traces) > 0:
            return

        if logger.isEnabledFor(logging.DEBUG):
            logger.debug(f"Forwarding {len(traces)} traces")

        try:
            serialized_trace_paylods = json.dumps(traces)
            self.trace_connection.send_traces(serialized_trace_paylods)
        except Exception as e:
            logger.error(
                f"Exception while forwarding traces {serialized_trace_paylods}: {e}"
            )
            if DD_STORE_FAILED_EVENTS and not key:
                self.storage.store_data(RetryPrefix.TRACES, traces)
        else:
            if logger.isEnabledFor(logging.DEBUG):
                logger.debug(f"Forwarded traces: {serialized_trace_paylods}")
            if key:
                self.storage.delete_data(key)
            send_event_metric("traces_forwarded", len(traces))


def dump_event(event):
    return json.dumps(event, ensure_ascii=False)
