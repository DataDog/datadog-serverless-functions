import gzip
import json
import logging
import os
import re
import urllib.parse
from io import BufferedReader, BytesIO

import boto3
import botocore
from caching.s3_tags_cache import S3TagsCache
from settings import (
    CN_STRING,
    DD_HOST,
    DD_CUSTOM_TAGS,
    DD_MULTILINE_LOG_REGEX_PATTERN,
    DD_SOURCE,
    DD_USE_VPC,
    GOV_STRING,
)
from steps.enums import AwsEventSource, AwsS3EventSourceKeyword
from steps.common import add_service_tag, is_cloudtrail, merge_dicts, parse_event_source

if DD_MULTILINE_LOG_REGEX_PATTERN:
    try:
        MULTILINE_REGEX = re.compile(
            "[\n\r\f]+(?={})".format(DD_MULTILINE_LOG_REGEX_PATTERN)
        )
    except Exception:
        raise Exception(
            "could not compile multiline regex with pattern: {}".format(
                DD_MULTILINE_LOG_REGEX_PATTERN
            )
        )
    MULTILINE_REGEX_START_PATTERN = re.compile(
        "^{}".format(DD_MULTILINE_LOG_REGEX_PATTERN)
    )
s3_tags_cache = S3TagsCache()

logger = logging.getLogger()
logger.setLevel(logging.getLevelName(os.environ.get("DD_LOG_LEVEL", "INFO").upper()))


# Handle S3 events
def s3_handler(event, context, metadata):
    # Get the S3 client
    s3 = get_s3_client()
    # if this is a S3 event carried in a SNS message, extract it and override the event
    first_record = event.get("Records")[0]
    if sns := first_record.get("Sns"):
        event = json.loads(sns.get("Message"))
    # Get the object from the event and show its content type
    bucket = first_record.get("s3").get("bucket").get("name")
    key = urllib.parse.unquote_plus(first_record.get("s3").get("object").get("key"))
    source = set_source(event, metadata, bucket, key)
    # Add Service tag
    add_service_tag(metadata)
    # Get the ARN of the service and set it as the hostname
    set_host(context, metadata, bucket, key, source)
    # Add S3 bucket tags
    add_s3_tags_from_cache(metadata, bucket)
    # Extract S3 object
    data = extract_data(s3, bucket, key)

    yield from get_structured_lines_for_s3_handler(data, bucket, key, source)


def extract_data(s3, bucket, key):
    response = s3.get_object(Bucket=bucket, Key=key)
    body = response.get("Body")
    data = body.read()
    return data


def get_s3_client():
    # Need to use path style to access s3 via VPC Endpoints
    # https://github.com/gford1000-aws/lambda_s3_access_using_vpc_endpoint#boto3-specific-notes
    if DD_USE_VPC:
        s3 = boto3.client(
            "s3",
            os.environ["AWS_REGION"],
            config=botocore.config.Config(s3={"addressing_style": "path"}),
        )
    else:
        s3 = boto3.client("s3")
    return s3


def add_s3_tags_from_cache(metadata, bucket):
    bucket_arn = get_s3_arn(bucket)

    if metadata.get(DD_HOST, "") == bucket_arn:
        return

    s3_tags = s3_tags_cache.get(bucket_arn)
    if len(s3_tags) > 0:
        metadata[DD_CUSTOM_TAGS] = (
            ",".join(s3_tags)
            if not metadata[DD_CUSTOM_TAGS]
            else metadata[DD_CUSTOM_TAGS] + "," + ",".join(s3_tags)
        )


def set_source(event, metadata, bucket, key):
    source = parse_event_source(event, key)
    if str(AwsS3EventSourceKeyword.TRANSITAGATEWAY) in bucket:
        source = AwsEventSource.TRANSITGATEWAY
    metadata[DD_SOURCE] = source

    return source


def set_host(context, metadata, bucket, key, source):
    hostname = parse_service_arn(source, key, bucket, context)
    if hostname:
        metadata[DD_HOST] = hostname


def get_structured_lines_for_s3_handler(data, bucket, key, source):
    # Decompress data that has a .gz extension or magic header http://www.onicos.com/staff/iz/formats/gzip.html
    if key[-3:] == ".gz" or data[:2] == b"\x1f\x8b":
        with gzip.GzipFile(fileobj=BytesIO(data)) as decompress_stream:
            # Reading line by line avoid a bug where gzip would take a very long time (>5min) for
            # file around 60MB gzipped
            data = b"".join(BufferedReader(decompress_stream))

    is_cloudtrail_bucket = False
    if is_cloudtrail(str(key)):
        try:
            cloud_trail = json.loads(data)
            if cloud_trail.get("Records") is not None:
                # only parse as a cloudtrail bucket if we have a Records field to parse
                is_cloudtrail_bucket = True
                for event in cloud_trail.get("Records"):
                    # Create structured object and send it
                    structured_line = merge_dicts(
                        event, {"aws": {"s3": {"bucket": bucket, "key": key}}}
                    )
                    yield structured_line
        except Exception as e:
            logger.debug("Unable to parse cloudtrail log: %s" % e)

    if not is_cloudtrail_bucket:
        # Check if using multiline log regex pattern
        # and determine whether line or pattern separated logs
        data = data.decode("utf-8", errors="ignore")
        if DD_MULTILINE_LOG_REGEX_PATTERN and MULTILINE_REGEX_START_PATTERN.match(data):
            split_data = MULTILINE_REGEX_START_PATTERN.split(data)
        else:
            if DD_MULTILINE_LOG_REGEX_PATTERN:
                logger.debug(
                    "DD_MULTILINE_LOG_REGEX_PATTERN %s did not match start of file, splitting by line",
                    DD_MULTILINE_LOG_REGEX_PATTERN,
                )
            if source == str(AwsEventSource.WAF):
                # WAF logs are \n separated
                split_data = [d for d in data.split("\n") if d != ""]
            else:
                split_data = data.splitlines()

        # Send lines to Datadog
        for line in split_data:
            # Create structured object and send it
            structured_line = {
                "aws": {"s3": {"bucket": bucket, "key": key}},
                "message": line,
            }
            yield structured_line


def parse_service_arn(source, key, bucket, context):
    src = AwsEventSource._value2member_map_.get(source)
    match src:
        case AwsEventSource.ELB:
            return handle_elb_source(key)
        case AwsEventSource.S3:
            # For S3 access logs we use the bucket name to rebuild the arn
            return get_s3_arn(bucket) if bucket else None
        case AwsEventSource.CLOUDFRONT:
            return handle_cloudfront_source(context, key)
        case AwsEventSource.REDSHIFT:
            return handle_redshift_source(key)

    return


def handle_elb_source(key):
    # For ELB logs we parse the filename to extract parameters in order to rebuild the ARN
    # 1. We extract the region from the filename
    # 2. We extract the loadbalancer name and replace the "." by "/" to match the ARN format
    # 3. We extract the id of the loadbalancer
    # 4. We build the arn
    idsplit = key.split("/")
    if not idsplit:
        logger.debug("Invalid service ARN, unable to parse ELB ARN")
        return
    # If there is a prefix on the S3 bucket, remove the prefix before splitting the key
    if idsplit[0] != "AWSLogs":
        try:
            idsplit = idsplit[idsplit.index("AWSLogs") :]
            keysplit = "/".join(idsplit).split("_")
        except ValueError:
            logger.debug("Invalid S3 key, doesn't contain AWSLogs")
            return
    # If no prefix, split the key
    else:
        keysplit = key.split("_")
    if len(keysplit) > 3:
        region = keysplit[2].lower()
        name = keysplit[3]
        elbname = name.replace(".", "/")
        if len(idsplit) > 1:
            idvalue = idsplit[1]
            partition = get_partition_from_region(region)
            return "arn:{}:elasticloadbalancing:{}:{}:loadbalancer/{}".format(
                partition, region, idvalue, elbname
            )


def handle_cloudfront_source(context, key):
    # For Cloudfront logs we need to get the account and distribution id from the lambda arn and the filename
    # 1. We extract the cloudfront id  from the filename
    # 2. We extract the AWS account id from the lambda arn
    namesplit = key.split("/")
    if len(namesplit) > 0:
        filename = namesplit[len(namesplit) - 1]
        # (distribution-ID.YYYY-MM-DD-HH.unique-ID.gz)
        filenamesplit = filename.split(".")
        if len(filenamesplit) > 3:
            distributionID = filenamesplit[len(filenamesplit) - 4].lower()
            arn = context.invoked_function_arn
            arnsplit = arn.split(":")
            if len(arnsplit) == 7:
                awsaccountID = arnsplit[4].lower()
                return "arn:aws:cloudfront::{}:distribution/{}".format(
                    awsaccountID, distributionID
                )


def handle_redshift_source(key):
    # For redshift logs we leverage the filename to extract the relevant information
    # 1. We extract the region from the filename
    # 2. We extract the account-id from the filename
    # 3. We extract the name of the cluster
    # 4. We build the arn: arn:aws:redshift:region:account-id:cluster:cluster-name
    namesplit = key.split("/")
    if len(namesplit) == 8:
        region = namesplit[3].lower()
        accountID = namesplit[1].lower()
        filename = namesplit[7]
        filesplit = filename.split("_")
        if len(filesplit) == 6:
            clustername = filesplit[3]
            return "arn:{}:redshift:{}:{}:cluster:{}:".format(
                get_partition_from_region(region),
                region,
                accountID,
                clustername,
            )


def get_partition_from_region(region):
    partition = "aws"
    if region:
        if GOV_STRING in region:
            partition = "aws-us-gov"
        elif CN_STRING in region:
            partition = "aws-cn"
    return partition


def get_s3_arn(bucket):
    return "arn:aws:s3:::{}".format(bucket)
