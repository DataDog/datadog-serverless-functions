
import logging
import os
import json
import datetime
from time import time
from random import randint

import boto3
from botocore.exceptions import ClientError

from settings import (
    DD_S3_BUCKET_NAME,
    DD_TAGS_CACHE_TTL_SECONDS,
    DD_S3_CACHE_LOCK_TTL_SECONDS,
)
from telemetry import (
    DD_FORWARDER_TELEMETRY_NAMESPACE_PREFIX,
    get_forwarder_telemetry_tags,
)


JITTER_MIN = 1
JITTER_MAX = 100

DD_TAGS_CACHE_TTL_SECONDS = DD_TAGS_CACHE_TTL_SECONDS + randint(JITTER_MIN, JITTER_MAX)
s3_client = boto3.resource("s3")

logger = logging.getLogger()

try:
    from datadog_lambda.metric import lambda_stats

    DD_SUBMIT_ENHANCED_METRICS = True
except ImportError:
    logger.debug(
        "Could not import from the Datadog Lambda layer so enhanced metrics won't be submitted. "
        "Add the Datadog Lambda layer to this function to submit enhanced metrics."
    )
    DD_SUBMIT_ENHANCED_METRICS = False


def send_forwarder_internal_metrics(name, additional_tags=[]):
    """Send forwarder's internal metrics to DD"""
    lambda_stats.distribution(
        "{}.{}".format(DD_FORWARDER_TELEMETRY_NAMESPACE_PREFIX, name),
        1,
        tags=get_forwarder_telemetry_tags() + additional_tags,
    )


def should_fetch_custom_tags():
    """Checks the env var to determine if the customer has opted-in to fetching custom tags"""
    return os.environ.get("DD_FETCH_LAMBDA_TAGS", "false").lower() == "true"


def get_last_modified_time(s3_file):
    last_modified_str = s3_file["ResponseMetadata"]["HTTPHeaders"]["last-modified"]
    last_modified_date = datetime.datetime.strptime(
        last_modified_str, "%a, %d %b %Y %H:%M:%S %Z"
    )
    last_modified_unix_time = int(last_modified_date.strftime("%s"))
    return last_modified_unix_time


class LambdaTagsCache(object):

    CACHE_FILENAME = None
    CACHE_LOCK_FILENAME = None

    def __init__(self, tags_ttl_seconds=DD_TAGS_CACHE_TTL_SECONDS):
        self.tags_ttl_seconds = tags_ttl_seconds

        self.tags_by_arn = {}
        self.last_tags_fetch_time = 0

    def write_cache_to_s3(self, data):
        """Writes tags cache to s3"""
        try:
            s3_object = s3_client.Object(DD_S3_BUCKET_NAME, self.CACHE_FILENAME)
            s3_object.put(Body=(bytes(json.dumps(data).encode("UTF-8"))))
        except ClientError:
            send_forwarder_internal_metrics("s3_cache_write_failure")
            logger.debug("Unable to write new cache to S3", exc_info=True)

    def acquire_s3_cache_lock(self):
        """Acquire cache lock"""
        cache_lock_object = s3_client.Object(DD_S3_BUCKET_NAME, self.CACHE_LOCK_FILENAME)
        try:
            file_content = cache_lock_object.get()

            # check lock file expiration
            last_modified_unix_time = get_last_modified_time(file_content)
            if last_modified_unix_time + DD_S3_CACHE_LOCK_TTL_SECONDS >= time():
                return False
        except Exception:
            logger.debug("Unable to get cache lock file")

        # lock file doesn't exist, create file to acquire lock
        try:
            cache_lock_object.put(Body=(bytes("lock".encode("UTF-8"))))
            send_forwarder_internal_metrics("s3_cache_lock_acquired")
            logger.debug("S3 cache lock acquired")
        except ClientError:
            logger.debug("Unable to write S3 cache lock file", exc_info=True)
            return False

        return True

    def release_s3_cache_lock(self):
        """Release cache lock"""
        try:
            cache_lock_object = s3_client.Object(
                DD_S3_BUCKET_NAME, self.CACHE_LOCK_FILENAME
            )
            cache_lock_object.delete()
            send_forwarder_internal_metrics("s3_cache_lock_released")
            logger.debug("S3 cache lock released")
        except ClientError:
            send_forwarder_internal_metrics("s3_cache_lock_release_failure")
            logger.debug("Unable to release S3 cache lock", exc_info=True)

    def get_cache_from_s3(self):
        """Retrieves tags cache from s3 and returns the body along with
        the last modified datetime for the cache"""
        cache_object = s3_client.Object(DD_S3_BUCKET_NAME, self.CACHE_FILENAME)
        try:
            file_content = cache_object.get()
            tags_cache = json.loads(file_content["Body"].read().decode("utf-8"))
            last_modified_unix_time = get_last_modified_time(file_content)
        except:
            send_forwarder_internal_metrics("s3_cache_fetch_failure")
            logger.debug("Unable to fetch cache from S3", exc_info=True)
            return {}, -1

        return tags_cache, last_modified_unix_time

    def _refresh(self):
        """Populate the tags in the local cache by getting cache from s3
        If cache not in s3, then cache is built using build_tags_cache
        """
        self.last_tags_fetch_time = time()

        # If the custom tag fetch env var is not set to true do not fetch
        if not should_fetch_custom_tags():
            logger.debug(
                "Not fetching custom tags because the env variable DD_FETCH_LAMBDA_TAGS is not set to true"
            )
            return

        tags_fetched, last_modified = self.get_cache_from_s3()

        # s3 cache fetch succeeded
        if last_modified > -1:
            self.tags_by_arn = tags_fetched

        if self._is_expired(last_modified):
            send_forwarder_internal_metrics("s3_cache_expired")
            logger.debug(
                "S3 cache expired, rebuilding cache"
            )
            lock_acquired = self.acquire_s3_cache_lock()
            if lock_acquired:
                success, tags_fetched = self.build_tags_cache()
                if success:
                    self.tags_by_arn = tags_fetched
                    self.write_cache_to_s3(self.tags_by_arn)

                self.release_s3_cache_lock()

    def _is_expired(self, last_modified=None):
        """Returns bool for whether the fetch TTL has expired"""
        if not last_modified:
            last_modified = self.last_tags_fetch_time

        earliest_time_to_refetch_tags = last_modified + self.tags_ttl_seconds
        return time() > earliest_time_to_refetch_tags

    def get(self, key):
        """Get the tags for the Lambda function from the cache

        Will refetch the tags if they are out of date, or a lambda arn is encountered
        which isn't in the tag list

        Note: the ARNs in the cache have been lowercased, so resource_arn must be lowercased

        Args:
            key (str): the key we're getting tags from the cache for

        Returns:
            lambda_tags (str[]): the list of "key:value" Datadog tag strings
        """
        if self._is_expired():
            send_forwarder_internal_metrics("local_cache_expired")
            logger.debug("Local cache expired, fetching cache from S3")
            self._refresh()

        function_tags = self.tags_by_arn.get(key, [])
        return function_tags

    def build_tags_cache(self):
        raise Exception("BUILD TAGS MUST BE DEFINED FOR TAGS CACHES")
