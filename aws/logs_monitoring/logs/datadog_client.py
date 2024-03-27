# Unless explicitly stated otherwise all files in this repository are licensed
# under the Apache License Version 2.0.
# This product includes software developed at Datadog (https://www.datadoghq.com/).
# Copyright 2021 Datadog, Inc.


import time
from logs.exceptions import RetriableException


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
