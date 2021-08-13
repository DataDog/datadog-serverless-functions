# Unless explicitly stated otherwise all files in this repository are licensed
# under the Apache License Version 2.0.
# This product includes software developed at Datadog (https://www.datadoghq.com/).
# Copyright 2021 Datadog, Inc.

from settings import DD_FORWARDER_VERSION
import gzip
import json
import os
from concurrent.futures import as_completed

import re
import socket
import ssl
import logging
import time
from requests_futures.sessions import FuturesSession

from datadog_lambda.metric import lambda_stats
from telemetry import (
    DD_FORWARDER_TELEMETRY_NAMESPACE_PREFIX,
    get_forwarder_telemetry_tags,
)
from settings import (
    DD_API_KEY,
    DD_USE_TCP,
    DD_USE_COMPRESSION,
    DD_COMPRESSION_LEVEL,
    DD_NO_SSL,
    DD_SKIP_SSL_VALIDATION,
    DD_URL,
    DD_PORT,
    SCRUBBING_RULE_CONFIGS,
    INCLUDE_AT_MATCH,
    EXCLUDE_AT_MATCH,
    DD_MAX_WORKERS,
)

logger = logging.getLogger()


class RetriableException(Exception):
    pass


class ScrubbingException(Exception):
    pass


def forward_logs(logs):
    """Forward logs to Datadog"""
    if logger.isEnabledFor(logging.DEBUG):
        logger.debug(f"Forwarding {len(logs)} logs")
    logs_to_forward = filter_logs(
        list(map(json.dumps, logs)),
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

    lambda_stats.distribution(
        "{}.logs_forwarded".format(DD_FORWARDER_TELEMETRY_NAMESPACE_PREFIX),
        len(logs_to_forward),
        tags=get_forwarder_telemetry_tags(),
    )


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


class DatadogClient(object):
    """
    Client that implements a exponential retrying logic to send a batch of logs.
    """

    def __init__(self, client, max_backoff=30):
        self._client = client
        self._max_backoff = max_backoff

    def send(self, logs):
        backoff = 1
        while True:
            try:
                self._client.send(logs)
                return
            except RetriableException:
                time.sleep(backoff)
                if backoff < self._max_backoff:
                    backoff *= 2
                continue

    def __enter__(self):
        self._client.__enter__()
        return self

    def __exit__(self, ex_type, ex_value, traceback):
        self._client.__exit__(ex_type, ex_value, traceback)


def compress_logs(batch, level):
    if level < 0:
        compression_level = 0
    elif level > 9:
        compression_level = 9
    else:
        compression_level = level

    return gzip.compress(bytes(batch, "utf-8"), compression_level)


class DatadogScrubber(object):
    def __init__(self, configs):
        rules = []
        for config in configs:
            if config.name in os.environ:
                rules.append(
                    ScrubbingRule(
                        compileRegex(config.name, config.pattern), config.placeholder
                    )
                )
        self._rules = rules

    def scrub(self, payload):
        for rule in self._rules:
            try:
                payload = rule.regex.sub(rule.placeholder, payload)
            except Exception:
                raise ScrubbingException()
        return payload


class ScrubbingRule(object):
    def __init__(self, regex, placeholder):
        self.regex = regex
        self.placeholder = placeholder


class DatadogBatcher(object):
    def __init__(self, max_item_size_bytes, max_batch_size_bytes, max_items_count):
        self._max_item_size_bytes = max_item_size_bytes
        self._max_batch_size_bytes = max_batch_size_bytes
        self._max_items_count = max_items_count

    def _sizeof_bytes(self, item):
        return len(str(item).encode("UTF-8"))

    def batch(self, items):
        """
        Returns an array of batches.
        Each batch contains at most max_items_count items and
        is not strictly greater than max_batch_size_bytes.
        All items strictly greater than max_item_size_bytes are dropped.
        """
        batches = []
        batch = []
        size_bytes = 0
        size_count = 0
        for item in items:
            item_size_bytes = self._sizeof_bytes(item)
            if size_count > 0 and (
                size_count >= self._max_items_count
                or size_bytes + item_size_bytes > self._max_batch_size_bytes
            ):
                batches.append(batch)
                batch = []
                size_bytes = 0
                size_count = 0
            # all items exceeding max_item_size_bytes are dropped here
            if item_size_bytes <= self._max_item_size_bytes:
                batch.append(item)
                size_bytes += item_size_bytes
                size_count += 1
        if size_count > 0:
            batches.append(batch)
        return batches


class DatadogTCPClient(object):
    """
    Client that sends a batch of logs over TCP.
    """

    def __init__(self, host, port, no_ssl, api_key, scrubber):
        self.host = host
        self.port = port
        self._use_ssl = not no_ssl
        self._api_key = api_key
        self._scrubber = scrubber
        self._sock = None
        if logger.isEnabledFor(logging.DEBUG):
            logger.debug(
                f"Initialized tcp client for logs intake: "
                f"<host: {host}, port: {port}, no_ssl: {no_ssl}>"
            )

    def _connect(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        if self._use_ssl:
            sock = ssl.create_default_context().wrap_socket(
                sock, server_hostname=self.host
            )
        sock.connect((self.host, self.port))
        self._sock = sock

    def _close(self):
        if self._sock:
            self._sock.close()

    def _reset(self):
        self._close()
        self._connect()

    def send(self, logs):
        try:
            frame = self._scrubber.scrub(
                "".join(["{} {}\n".format(self._api_key, log) for log in logs])
            )
            self._sock.sendall(frame.encode("UTF-8"))
        except ScrubbingException:
            raise Exception("could not scrub the payload")
        except Exception:
            # most likely a network error, reset the connection
            self._reset()
            raise RetriableException()

    def __enter__(self):
        self._connect()
        return self

    def __exit__(self, ex_type, ex_value, traceback):
        self._close()


class DatadogHTTPClient(object):
    """
    Client that sends a batch of logs over HTTP.
    """

    _POST = "POST"
    if DD_USE_COMPRESSION:
        _HEADERS = {"Content-type": "application/json", "Content-Encoding": "gzip"}
    else:
        _HEADERS = {"Content-type": "application/json"}

    _HEADERS["DD-EVP-ORIGIN"] = "aws_forwarder"
    _HEADERS["DD-EVP-ORIGIN-VERSION"] = DD_FORWARDER_VERSION

    def __init__(
        self, host, port, no_ssl, skip_ssl_validation, api_key, scrubber, timeout=10
    ):
        self._HEADERS.update({"DD-API-KEY": api_key})
        protocol = "http" if no_ssl else "https"
        self._url = "{}://{}:{}/api/v2/logs".format(protocol, host, port)
        self._scrubber = scrubber
        self._timeout = timeout
        self._session = None
        self._ssl_validation = not skip_ssl_validation
        self._futures = []
        if logger.isEnabledFor(logging.DEBUG):
            logger.debug(
                f"Initialized http client for logs intake: "
                f"<host: {host}, port: {port}, url: {self._url}, no_ssl: {no_ssl}, "
                f"skip_ssl_validation: {skip_ssl_validation}, timeout: {timeout}>"
            )

    def _connect(self):
        self._session = FuturesSession(max_workers=DD_MAX_WORKERS)
        self._session.headers.update(self._HEADERS)

    def _close(self):
        # Resolve all the futures and log exceptions if any
        for future in as_completed(self._futures):
            try:
                future.result()
            except Exception:
                logger.exception("Exception while forwarding logs")

        self._session.close()

    def send(self, logs):
        """
        Sends a batch of log, only retry on server and network errors.
        """
        try:
            data = self._scrubber.scrub("[{}]".format(",".join(logs)))
        except ScrubbingException:
            raise Exception("could not scrub the payload")
        if DD_USE_COMPRESSION:
            data = compress_logs(data, DD_COMPRESSION_LEVEL)

        # FuturesSession returns immediately with a future object
        future = self._session.post(
            self._url, data, timeout=self._timeout, verify=self._ssl_validation
        )
        self._futures.append(future)

    def __enter__(self):
        self._connect()
        return self

    def __exit__(self, ex_type, ex_value, traceback):
        self._close()
