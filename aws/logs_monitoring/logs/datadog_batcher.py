# Unless explicitly stated otherwise all files in this repository are licensed
# under the Apache License Version 2.0.
# This product includes software developed at Datadog (https://www.datadoghq.com/).
# Copyright 2021 Datadog, Inc.


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
