from collections import defaultdict
from time import time

import boto3


ILLEGAL_CHARACTERS = {":", "/", "-"}
REPLACEMENT_CHARACTER = "_"


resource_tagging_client = boto3.client("resourcegroupstaggingapi")


def sanitize_aws_tag_string(raw_string):
    """Convert banned characters to underscores
    """
    sanitized_string = ""
    for character in raw_string:
        if character in ILLEGAL_CHARACTERS:
            sanitized_string += REPLACEMENT_CHARACTER
            continue
        sanitized_string += character
    return sanitized_string


def get_dd_tag_string_from_aws_dict(aws_key_value_tag_dict):
    """Converts the AWS dict tag format to the dd key:value string format

    Args:
        aws_key_value_tag_dict (dict): the dict the GetResources endpoint returns for a tag
            ex: { "Key": "creator", "Value": "swf"}

    Returns:
        key:value colon-separated string built from the dict
            ex: "creator:swf"
    """
    key = sanitize_aws_tag_string(aws_key_value_tag_dict["Key"])
    value = sanitize_aws_tag_string(aws_key_value_tag_dict["Value"])
    return "{}:{}".format(key, value)


def build_arn_to_tags_cache(resource_filter):
    """Makes API calls to GetResources to get the live tags of the resources
    """
    arn_to_tags_cache = defaultdict(list)
    get_resources_paginator = resource_tagging_client.get_paginator("get_resources")

    for page in get_resources_paginator.paginate(
        ResourceTypeFilters=[resource_filter], ResourcesPerPage=100
    ):
        # log.info("Response from resource tagging endpoint: %s", page)
        aws_resouce_tag_mapping_list = page["ResourceTagMappingList"]
        for aws_resource_tag_mapping in aws_resouce_tag_mapping_list:
            function_arn = aws_resource_tag_mapping["ResourceARN"]
            raw_aws_tags = aws_resource_tag_mapping["Tags"]
            tags = map(get_dd_tag_string_from_aws_dict, raw_aws_tags)

            arn_to_tags_cache[function_arn] += tags

    # log.info(
    #     "Computed this arn_to_tags_cache of length %s size %s bytes: %s",
    #     len(arn_to_tags_cache),
    #     get_recursive_size(arn_to_tags_cache),
    #     arn_to_tags_cache,
    # )
    # average_tags_per_function = (
    #     sum([len(tag_list) for tag_list in arn_to_tags_cache.values()])
    #     * 1.0
    #     / len(arn_to_tags_cache)
    # )
    # log.info("Found an average of %s tags per function", average_tags_per_function)
    return arn_to_tags_cache


class TagsCache(object):
    def __init__(self, resource_filter, tags_ttl_seconds):
        self.resource_filter = resource_filter
        self.tags_ttl_seconds = tags_ttl_seconds

        self.tags_by_arn = {}
        self.last_tags_fetch_time = 0

        self._fetch_tags()

    def _fetch_tags(self):
        """Populate the tags in the cache by making calls to GetResources
        """
        self.tags_by_arn = build_arn_to_tags_cache(self.resource_filter)
        self.last_tags_fetch_time = time()

    def _are_tags_out_of_date(self):
        """Returns bool for whether the tag fetch TTL has expired
        """
        time_now = time()
        time_to_refetch_tags = self.last_tags_fetch_time + self.tags_ttl_seconds
        return time_now > time_to_refetch_tags

    def get_tags(self, resource_arn):
        """Get the tags for the resource from the cache

        Will refetch the tags if they are out of date
        """
        if self._are_tags_out_of_date():
            self._fetch_tags()

        return self.tags_by_arn.get(resource_arn)
