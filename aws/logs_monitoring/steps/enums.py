from enum import Enum


class AwsEventSource(Enum):
    APIGATEWAY = "apigateway"
    APPSYNC = "appsync"
    AWS = "aws"
    BEDROCK = "bedrock"
    CARBONBLACK = "carbonblack"
    CLOUDFRONT = "cloudfront"
    CLOUDTRAIL = "cloudtrail"
    CLOUDWATCH = "cloudwatch"
    CODEBUILD = "codebuild"
    DMS = "dms"
    DOCDB = "docdb"
    EKS = "eks"
    ELASTICSEARCH = "elasticsearch"
    ELB = "elb"
    FARGATE = "fargate"
    FSX = "aws.fsx"
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
    RDS = "rds"
    REDSHIFT = "redshift"
    ROUTE53 = "route53"
    S3 = "s3"
    SNS = "sns"
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
            AwsEventSource.NETWORKFIREWALL,
            AwsEventSource.ROUTE53,
            AwsEventSource.VPC,
            AwsEventSource.FARGATE,
            AwsEventSource.CLOUDTRAIL,
            AwsEventSource.MSK,
            AwsEventSource.ELASTICSEARCH,
            AwsEventSource.TRANSITGATEWAY,
            AwsEventSource.VERIFIED_ACCESS,
            AwsEventSource.BEDROCK,
            AwsEventSource.CLOUDFRONT,
        ]

    @staticmethod
    def rds_sources():
        return [AwsEventSource.MARIADB, AwsEventSource.MYSQL, AwsEventSource.POSTGRESQL]


class AwsS3EventSourceKeyword(Enum):
    def __init__(self, string, event_source):
        self.string = string
        self.event_source = event_source

    # e.g. 2020/10/02/21/aws-waf-logs-testing-1-2020-10-02-21-25-30-x123x-x456x or AWSLogs/123456779121/WAFLogs/us-east-1/xxxxxx-waf/2022/10/11/14/10/123456779121_waflogs_us-east-1_xxxxx-waf_20221011T1410Z_12756524.log.gz
    WAF_0 = ("aws-waf-logs", AwsEventSource.WAF)
    WAF_1 = ("waflogs", AwsEventSource.WAF)

    # e.g. 2024/06/12/08/amazon-apigateway-<firehose-ds-name>-2-2024-06-12-08-45-12-796e56c0-7fdf-47b7-9268-38b875bb62d2
    APIGATEWAY = ("amazon-apigateway", AwsEventSource.APIGATEWAY)
    BEDROCK = ("bedrock", AwsEventSource.BEDROCK)
    # e.g. carbon-black-cloud-forwarder/alerts/org_key=*****/year=2021/month=7/day=19/hour=18/minute=15/second=41/8436e850-7e78-40e4-b3cd-6ebbc854d0a2.jsonl.gz
    CARBONBLACK = ("carbon-black", AwsEventSource.CARBONBLACK)
    CODEBUILD = ("amazon_codebuild", AwsEventSource.CODEBUILD)
    CLOUDFRONT = ("cloudfront", AwsEventSource.CLOUDFRONT)
    DMS = ("amazon_dms", AwsEventSource.DMS)
    DOCDB = ("amazon_documentdb", AwsEventSource.DOCDB)
    # e.g. AWSLogs/123456779121/elasticloadbalancing/us-east-1/2020/10/02/123456779121_elasticloadbalancing_us-east-1_app.alb.xxxxx.xx.xxx.xxx_x.log.gz
    ELB = ("elasticloadbalancing", AwsEventSource.ELB)
    KINESIS = ("amazon_kinesis", AwsEventSource.KINESIS)
    MSK = ("amazon_msk", AwsEventSource.MSK)
    NETWORKFIREWALL = ("network-firewall", AwsEventSource.NETWORKFIREWALL)
    # e.g. AWSLogs/123456779121/redshift/us-east-1/2020/10/21/123456779121_redshift_us-east-1_mycluster_userlog_2020-10-21T18:01.gz
    REDSHIFT = ("_redshift_", AwsEventSource.REDSHIFT)
    # e.g. AWSLogs/123456779121/vpcdnsquerylogs/vpc-********/2021/05/11/vpc-********_vpcdnsquerylogs_********_20210511T0910Z_71584702.log.gz
    ROUTE53 = ("vpcdnsquerylogs", AwsEventSource.ROUTE53)
    TRANSITAGATEWAY = ("transit-gateway", AwsEventSource.TRANSITGATEWAY)
    VERIFIED_ACCESS = ("verified-access", AwsEventSource.VERIFIED_ACCESS)
    # e.g. AWSLogs/123456779121/vpcflowlogs/us-east-1/2020/10/02/123456779121_vpcflowlogs_us-east-1_fl-xxxxx.log.gz
    VPC = ("vpcflowlogs", AwsEventSource.VPC)

    def __str__(self):
        return f"{self.string}"


class AwsCwEventSourcePrefix(Enum):
    def __init__(self, string, event_source):
        self.string = string
        self.event_source = event_source

    # default location for rest api execution logs
    APIGATEWAY_0 = ("api-gateway", AwsEventSource.APIGATEWAY)
    # default location set by serverless framework for rest api access logs
    APIGATEWAY_1 = ("/aws/api-gateway", AwsEventSource.APIGATEWAY)
    # default location set by serverless framework for http api logs
    APIGATEWAY_2 = ("/aws/http-api", AwsEventSource.APIGATEWAY)
    # WebSocket API Execution Logs, e.g. /aws/apigateway/api-id/stage-name
    APIGATEWAY_3 = ("/aws/apigateway", AwsEventSource.APIGATEWAY)
    # e.g. /aws/appsync/yourApiId
    APPSYNC = ("/aws/appsync", AwsEventSource.APPSYNC)
    BEDROCK = ("aws/bedrock/modelinvocations", AwsEventSource.BEDROCK)
    # e.g. /aws/codebuild/my-project
    CODEBUILD = ("/aws/codebuild", AwsEventSource.CODEBUILD)
    CLOUDTRAIL = ("_CloudTrail_", AwsEventSource.CLOUDTRAIL)
    # e.g. dms-tasks-test-instance
    DMS = ("dms-tasks", AwsEventSource.DMS)
    # e.g. /aws/docdb/yourClusterName/profile
    DOCDB = ("/aws/docdb", AwsEventSource.DOCDB)
    # e.g. /aws/eks/yourClusterName/profile
    EKS = ("/aws/eks", AwsEventSource.EKS)
    # e.g. /aws/fsx/windows/xxx
    FSX = ("/aws/fsx/windows", AwsEventSource.FSX)
    # e.g. /aws/kinesisfirehose/dev
    KINESIS = ("/aws/kinesis", AwsEventSource.KINESIS)
    # e.g. /aws/lambda/helloDatadog
    lAMBDA = ("/aws/lambda", AwsEventSource.LAMBDA)
    RDS = ("/aws/rds", AwsEventSource.RDS)
    # e.g. sns/us-east-1/123456779121/SnsTopicX
    SNS = ("sns/", AwsEventSource.SNS)
    STEPFUNCTION = ("/aws/vendedlogs/states", AwsEventSource.STEPFUNCTION)
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
