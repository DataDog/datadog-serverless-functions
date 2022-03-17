import logging
import os
import json
import datetime
import re
from collections import defaultdict
from time import time
from random import randint

import boto3
from botocore.exceptions import ClientError

from settings import (
    DD_S3_BUCKET_NAME,
    DD_TAGS_CACHE_TTL_SECONDS,
    DD_S3_CACHE_LOCK_TTL_SECONDS,
    DD_S3_CACHE_FILENAME,
    DD_S3_CACHE_LOCK_FILENAME,
    DD_S3_LOG_GROUP_CACHE_FILENAME,
    DD_S3_LOG_GROUP_CACHE_LOCK_FILENAME,
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

_other_chars = r"\w:\-\.\/"
Sanitize = re.compile(r"[^%s]" % _other_chars, re.UNICODE).sub
Dedupe = re.compile(r"_+", re.UNICODE).sub
FixInit = re.compile(r"^[_\d]*", re.UNICODE).sub


def sanitize_aws_tag_string(tag, remove_colons=False, remove_leading_digits=True):
    """Convert characters banned from DD but allowed in AWS tags to underscores"""
    global Sanitize, Dedupe, FixInit

    # 1. Replace colons with _
    # 2. Convert to all lowercase unicode string
    # 3. Convert bad characters to underscores
    # 4. Dedupe contiguous underscores
    # 5. Remove initial underscores/digits such that the string
    #    starts with an alpha char
    #    FIXME: tag normalization incorrectly supports tags starting
    #    with a ':', but this behavior should be phased out in future
    #    as it results in unqueryable data.  See dogweb/#11193
    # 6. Strip trailing underscores

    if len(tag) == 0:
        # if tag is empty, nothing to do
        return tag

    if remove_colons:
        tag = tag.replace(":", "_")
    tag = Dedupe("_", Sanitize("_", tag.lower()))
    if remove_leading_digits:
        first_char = tag[0]
        if first_char == "_" or "0" <= first_char <= "9":
            tag = FixInit("", tag)
    tag = tag.rstrip("_")
    return tag


def send_forwarder_internal_metrics(name, additional_tags=[]):
    """Send forwarder's internal metrics to DD"""
    lambda_stats.distribution(
        "{}.{}".format(DD_FORWARDER_TELEMETRY_NAMESPACE_PREFIX, name),
        1,
        tags=get_forwarder_telemetry_tags() + additional_tags,
    )


def should_fetch_lambda_tags():
    """Checks the env var to determine if the customer has opted-in to fetching lambda tags"""
    return os.environ.get("DD_FETCH_LAMBDA_TAGS", "false").lower() == "true"


def should_fetch_log_group_tags():
    """Checks the env var to determine if the customer has opted-in to fetching log group tags"""
    return os.environ.get("DD_FETCH_LOG_GROUP_TAGS", "false").lower() == "true"


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

        self.tags_by_id = {}
        self.last_tags_fetch_time = 0

    def write_cache_to_s3(self, data):
        """Writes tags cache to s3"""
        try:
            logger.debug("Trying to write data to s3: {}".format(data))
            s3_object = s3_client.Object(DD_S3_BUCKET_NAME, self.CACHE_FILENAME)
            s3_object.put(Body=(bytes(json.dumps(data).encode("UTF-8"))))
        except ClientError:
            send_forwarder_internal_metrics("s3_cache_write_failure")
            logger.debug("Unable to write new cache to S3", exc_info=True)

    def acquire_s3_cache_lock(self):
        """Acquire cache lock"""
        cache_lock_object = s3_client.Object(
            DD_S3_BUCKET_NAME, self.CACHE_LOCK_FILENAME
        )
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
        if not self.should_fetch_tags():
            logger.debug(
                "Not fetching custom tags because the env variable DD_FETCH_LAMBDA_TAGS is not set to true"
            )
            return

        tags_fetched, last_modified = self.get_cache_from_s3()

        if self._is_expired(last_modified):
            send_forwarder_internal_metrics("s3_cache_expired")
            logger.debug("S3 cache expired, rebuilding cache")
            lock_acquired = self.acquire_s3_cache_lock()
            if lock_acquired:
                success, tags_fetched = self.build_tags_cache()
                if success:
                    self.tags_by_id = tags_fetched
                    self.write_cache_to_s3(self.tags_by_id)

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


######################
# Lambda Custom Tags #
######################

resource_tagging_client = boto3.client("resourcegroupstaggingapi")
GET_RESOURCES_LAMBDA_FILTER = "lambda"


def get_dd_tag_string_from_aws_dict(aws_key_value_tag_dict):
    """Converts the AWS dict tag format to the dd key:value string format and truncates to 200 characters

    Args:
        aws_key_value_tag_dict (dict): the dict the GetResources endpoint returns for a tag
            ex: { "Key": "creator", "Value": "swf"}

    Returns:
        key:value colon-separated string built from the dict
            ex: "creator:swf"
    """
    key = sanitize_aws_tag_string(aws_key_value_tag_dict["Key"], remove_colons=True)
    value = sanitize_aws_tag_string(
        aws_key_value_tag_dict.get("Value"), remove_leading_digits=False
    )
    # Value is optional in DD and AWS
    if not value:
        return key
    return f"{key}:{value}"[0:200]


def parse_get_resources_response_for_tags_by_arn(get_resources_page):
    """Parses a page of GetResources response for the mapping from ARN to tags

    Args:
        get_resources_page (dict<str, dict<str, dict | str>[]>): one page of the GetResources response.
            Partial example:
                {"ResourceTagMappingList": [{
                    'ResourceARN': 'arn:aws:lambda:us-east-1:123497598159:function:my-test-lambda',
                    'Tags': [{'Key': 'stage', 'Value': 'dev'}, {'Key': 'team', 'Value': 'serverless'}]
                }]}

    Returns:
        tags_by_arn (dict<str, str[]>): Lambda tag lists keyed by ARN
    """
    tags_by_arn = defaultdict(list)

    aws_resouce_tag_mappings = get_resources_page["ResourceTagMappingList"]
    for aws_resource_tag_mapping in aws_resouce_tag_mappings:
        function_arn = aws_resource_tag_mapping["ResourceARN"]
        lowercase_function_arn = function_arn.lower()

        raw_aws_tags = aws_resource_tag_mapping["Tags"]
        tags = map(get_dd_tag_string_from_aws_dict, raw_aws_tags)

        tags_by_arn[lowercase_function_arn] += tags

    return tags_by_arn


class LambdaCustomTagsCache(LambdaTagsCache):
    CACHE_FILENAME = DD_S3_CACHE_FILENAME
    CACHE_LOCK_FILENAME = DD_S3_CACHE_LOCK_FILENAME

    def should_fetch_tags(self):
        return should_fetch_lambda_tags()

    def build_tags_cache(self):
        """Makes API calls to GetResources to get the live tags of the account's Lambda functions

        Returns an empty dict instead of fetching custom tags if the tag fetch env variable is not set to true

        Returns:
            tags_by_arn_cache (dict<str, str[]>): each Lambda's tags in a dict keyed by ARN
        """
        tags_fetch_success = False
        tags_by_arn_cache = {}
        get_resources_paginator = resource_tagging_client.get_paginator("get_resources")

        try:
            for page in get_resources_paginator.paginate(
                ResourceTypeFilters=[GET_RESOURCES_LAMBDA_FILTER], ResourcesPerPage=100
            ):
                send_forwarder_internal_metrics("get_resources_api_calls")
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

        logger.debug(
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
        if self._is_expired():
            send_forwarder_internal_metrics("local_cache_expired")
            logger.debug("Local cache expired, fetching cache from S3")
            self._refresh()

        function_tags = self.tags_by_id.get(key, [])
        return function_tags


#############################
# Cloudwatch Log Group Tags #
#############################

cloudwatch_logs_client = boto3.client("logs")


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


class CloudwatchLogGroupTagsCache(LambdaTagsCache):
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
                    "Not fetching custom tags because the env variable DD_FETCH_LAMBDA_TAGS is not set to true"
                )
                return []
            log_group_tags = get_log_group_tags(log_group) or []
            self.tags_by_id[log_group] = log_group_tags

        return log_group_tags
