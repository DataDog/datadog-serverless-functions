from enum import Enum


class AwsEventSource(Enum):
    AWS = "aws"
    CLOUDTRAIL = "cloudtrail"
    CLOUDWATCH = "cloudwatch"
    ELASTICSEARCH = "elasticsearch"
    FARGATE = "fargate"
    GUARDDUTY = "guardduty"
    KINESIS = "kinesis"
    LAMBDA = "lambda"
    MARIADB = "mariadb"
    MSK = "msk"
    MYSQL = "mysql"
    POSTGRESQL = "postgresql"
    S3 = "s3"
    SNS = "sns"
    STEPFUNCTION = "stepfunction"
    WAF = "waf"

    def __str__(self):
        return f"{self.value}"

    @staticmethod
    def cloudwatch_sources():
        return [
            AwsEventSource.CLOUDTRAIL,
            AwsEventSource.ELASTICSEARCH,
            AwsEventSource.FARGATE,
            AwsEventSource.MSK,
        ]


class AwsS3EventSourceKeyword(Enum):
    def __init__(self, string, event_source):
        self.string = string
        self.event_source = event_source

    # e.g. 2020/10/02/21/aws-waf-logs-testing-1-2020-10-02-21-25-30-x123x-x456x or AWSLogs/123456779121/WAFLogs/us-east-1/xxxxxx-waf/2022/10/11/14/10/123456779121_waflogs_us-east-1_xxxxx-waf_20221011T1410Z_12756524.log.gz
    WAF_0 = ("aws-waf-logs", AwsEventSource.WAF)
    WAF_1 = ("waflogs", AwsEventSource.WAF)

    GUARDDUTY = ("guardduty", AwsEventSource.GUARDDUTY)
    KINESIS = ("amazon_kinesis", AwsEventSource.KINESIS)
    MSK = ("amazon_msk", AwsEventSource.MSK)

    def __str__(self):
        return f"{self.string}"


class AwsCwEventSourcePrefix(Enum):
    def __init__(self, string, event_source):
        self.string = string
        self.event_source = event_source

    # e.g. /aws/codebuild/my-project
    CLOUDTRAIL = ("_CloudTrail_", AwsEventSource.CLOUDTRAIL)
    # e.g. /aws/kinesisfirehose/dev
    KINESIS = ("/aws/kinesis", AwsEventSource.KINESIS)
    # e.g. /aws/lambda/helloDatadog
    LAMBDA = ("/aws/lambda", AwsEventSource.LAMBDA)
    # e.g. sns/us-east-1/123456779121/SnsTopicX
    SNS = ("sns/", AwsEventSource.SNS)

    def __str__(self):
        return f"{self.string}"


class AwsEventType(Enum):
    AWSLOGS = "awslogs"
    EVENTS = "events"
    KINESIS = "kinesis"
    S3 = "s3"
    SNS = "sns"
    UNKNOWN = "unknown"

    def __str__(self):
        return f"{self.value}"


class AwsEventTypeKeyword(Enum):
    MESSAGE = "Message"
    RECORDS = "Records"
    SNS = "Sns"

    def __str__(self):
        return f"{self.value}"
