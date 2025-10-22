# Unless explicitly stated otherwise all files in this repository are licensed
# under the Apache License Version 2.0.
# This product includes software developed at Datadog (https://www.datadoghq.com/).
# Copyright 2021 Datadog, Inc.


import logging
import os
from concurrent.futures import as_completed

from requests_futures.sessions import FuturesSession

from logs.exceptions import ScrubbingException
from logs.helpers import compress_logs
from settings import (
    DD_COMPRESSION_LEVEL,
    DD_FORWARDER_VERSION,
    DD_MAX_WORKERS,
    DD_USE_COMPRESSION,
    get_enrich_cloudwatch_tags,
    get_enrich_s3_tags,
)

logger = logging.getLogger()
logger.setLevel(logging.getLevelName(os.environ.get("DD_LOG_LEVEL", "INFO").upper()))


def get_dd_storage_tag_header():
    storage_tag = ""

    if get_enrich_s3_tags():
        storage_tag += "s3"

    if get_enrich_cloudwatch_tags():
        if storage_tag != "":
            storage_tag += ","
        storage_tag += "cloudwatch"

    return storage_tag


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

    storage_tag = get_dd_storage_tag_header()
    if storage_tag != "":
        _HEADERS["DD-STORAGE-TAG"] = storage_tag

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
            except Exception as e:
                logger.error(f"Exception while forwarding logs: {e}")

        self._session.close()

    def send(self, logs):
        """
        Sends a batch of log, only retry on server and network errors.
        """
        try:
            data = self._scrubber.scrub("[{}]".format(",".join(logs)))
        except ScrubbingException as e:
            raise Exception(f"could not scrub the payload: {e}")
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
