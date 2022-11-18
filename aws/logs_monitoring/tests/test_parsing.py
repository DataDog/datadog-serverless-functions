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

env_patch = patch.dict(
    os.environ,
    {
        "DD_API_KEY": "11111111111111111111111111111111",
    },
)
env_patch.start()
from parsing import (
    awslogs_handler,
    parse_event_source,
    parse_service_arn,
    separate_security_hub_findings,
    parse_aws_waf_logs,
    get_service_from_tags,
)
from settings import (
    DD_CUSTOM_TAGS,
    DD_SOURCE,
)

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

    def test_cloudtrail_digest_event(self):
        self.assertEqual(
            parse_event_source(
                {"Records": ["logs-from-s3"]},
                "cloud-trail/AWSLogs/123456779121/CloudTrail/us-east-1/2018/01/07/123456779121_CloudTrail-Digest_us-east-1_AWS-CloudTrail_us-east-1_20180707T173567Z.json.gz",
            ),
            "cloudtrail",
        )

    def test_cloudtrail_gov_event(self):
        self.assertEqual(
            parse_event_source(
                {"Records": ["logs-from-s3"]},
                "cloud-trail/AWSLogs/123456779121/CloudTrail/us-gov-west-1/2018/01/07/123456779121_CloudTrail_us-gov-west-1_20180707T1735Z_abcdefghi0MCRL2O.json.gz",
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

        self.assertEqual(
            parse_event_source(
                {"Records": ["logs-from-s3"]},
                "AWSLogs/123456779121/WAFLogs/us-east-1/xxxxxx-waf/2022/10/11/14/10/123456779121_waflogs_us-east-1_xxxxx-waf_20221011T1410Z_12756524.log.gz",
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

    def test_redshift_gov_event(self):
        self.assertEqual(
            parse_event_source(
                {"Records": ["logs-from-s3"]},
                "AWSLogs/123456779121/redshift/us-gov-east-1/2020/10/21/123456779121_redshift_us-gov-east"
                "-1_mycluster_userlog_2020-10-21T18:01.gz",
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

    def test_vpcdnsquerylogs_event(self):
        self.assertEqual(
            parse_event_source(
                {"Records": ["logs-from-s3"]},
                "AWSLogs/123456779121/vpcdnsquerylogs/vpc-********/2021/05/11/vpc-********_vpcdnsquerylogs_********_20210511T0910Z_71584702.log.gz",
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

    def test_appsync_event(self):
        self.assertEqual(
            parse_event_source(
                {"awslogs": "logs"},
                "/aws/appsync/apis/",
            ),
            "appsync",
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

    def test_carbon_black_event(self):
        self.assertEqual(
            parse_event_source(
                {"Records": ["logs-from-s3"]},
                "carbon-black-cloud-forwarder/alerts/8436e850-7e78-40e4-b3cd-6ebbc854d0a2.jsonl.gz",
            ),
            "carbonblack",
        )

    def test_step_function_event(self):
        self.assertEqual(
            parse_event_source(
                {"awslogs": "logs"}, "/aws/vendedlogs/states/MyStateMachine-Logs"
            ),
            "stepfunction",
        )

    def test_cloudwatch_source_if_none_found(self):
        self.assertEqual(parse_event_source({"awslogs": "logs"}, ""), "cloudwatch")

    def test_s3_source_if_none_found(self):
        self.assertEqual(parse_event_source({"Records": ["logs-from-s3"]}, ""), "s3")


class TestParseServiceArn(unittest.TestCase):
    def test_elb_s3_key_invalid(self):
        self.assertEqual(
            parse_service_arn(
                "elb",
                "123456789123/elasticloadbalancing/us-east-1/2022/02/08/123456789123_elasticloadbalancing_us-east-1_app.my-alb-name.123456789aabcdef_20220208T1127Z_10.0.0.2_1abcdef2.log.gz",
                None,
                None,
            ),
            None,
        )

    def test_elb_s3_key_no_prefix(self):
        self.assertEqual(
            parse_service_arn(
                "elb",
                "AWSLogs/123456789123/elasticloadbalancing/us-east-1/2022/02/08/123456789123_elasticloadbalancing_us-east-1_app.my-alb-name.123456789aabcdef_20220208T1127Z_10.0.0.2_1abcdef2.log.gz",
                None,
                None,
            ),
            "arn:aws:elasticloadbalancing:us-east-1:123456789123:loadbalancer/app/my-alb-name/123456789aabcdef",
        )

    def test_elb_s3_key_single_prefix(self):
        self.assertEqual(
            parse_service_arn(
                "elb",
                "elasticloadbalancing/AWSLogs/123456789123/elasticloadbalancing/us-east-1/2022/02/08/123456789123_elasticloadbalancing_us-east-1_app.my-alb-name.123456789aabcdef_20220208T1127Z_10.0.0.2_1abcdef2.log.gz",
                None,
                None,
            ),
            "arn:aws:elasticloadbalancing:us-east-1:123456789123:loadbalancer/app/my-alb-name/123456789aabcdef",
        )

    def test_elb_s3_key_multi_prefix(self):
        self.assertEqual(
            parse_service_arn(
                "elb",
                "elasticloadbalancing/my-alb-name/AWSLogs/123456789123/elasticloadbalancing/us-east-1/2022/02/08/123456789123_elasticloadbalancing_us-east-1_app.my-alb-name.123456789aabcdef_20220208T1127Z_10.0.0.2_1abcdef2.log.gz",
                None,
                None,
            ),
            "arn:aws:elasticloadbalancing:us-east-1:123456789123:loadbalancer/app/my-alb-name/123456789aabcdef",
        )

    def test_elb_s3_key_multi_prefix_gov(self):
        self.assertEqual(
            parse_service_arn(
                "elb",
                "elasticloadbalancing/my-alb-name/AWSLogs/123456789123/elasticloadbalancing/us-gov-east-1/2022/02/08"
                "/123456789123_elasticloadbalancing_us-gov-east-1_app.my-alb-name.123456789aabcdef_20220208T1127Z_10"
                ".0.0.2_1abcdef2.log.gz",
                None,
                None,
            ),
            "arn:aws-us-gov:elasticloadbalancing:us-gov-east-1:123456789123:loadbalancer/app/my-alb-name"
            "/123456789aabcdef",
        )


class TestParseAwsWafLogs(unittest.TestCase):
    def test_waf_string_invalid_json(self):
        event = "This is not valid JSON."
        self.assertEqual(parse_aws_waf_logs(event), "This is not valid JSON.")

    def test_waf_string_json(self):
        event = '{"ddsource":"waf","message":"This is a string of JSON"}'
        self.assertEqual(
            parse_aws_waf_logs(event),
            {"ddsource": "waf", "message": "This is a string of JSON"},
        )

    def test_waf_headers(self):
        event = {
            "ddsource": "waf",
            "message": {
                "httpRequest": {
                    "headers": [
                        {"name": "header1", "value": "value1"},
                        {"name": "header2", "value": "value2"},
                    ]
                }
            },
        }
        self.assertEqual(
            parse_aws_waf_logs(event),
            {
                "ddsource": "waf",
                "message": {
                    "httpRequest": {
                        "headers": {"header1": "value1", "header2": "value2"}
                    }
                },
            },
        )

    def test_waf_non_terminating_matching_rules(self):
        event = {
            "ddsource": "waf",
            "message": {
                "nonTerminatingMatchingRules": [
                    {"ruleId": "nonterminating1", "action": "COUNT"},
                    {"ruleId": "nonterminating2", "action": "COUNT"},
                ]
            },
        }
        self.assertEqual(
            parse_aws_waf_logs(event),
            {
                "ddsource": "waf",
                "message": {
                    "nonTerminatingMatchingRules": {
                        "nonterminating2": {"action": "COUNT"},
                        "nonterminating1": {"action": "COUNT"},
                    }
                },
            },
        )

    def test_waf_rate_based_rules(self):
        event = {
            "ddsource": "waf",
            "message": {
                "rateBasedRuleList": [
                    {
                        "limitValue": "195.154.122.189",
                        "rateBasedRuleName": "tf-rate-limit-5-min",
                        "rateBasedRuleId": "arn:aws:wafv2:ap-southeast-2:068133125972_MANAGED:regional/ipset/0f94bd8b-0fa5-4865-81ce-d11a60051fb4_fef50279-8b9a-4062-b733-88ecd1cfd889_IPV4/fef50279-8b9a-4062-b733-88ecd1cfd889",
                        "maxRateAllowed": 300,
                        "limitKey": "IP",
                    },
                    {
                        "limitValue": "195.154.122.189",
                        "rateBasedRuleName": "no-rate-limit",
                        "rateBasedRuleId": "arn:aws:wafv2:ap-southeast-2:068133125972_MANAGED:regional/ipset/0f94bd8b-0fa5-4865-81ce-d11a60051fb4_fef50279-8b9a-4062-b733-88ecd1cfd889_IPV4/fef50279-8b9a-4062-b733-88ecd1cfd889",
                        "maxRateAllowed": 300,
                        "limitKey": "IP",
                    },
                ]
            },
        }
        self.assertEqual(
            parse_aws_waf_logs(event),
            {
                "ddsource": "waf",
                "message": {
                    "rateBasedRuleList": {
                        "tf-rate-limit-5-min": {
                            "rateBasedRuleId": "arn:aws:wafv2:ap-southeast-2:068133125972_MANAGED:regional/ipset/0f94bd8b-0fa5-4865-81ce-d11a60051fb4_fef50279-8b9a-4062-b733-88ecd1cfd889_IPV4/fef50279-8b9a-4062-b733-88ecd1cfd889",
                            "limitValue": "195.154.122.189",
                            "maxRateAllowed": 300,
                            "limitKey": "IP",
                        },
                        "no-rate-limit": {
                            "rateBasedRuleId": "arn:aws:wafv2:ap-southeast-2:068133125972_MANAGED:regional/ipset/0f94bd8b-0fa5-4865-81ce-d11a60051fb4_fef50279-8b9a-4062-b733-88ecd1cfd889_IPV4/fef50279-8b9a-4062-b733-88ecd1cfd889",
                            "limitValue": "195.154.122.189",
                            "maxRateAllowed": 300,
                            "limitKey": "IP",
                        },
                    }
                },
            },
        )

    def test_waf_rule_group_with_excluded_and_nonterminating_rules(self):
        event = {
            "ddsource": "waf",
            "message": {
                "ruleGroupList": [
                    {
                        "ruleGroupId": "AWS#AWSManagedRulesSQLiRuleSet",
                        "terminatingRule": {
                            "ruleId": "SQLi_QUERYARGUMENTS",
                            "action": "BLOCK",
                        },
                        "nonTerminatingMatchingRules": [
                            {
                                "exclusionType": "REGULAR",
                                "ruleId": "first_nonterminating",
                            },
                            {
                                "exclusionType": "REGULAR",
                                "ruleId": "second_nonterminating",
                            },
                        ],
                        "excludedRules": [
                            {
                                "exclusionType": "EXCLUDED_AS_COUNT",
                                "ruleId": "GenericRFI_BODY",
                            },
                            {
                                "exclusionType": "EXCLUDED_AS_COUNT",
                                "ruleId": "second_exclude",
                            },
                        ],
                    }
                ]
            },
        }
        self.assertEqual(
            parse_aws_waf_logs(event),
            {
                "ddsource": "waf",
                "message": {
                    "ruleGroupList": {
                        "AWS#AWSManagedRulesSQLiRuleSet": {
                            "nonTerminatingMatchingRules": {
                                "second_nonterminating": {"exclusionType": "REGULAR"},
                                "first_nonterminating": {"exclusionType": "REGULAR"},
                            },
                            "excludedRules": {
                                "GenericRFI_BODY": {
                                    "exclusionType": "EXCLUDED_AS_COUNT"
                                },
                                "second_exclude": {
                                    "exclusionType": "EXCLUDED_AS_COUNT"
                                },
                            },
                            "terminatingRule": {
                                "SQLi_QUERYARGUMENTS": {"action": "BLOCK"}
                            },
                        }
                    }
                },
            },
        )

    def test_waf_rule_group_two_rules_same_group_id(self):
        event = {
            "ddsource": "waf",
            "message": {
                "ruleGroupList": [
                    {
                        "ruleGroupId": "AWS#AWSManagedRulesSQLiRuleSet",
                        "terminatingRule": {
                            "ruleId": "SQLi_QUERYARGUMENTS",
                            "action": "BLOCK",
                        },
                    },
                    {
                        "ruleGroupId": "AWS#AWSManagedRulesSQLiRuleSet",
                        "terminatingRule": {"ruleId": "secondRULE", "action": "BLOCK"},
                    },
                ]
            },
        }
        self.assertEqual(
            parse_aws_waf_logs(event),
            {
                "ddsource": "waf",
                "message": {
                    "ruleGroupList": {
                        "AWS#AWSManagedRulesSQLiRuleSet": {
                            "terminatingRule": {
                                "SQLi_QUERYARGUMENTS": {"action": "BLOCK"},
                                "secondRULE": {"action": "BLOCK"},
                            }
                        }
                    }
                },
            },
        )

    def test_waf_rule_group_three_rules_two_group_ids(self):
        event = {
            "ddsource": "waf",
            "message": {
                "ruleGroupList": [
                    {
                        "ruleGroupId": "AWS#AWSManagedRulesSQLiRuleSet",
                        "terminatingRule": {
                            "ruleId": "SQLi_QUERYARGUMENTS",
                            "action": "BLOCK",
                        },
                    },
                    {
                        "ruleGroupId": "AWS#AWSManagedRulesSQLiRuleSet",
                        "terminatingRule": {"ruleId": "secondRULE", "action": "BLOCK"},
                    },
                    {
                        "ruleGroupId": "A_DIFFERENT_ID",
                        "terminatingRule": {"ruleId": "thirdRULE", "action": "BLOCK"},
                    },
                ]
            },
        }
        self.assertEqual(
            parse_aws_waf_logs(event),
            {
                "ddsource": "waf",
                "message": {
                    "ruleGroupList": {
                        "AWS#AWSManagedRulesSQLiRuleSet": {
                            "terminatingRule": {
                                "SQLi_QUERYARGUMENTS": {"action": "BLOCK"},
                                "secondRULE": {"action": "BLOCK"},
                            }
                        },
                        "A_DIFFERENT_ID": {
                            "terminatingRule": {"thirdRULE": {"action": "BLOCK"}}
                        },
                    }
                },
            },
        )


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
    @patch("parsing.CloudwatchLogGroupTagsCache.get")
    @patch("parsing.CloudwatchLogGroupTagsCache.release_s3_cache_lock")
    @patch("parsing.CloudwatchLogGroupTagsCache.acquire_s3_cache_lock")
    @patch("parsing.CloudwatchLogGroupTagsCache.write_cache_to_s3")
    @patch("base_tags_cache.send_forwarder_internal_metrics")
    @patch("parsing.CloudwatchLogGroupTagsCache.get_cache_from_s3")
    def test_awslogs_handler_rds_postgresql(
        self,
        mock_get_s3_cache,
        mock_forward_metrics,
        mock_write_cache,
        mock_acquire_lock,
        mock_release_lock,
        mock_cache_get,
    ):
        os.environ["DD_FETCH_LAMBDA_TAGS"] = "True"
        os.environ["DD_FETCH_LOG_GROUP_TAGS"] = "True"
        mock_acquire_lock.return_value = True
        mock_cache_get.return_value = ["test_tag_key:test_tag_value"]
        mock_get_s3_cache.return_value = (
            {},
            1000,
        )

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
                "ddtags": "env:dev,test_tag_key:test_tag_value,logname:postgresql",
                "host": "datadog",
                "service": "postgresql",
            },
            metadata,
        )

    @patch("parsing.CloudwatchLogGroupTagsCache.get")
    @patch("parsing.StepFunctionsTagsCache.get")
    @patch("parsing.StepFunctionsTagsCache.release_s3_cache_lock")
    @patch("parsing.StepFunctionsTagsCache.acquire_s3_cache_lock")
    @patch("parsing.StepFunctionsTagsCache.write_cache_to_s3")
    @patch("base_tags_cache.send_forwarder_internal_metrics")
    @patch("parsing.StepFunctionsTagsCache.get_cache_from_s3")
    def test_awslogs_handler_step_functions_tags_added_properly(
        self,
        mock_get_s3_cache,
        mock_forward_metrics,
        mock_write_cache,
        mock_acquire_lock,
        mock_release_lock,
        mock_step_functions_cache_get,
        mock_cw_log_group_cache_get,
    ):
        os.environ["DD_FETCH_LAMBDA_TAGS"] = "True"
        os.environ["DD_FETCH_LOG_GROUP_TAGS"] = "True"
        os.environ["DD_FETCH_STEP_FUNCTIONS_TAGS"] = "True"
        mock_acquire_lock.return_value = True
        mock_step_functions_cache_get.return_value = ["test_tag_key:test_tag_value"]
        mock_cw_log_group_cache_get.return_value = []
        mock_get_s3_cache.return_value = (
            {},
            1000,
        )

        event = {
            "awslogs": {
                "data": base64.b64encode(
                    gzip.compress(
                        bytes(
                            json.dumps(
                                {
                                    "messageType": "DATA_MESSAGE",
                                    "owner": "425362996713",
                                    "logGroup": "/aws/vendedlogs/states/logs-to-traces-sequential-Logs",
                                    "logStream": "states/logs-to-traces-sequential/2022-11-10-15-50/7851b2d9",
                                    "subscriptionFilters": ["testFilter"],
                                    "logEvents": [
                                        {
                                            "id": "37199773595581154154810589279545129148442535997644275712",
                                            "timestamp": 1668095539607,
                                            "message": '{"id":"1","type":"ExecutionStarted","details":{"input":"{"Comment": "Insert your JSON here"}","inputDetails":{"truncated":false},"roleArn":"arn:aws:iam::425362996713:role/service-role/StepFunctions-logs-to-traces-sequential-role-ccd69c03"},",previous_event_id":"0","event_timestamp":"1668095539607","execution_arn":"arn:aws:states:sa-east-1:425362996713:express:logs-to-traces-sequential:d0dbefd8-a0f6-b402-da4c-f4863def7456:7fa0cfbe-be28-4a20-9875-73c37f5dc39e"}',
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
                            "logGroup": "/aws/vendedlogs/states/logs-to-traces-sequential-Logs",
                            "logStream": "states/logs-to-traces-sequential/2022-11-10-15-50/7851b2d9",
                            "owner": "425362996713",
                        }
                    },
                    "id": "37199773595581154154810589279545129148442535997644275712",
                    "message": '{"id":"1","type":"ExecutionStarted","details":{"input":"{"Comment": "Insert your JSON here"}","inputDetails":{"truncated":false},"roleArn":"arn:aws:iam::425362996713:role/service-role/StepFunctions-logs-to-traces-sequential-role-ccd69c03"},",previous_event_id":"0","event_timestamp":"1668095539607","execution_arn":"arn:aws:states:sa-east-1:425362996713:express:logs-to-traces-sequential:d0dbefd8-a0f6-b402-da4c-f4863def7456:7fa0cfbe-be28-4a20-9875-73c37f5dc39e"}',
                    "timestamp": 1668095539607,
                }
            ],
            list(awslogs_handler(event, context, metadata)),
        )
        self.assertEqual(
            {
                "ddsource": "stepfunction",
                "ddtags": "env:dev,test_tag_key:test_tag_value",
                "host": "/aws/vendedlogs/states/logs-to-traces-sequential-Logs",
                "service": "stepfunction",
            },
            metadata,
        )


class TestGetServiceFromTags(unittest.TestCase):
    def test_get_service_from_tags(self):
        metadata = {
            DD_SOURCE: "ecs",
            DD_CUSTOM_TAGS: "env:dev,tag,stack:aws:ecs,service:web,version:v1",
        }
        self.assertEqual(get_service_from_tags(metadata), "web")

    def test_get_service_from_tags_default_to_source(self):
        metadata = {
            DD_SOURCE: "ecs",
            DD_CUSTOM_TAGS: "env:dev,tag,stack:aws:ecs,version:v1",
        }
        self.assertEqual(get_service_from_tags(metadata), "ecs")


if __name__ == "__main__":
    unittest.main()
