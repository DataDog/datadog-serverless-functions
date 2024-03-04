import re

from settings import DD_CUSTOM_TAGS, DD_SERVICE, DD_SOURCE

CLOUDTRAIL_REGEX = re.compile(
    "\d+_CloudTrail(|-Digest)_\w{2}(|-gov|-cn)-\w{4,9}-\d_(|.+)\d{8}T\d{4,6}Z(|.+).json.gz$",
    re.I,
)


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
            # WebSocket API Execution Logs, e.g. /aws/apigateway/api-id/stage-name
            "/aws/apigateway/",
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
        "transitgateway",
        "verified-access",
        "bedrock",
    ]:
        if source in log_group:
            return source

    return "cloudwatch"


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

    # e.g. 2020/10/02/21/aws-waf-logs-testing-1-2020-10-02-21-25-30-x123x-x456x or AWSLogs/123456779121/WAFLogs/us-east-1/xxxxxx-waf/2022/10/11/14/10/123456779121_waflogs_us-east-1_xxxxx-waf_20221011T1410Z_12756524.log.gz
    if "aws-waf-logs" in key or "waflogs" in key:
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
        "verified-access",
        "bedrock",
    ]:
        if source in key:
            return source.replace("amazon_", "")

    return "s3"


def get_service_from_tags_and_remove_duplicates(metadata):
    service = ""
    tagsplit = metadata[DD_CUSTOM_TAGS].split(",")
    for i, tag in enumerate(tagsplit):
        if tag.startswith("service:"):
            if service:
                # remove duplicate entry from the tags
                del tagsplit[i]
            else:
                service = tag[8:]
    metadata[DD_CUSTOM_TAGS] = ",".join(tagsplit)

    # Default service to source value
    return service if service else metadata[DD_SOURCE]


def add_service_tag(metadata):
    metadata[DD_SERVICE] = get_service_from_tags_and_remove_duplicates(metadata)


def is_cloudtrail(key):
    match = CLOUDTRAIL_REGEX.search(key)
    return bool(match)


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
