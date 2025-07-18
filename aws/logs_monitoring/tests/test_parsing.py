import unittest

from settings import DD_CUSTOM_TAGS, DD_SOURCE
from steps.common import get_service_from_tags_and_remove_duplicates, parse_event_source
from steps.enums import AwsEventSource


class TestParseEventSource(unittest.TestCase):
    def test_aws_source_if_none_found(self):
        self.assertEqual(parse_event_source({}, "asdfalsfhalskjdfhalsjdf"), "aws")

    def test_cloudtrail_event(self):
        self.assertEqual(
            parse_event_source(
                {"Records": ["logs-from-s3"]},
                "cloud-trail/AWSLogs/123456779121/CloudTrail/us-west-3/2018/01/07/123456779121_CloudTrail_eu-west-3_20180707T1735Z_abcdefghi0MCRL2O.json.gz",
            ),
            str(AwsEventSource.CLOUDTRAIL),
        )

    def test_cloudtrail_digest_event(self):
        self.assertEqual(
            parse_event_source(
                {"Records": ["logs-from-s3"]},
                "cloud-trail/AWSLogs/123456779121/CloudTrail/us-east-1/2018/01/07/123456779121_CloudTrail-Digest_us-east-1_AWS-CloudTrail_us-east-1_20180707T173567Z.json.gz",
            ),
            str(AwsEventSource.CLOUDTRAIL),
        )

    def test_cloudtrail_gov_event(self):
        self.assertEqual(
            parse_event_source(
                {"Records": ["logs-from-s3"]},
                "cloud-trail/AWSLogs/123456779121/CloudTrail/us-gov-west-1/2018/01/07/123456779121_CloudTrail_us-gov-west-1_20180707T1735Z_abcdefghi0MCRL2O.json.gz",
            ),
            str(AwsEventSource.CLOUDTRAIL),
        )

    def test_cloudtrail_event_with_service_substrings(self):
        # Assert that source "cloudtrail" is parsed even though substrings "waf" and "sns" are present in the key
        self.assertEqual(
            parse_event_source(
                {"Records": ["logs-from-s3"]},
                "cloud-trail/AWSLogs/123456779121/CloudTrail/us-west-3/2018/01/07/123456779121_CloudTrail_eu-west-3_20180707T1735Z_xywafKsnsXMBrdsMCRL2O.json.gz",
            ),
            str(AwsEventSource.CLOUDTRAIL),
        )

    def test_rds_event(self):
        self.assertEqual(
            parse_event_source({"awslogs": "logs"}, "/aws/rds/my-rds-resource"),
            str(AwsEventSource.CLOUDWATCH),
        )

    def test_mariadb_event(self):
        self.assertEqual(
            parse_event_source({"awslogs": "logs"}, "/aws/rds/mariaDB-instance/error"),
            str(AwsEventSource.CLOUDWATCH),
        )

    def test_mysql_event(self):
        self.assertEqual(
            parse_event_source({"awslogs": "logs"}, "/aws/rds/mySQL-instance/error"),
            str(AwsEventSource.CLOUDWATCH),
        )

    def test_postgresql_event(self):
        self.assertEqual(
            parse_event_source(
                {"awslogs": "logs"}, "/aws/rds/instance/datadog/postgresql"
            ),
            str(AwsEventSource.CLOUDWATCH),
        )

    def test_lambda_event(self):
        self.assertEqual(
            parse_event_source({"awslogs": "logs"}, "/aws/lambda/postRestAPI"),
            str(AwsEventSource.LAMBDA),
        )

    def test_sns_event(self):
        self.assertEqual(
            parse_event_source(
                {"awslogs": "logs"}, "sns/us-east-1/123456779121/SnsTopicX"
            ),
            str(AwsEventSource.SNS),
        )

    def test_kinesis_event(self):
        self.assertEqual(
            parse_event_source({"awslogs": "logs"}, "/aws/kinesisfirehose/test"),
            str(AwsEventSource.KINESIS),
        )
        self.assertEqual(
            parse_event_source(
                {"Records": ["logs-from-s3"]}, "AWSLogs/amazon_kinesis/my-s3.json.gz"
            ),
            str(AwsEventSource.KINESIS),
        )

    def test_waf_event(self):
        self.assertEqual(
            parse_event_source(
                {"Records": ["logs-from-s3"]},
                "2020/10/02/21/aws-waf-logs-testing-1-2020-10-02-21-25-30-x123x-x456x",
            ),
            str(AwsEventSource.WAF),
        )

        self.assertEqual(
            parse_event_source(
                {"Records": ["logs-from-s3"]},
                "AWSLogs/123456779121/WAFLogs/us-east-1/xxxxxx-waf/2022/10/11/14/10/123456779121_waflogs_us-east-1_xxxxx-waf_20221011T1410Z_12756524.log.gz",
            ),
            str(AwsEventSource.WAF),
        )

    def test_redshift_event(self):
        self.assertEqual(
            parse_event_source(
                {"Records": ["logs-from-s3"]},
                "AWSLogs/123456779121/redshift/us-east-1/2020/10/21/123456779121_redshift_us-east-1_mycluster_userlog_2020-10-21T18:01.gz",
            ),
            str(AwsEventSource.S3),
        )

    def test_redshift_gov_event(self):
        self.assertEqual(
            parse_event_source(
                {"Records": ["logs-from-s3"]},
                "AWSLogs/123456779121/redshift/us-gov-east-1/2020/10/21/123456779121_redshift_us-gov-east"
                "-1_mycluster_userlog_2020-10-21T18:01.gz",
            ),
            str(AwsEventSource.S3),
        )

    def test_route53_event(self):
        self.assertEqual(
            parse_event_source(
                {"awslogs": "logs"},
                "my-route53-loggroup123",
            ),
            str(AwsEventSource.ROUTE53),
        )

    def test_vpcdnsquerylogs_event(self):
        self.assertEqual(
            parse_event_source(
                {"Records": ["logs-from-s3"]},
                "AWSLogs/123456779121/vpcdnsquerylogs/vpc-********/2021/05/11/vpc-********_vpcdnsquerylogs_********_20210511T0910Z_71584702.log.gz",
            ),
            str(AwsEventSource.ROUTE53),
        )

    def test_fargate_event(self):
        self.assertEqual(
            parse_event_source(
                {"awslogs": "logs"},
                "/ecs/fargate-logs",
            ),
            str(AwsEventSource.FARGATE),
        )

    def test_cloudfront_event(self):
        self.assertEqual(
            parse_event_source(
                {"Records": ["logs-from-s3"]},
                "AWSLogs/cloudfront/123456779121/test/01.gz",
            ),
            str(AwsEventSource.S3),
        )

    def test_elasticsearch_event(self):
        self.assertEqual(
            parse_event_source({"awslogs": "logs"}, "/elasticsearch/domain"),
            str(AwsEventSource.ELASTICSEARCH),
        )

    def test_msk_event(self):
        self.assertEqual(
            parse_event_source(
                {"awslogs": "logs"},
                "/myMSKLogGroup",
            ),
            str(AwsEventSource.MSK),
        )
        self.assertEqual(
            parse_event_source(
                {"Records": ["logs-from-s3"]},
                "AWSLogs/amazon_msk/us-east-1/xxxxx.log.gz",
            ),
            str(AwsEventSource.MSK),
        )

    def test_cloudwatch_source_if_none_found(self):
        self.assertEqual(
            parse_event_source({"awslogs": "logs"}, ""), str(AwsEventSource.CLOUDWATCH)
        )

    def test_s3_source_if_none_found(self):
        self.assertEqual(
            parse_event_source({"Records": ["logs-from-s3"]}, ""),
            str(AwsEventSource.S3),
        )


class TestGetServiceFromTags(unittest.TestCase):
    def test_get_service_from_tags(self):
        metadata = {
            DD_SOURCE: "ecs",
            DD_CUSTOM_TAGS: "env:dev,tag,stack:aws:ecs,service:web,version:v1",
        }
        self.assertEqual(get_service_from_tags_and_remove_duplicates(metadata), "web")

    def test_get_service_from_tags_default_to_source(self):
        metadata = {
            DD_SOURCE: "ecs",
            DD_CUSTOM_TAGS: "env:dev,tag,stack:aws:ecs,version:v1",
        }
        self.assertEqual(get_service_from_tags_and_remove_duplicates(metadata), "ecs")

    def test_get_service_from_tags_removing_duplicates(self):
        metadata = {
            DD_SOURCE: "ecs",
            DD_CUSTOM_TAGS: (
                "env:dev,tag,stack:aws:ecs,service:web,version:v1,service:other"
            ),
        }
        self.assertEqual(get_service_from_tags_and_remove_duplicates(metadata), "web")
        self.assertEqual(
            metadata[DD_CUSTOM_TAGS], "env:dev,tag,stack:aws:ecs,service:web,version:v1"
        )


if __name__ == "__main__":
    unittest.main()
