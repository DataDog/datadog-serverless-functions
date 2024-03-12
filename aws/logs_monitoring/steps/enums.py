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


class AwsS3EventSourceKeyword(Enum):
    BEDROCK = "bedrock"
    # e.g. carbon-black-cloud-forwarder/alerts/org_key=*****/year=2021/month=7/day=19/hour=18/minute=15/second=41/8436e850-7e78-40e4-b3cd-6ebbc854d0a2.jsonl.gz
    CARBONBLACK = "carbon-black"
    CODEBUILD = "amazon_codebuild"
    CLOUDFRONT = "cloudfront"
    DMS = "amazon_dms"
    DOCDB = "amazon_documentdb"
    # e.g. AWSLogs/123456779121/elasticloadbalancing/us-east-1/2020/10/02/123456779121_elasticloadbalancing_us-east-1_app.alb.xxxxx.xx.xxx.xxx_x.log.gz
    ELB = "elasticloadbalancing"
    KINESIS = "amazon_kinesis"
    MSK = "amazon_msk"
    NETWORKFIREWALL = "network-firewall"
    # e.g. AWSLogs/123456779121/redshift/us-east-1/2020/10/21/123456779121_redshift_us-east-1_mycluster_userlog_2020-10-21T18:01.gz
    REDSHIFT = "_redshift_"
    # e.g. AWSLogs/123456779121/vpcdnsquerylogs/vpc-********/2021/05/11/vpc-********_vpcdnsquerylogs_********_20210511T0910Z_71584702.log.gz
    ROUTE53 = "vpcdnsquerylogs"
    TRANSITAGATEWAY = "transit-gateway"
    VERIFIED_ACCESS = "verified-access"
    # e.g. AWSLogs/123456779121/vpcflowlogs/us-east-1/2020/10/02/123456779121_vpcflowlogs_us-east-1_fl-xxxxx.log.gz
    VPC = "vpcflowlogs"
    # e.g. 2020/10/02/21/aws-waf-logs-testing-1-2020-10-02-21-25-30-x123x-x456x or AWSLogs/123456779121/WAFLogs/us-east-1/xxxxxx-waf/2022/10/11/14/10/123456779121_waflogs_us-east-1_xxxxx-waf_20221011T1410Z_12756524.log.gz
    WAF_0 = "aws-waf-logs"
    WAF_1 = "waflogs"

    def __str__(self):
        return f"{self.value}"


KEYWORD_TO_SOURCE_MAP = {
    AwsS3EventSourceKeyword.BEDROCK: AwsEventSource.BEDROCK,
    AwsS3EventSourceKeyword.CARBONBLACK: AwsEventSource.CARBONBLACK,
    AwsS3EventSourceKeyword.CODEBUILD: AwsEventSource.CODEBUILD,
    AwsS3EventSourceKeyword.CLOUDFRONT: AwsEventSource.CLOUDFRONT,
    AwsS3EventSourceKeyword.DMS: AwsEventSource.DMS,
    AwsS3EventSourceKeyword.DOCDB: AwsEventSource.DOCDB,
    AwsS3EventSourceKeyword.ELB: AwsEventSource.ELB,
    AwsS3EventSourceKeyword.KINESIS: AwsEventSource.KINESIS,
    AwsS3EventSourceKeyword.MSK: AwsEventSource.MSK,
    AwsS3EventSourceKeyword.NETWORKFIREWALL: AwsEventSource.NETWORKFIREWALL,
    AwsS3EventSourceKeyword.REDSHIFT: AwsEventSource.REDSHIFT,
    AwsS3EventSourceKeyword.ROUTE53: AwsEventSource.ROUTE53,
    AwsS3EventSourceKeyword.TRANSITAGATEWAY: AwsEventSource.TRANSITGATEWAY,
    AwsS3EventSourceKeyword.VERIFIED_ACCESS: AwsEventSource.VERIFIED_ACCESS,
    AwsS3EventSourceKeyword.VPC: AwsEventSource.VPC,
    AwsS3EventSourceKeyword.WAF_0: AwsEventSource.WAF,
    AwsS3EventSourceKeyword.WAF_1: AwsEventSource.WAF,
}


class AwsCwEventSourcePrefix(Enum):
    # default location for rest api execution logs
    APIGATEWAY_0 = "api-gateway"
    # default location set by serverless framework for rest api access logs
    APIGATEWAY_1 = "/aws/api-gateway"
    # default location set by serverless framework for http api logs
    APIGATEWAY_2 = "/aws/http-api"
    # WebSocket API Execution Logs, e.g. /aws/apigateway/api-id/stage-name
    APIGATEWAY_3 = "/aws/apigateway"
    # e.g. /aws/appsync/yourApiId
    APPSYNC = "/aws/appsync"
    BEDROCK = "aws/bedrock/modelinvocations"
    # e.g. /aws/codebuild/my-project
    CODEBUILD = "/aws/codebuild"
    CLOUDTRAIL = "_CloudTrail_"
    # e.g. dms-tasks-test-instance
    DMS = "dms-tasks"
    # e.g. /aws/docdb/yourClusterName/profile
    DOCDB = "/aws/docdb"
    # e.g. /aws/eks/yourClusterName/profile
    EKS = "/aws/eks"
    # e.g. /aws/fsx/windows/xxx
    FSX = "/aws/fsx/windows"
    # e.g. /aws/kinesisfirehose/dev
    KINESIS = "/aws/kinesis"
    # e.g. /aws/lambda/helloDatadog
    lAMBDA = "/aws/lambda"
    RDS = "/aws/rds"
    # e.g. sns/us-east-1/123456779121/SnsTopicX
    SNS = "sns/"
    STEPFUNCTION = "/aws/vendedlogs/states"
    TRANSITGATEWAY = "tgw-attach"

    def __str__(self):
        return f"{self.value}"


PREFIX_TO_SOURCE_MAP = {
    AwsCwEventSourcePrefix.APIGATEWAY_0: AwsEventSource.APIGATEWAY,
    AwsCwEventSourcePrefix.APIGATEWAY_1: AwsEventSource.APIGATEWAY,
    AwsCwEventSourcePrefix.APIGATEWAY_2: AwsEventSource.APIGATEWAY,
    AwsCwEventSourcePrefix.APIGATEWAY_3: AwsEventSource.APIGATEWAY,
    AwsCwEventSourcePrefix.APPSYNC: AwsEventSource.APPSYNC,
    AwsCwEventSourcePrefix.BEDROCK: AwsEventSource.BEDROCK,
    AwsCwEventSourcePrefix.CODEBUILD: AwsEventSource.CODEBUILD,
    AwsCwEventSourcePrefix.CLOUDTRAIL: AwsEventSource.CLOUDTRAIL,
    AwsCwEventSourcePrefix.DMS: AwsEventSource.DMS,
    AwsCwEventSourcePrefix.DOCDB: AwsEventSource.DOCDB,
    AwsCwEventSourcePrefix.EKS: AwsEventSource.EKS,
    AwsCwEventSourcePrefix.FSX: AwsEventSource.FSX,
    AwsCwEventSourcePrefix.KINESIS: AwsEventSource.KINESIS,
    AwsCwEventSourcePrefix.lAMBDA: AwsEventSource.LAMBDA,
    AwsCwEventSourcePrefix.RDS: AwsEventSource.RDS,
    AwsCwEventSourcePrefix.SNS: AwsEventSource.SNS,
    AwsCwEventSourcePrefix.STEPFUNCTION: AwsEventSource.STEPFUNCTION,
    AwsCwEventSourcePrefix.TRANSITGATEWAY: AwsEventSource.TRANSITGATEWAY,
}


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
