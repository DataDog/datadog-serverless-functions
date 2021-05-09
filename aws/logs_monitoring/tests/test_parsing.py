import base64
import gzip
import json
from unittest.mock import MagicMock, patch
import os
import sys
import unittest

sys.modules["trace_forwarder.connection"] = MagicMock()
sys.modules["datadog_lambda.wrapper"] = MagicMock()
sys.modules["datadog_lambda.metric"] = MagicMock()
sys.modules["datadog"] = MagicMock()
sys.modules["requests"] = MagicMock()
sys.modules["requests_futures.sessions"] = MagicMock()

env_patch = patch.dict(os.environ, {"DD_API_KEY": "11111111111111111111111111111111"})
env_patch.start()
from parsing import awslogs_handler, parse_event_source, separate_security_hub_findings

env_patch.stop()


class TestParseEventSource(unittest.TestCase):
    def test_aws_source_if_none_found(self):
        self.assertEqual(parse_event_source({}, "asdfalsfhalskjdfhalsjdf"), "aws")

    def test_cloudtrail_event(self):
        self.assertEqual(
            parse_event_source(
                {"Records": ["logs-from-s3"]},
                "cloud-trail/AWSLogs/123456779121/CloudTrail/us-west-3/2018/01/07/123456779121_CloudTrail_eu-west-3_20180707T1735Z_abcdefghi0MCRL2O.json.gz",
            ),
            "cloudtrail",
        )

    def test_cloudtrail_event_with_service_substrings(self):
        # Assert that source "cloudtrail" is parsed even though substrings "waf" and "sns" are present in the key
        self.assertEqual(
            parse_event_source(
                {"Records": ["logs-from-s3"]},
                "cloud-trail/AWSLogs/123456779121/CloudTrail/us-west-3/2018/01/07/123456779121_CloudTrail_eu-west-3_20180707T1735Z_xywafKsnsXMBrdsMCRL2O.json.gz",
            ),
            "cloudtrail",
        )

    def test_rds_event(self):
        self.assertEqual(
            parse_event_source({"awslogs": "logs"}, "/aws/rds/my-rds-resource"), "rds"
        )

    def test_mariadb_event(self):
        self.assertEqual(
            parse_event_source({"awslogs": "logs"}, "/aws/rds/mariaDB-instance/error"),
            "mariadb",
        )

    def test_mysql_event(self):
        self.assertEqual(
            parse_event_source({"awslogs": "logs"}, "/aws/rds/mySQL-instance/error"),
            "mysql",
        )

    def test_postgresql_event(self):
        self.assertEqual(
            parse_event_source(
                {"awslogs": "logs"}, "/aws/rds/instance/datadog/postgresql"
            ),
            "postgresql",
        )

    def test_lambda_event(self):
        self.assertEqual(
            parse_event_source({"awslogs": "logs"}, "/aws/lambda/postRestAPI"), "lambda"
        )

    def test_apigateway_event(self):
        self.assertEqual(
            parse_event_source(
                {"awslogs": "logs"}, "Api-Gateway-Execution-Logs_a1b23c/test"
            ),
            "apigateway",
        )
        self.assertEqual(
            parse_event_source({"awslogs": "logs"}, "/aws/api-gateway/my-project"),
            "apigateway",
        )
        self.assertEqual(
            parse_event_source({"awslogs": "logs"}, "/aws/http-api/my-project"),
            "apigateway",
        )

    def test_dms_event(self):
        self.assertEqual(
            parse_event_source({"awslogs": "logs"}, "dms-tasks-test-instance"), "dms"
        )
        self.assertEqual(
            parse_event_source(
                {"Records": ["logs-from-s3"]}, "AWSLogs/amazon_dms/my-s3.json.gz"
            ),
            "dms",
        )

    def test_sns_event(self):
        self.assertEqual(
            parse_event_source(
                {"awslogs": "logs"}, "sns/us-east-1/123456779121/SnsTopicX"
            ),
            "sns",
        )

    def test_codebuild_event(self):
        self.assertEqual(
            parse_event_source(
                {"awslogs": "logs"}, "/aws/codebuild/new-project-sample"
            ),
            "codebuild",
        )

    def test_kinesis_event(self):
        self.assertEqual(
            parse_event_source({"awslogs": "logs"}, "/aws/kinesisfirehose/test"),
            "kinesis",
        )
        self.assertEqual(
            parse_event_source(
                {"Records": ["logs-from-s3"]}, "AWSLogs/amazon_kinesis/my-s3.json.gz"
            ),
            "kinesis",
        )

    def test_docdb_event(self):
        self.assertEqual(
            parse_event_source({"awslogs": "logs"}, "/aws/docdb/testCluster/profile"),
            "docdb",
        )
        self.assertEqual(
            parse_event_source(
                {"Records": ["logs-from-s3"]}, "/amazon_documentdb/dev/123abc.zip"
            ),
            "docdb",
        )

    def test_vpc_event(self):
        self.assertEqual(
            parse_event_source({"awslogs": "logs"}, "abc123_my_vpc_loggroup"), "vpc"
        )
        self.assertEqual(
            parse_event_source(
                {"Records": ["logs-from-s3"]},
                "AWSLogs/123456779121/vpcflowlogs/us-east-1/2020/10/02/123456779121_vpcflowlogs_us-east-1_fl-xxxxx.log.gz",
            ),
            "vpc",
        )

    def test_elb_event(self):
        self.assertEqual(
            parse_event_source(
                {"Records": ["logs-from-s3"]},
                "AWSLogs/123456779121/elasticloadbalancing/us-east-1/2020/10/02/123456779121_elasticloadbalancing_us-east-1_app.alb.xxxxx.xx.xxx.xxx_x.log.gz",
            ),
            "elb",
        )

    def test_waf_event(self):
        self.assertEqual(
            parse_event_source(
                {"Records": ["logs-from-s3"]},
                "2020/10/02/21/aws-waf-logs-testing-1-2020-10-02-21-25-30-x123x-x456x",
            ),
            "waf",
        )

    def test_redshift_event(self):
        self.assertEqual(
            parse_event_source(
                {"Records": ["logs-from-s3"]},
                "AWSLogs/123456779121/redshift/us-east-1/2020/10/21/123456779121_redshift_us-east-1_mycluster_userlog_2020-10-21T18:01.gz",
            ),
            "redshift",
        )

    def test_route53_event(self):
        self.assertEqual(
            parse_event_source(
                {"awslogs": "logs"},
                "my-route53-loggroup123",
            ),
            "route53",
        )

    def test_fargate_event(self):
        self.assertEqual(
            parse_event_source(
                {"awslogs": "logs"},
                "/ecs/fargate-logs",
            ),
            "fargate",
        )

    def test_cloudfront_event(self):
        self.assertEqual(
            parse_event_source(
                {"Records": ["logs-from-s3"]},
                "AWSLogs/cloudfront/123456779121/test/01.gz",
            ),
            "cloudfront",
        )

    def test_eks_event(self):
        self.assertEqual(
            parse_event_source(
                {"awslogs": "logs"},
                "/aws/eks/control-plane/cluster",
            ),
            "eks",
        )

    def test_elasticsearch_event(self):
        self.assertEqual(
            parse_event_source({"awslogs": "logs"}, "/elasticsearch/domain"),
            "elasticsearch",
        )

    def test_msk_event(self):
        self.assertEqual(
            parse_event_source(
                {"awslogs": "logs"},
                "/myMSKLogGroup",
            ),
            "msk",
        )
        self.assertEqual(
            parse_event_source(
                {"Records": ["logs-from-s3"]},
                "AWSLogs/amazon_msk/us-east-1/xxxxx.log.gz",
            ),
            "msk",
        )

    def test_cloudwatch_source_if_none_found(self):
        self.assertEqual(parse_event_source({"awslogs": "logs"}, ""), "cloudwatch")

    def test_s3_source_if_none_found(self):
        self.assertEqual(parse_event_source({"Records": ["logs-from-s3"]}, ""), "s3")


class TestParseSecurityHubEvents(unittest.TestCase):
    def test_security_hub_no_findings(self):
        event = {"ddsource": "securityhub"}
        self.assertEqual(
            separate_security_hub_findings(event),
            None,
        )

    def test_security_hub_one_finding_no_resources(self):
        event = {
            "ddsource": "securityhub",
            "detail": {"findings": [{"myattribute": "somevalue"}]},
        }
        self.assertEqual(
            separate_security_hub_findings(event),
            [
                {
                    "ddsource": "securityhub",
                    "detail": {
                        "finding": {"myattribute": "somevalue", "resources": {}}
                    },
                }
            ],
        )

    def test_security_hub_two_findings_one_resource_each(self):
        event = {
            "ddsource": "securityhub",
            "detail": {
                "findings": [
                    {
                        "myattribute": "somevalue",
                        "Resources": [
                            {"Region": "us-east-1", "Type": "AwsEc2SecurityGroup"}
                        ],
                    },
                    {
                        "myattribute": "somevalue",
                        "Resources": [
                            {"Region": "us-east-1", "Type": "AwsEc2SecurityGroup"}
                        ],
                    },
                ]
            },
        }
        self.assertEqual(
            separate_security_hub_findings(event),
            [
                {
                    "ddsource": "securityhub",
                    "detail": {
                        "finding": {
                            "myattribute": "somevalue",
                            "resources": {
                                "AwsEc2SecurityGroup": {"Region": "us-east-1"}
                            },
                        }
                    },
                },
                {
                    "ddsource": "securityhub",
                    "detail": {
                        "finding": {
                            "myattribute": "somevalue",
                            "resources": {
                                "AwsEc2SecurityGroup": {"Region": "us-east-1"}
                            },
                        }
                    },
                },
            ],
        )

    def test_security_hub_multiple_findings_multiple_resources(self):
        event = {
            "ddsource": "securityhub",
            "detail": {
                "findings": [
                    {
                        "myattribute": "somevalue",
                        "Resources": [
                            {"Region": "us-east-1", "Type": "AwsEc2SecurityGroup"}
                        ],
                    },
                    {
                        "myattribute": "somevalue",
                        "Resources": [
                            {"Region": "us-east-1", "Type": "AwsEc2SecurityGroup"},
                            {"Region": "us-east-1", "Type": "AwsOtherSecurityGroup"},
                        ],
                    },
                    {
                        "myattribute": "somevalue",
                        "Resources": [
                            {"Region": "us-east-1", "Type": "AwsEc2SecurityGroup"},
                            {"Region": "us-east-1", "Type": "AwsOtherSecurityGroup"},
                            {"Region": "us-east-1", "Type": "AwsAnotherSecurityGroup"},
                        ],
                    },
                ]
            },
        }
        self.assertEqual(
            separate_security_hub_findings(event),
            [
                {
                    "ddsource": "securityhub",
                    "detail": {
                        "finding": {
                            "myattribute": "somevalue",
                            "resources": {
                                "AwsEc2SecurityGroup": {"Region": "us-east-1"}
                            },
                        }
                    },
                },
                {
                    "ddsource": "securityhub",
                    "detail": {
                        "finding": {
                            "myattribute": "somevalue",
                            "resources": {
                                "AwsEc2SecurityGroup": {"Region": "us-east-1"},
                                "AwsOtherSecurityGroup": {"Region": "us-east-1"},
                            },
                        }
                    },
                },
                {
                    "ddsource": "securityhub",
                    "detail": {
                        "finding": {
                            "myattribute": "somevalue",
                            "resources": {
                                "AwsEc2SecurityGroup": {"Region": "us-east-1"},
                                "AwsOtherSecurityGroup": {"Region": "us-east-1"},
                                "AwsAnotherSecurityGroup": {"Region": "us-east-1"},
                            },
                        }
                    },
                },
            ],
        )


class TestAWSLogsHandler(unittest.TestCase):
    def test_awslogs_handler_rds_postgresql(self):
        event = {
            "awslogs": {
                "data": base64.b64encode(
                    gzip.compress(
                        bytes(
                            json.dumps(
                                {
                                    "owner": "123456789012",
                                    "logGroup": "/aws/rds/instance/datadog/postgresql",
                                    "logStream": "datadog.0",
                                    "logEvents": [
                                        {
                                            "id": "31953106606966983378809025079804211143289615424298221568",
                                            "timestamp": 1609556645000,
                                            "message": "2021-01-02 03:04:05 UTC::@:[5306]:LOG:  database system is ready to accept connections",
                                        }
                                    ],
                                }
                            ),
                            "utf-8",
                        )
                    )
                )
            }
        }
        context = None
        metadata = {"ddsource": "postgresql", "ddtags": "env:dev"}

        self.assertEqual(
            [
                {
                    "aws": {
                        "awslogs": {
                            "logGroup": "/aws/rds/instance/datadog/postgresql",
                            "logStream": "datadog.0",
                            "owner": "123456789012",
                        }
                    },
                    "id": "31953106606966983378809025079804211143289615424298221568",
                    "message": "2021-01-02 03:04:05 UTC::@:[5306]:LOG:  database system is ready "
                    "to accept connections",
                    "timestamp": 1609556645000,
                }
            ],
            list(awslogs_handler(event, context, metadata)),
        )
        self.assertEqual(
            {
                "ddsource": "postgresql",
                "ddtags": "env:dev,logname:postgresql",
                "host": "datadog",
                "service": "postgresql",
            },
            metadata,
        )


if __name__ == "__main__":
    unittest.main()
