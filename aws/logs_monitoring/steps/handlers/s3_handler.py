import gzip
import json
import logging
import os
import re
import urllib.parse
from io import BufferedReader, BytesIO

import boto3
import botocore

from settings import (
    CN_STRING,
    DD_CUSTOM_TAGS,
    DD_HOST,
    DD_MULTILINE_LOG_REGEX_PATTERN,
    DD_SOURCE,
    DD_USE_VPC,
    GOV_STRING,
)
from steps.common import (
    add_service_tag,
    is_cloudtrail,
    is_vpc_flowlog,
    merge_dicts,
    parse_event_source,
)


class S3EventDataStore:
    def __init__(self):
        self.bucket = None
        self.key = None
        self.source = None
        self.data = None
        self.cloudtrail_bucket = False


class S3EventHandler:
    def __init__(self, context, metadata, cache_layer):
        self.logger = logging.getLogger()
        self.logger.setLevel(
            logging.getLevelName(os.environ.get("DD_LOG_LEVEL", "INFO").upper())
        )
        self.context = context
        self.metadata = metadata
        self.cache_layer = cache_layer
        self.multiline_regex_start_pattern = (
            re.compile("^{}".format(DD_MULTILINE_LOG_REGEX_PATTERN))
            if DD_MULTILINE_LOG_REGEX_PATTERN
            else None
        )
        self.multiline_regex_pattern = (
            re.compile("[\n\r\f]+(?={})".format(DD_MULTILINE_LOG_REGEX_PATTERN))
            if DD_MULTILINE_LOG_REGEX_PATTERN
            else None
        )
        # a private data store for event attributes
        self.data_store = S3EventDataStore()

    def handle(self, event):
        event = self._extract_event(event)

        if self.metadata.get(DD_SOURCE) is None:
            self._set_source(event)

        self._add_s3_tags_from_cache()

        add_service_tag(self.metadata)

        self._extract_data()

        yield from self._get_structured_lines_for_s3_handler()

    def _extract_event(self, event):
        # if this is a S3 event carried in a SNS message, extract it and override the event
        if "Sns" in event.get("Records")[0]:
            event = json.loads(event.get("Records")[0].get("Sns").get("Message"))
        # Get the object from the event and show its content type
        bucket = event.get("Records")[0].get("s3").get("bucket").get("name")
        key = urllib.parse.unquote_plus(
            event.get("Records")[0].get("s3").get("object").get("key")
        )

        self.data_store.bucket = bucket
        self.data_store.key = key

        return event

    def _set_source(self, event):
        self.data_store.source = parse_event_source(event, self.data_store.key)
        self.metadata[DD_SOURCE] = self.data_store.source

    def _get_s3_arn(self):
        if not self.data_store.bucket:
            return None
        return "arn:aws:s3:::{}".format(self.data_store.bucket)

    def _get_partition_from_region(self, region):
        partition = "aws"
        if region:
            if GOV_STRING in region:
                partition = "aws-us-gov"
            elif CN_STRING in region:
                partition = "aws-cn"
        return partition

    def _add_s3_tags_from_cache(self):
        bucket_arn = self._get_s3_arn()

        if self.metadata.get(DD_HOST, "") == bucket_arn:
            return

        s3_tags = self.cache_layer.get_s3_tags_cache().get(bucket_arn)
        if len(s3_tags) > 0:
            self.metadata[DD_CUSTOM_TAGS] = (
                ",".join(s3_tags)
                if not self.metadata[DD_CUSTOM_TAGS]
                else ",".join(s3_tags) + "," + self.metadata[DD_CUSTOM_TAGS]
            )

    def _extract_data(self):
        s3_client = self._get_s3_client()
        response = s3_client.get_object(
            Bucket=self.data_store.bucket, Key=self.data_store.key
        )
        body = response.get("Body")
        self.data_store.data = body.read()

    def _get_s3_client(self):
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

    def _get_structured_lines_for_s3_handler(self):
        self._decompress_data()

        if is_cloudtrail(self.data_store.key):
            yield from self._extract_cloudtrail_logs()

        if not self.data_store.cloudtrail_bucket:
            yield from self._extract_other_logs()

    def _decompress_data(self):
        # Decompress data that has a .gz extension or magic header http://www.onicos.com/staff/iz/formats/gzip.html
        if self.data_store.key[-3:] == ".gz" or self.data_store.data[:2] == b"\x1f\x8b":
            with gzip.GzipFile(
                fileobj=BytesIO(self.data_store.data)
            ) as decompress_stream:
                # Reading line by line avoid a bug where gzip would take a very long time (>5min) for
                # file around 60MB gzipped
                self.data_store.data = b"".join(BufferedReader(decompress_stream))

    def _extract_cloudtrail_logs(self):
        try:
            cloudtrail_data = json.loads(self.data_store.data)
            if cloudtrail_data.get("Records", None) is None:
                return

            self.data_store.cloudtrail_bucket = True
            # only parse as a cloudtrail bucket if we have a Records field to parse
            for event in cloudtrail_data.get("Records"):
                # Create structured object and send it
                structured_line = merge_dicts(
                    event,
                    {
                        "aws": {
                            "s3": {
                                "bucket": self.data_store.bucket,
                                "key": self.data_store.key,
                            }
                        }
                    },
                )
                yield structured_line
        except Exception as e:
            self.logger.debug("Unable to parse cloudtrail log: %s" % e)

    def _extract_other_logs(self):
        # VPC flow logs have a header line that should be skipped
        skip_first_line = is_vpc_flowlog(self.data_store.key)

        # Check if using multiline log regex pattern
        # and determine whether line or pattern separated logs
        if self.multiline_regex_start_pattern and self.multiline_regex_pattern:
            # We'll do string manipulation, so decode bytes into utf-8 first
            self.data_store.data = self.data_store.data.decode("utf-8", errors="ignore")

            if self.multiline_regex_start_pattern.match(self.data_store.data):
                self.data_store.data = list(
                    filter(
                        None, self.multiline_regex_pattern.split(self.data_store.data)
                    )
                )
            else:
                self.logger.debug(
                    "DD_MULTILINE_LOG_REGEX_PATTERN %s did not match start of file, splitting by line",
                    DD_MULTILINE_LOG_REGEX_PATTERN,
                )
                self.data_store.data = self.data_store.data.splitlines()

            for i, line in enumerate(self.data_store.data):
                if skip_first_line and i == 0:
                    continue
                yield self._format_event(line)

        else:
            # Using bytes instead of utf-8 string give us universal splitlines (\r\n)
            # rather than extended set of line separators of the string
            #
            # https://docs.python.org/3/library/stdtypes.html#str.splitlines
            # https://docs.python.org/3/library/stdtypes.html#bytes.splitlines
            for i, line in enumerate(self.data_store.data.splitlines()):
                if skip_first_line and i == 0:
                    continue

                line = line.decode("utf-8", errors="ignore").strip()
                if len(line) == 0:
                    continue

                yield self._format_event(line)

    def _format_event(self, line):
        return {
            "aws": {
                "s3": {
                    "bucket": self.data_store.bucket,
                    "key": self.data_store.key,
                }
            },
            "message": line,
        }
