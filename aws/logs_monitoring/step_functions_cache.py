from botocore.exceptions import ClientError

from base_tags_cache import (
    BaseTagsCache,
    logger,
    parse_get_resources_response_for_tags_by_arn,
    resource_tagging_client,
    sanitize_aws_tag_string,
    send_forwarder_internal_metrics,
    should_fetch_step_functions_tags,
)
from settings import (
    DD_S3_STEP_FUNCTIONS_CACHE_FILENAME,
    DD_S3_STEP_FUNCTIONS_CACHE_LOCK_FILENAME,
)


class StepFunctionsTagsCache(BaseTagsCache):
    CACHE_FILENAME = DD_S3_STEP_FUNCTIONS_CACHE_FILENAME
    CACHE_LOCK_FILENAME = DD_S3_STEP_FUNCTIONS_CACHE_LOCK_FILENAME

    def should_fetch_tags(self):
        return should_fetch_step_functions_tags()

    def build_tags_cache(self):
        """Makes API calls to GetResources to get the live tags of the account's Step Functions
        Returns an empty dict instead of fetching custom tags if the tag fetch env variable is not
        set to true.
        Returns:
            tags_by_arn_cache (dict<str, str[]>): each Lambda's tags in a dict keyed by ARN
        """
        tags_fetch_success = False
        tags_by_arn_cache = {}
        get_resources_paginator = resource_tagging_client.get_paginator("get_resources")

        try:
            for page in get_resources_paginator.paginate(
                ResourceTypeFilters=["states"], ResourcesPerPage=100
            ):
                send_forwarder_internal_metrics(
                    "step_functions_get_resources_api_calls"
                )
                page_tags_by_arn = parse_get_resources_response_for_tags_by_arn(page)
                tags_by_arn_cache.update(page_tags_by_arn)
                tags_fetch_success = True

        except ClientError as e:
            logger.exception(
                "Encountered a ClientError when trying to fetch tags. You may need to give "
                "this Lambda's role the 'tag:GetResources' permission"
            )
            additional_tags = [
                f"http_status_code:{e.response['ResponseMetadata']['HTTPStatusCode']}"
            ]
            send_forwarder_internal_metrics(
                "client_error", additional_tags=additional_tags
            )

        logger.debug("All Step Functions tags refreshed: {}".format(tags_by_arn_cache))

        return tags_fetch_success, tags_by_arn_cache

    def get(self, state_machine_arn):
        """Get the tags for the Step Functions from the cache

        Will re-fetch the tags if they are out of date, or a log group is encountered
        which isn't in the tag list

        Args:
            state_machine_arn (str): the key we're getting tags from the cache for

        Returns:
            state_machine_tags (List[str]): the list of "key:value" Datadog tag strings
        """
        if self._is_expired():
            send_forwarder_internal_metrics("local_step_functions_tags_cache_expired")
            logger.debug(
                "Local cache expired for Step Functions tags. Fetching cache from S3"
            )
            self._refresh()

        state_machine_tags = self.tags_by_id.get(state_machine_arn, None)
        if state_machine_tags is None:
            # If the custom tag fetch env var is not set to true do not fetch
            if not self.should_fetch_tags():
                logger.debug(
                    "Not fetching custom tags because the env variable DD_FETCH_STEP_FUNCTIONS_TAGS"
                    " is not set to true"
                )
                return []
            state_machine_tags = get_state_machine_tags(state_machine_arn) or []
            self.tags_by_id[state_machine_arn] = state_machine_tags

        return state_machine_tags


def get_state_machine_tags(state_machine_arn: str):
    """Return a list of tags of a state machine in dd format (max 200 chars)

    Example response from get source api:
    {
        "ResourceTagMappingList": [
            {
                "ResourceARN": "arn:aws:states:us-east-1:1234567890:stateMachine:example-machine",
                "Tags": [
                    {
                        "Key": "ENV",
                        "Value": "staging"
                    }
                ]
            }
        ]
    }

    Args:
            state_machine_arn (str): the key we're getting tags from the cache for
    Returns:
        state_machine_arn (List[str]): e.g. ["k1:v1", "k2:v2"]
    """
    response = None
    formatted_tags = []

    try:
        send_forwarder_internal_metrics("get_state_machine_tags")
        response = resource_tagging_client.get_resources(
            ResourceARNList=[state_machine_arn]
        )
    except Exception as e:
        logger.exception(f"Failed to get Step Functions tags due to {e}")

    if len(response.get("ResourceTagMappingList", {})) > 0:
        resource_dict = response.get("ResourceTagMappingList")[0]
        for a_tag in resource_dict.get("Tags", []):
            key = sanitize_aws_tag_string(a_tag["Key"], remove_colons=True)
            value = sanitize_aws_tag_string(
                a_tag.get("Value"), remove_leading_digits=False
            )
            formatted_tags.append(f"{key}:{value}"[:200])  # same logic as lambda

    return formatted_tags
