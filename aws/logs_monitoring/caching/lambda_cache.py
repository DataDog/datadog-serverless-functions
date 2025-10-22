from botocore.exceptions import ClientError

from caching.base_tags_cache import BaseTagsCache
from caching.common import parse_get_resources_response_for_tags_by_arn
from settings import (
    DD_S3_LAMBDA_CACHE_FILENAME,
    DD_S3_LAMBDA_CACHE_LOCK_FILENAME,
    GET_RESOURCES_LAMBDA_FILTER,
    get_fetch_lambda_tags,
)
from telemetry import send_forwarder_internal_metrics


class LambdaTagsCache(BaseTagsCache):
    def __init__(self, prefix):
        super().__init__(
            prefix, DD_S3_LAMBDA_CACHE_FILENAME, DD_S3_LAMBDA_CACHE_LOCK_FILENAME
        )

    def should_fetch_tags(self):
        return get_fetch_lambda_tags()

    def build_tags_cache(self):
        """Makes API calls to GetResources to get the live tags of the account's Lambda functions

        Returns an empty dict instead of fetching custom tags if the tag fetch env variable is not set to true

        Returns:
            tags_by_arn_cache (dict<str, str[]>): each Lambda's tags in a dict keyed by ARN
        """
        tags_fetch_success = False
        tags_by_arn_cache = {}
        resource_paginator = self.get_resources_paginator()

        try:
            for page in resource_paginator.paginate(
                ResourceTypeFilters=[GET_RESOURCES_LAMBDA_FILTER], ResourcesPerPage=100
            ):
                send_forwarder_internal_metrics("get_resources_api_calls")
                page_tags_by_arn = parse_get_resources_response_for_tags_by_arn(page)
                tags_by_arn_cache.update(page_tags_by_arn)
                tags_fetch_success = True

        except ClientError as e:
            self.logger.error(
                f"Failed to fetch Lambda tags: {e}. "
                "Add 'tag:GetResources' permission to the Forwarder's IAM role."
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
        if not self.should_fetch_tags():
            self.logger.debug(
                "Not fetching lambda function tags because the env variable DD_FETCH_LAMBDA_TAGS is "
                "not set to true"
            )
            return []

        if self._is_expired():
            send_forwarder_internal_metrics("local_lambda_cache_expired")
            self.logger.debug("Local cache expired, fetching cache from S3")
            self._refresh()

        return self.tags_by_id.get(key, [])
