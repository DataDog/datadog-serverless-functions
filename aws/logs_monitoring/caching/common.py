import os
import datetime
import logging
import re
from collections import defaultdict

logger = logging.getLogger()
logger.setLevel(logging.getLevelName(os.environ.get("DD_LOG_LEVEL", "INFO").upper()))


_other_chars = r"\w:\-\.\/"
Sanitize = re.compile(r"[^%s]" % _other_chars, re.UNICODE).sub
Dedupe = re.compile(r"_+", re.UNICODE).sub
FixInit = re.compile(r"^[_\d]*", re.UNICODE).sub


def get_last_modified_time(s3_file):
    last_modified_str = s3_file["ResponseMetadata"]["HTTPHeaders"]["last-modified"]
    last_modified_date = datetime.datetime.strptime(
        last_modified_str, "%a, %d %b %Y %H:%M:%S %Z"
    )
    last_modified_unix_time = int(last_modified_date.strftime("%s"))
    return last_modified_unix_time


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
