# Unless explicitly stated otherwise all files in this repository are licensed
# under the Apache License Version 2.0.
# This product includes software developed at Datadog (https://www.datadoghq.com/).
# Copyright 2021 Datadog, Inc.


import time
from logs.exceptions import RetriableException

# Reserve time for another intake request and failed-event storage before retrying.
MIN_REMAINING_TIME_MS = 15_000


class DatadogClient(object):
    """
    Client that implements a exponential retrying logic to send a batch of logs.
    """

    def __init__(
        self,
        client,
        max_backoff=30,
        max_retries=5,
        remaining_time_provider=None,
    ):
        self._client = client
        self._max_backoff = max_backoff
        self._max_retries = max_retries
        self._remaining_time_provider = remaining_time_provider

    def send(self, logs):
        backoff = 1
        retries = 0
        while True:
            try:
                self._client.send(logs)
                return
            except RetriableException:
                if retries >= self._max_retries or not self._can_retry(backoff):
                    raise
                time.sleep(backoff)
                retries += 1
                if backoff < self._max_backoff:
                    backoff *= 2
                continue

    def can_send(self):
        return self._has_remaining_time()

    def _can_retry(self, backoff):
        return self._has_remaining_time(backoff * 1000)

    def _has_remaining_time(self, additional_time_ms=0):
        if self._remaining_time_provider is None:
            return True

        try:
            remaining_time_ms = self._remaining_time_provider()
        except Exception:
            return False

        return remaining_time_ms > MIN_REMAINING_TIME_MS + additional_time_ms

    def __enter__(self):
        self._client.__enter__()
        return self

    def __exit__(self, ex_type, ex_value, traceback):
        self._client.__exit__(ex_type, ex_value, traceback)
