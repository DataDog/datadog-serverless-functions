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
from lambda_function import parse_event_source

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


if __name__ == "__main__":
    unittest.main()
