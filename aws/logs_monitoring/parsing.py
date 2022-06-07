# Unless explicitly stated otherwise all files in this repository are licensed
# under the Apache License Version 2.0.
# This product includes software developed at Datadog (https://www.datadoghq.com/).
# Copyright 2021 Datadog, Inc.

import base64
import gzip
import json
import os
import copy

import boto3
import botocore
import itertools
import re
import urllib
import logging
from io import BytesIO, BufferedReader

from datadog_lambda.metric import lambda_stats

from cache import CloudwatchLogGroupTagsCache
from telemetry import (
    DD_FORWARDER_TELEMETRY_NAMESPACE_PREFIX,
    get_forwarder_telemetry_tags,
    set_forwarder_telemetry_tags,
)
from settings import (
    DD_TAGS,
    DD_MULTILINE_LOG_REGEX_PATTERN,
    DD_SOURCE,
    DD_CUSTOM_TAGS,
    DD_SERVICE,
    DD_HOST,
    DD_FORWARDER_VERSION,
    DD_USE_VPC,
)


logger = logging.getLogger()

if DD_MULTILINE_LOG_REGEX_PATTERN:
    try:
        multiline_regex = re.compile(
            "[\n\r\f]+(?={})".format(DD_MULTILINE_LOG_REGEX_PATTERN)
        )
    except Exception:
        raise Exception(
            "could not compile multiline regex with pattern: {}".format(
                DD_MULTILINE_LOG_REGEX_PATTERN
            )
        )
    multiline_regex_start_pattern = re.compile(
        "^{}".format(DD_MULTILINE_LOG_REGEX_PATTERN)
    )

rds_regex = re.compile("/aws/rds/(instance|cluster)/(?P<host>[^/]+)/(?P<name>[^/]+)")

cloudtrail_regex = re.compile(
    "\d+_CloudTrail_\w{2}-\w{4,9}-\d_\d{8}T\d{4}Z.+.json.gz$", re.I
)

# Store the cache in the global scope so that it will be reused as long as
# the log forwarder Lambda container is running
account_cw_logs_tags_cache = CloudwatchLogGroupTagsCache()


def parse(event, context):
    """Parse Lambda input to normalized events"""
    metadata = generate_metadata(context)
    event_type = "unknown"
    try:
        # Route to the corresponding parser
        event_type = parse_event_type(event)
        if logger.isEnabledFor(logging.DEBUG):
            logger.debug(f"Parsed event type: {event_type}")
        if event_type == "s3":
            events = s3_handler(event, context, metadata)
        elif event_type == "awslogs":
            events = awslogs_handler(event, context, metadata)
        elif event_type == "events":
            events = cwevent_handler(event, metadata)
        elif event_type == "sns":
            events = sns_handler(event, metadata)
        elif event_type == "kinesis":
            events = kinesis_awslogs_handler(event, context, metadata)
    except Exception as e:
        # Logs through the socket the error
        err_message = "Error parsing the object. Exception: {} for event {}".format(
            str(e), event
        )
        events = [err_message]

    set_forwarder_telemetry_tags(context, event_type)

    return normalize_events(events, metadata)


def generate_metadata(context):
    metadata = {
        "ddsourcecategory": "aws",
        "aws": {
            "function_version": context.function_version,
            "invoked_function_arn": context.invoked_function_arn,
        },
    }
    # Add custom tags here by adding new value with the following format "key1:value1, key2:value2"  - might be subject to modifications
    dd_custom_tags_data = {
        "forwardername": context.function_name.lower(),
        "forwarder_memorysize": context.memory_limit_in_mb,
        "forwarder_version": DD_FORWARDER_VERSION,
    }

    metadata[DD_CUSTOM_TAGS] = ",".join(
        filter(
            None,
            [
                DD_TAGS,
                ",".join(
                    ["{}:{}".format(k, v) for k, v in dd_custom_tags_data.items()]
                ),
            ],
        )
    )

    return metadata


def parse_event_type(event):
    if "Records" in event and len(event["Records"]) > 0:
        if "s3" in event["Records"][0]:
            return "s3"
        elif "Sns" in event["Records"][0]:
            # it's not uncommon to fan out s3 notifications through SNS,
            # should treat it as an s3 event rather than sns event.
            sns_msg = event["Records"][0]["Sns"]["Message"]
            try:
                sns_msg_dict = json.loads(sns_msg)
                if "Records" in sns_msg_dict and "s3" in sns_msg_dict["Records"][0]:
                    return "s3"
            except Exception:
                if logger.isEnabledFor(logging.DEBUG):
                    logger.debug(f"No s3 event detected from SNS message: {sns_msg}")
            return "sns"
        elif "kinesis" in event["Records"][0]:
            return "kinesis"

    elif "awslogs" in event:
        return "awslogs"

    elif "detail" in event:
        return "events"
    raise Exception("Event type not supported (see #Event supported section)")


# Handle S3 events
def s3_handler(event, context, metadata):
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
    # if this is a S3 event carried in a SNS message, extract it and override the event
    if "Sns" in event["Records"][0]:
        event = json.loads(event["Records"][0]["Sns"]["Message"])

    # Get the object from the event and show its content type
    bucket = event["Records"][0]["s3"]["bucket"]["name"]
    key = urllib.parse.unquote_plus(event["Records"][0]["s3"]["object"]["key"])

    source = parse_event_source(event, key)
    metadata[DD_SOURCE] = source

    metadata[DD_SERVICE] = get_service_from_tags(metadata)

    ##Get the ARN of the service and set it as the hostname
    hostname = parse_service_arn(source, key, bucket, context)
    if hostname:
        metadata[DD_HOST] = hostname

    # Extract the S3 object
    response = s3.get_object(Bucket=bucket, Key=key)
    body = response["Body"]
    data = body.read()

    # Decompress data that has a .gz extension or magic header http://www.onicos.com/staff/iz/formats/gzip.html
    if key[-3:] == ".gz" or data[:2] == b"\x1f\x8b":
        with gzip.GzipFile(fileobj=BytesIO(data)) as decompress_stream:
            # Reading line by line avoid a bug where gzip would take a very long time (>5min) for
            # file around 60MB gzipped
            data = b"".join(BufferedReader(decompress_stream))

    if is_cloudtrail(str(key)):
        cloud_trail = json.loads(data)
        for event in cloud_trail["Records"]:
            # Create structured object and send it
            structured_line = merge_dicts(
                event, {"aws": {"s3": {"bucket": bucket, "key": key}}}
            )
            yield structured_line
    else:
        # Check if using multiline log regex pattern
        # and determine whether line or pattern separated logs
        data = data.decode("utf-8", errors="ignore")
        if DD_MULTILINE_LOG_REGEX_PATTERN and multiline_regex_start_pattern.match(data):
            split_data = multiline_regex.split(data)
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


def get_service_from_tags(metadata):
    # Get service from dd_custom_tags if it exists
    tagsplit = metadata[DD_CUSTOM_TAGS].split(",")
    for tag in tagsplit:
        if tag.startswith("service:"):
            return tag[8:]

    # Default service to source value
    return metadata[DD_SOURCE]


def parse_event_source(event, key):
    """Parse out the source that will be assigned to the log in Datadog
    Args:
        event (dict): The AWS-formatted log event that the forwarder was triggered with
        key (string): The S3 object key if the event is from S3 or the CW Log Group if the event is from CW Logs
    """
    lowercase_key = str(key).lower()

    # Determines if the key matches any known sources for Cloudwatch logs
    if "awslogs" in event:
        return find_cloudwatch_source(lowercase_key)

    # Determines if the key matches any known sources for S3 logs
    if "Records" in event and len(event["Records"]) > 0:
        if "s3" in event["Records"][0]:
            if is_cloudtrail(str(key)):
                return "cloudtrail"

            return find_s3_source(lowercase_key)

    return "aws"


def find_cloudwatch_source(log_group):
    # e.g. /aws/rds/instance/my-mariadb/error
    if log_group.startswith("/aws/rds"):
        for engine in ["mariadb", "mysql", "postgresql"]:
            if engine in log_group:
                return engine
        return "rds"

    if log_group.startswith(
        (
            # default location for rest api execution logs
            "api-gateway",  # e.g. Api-Gateway-Execution-Logs_xxxxxx/dev
            # default location set by serverless framework for rest api access logs
            "/aws/api-gateway",  # e.g. /aws/api-gateway/my-project
            # default location set by serverless framework for http api logs
            "/aws/http-api",  # e.g. /aws/http-api/my-project
        )
    ):
        return "apigateway"

    if log_group.startswith("/aws/vendedlogs/states"):
        return "stepfunction"

    # e.g. dms-tasks-test-instance
    if log_group.startswith("dms-tasks"):
        return "dms"

    # e.g. sns/us-east-1/123456779121/SnsTopicX
    if log_group.startswith("sns/"):
        return "sns"

    # e.g. /aws/fsx/windows/xxx
    if log_group.startswith("/aws/fsx/windows"):
        return "aws.fsx"

    if log_group.startswith("/aws/appsync/"):
        return "appsync"

    for source in [
        "/aws/lambda",  # e.g. /aws/lambda/helloDatadog
        "/aws/codebuild",  # e.g. /aws/codebuild/my-project
        "/aws/kinesis",  # e.g. /aws/kinesisfirehose/dev
        "/aws/docdb",  # e.g. /aws/docdb/yourClusterName/profile
        "/aws/eks",  # e.g. /aws/eks/yourClusterName/profile
    ]:
        if log_group.startswith(source):
            return source.replace("/aws/", "")

    # the below substrings must be in your log group to be detected
    for source in [
        "network-firewall",
        "route53",
        "vpc",
        "fargate",
        "cloudtrail",
        "msk",
        "elasticsearch",
    ]:
        if source in log_group:
            return source

    return "cloudwatch"


def is_cloudtrail(key):
    match = cloudtrail_regex.search(key)
    return bool(match)


def find_s3_source(key):
    # e.g. AWSLogs/123456779121/elasticloadbalancing/us-east-1/2020/10/02/123456779121_elasticloadbalancing_us-east-1_app.alb.xxxxx.xx.xxx.xxx_x.log.gz
    if "elasticloadbalancing" in key:
        return "elb"

    # e.g. AWSLogs/123456779121/vpcflowlogs/us-east-1/2020/10/02/123456779121_vpcflowlogs_us-east-1_fl-xxxxx.log.gz
    if "vpcflowlogs" in key:
        return "vpc"

    # e.g. AWSLogs/123456779121/vpcdnsquerylogs/vpc-********/2021/05/11/vpc-********_vpcdnsquerylogs_********_20210511T0910Z_71584702.log.gz
    if "vpcdnsquerylogs" in key:
        return "route53"

    # e.g. 2020/10/02/21/aws-waf-logs-testing-1-2020-10-02-21-25-30-x123x-x456x
    if "aws-waf-logs" in key:
        return "waf"

    # e.g. AWSLogs/123456779121/redshift/us-east-1/2020/10/21/123456779121_redshift_us-east-1_mycluster_userlog_2020-10-21T18:01.gz
    if "_redshift_" in key:
        return "redshift"

    # this substring must be in your target prefix to be detected
    if "amazon_documentdb" in key:
        return "docdb"

    # e.g. carbon-black-cloud-forwarder/alerts/org_key=*****/year=2021/month=7/day=19/hour=18/minute=15/second=41/8436e850-7e78-40e4-b3cd-6ebbc854d0a2.jsonl.gz
    if "carbon-black" in key:
        return "carbonblack"

    # the below substrings must be in your target prefix to be detected
    for source in [
        "amazon_codebuild",
        "amazon_kinesis",
        "amazon_dms",
        "amazon_msk",
        "network-firewall",
        "cloudfront",
    ]:
        if source in key:
            return source.replace("amazon_", "")

    return "s3"


def parse_service_arn(source, key, bucket, context):
    if source == "elb":
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
                return "arn:aws:elasticloadbalancing:{}:{}:loadbalancer/{}".format(
                    region, idvalue, elbname
                )
    if source == "s3":
        # For S3 access logs we use the bucket name to rebuild the arn
        if bucket:
            return "arn:aws:s3:::{}".format(bucket)
    if source == "cloudfront":
        # For Cloudfront logs we need to get the account and distribution id from the lambda arn and the filename
        # 1. We extract the cloudfront id  from the filename
        # 2. We extract the AWS account id from the lambda arn
        # 3. We build the arn
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
    if source == "redshift":
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
                return "arn:aws:redshift:{}:{}:cluster:{}:".format(
                    region, accountID, clustername
                )
    return


# Handle CloudWatch logs
def awslogs_handler(event, context, metadata):
    # Get logs
    with gzip.GzipFile(
        fileobj=BytesIO(base64.b64decode(event["awslogs"]["data"]))
    ) as decompress_stream:
        # Reading line by line avoid a bug where gzip would take a very long
        # time (>5min) for file around 60MB gzipped
        data = b"".join(BufferedReader(decompress_stream))
    logs = json.loads(data)

    # Set the source on the logs
    source = logs.get("logGroup", "cloudwatch")

    # Use the logStream to identify if this is a CloudTrail event
    # i.e. 123456779121_CloudTrail_us-east-1
    if "_CloudTrail_" in logs["logStream"]:
        source = "cloudtrail"
    metadata[DD_SOURCE] = parse_event_source(event, source)

    metadata[DD_SERVICE] = get_service_from_tags(metadata)

    # Build aws attributes
    aws_attributes = {
        "aws": {
            "awslogs": {
                "logGroup": logs["logGroup"],
                "logStream": logs["logStream"],
                "owner": logs["owner"],
            }
        }
    }

    formatted_tags = account_cw_logs_tags_cache.get(logs["logGroup"])
    if len(formatted_tags) > 0:
        metadata[DD_CUSTOM_TAGS] = (
            ",".join(formatted_tags)
            if not metadata[DD_CUSTOM_TAGS]
            else metadata[DD_CUSTOM_TAGS] + "," + ",".join(formatted_tags)
        )

    # Set host as log group where cloudwatch is source
    if metadata[DD_SOURCE] == "cloudwatch" or metadata.get(DD_HOST, None) == None:
        metadata[DD_HOST] = aws_attributes["aws"]["awslogs"]["logGroup"]

    if metadata[DD_SOURCE] == "appsync":
        metadata[DD_HOST] = aws_attributes["aws"]["awslogs"]["logGroup"].split("/")[-1]

    if metadata[DD_SOURCE] == "stepfunction" and logs["logStream"].startswith(
        "states/"
    ):
        try:
            message = json.loads(logs["logEvents"][0]["message"])
            if message.get("execution_arn") is not None:
                execution_arn = message["execution_arn"]
                arn_tokens = execution_arn.split(":")
                arn_tokens[5] = "stateMachine"
                metadata[DD_HOST] = ":".join(arn_tokens[:-1])
        except Exception as e:
            logger.debug("Unable to set stepfunction host: %s" % e)

    # When parsing rds logs, use the cloudwatch log group name to derive the
    # rds instance name, and add the log name of the stream ingested
    if metadata[DD_SOURCE] in ["rds", "mariadb", "mysql", "postgresql"]:
        match = rds_regex.match(logs["logGroup"])
        if match is not None:
            metadata[DD_HOST] = match.group("host")
            metadata[DD_CUSTOM_TAGS] = (
                metadata[DD_CUSTOM_TAGS] + ",logname:" + match.group("name")
            )

    # For Lambda logs we want to extract the function name,
    # then rebuild the arn of the monitored lambda using that name.
    # Start by splitting the log group to get the function name
    if metadata[DD_SOURCE] == "lambda":
        log_group_parts = logs["logGroup"].split("/lambda/")
        if len(log_group_parts) > 1:
            lowercase_function_name = log_group_parts[1].lower()
            # Split the arn of the forwarder to extract the prefix
            arn_parts = context.invoked_function_arn.split("function:")
            if len(arn_parts) > 0:
                arn_prefix = arn_parts[0]
                # Rebuild the arn with the lowercased function name
                lowercase_arn = arn_prefix + "function:" + lowercase_function_name
                # Add the lowercased arn as a log attribute
                arn_attributes = {"lambda": {"arn": lowercase_arn}}
                aws_attributes = merge_dicts(aws_attributes, arn_attributes)

                env_tag_exists = (
                    metadata[DD_CUSTOM_TAGS].startswith("env:")
                    or ",env:" in metadata[DD_CUSTOM_TAGS]
                )
                # If there is no env specified, default to env:none
                if not env_tag_exists:
                    metadata[DD_CUSTOM_TAGS] += ",env:none"

    # The EKS log group contains various sources from the K8S control plane.
    # In order to have these automatically trigger the correct pipelines they
    # need to send their events with the correct log source.
    if metadata[DD_SOURCE] == "eks":
        if logs["logStream"].startswith("kube-apiserver-audit-"):
            metadata[DD_SOURCE] = "kubernetes.audit"
        elif logs["logStream"].startswith("kube-scheduler-"):
            metadata[DD_SOURCE] = "kube_scheduler"
        # In case the conditions above don't match we maintain eks as the source

    # Create and send structured logs to Datadog
    for log in logs["logEvents"]:
        yield merge_dicts(log, aws_attributes)


def merge_dicts(a, b, path=None):
    if path is None:
        path = []
    for key in b:
        if key in a:
            if isinstance(a[key], dict) and isinstance(b[key], dict):
                merge_dicts(a[key], b[key], path + [str(key)])
            elif a[key] == b[key]:
                pass  # same leaf value
            else:
                raise Exception(
                    "Conflict while merging metadatas and the log entry at %s"
                    % ".".join(path + [str(key)])
                )
        else:
            a[key] = b[key]
    return a


# Handle Cloudwatch Events
def cwevent_handler(event, metadata):
    data = event

    # Set the source on the log
    source = data.get("source", "cloudwatch")
    service = source.split(".")
    if len(service) > 1:
        metadata[DD_SOURCE] = service[1]
    else:
        metadata[DD_SOURCE] = "cloudwatch"

    metadata[DD_SERVICE] = get_service_from_tags(metadata)

    yield data


def parse_aws_waf_logs(event):
    """Parse out complex arrays of objects in AWS WAF logs

    Attributes to convert:
        httpRequest.headers
        nonTerminatingMatchingRules
        rateBasedRuleList
        ruleGroupList

    This prevents having an unparsable array of objects in the final log.
    """
    if isinstance(event, str):
        try:
            event = json.loads(event)
        except json.JSONDecodeError:
            logger.debug("Argument provided for waf parser is not valid JSON")
            return event
    if event.get(DD_SOURCE) != "waf":
        return event

    event_copy = copy.deepcopy(event)

    message = event_copy.get("message", {})
    if isinstance(message, str):
        try:
            message = json.loads(message)
        except json.JSONDecodeError:
            logger.debug("Failed to decode waf message")
            return event

    headers = message.get("httpRequest", {}).get("headers")
    if headers:
        message["httpRequest"]["headers"] = convert_rule_to_nested_json(headers)

    # Iterate through rules in ruleGroupList and nest them under the group id
    # ruleGroupList has three attributes that need to be handled separately
    rule_groups = message.get("ruleGroupList", {})
    if rule_groups and isinstance(rule_groups, list):
        message["ruleGroupList"] = {}
        for rule_group in rule_groups:
            group_id = None
            if "ruleGroupId" in rule_group and rule_group["ruleGroupId"]:
                group_id = rule_group.pop("ruleGroupId", None)
            if group_id not in message["ruleGroupList"]:
                message["ruleGroupList"][group_id] = {}

            # Extract the terminating rule and nest it under its own id
            if "terminatingRule" in rule_group and rule_group["terminatingRule"]:
                terminating_rule = rule_group.pop("terminatingRule", None)
                if not "terminatingRule" in message["ruleGroupList"][group_id]:
                    message["ruleGroupList"][group_id]["terminatingRule"] = {}
                message["ruleGroupList"][group_id]["terminatingRule"].update(
                    convert_rule_to_nested_json(terminating_rule)
                )

            # Iterate through array of non-terminating rules and nest each under its own id
            if "nonTerminatingMatchingRules" in rule_group and isinstance(
                rule_group["nonTerminatingMatchingRules"], list
            ):
                non_terminating_rules = rule_group.pop(
                    "nonTerminatingMatchingRules", None
                )
                if (
                    "nonTerminatingMatchingRules"
                    not in message["ruleGroupList"][group_id]
                ):
                    message["ruleGroupList"][group_id][
                        "nonTerminatingMatchingRules"
                    ] = {}
                message["ruleGroupList"][group_id][
                    "nonTerminatingMatchingRules"
                ].update(convert_rule_to_nested_json(non_terminating_rules))

            # Iterate through array of excluded rules and nest each under its own id
            if "excludedRules" in rule_group and isinstance(
                rule_group["excludedRules"], list
            ):
                excluded_rules = rule_group.pop("excludedRules", None)
                if "excludedRules" not in message["ruleGroupList"][group_id]:
                    message["ruleGroupList"][group_id]["excludedRules"] = {}
                message["ruleGroupList"][group_id]["excludedRules"].update(
                    convert_rule_to_nested_json(excluded_rules)
                )

    rate_based_rules = message.get("rateBasedRuleList", {})
    if rate_based_rules:
        message["rateBasedRuleList"] = convert_rule_to_nested_json(rate_based_rules)

    non_terminating_rules = message.get("nonTerminatingMatchingRules", {})
    if non_terminating_rules:
        message["nonTerminatingMatchingRules"] = convert_rule_to_nested_json(
            non_terminating_rules
        )

    event_copy["message"] = message
    return event_copy


def convert_rule_to_nested_json(rule):
    key = None
    result_obj = {}
    if not isinstance(rule, list):
        if "ruleId" in rule and rule["ruleId"]:
            key = rule.pop("ruleId", None)
            result_obj.update({key: rule})
            return result_obj
    for entry in rule:
        if "ruleId" in entry and entry["ruleId"]:
            key = entry.pop("ruleId", None)
        elif "rateBasedRuleName" in entry and entry["rateBasedRuleName"]:
            key = entry.pop("rateBasedRuleName", None)
        elif "name" in entry and "value" in entry:
            key = entry["name"]
            entry = entry["value"]
        result_obj.update({key: entry})
    return result_obj


def separate_security_hub_findings(event):
    """Replace Security Hub event with series of events based on findings

    Each event should contain one finding only.
    This prevents having an unparsable array of objects in the final log.
    """
    if event.get(DD_SOURCE) != "securityhub" or not event.get("detail", {}).get(
        "findings"
    ):
        return None
    events = []
    event_copy = copy.deepcopy(event)
    # Copy findings before separating
    findings = event_copy.get("detail", {}).get("findings")
    if findings:
        # Remove findings from the original event once we have a copy
        del event_copy["detail"]["findings"]
        # For each finding create a separate log event
        for index, item in enumerate(findings):
            # Copy the original event with source and other metadata
            new_event = copy.deepcopy(event_copy)
            current_finding = findings[index]
            # Get the resources array from the current finding
            resources = current_finding.get("Resources", {})
            new_event["detail"]["finding"] = current_finding
            new_event["detail"]["finding"]["resources"] = {}
            # Separate objects in resources array into distinct attributes
            if resources:
                # Remove from current finding once we have a copy
                del current_finding["Resources"]
                for item in resources:
                    current_resource = item
                    # Capture the type and use it as the distinguishing key
                    resource_type = current_resource.get("Type", {})
                    del current_resource["Type"]
                    new_event["detail"]["finding"]["resources"][
                        resource_type
                    ] = current_resource
            events.append(new_event)
    return events


# Handle Sns events
def sns_handler(event, metadata):
    data = event
    # Set the source on the log
    metadata[DD_SOURCE] = "sns"

    for ev in data["Records"]:
        # Create structured object and send it
        structured_line = ev
        yield structured_line


# Handle CloudWatch logs from Kinesis
def kinesis_awslogs_handler(event, context, metadata):
    def reformat_record(record):
        return {"awslogs": {"data": record["kinesis"]["data"]}}

    return itertools.chain.from_iterable(
        awslogs_handler(reformat_record(r), context, metadata) for r in event["Records"]
    )


def normalize_events(events, metadata):
    normalized = []
    events_counter = 0

    for event in events:
        events_counter += 1
        if isinstance(event, dict):
            normalized.append(merge_dicts(event, metadata))
        elif isinstance(event, str):
            normalized.append(merge_dicts({"message": event}, metadata))
        else:
            # drop this log
            continue

    """Submit count of total events"""
    lambda_stats.distribution(
        "{}.incoming_events".format(DD_FORWARDER_TELEMETRY_NAMESPACE_PREFIX),
        events_counter,
        tags=get_forwarder_telemetry_tags(),
    )

    return normalized
