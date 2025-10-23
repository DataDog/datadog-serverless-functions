import json
import logging
import os
from random import randint
from time import time

import boto3
from botocore.exceptions import ClientError

from caching.common import get_last_modified_time
from settings import (
    DD_S3_BUCKET_NAME,
    DD_S3_CACHE_DIRNAME,
    DD_S3_CACHE_LOCK_TTL_SECONDS,
    DD_TAGS_CACHE_TTL_SECONDS,
)
from telemetry import send_forwarder_internal_metrics

JITTER_MIN = 1
JITTER_MAX = 100
DD_TAGS_CACHE_TTL_SECONDS = DD_TAGS_CACHE_TTL_SECONDS + randint(JITTER_MIN, JITTER_MAX)


class BaseTagsCache(object):
    def __init__(
        self,
        prefix,
        cache_filename,
        cache_lock_filename,
        tags_ttl_seconds=DD_TAGS_CACHE_TTL_SECONDS,
    ):
        self.cache_dirname = DD_S3_CACHE_DIRNAME
        self.tags_ttl_seconds = tags_ttl_seconds
        self.tags_by_id = {}
        self.last_tags_fetch_time = 0
        self.cache_prefix = prefix
        self.cache_filename = cache_filename
        self.cache_lock_filename = cache_lock_filename
        self.logger = logging.getLogger()
        self.logger.setLevel(
            logging.getLevelName(os.environ.get("DD_LOG_LEVEL", "INFO").upper())
        )
        self.resource_tagging_client = boto3.client("resourcegroupstaggingapi")
        self.s3_client = boto3.resource("s3")

    def get_resources_paginator(self):
        return self.resource_tagging_client.get_paginator("get_resources")

    def get_cache_name_with_prefix(self):
        return f"{self.cache_dirname}/{self.cache_prefix}_{self.cache_filename}"

    def get_cache_lock_with_prefix(self):
        return f"{self.cache_dirname}/{self.cache_prefix}_{self.cache_lock_filename}"

    def write_cache_to_s3(self, data):
        """Writes tags cache to s3"""
        try:
            self.logger.debug("Trying to write data to s3: {}".format(data))
            s3_object = self.s3_client.Object(
                DD_S3_BUCKET_NAME, self.get_cache_name_with_prefix()
            )
            s3_object.put(Body=(bytes(json.dumps(data).encode("UTF-8"))))
        except ClientError as e:
            send_forwarder_internal_metrics("s3_cache_write_failure")
            self.logger.debug(f"Unable to write new cache to S3: {e}", exc_info=True)

    def acquire_s3_cache_lock(self):
        """Acquire cache lock"""
        cache_lock_object = self.s3_client.Object(
            DD_S3_BUCKET_NAME, self.get_cache_lock_with_prefix()
        )
        try:
            file_content = cache_lock_object.get()

            # check lock file expiration
            last_modified_unix_time = get_last_modified_time(file_content)
            if last_modified_unix_time + DD_S3_CACHE_LOCK_TTL_SECONDS >= time():
                return False
        except Exception as e:
            self.logger.debug(f"Unable to get cache lock file: {e}")

        # lock file doesn't exist, create file to acquire lock
        try:
            cache_lock_object.put(Body=(bytes("lock".encode("UTF-8"))))
            send_forwarder_internal_metrics("s3_cache_lock_acquired")
            self.logger.debug("S3 cache lock acquired")
        except ClientError as e:
            self.logger.debug(f"Unable to write S3 cache lock file: {e}", exc_info=True)
            return False

        return True

    def release_s3_cache_lock(self):
        """Release cache lock"""
        try:
            cache_lock_object = self.s3_client.Object(
                DD_S3_BUCKET_NAME, self.get_cache_lock_with_prefix()
            )
            cache_lock_object.delete()
            send_forwarder_internal_metrics("s3_cache_lock_released")
            self.logger.debug("S3 cache lock released")
        except ClientError as e:
            send_forwarder_internal_metrics("s3_cache_lock_release_failure")
            self.logger.debug(f"Unable to release S3 cache lock: {e}", exc_info=True)

    def get_cache_from_s3(self):
        """Retrieves tags cache from s3 and returns the body along with
        the last modified datetime for the cache"""
        cache_object = self.s3_client.Object(
            DD_S3_BUCKET_NAME, self.get_cache_name_with_prefix()
        )
        try:
            file_content = cache_object.get()
            tags_cache = json.loads(file_content["Body"].read().decode("utf-8"))
            last_modified_unix_time = get_last_modified_time(file_content)
        except Exception as e:
            send_forwarder_internal_metrics("s3_cache_fetch_failure")
            self.logger.debug(f"Unable to fetch cache from S3: {e}", exc_info=True)
            return {}, -1

        return tags_cache, last_modified_unix_time

    def _refresh(self):
        """Populate the tags in the local cache by getting cache from s3
        If cache not in s3, then cache is built using build_tags_cache
        """
        self.last_tags_fetch_time = time()

        # If the custom tag fetch env var is not set to true do not fetch
        if not self.should_fetch_tags():
            self.logger.debug(
                "Not fetching custom tags because the env variable for the cache {} is not set to true".format(
                    self.cache_filename
                )
            )
            return

        tags_fetched, last_modified = self.get_cache_from_s3()

        if self._is_expired(last_modified):
            send_forwarder_internal_metrics("s3_cache_expired")
            self.logger.debug("S3 cache expired, rebuilding cache")
            lock_acquired = self.acquire_s3_cache_lock()
            if lock_acquired:
                success, new_tags_fetched = self.build_tags_cache()
                if success:
                    self.tags_by_id = new_tags_fetched
                    self.write_cache_to_s3(self.tags_by_id)
                elif tags_fetched != {}:
                    self.tags_by_id = tags_fetched

                self.release_s3_cache_lock()
        # s3 cache fetch succeeded and isn't expired
        elif last_modified > -1:
            self.tags_by_id = tags_fetched

    def _is_expired(self, last_modified=None):
        """Returns bool for whether the fetch TTL has expired"""
        if not last_modified:
            last_modified = self.last_tags_fetch_time

        earliest_time_to_refetch_tags = last_modified + self.tags_ttl_seconds
        return time() > earliest_time_to_refetch_tags

    def should_fetch_tags(self):
        raise Exception("SHOULD FETCH TAGS MUST BE DEFINED FOR TAGS CACHES")

    def get(self, key):
        raise Exception("GET TAGS MUST BE DEFINED FOR TAGS CACHES")

    def build_tags_cache(self):
        raise Exception("BUILD TAGS MUST BE DEFINED FOR TAGS CACHES")
