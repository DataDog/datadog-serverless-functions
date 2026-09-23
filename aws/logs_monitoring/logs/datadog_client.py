# Unless explicitly stated otherwise all files in this repository are licensed
# under the Apache License Version 2.0.
# This product includes software developed at Datadog (https://www.datadoghq.com/).
# Copyright 2021 Datadog, Inc.


import time
from logs.exceptions import RetriableException

# Allow the default 10-second intake timeout plus five seconds for failure storage.
MIN_RETRY_TIME_MS = 15_000


class DatadogClient(object):
    """
    Client that implements a exponential retrying logic to send a batch of logs.
    """

    def __init__(
        self, client, max_backoff=30, max_retries=2, remaining_time_provider=None
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
                # Read the live budget again: the sleep may have taken longer.
                if not self._can_retry(0):
                    raise
                retries += 1
                backoff = min(backoff * 2, self._max_backoff)
                continue

    def _can_retry(self, backoff):
        return (
            self._remaining_time_provider is None
            or self._remaining_time_provider() > MIN_RETRY_TIME_MS + backoff * 1000
        )

    def __enter__(self):
        self._client.__enter__()
        return self

    def __exit__(self, ex_type, ex_value, traceback):
        self._client.__exit__(ex_type, ex_value, traceback)
