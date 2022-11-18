import boto3

from base_tags_cache import (
    BaseTagsCache,
    logger,
    sanitize_aws_tag_string,
    send_forwarder_internal_metrics,
    should_fetch_log_group_tags,
)
from settings import (
    DD_S3_LOG_GROUP_CACHE_FILENAME,
    DD_S3_LOG_GROUP_CACHE_LOCK_FILENAME,
)


class CloudwatchLogGroupTagsCache(BaseTagsCache):
    CACHE_FILENAME = DD_S3_LOG_GROUP_CACHE_FILENAME
    CACHE_LOCK_FILENAME = DD_S3_LOG_GROUP_CACHE_LOCK_FILENAME

    def should_fetch_tags(self):
        return should_fetch_log_group_tags()

    def build_tags_cache(self):
        """Makes API calls to GetResources to get the live tags of the account's Lambda functions

        Returns an empty dict instead of fetching custom tags if the tag fetch env variable is not set to true

        Returns:
            tags_by_arn_cache (dict<str, str[]>): each Lambda's tags in a dict keyed by ARN
        """
        new_tags = {}
        for log_group in self.tags_by_id.keys():
            log_group_tags = get_log_group_tags(log_group)
            # If we didn't get back log group tags we'll use the locally cached ones if they exist
            # This avoids losing tags on a failed api call
            if log_group_tags is None:
                log_group_tags = self.tags_by_id.get(log_group, [])
            new_tags[log_group] = log_group_tags

        logger.debug("All tags in Cloudwatch Log Groups refresh: {}".format(new_tags))
        return True, new_tags

    def get(self, log_group):
        """Get the tags for the Cloudwatch Log Group from the cache

        Will refetch the tags if they are out of date, or a log group is encountered
        which isn't in the tag list

        Args:
            key (str): the key we're getting tags from the cache for

        Returns:
            log_group_tags (str[]): the list of "key:value" Datadog tag strings
        """
        if self._is_expired():
            send_forwarder_internal_metrics("local_cache_expired")
            logger.debug("Local cache expired, fetching cache from S3")
            self._refresh()

        log_group_tags = self.tags_by_id.get(log_group, None)
        if log_group_tags is None:
            # If the custom tag fetch env var is not set to true do not fetch
            if not self.should_fetch_tags():
                logger.debug(
                    "Not fetching custom tags because the env variable DD_FETCH_LOG_GROUP_TAGS is "
                    "not set to true"
                )
                return []
            log_group_tags = get_log_group_tags(log_group) or []
            self.tags_by_id[log_group] = log_group_tags

        return log_group_tags


def get_log_group_tags(log_group):
    response = None
    try:
        send_forwarder_internal_metrics("list_tags_log_group_api_call")
        response = cloudwatch_logs_client.list_tags_log_group(logGroupName=log_group)
    except Exception as e:
        logger.exception(f"Failed to get log group tags due to {e}")
    formatted_tags = None
    if response is not None:
        formatted_tags = [
            "{key}:{value}".format(
                key=sanitize_aws_tag_string(k, remove_colons=True),
                value=sanitize_aws_tag_string(v, remove_leading_digits=False),
            )
            if v
            else sanitize_aws_tag_string(k, remove_colons=True)
            for k, v in response["tags"].items()
        ]
    return formatted_tags


cloudwatch_logs_client = boto3.client("logs")
