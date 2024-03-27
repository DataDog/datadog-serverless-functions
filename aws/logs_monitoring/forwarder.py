# Unless explicitly stated otherwise all files in this repository are licensed
# under the Apache License Version 2.0.
# This product includes software developed at Datadog (https://www.datadoghq.com/).
# Copyright 2021 Datadog, Inc.


import logging
import json
import os
from random import randint

from telemetry import send_event_metric, send_log_metric
from trace_forwarder.connection import TraceConnection
from logs.datadog_http_client import DatadogHTTPClient
from logs.datadog_batcher import DatadogBatcher
from logs.datadog_client import DatadogClient
from logs.datadog_tcp_client import DatadogTCPClient
from logs.datadog_scrubber import DatadogScrubber
from logs.helpers import filter_logs
from retry.storage import Storage
from retry.enums import RetryPrefix
from settings import (
    DD_API_KEY,
    DD_USE_TCP,
    DD_NO_SSL,
    DD_SKIP_SSL_VALIDATION,
    DD_URL,
    DD_PORT,
    DD_TRACE_INTAKE_URL,
    DD_FORWARD_LOG,
    DD_RETRY_EVENTS,
    SCRUBBING_RULE_CONFIGS,
    INCLUDE_AT_MATCH,
    EXCLUDE_AT_MATCH,
    RETRY_INTERVAL_SECONDS,
)

logger = logging.getLogger()
logger.setLevel(logging.getLevelName(os.environ.get("DD_LOG_LEVEL", "INFO").upper()))


class Forwarder(object):
    def __init__(self, function_prefix):
        self.trace_connection = TraceConnection(
            DD_TRACE_INTAKE_URL, DD_API_KEY, DD_SKIP_SSL_VALIDATION
        )
        self.storage = Storage(function_prefix)
        self.retry_interval_seconds = RETRY_INTERVAL_SECONDS + randint(1, 100)

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
        if not DD_RETRY_EVENTS:
            return

        for prefix in RetryPrefix:
            self._retry_prefix(prefix)

    def _retry_prefix(self, prefix):
        if not self._can_retry(prefix):
            return

        if logger.isEnabledFor(logging.DEBUG):
            logger.debug(f"Retrying {prefix} data")

        data = self.storage.get_data(prefix)

        for d in data:
            if d is None:
                continue
            match prefix:
                case RetryPrefix.LOGS:
                    self._forward_logs(data, retry_context=False)
                case RetryPrefix.METRICS:
                    self._forward_metrics(data, retry_context=False)
                case RetryPrefix.TRACES:
                    self._forward_traces(data, retry_context=False)

    def _can_retry(self, prefix):
        return self.storage.get_lock(prefix, self.retry_interval_seconds)

    def _forward_logs(self, logs, retry_context=True):
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

        falied_logs = []
        with DatadogClient(cli) as client:
            for batch in batcher.batch(logs_to_forward):
                try:
                    client.send(batch)
                except Exception:
                    logger.exception(
                        f"Exception while forwarding log batch {json.dumps(batch)}"
                    )
                    falied_logs.extend(batch)
                else:
                    if logger.isEnabledFor(logging.DEBUG):
                        logger.debug(f"Forwarded log batch: {json.dumps(batch)}")

        if DD_RETRY_EVENTS and retry_context and len(falied_logs) > 0:
            self.storage.store_data(RetryPrefix.LOGS, falied_logs)

        send_event_metric("logs_forwarded", len(logs_to_forward) - len(falied_logs))

    def _forward_metrics(self, metrics, retry_context=True):
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
            except Exception:
                logger.exception(
                    f"Exception while forwarding metric {json.dumps(metric)}"
                )
                failed_metrics.append(metric)
            else:
                if logger.isEnabledFor(logging.DEBUG):
                    logger.debug(f"Forwarded metric: {json.dumps(metric)}")

        if DD_RETRY_EVENTS and retry_context and len(failed_metrics) > 0:
            self.storage.store_data(RetryPrefix.METRICS, failed_metrics)

        send_event_metric("metrics_forwarded", len(metrics) - len(failed_metrics))

    def _forward_traces(self, traces, retry_context=True):
        if not len(traces) > 0:
            return

        if logger.isEnabledFor(logging.DEBUG):
            logger.debug(f"Forwarding {len(traces)} traces")

        try:
            self.trace_connection.send_traces(traces)
        except Exception:
            logger.exception(f"Exception while forwarding traces {json.dumps(traces)}")
            if DD_RETRY_EVENTS and retry_context:
                self.storage.store_data(RetryPrefix.TRACES, traces)
        else:
            if logger.isEnabledFor(logging.DEBUG):
                logger.debug(f"Forwarded traces: {json.dumps(traces)}")
            send_event_metric("traces_forwarded", len(traces))
