import os
from botocore.exceptions import ClientError
from caching.base_tags_cache import BaseTagsCache
from caching.common import parse_get_resources_response_for_tags_by_arn
from telemetry import send_forwarder_internal_metrics
from settings import (
    DD_S3_TAGS_CACHE_FILENAME,
    DD_S3_TAGS_CACHE_LOCK_FILENAME,
    GET_RESOURCES_S3_FILTER,
)


class S3TagsCache(BaseTagsCache):
    def __init__(self, prefix):
        super().__init__(
            prefix, DD_S3_TAGS_CACHE_FILENAME, DD_S3_TAGS_CACHE_LOCK_FILENAME
        )

    def should_fetch_tags(self):
        # set it to true if we don't have the environment variable set to keep the default behavior
        return os.environ.get("DD_FETCH_S3_TAGS", "true").lower() == "true"

    def build_tags_cache(self):
        """Makes API calls to GetResources to get the live tags of the account's S3 buckets
        Returns an empty dict instead of fetching custom tags if the tag fetch env variable is not set to true
        Returns:
            tags_by_arn_cache (dict<str, str[]>): each S3 bucket's tags in a dict keyed by ARN
        """
        tags_fetch_success = False
        tags_by_arn_cache = {}
        resource_paginator = self.get_resources_paginator()

        try:
            for page in resource_paginator.paginate(
                ResourceTypeFilters=[GET_RESOURCES_S3_FILTER], ResourcesPerPage=100
            ):
                send_forwarder_internal_metrics("get_s3_resources_api_calls")
                page_tags_by_arn = parse_get_resources_response_for_tags_by_arn(page)
                tags_by_arn_cache.update(page_tags_by_arn)
                tags_fetch_success = True
        except ClientError as e:
            self.logger.exception(
                "Encountered a ClientError when trying to fetch tags. You may need to give "
                "this Lambda's role the 'tag:GetResources' permission"
            )
            additional_tags = [
                f"http_status_code:{e.response['ResponseMetadata']['HTTPStatusCode']}"
            ]
            send_forwarder_internal_metrics(
                "client_error", additional_tags=additional_tags
            )
            tags_fetch_success = False

        self.logger.debug(
            "Built this tags cache from GetResources API calls: %s", tags_by_arn_cache
        )

        return tags_fetch_success, tags_by_arn_cache

    def get(self, bucket_arn):
        if not self.should_fetch_tags():
            self.logger.debug(
                "Not fetching S3  tags because the env variable DD_FETCH_S3_TAGS is "
                "not set to true"
            )
            return []

        if self._is_expired():
            send_forwarder_internal_metrics("local_s3_tags_cache_expired")
            self.logger.debug("Local cache expired, fetching cache from S3")
            self._refresh()

        return self.tags_by_id.get(bucket_arn, [])
