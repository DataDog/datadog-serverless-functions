from enum import Enum


class AwsEventSource(Enum):
    AWS = "aws"
    CARBONBLACK = "carbonblack"
    CLOUDFRONT = "cloudfront"
    CLOUDTRAIL = "cloudtrail"
    CLOUDWATCH = "cloudwatch"
    ELASTICSEARCH = "elasticsearch"
    ELB = "elb"
    FARGATE = "fargate"
    GUARDDUTY = "guardduty"
    IAMAUTHENTICATOR = "aws-iam-authenticator"
    KINESIS = "kinesis"
    KUBEAPISERVER = "kube-apiserver"
    KUBECONTROLLERMANAGER = "kube-controller-manager"
    KUBERNETESAUDIT = "kubernetes.audit"
    KUBESCHEDULER = "kube_scheduler"
    LAMBDA = "lambda"
    MARIADB = "mariadb"
    MSK = "msk"
    MYSQL = "mysql"
    NETWORKFIREWALL = "network-firewall"
    POSTGRESQL = "postgresql"
    ROUTE53 = "route53"
    S3 = "s3"
    SNS = "sns"
    SSM = "ssm"
    STEPFUNCTION = "stepfunction"
    TRANSITGATEWAY = "transitgateway"
    VERIFIED_ACCESS = "verified-access"
    VPC = "vpc"
    WAF = "waf"

    def __str__(self):
        return f"{self.value}"

    @staticmethod
    def cloudwatch_sources():
        return [
            AwsEventSource.CLOUDFRONT,
            AwsEventSource.CLOUDTRAIL,
            AwsEventSource.ELASTICSEARCH,
            AwsEventSource.FARGATE,
            AwsEventSource.MSK,
            AwsEventSource.NETWORKFIREWALL,
            AwsEventSource.ROUTE53,
            AwsEventSource.TRANSITGATEWAY,
            AwsEventSource.VERIFIED_ACCESS,
            AwsEventSource.VPC,
        ]


class AwsS3EventSourceKeyword(Enum):
    def __init__(self, string, event_source):
        self.string = string
        self.event_source = event_source

    # e.g. 2020/10/02/21/aws-waf-logs-testing-1-2020-10-02-21-25-30-x123x-x456x or AWSLogs/123456779121/WAFLogs/us-east-1/xxxxxx-waf/2022/10/11/14/10/123456779121_waflogs_us-east-1_xxxxx-waf_20221011T1410Z_12756524.log.gz
    WAF_0 = ("aws-waf-logs", AwsEventSource.WAF)
    WAF_1 = ("waflogs", AwsEventSource.WAF)

    # e.g. carbon-black-cloud-forwarder/alerts/org_key=*****/year=2021/month=7/day=19/hour=18/minute=15/second=41/8436e850-7e78-40e4-b3cd-6ebbc854d0a2.jsonl.gz
    CARBONBLACK = ("carbon-black", AwsEventSource.CARBONBLACK)
    # e.g. AWSLogs/123456779121/elasticloadbalancing/us-east-1/2020/10/02/123456779121_elasticloadbalancing_us-east-1_app.alb.xxxxx.xx.xxx.xxx_x.log.gz
    ELB = ("elasticloadbalancing", AwsEventSource.ELB)
    GUARDDUTY = ("guardduty", AwsEventSource.GUARDDUTY)
    KINESIS = ("amazon_kinesis", AwsEventSource.KINESIS)
    MSK = ("amazon_msk", AwsEventSource.MSK)
    NETWORKFIREWALL = ("network-firewall", AwsEventSource.NETWORKFIREWALL)
    # e.g. AWSLogs/123456779121/vpcdnsquerylogs/vpc-********/2021/05/11/vpc-********_vpcdnsquerylogs_********_20210511T0910Z_71584702.log.gz
    ROUTE53 = ("vpcdnsquerylogs", AwsEventSource.ROUTE53)
    TRANSITGATEWAY = ("transit-gateway", AwsEventSource.TRANSITGATEWAY)
    VERIFIED_ACCESS = ("verified-access", AwsEventSource.VERIFIED_ACCESS)
    # e.g. AWSLogs/123456779121/vpcflowlogs/us-east-1/2020/10/02/123456779121_vpcflowlogs_us-east-1_fl-xxxxx.log.gz
    VPC = ("vpcflowlogs", AwsEventSource.VPC)

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
    SSM = ("/aws/ssm/", AwsEventSource.SSM)
    TRANSITGATEWAY = ("tgw-attach", AwsEventSource.TRANSITGATEWAY)

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
