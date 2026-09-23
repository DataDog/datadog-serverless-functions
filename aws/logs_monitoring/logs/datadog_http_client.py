# Unless explicitly stated otherwise all files in this repository are licensed
# under the Apache License Version 2.0.
# This product includes software developed at Datadog (https://www.datadoghq.com/).
# Copyright 2021 Datadog, Inc.


import logging
import math
import os
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from threading import BoundedSemaphore

import requests

from logs.constants import DEFAULT_INTAKE_TIMEOUT_SECONDS, FAILED_EVENT_RESERVE_SECONDS
from logs.exceptions import (
    LogForwardingDeadlineExceeded,
    RetriableException,
    ScrubbingException,
)
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

# Reuse a bounded pool across warm invocations. A timed-out request may still be
# running, so admission must be bounded as well as the number of worker threads.
_request_executor = ThreadPoolExecutor(max_workers=DD_MAX_WORKERS)
_request_slots = BoundedSemaphore(DD_MAX_WORKERS)


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

    if os.environ.get("DD_STEP_FUNCTIONS_TRACE_ENABLED", "false").lower() == "true":
        _HEADERS["DD-STEP-FUNCTIONS-TRACE-ENABLED"] = "true"

    def __init__(
        self,
        host,
        port,
        no_ssl,
        skip_ssl_validation,
        api_key,
        scrubber,
        timeout=DEFAULT_INTAKE_TIMEOUT_SECONDS,
        remaining_time_provider=None,
    ):
        self._HEADERS.update({"DD-API-KEY": api_key})
        protocol = "http" if no_ssl else "https"
        self._url = "{}://{}:{}/api/v2/logs".format(protocol, host, port)
        self._scrubber = scrubber
        self._timeout = timeout
        self._remaining_time_provider = remaining_time_provider
        self._session = None
        self._executor = None
        self._abandoned_request = None
        self._deadline_exceeded = False
        self._ssl_validation = not skip_ssl_validation

        if logger.isEnabledFor(logging.DEBUG):
            logger.debug(
                f"Initialized http client for logs intake: "
                f"<host: {host}, port: {port}, url: {self._url}, no_ssl: {no_ssl}, "
                f"skip_ssl_validation: {skip_ssl_validation}, timeout: {timeout}>"
            )

    def _connect(self):
        self._session = requests.Session()
        self._session.headers.update(self._HEADERS)
        self._executor = _request_executor

    def _close(self):
        # Neither join an abandoned worker nor close a session it is still
        # using. The shared executor remains bounded across warm invocations.
        if self._abandoned_request is None:
            self._session.close()
        else:
            self._abandoned_request.add_done_callback(self._close_abandoned_response)

    def send(self, logs):
        """
        Sends a batch of log, only retry on server and network errors.
        """
        if self._deadline_exceeded:
            raise LogForwardingDeadlineExceeded("Logs intake client deadline exceeded")
        try:
            data = self._scrubber.scrub("[{}]".format(",".join(logs)))
        except ScrubbingException as e:
            raise Exception(f"could not scrub the payload: {e}")
        if DD_USE_COMPRESSION:
            data = compress_logs(data, DD_COMPRESSION_LEVEL)

        # Serialization and compression may have consumed time since the retry
        # wrapper's check, so read the live budget immediately before submitting.
        timeout = self._request_timeout()
        deadline = time.monotonic() + timeout
        slots = _request_slots
        if not slots.acquire(blocking=False):
            raise LogForwardingDeadlineExceeded("Logs intake request workers are busy")
        response = None
        future = None
        try:
            # Resolve the future here so callers can attribute failures to this batch.
            try:
                future = self._executor.submit(
                    self._post,
                    slots,
                    self._url,
                    data,
                    timeout=timeout,
                    verify=self._ssl_validation,
                    stream=True,
                )
            except Exception:
                slots.release()
                raise
            # A cancelled queued task never enters _post's finally block.
            future.add_done_callback(
                lambda completed: slots.release() if completed.cancelled() else None
            )
            response = future.result(timeout=max(0, deadline - time.monotonic()))
            response.raise_for_status()
        except FutureTimeoutError as e:
            self._deadline_exceeded = True
            if future is not None:
                self._abandoned_request = future
                future.cancel()
            raise LogForwardingDeadlineExceeded(
                "Datadog logs intake request exceeded its deadline"
            ) from e
        except requests.exceptions.HTTPError as e:
            status_code = getattr(e.response, "status_code", None)
            if status_code is None:
                status_code = getattr(response, "status_code", None)
            if status_code is not None and 500 <= status_code < 600:
                raise RetriableException(
                    f"Datadog logs intake returned HTTP {status_code}"
                ) from e
            raise
        except (
            requests.exceptions.ConnectionError,
            requests.exceptions.Timeout,
            requests.exceptions.ChunkedEncodingError,
        ) as e:
            raise RetriableException(f"Datadog logs intake request failed: {e}") from e
        finally:
            if response is not None:
                response.close()

    def _post(self, slots, *args, **kwargs):
        try:
            return self._session.post(*args, **kwargs)
        finally:
            # Release admission before Future.result() can observe completion.
            slots.release()

    def _request_timeout(self):
        if self._remaining_time_provider is None:
            return self._timeout

        try:
            remaining_seconds = self._remaining_time_provider() / 1000
            if math.isfinite(remaining_seconds):
                timeout = min(
                    self._timeout, remaining_seconds - FAILED_EVENT_RESERVE_SECONDS
                )
                if timeout > 0:
                    return timeout
        except Exception as e:
            raise LogForwardingDeadlineExceeded(
                "Could not determine the remaining Lambda time"
            ) from e

        raise LogForwardingDeadlineExceeded("Insufficient Lambda time to forward logs")

    def _close_abandoned_response(self, future):
        # The request may finish after its batch has been saved for retry.
        # Release its connection without waiting for it in the handler thread.
        try:
            if not future.cancelled():
                try:
                    future.result().close()
                except Exception:
                    pass
        finally:
            self._session.close()

    def __enter__(self):
        self._connect()
        return self

    def __exit__(self, ex_type, ex_value, traceback):
        self._close()
