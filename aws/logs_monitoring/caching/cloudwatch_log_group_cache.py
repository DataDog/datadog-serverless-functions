import json
import logging
import os
from random import randint
from time import time

import boto3
from botocore.config import Config

from caching.common import sanitize_aws_tag_string
from settings import (
    DD_S3_BUCKET_NAME,
    DD_S3_CACHE_DIRNAME,
    DD_S3_LOG_GROUP_CACHE_DIRNAME,
    DD_TAGS_CACHE_TTL_SECONDS,
    get_fetch_log_group_tags,
)
from telemetry import send_forwarder_internal_metrics


class CloudwatchLogGroupTagsCache:
    def __init__(
        self,
        prefix,
    ):
        self.cache_dirname = f"{DD_S3_CACHE_DIRNAME}/{DD_S3_LOG_GROUP_CACHE_DIRNAME}"
        self.cache_ttl_seconds = DD_TAGS_CACHE_TTL_SECONDS
        self.bucket_name = DD_S3_BUCKET_NAME
        self.cache_prefix = prefix
        self.tags_by_log_group = {}
        # We need to use the standard retry mode for the Cloudwatch Logs client that defaults to 3 retries
        self.cloudwatch_logs_client = boto3.client(
            "logs", config=Config(retries={"mode": "standard"})
        )
        self.s3_client = boto3.client("s3")

        self.logger = logging.getLogger()
        self.logger.setLevel(
            logging.getLevelName(os.environ.get("DD_LOG_LEVEL", "INFO").upper())
        )

    def get(self, log_group_arn):
        """Get the tags for the Cloudwatch Log Group from the cache

        Will refetch the tags if they are out of date, or a log group is encountered
        which isn't in the tag list

        Args:
            key (str): the key we're getting tags from the cache for

        Returns:
            log_group_tags (str[]): the list of "key:value" Datadog tag strings
        """
        # If the custom tag fetch env var is not set to true do not fetch tags
        if not self._should_fetch_tags():
            self.logger.debug(
                "Not fetching custom tags because the env variable DD_FETCH_LOG_GROUP_TAGS is "
                "not set to true"
            )
            return []

        return self._fetch_log_group_tags(log_group_arn)

    def _should_fetch_tags(self):
        return get_fetch_log_group_tags()

    def _fetch_log_group_tags(self, log_group_arn):
        # first, check in-memory cache
        log_group_tags_struct = self.tags_by_log_group.get(log_group_arn, None)
        if log_group_tags_struct and not self._is_expired(
            log_group_tags_struct.get("last_modified", None)
        ):
            send_forwarder_internal_metrics("loggroup_local_cache_hit")
            return log_group_tags_struct.get("tags", [])

        # then, check cache file, update and return
        cache_file_name = self._get_cache_file_name(log_group_arn)
        log_group_tags, last_modified = self._get_log_group_tags_from_cache(
            cache_file_name
        )
        if log_group_tags and not self._is_expired(last_modified):
            self.tags_by_log_group[log_group_arn] = {
                "tags": log_group_tags,
                "last_modified": time(),
            }
            send_forwarder_internal_metrics("loggroup_s3_cache_hit")
            return log_group_tags

        # finally, make an api call, update and return
        log_group_tags = self._get_log_group_tags(log_group_arn) or []
        self._update_log_group_tags_cache(log_group_arn, log_group_tags)
        self.tags_by_log_group[log_group_arn] = {
            "tags": log_group_tags,
            "last_modified": time(),
        }

        return log_group_tags

    def _get_log_group_tags_from_cache(self, cache_file_name):
        try:
            response = self.s3_client.get_object(
                Bucket=self.bucket_name, Key=cache_file_name
            )
            tags_cache = json.loads(response.get("Body").read().decode("utf-8"))
            last_modified_unix_time = int(response.get("LastModified").timestamp())
        except Exception:
            send_forwarder_internal_metrics("loggroup_cache_fetch_failure")
            self.logger.exception(
                "Failed to get log group tags from cache", exc_info=True
            )
            return None, -1

        return tags_cache, last_modified_unix_time

    def _update_log_group_tags_cache(self, log_group, tags):
        cache_file_name = self._get_cache_file_name(log_group)
        try:
            self.s3_client.put_object(
                Bucket=self.bucket_name,
                Key=cache_file_name,
                Body=(bytes(json.dumps(tags).encode("UTF-8"))),
            )
        except Exception:
            send_forwarder_internal_metrics("loggroup_cache_write_failure")
            self.logger.exception(
                "Failed to update log group tags cache", exc_info=True
            )

    def _is_expired(self, last_modified):
        if not last_modified:
            return True

        # add a random number of seconds to avoid having all tags refetched at the same time
        earliest_time_to_refetch_tags = (
            last_modified + self.cache_ttl_seconds + randint(1, 100)
        )
        return time() > earliest_time_to_refetch_tags

    def _get_cache_file_name(self, log_group_arn):
        log_group_name = log_group_arn.replace("/", "_").replace(":", "_")
        return f"{self._get_cache_file_prefix()}/{log_group_name}.json"

    def _get_cache_file_prefix(self):
        return f"{self.cache_dirname}/{self.cache_prefix}"

    def _get_log_group_tags(self, log_group_arn):
        response = None
        try:
            send_forwarder_internal_metrics("list_tags_log_group_api_call")
            response = self.cloudwatch_logs_client.list_tags_for_resource(
                resourceArn=log_group_arn
            )
        except Exception:
            self.logger.exception("Failed to get log group tags", exc_info=True)
        formatted_tags = None
        if response is not None:
            formatted_tags = [
                (
                    "{key}:{value}".format(
                        key=sanitize_aws_tag_string(k, remove_colons=True),
                        value=sanitize_aws_tag_string(v, remove_leading_digits=False),
                    )
                    if v
                    else sanitize_aws_tag_string(k, remove_colons=True)
                )
                for k, v in response["tags"].items()
            ]
        return formatted_tags
