import unittest
from approvaltests.approvals import verify_as_json
from steps.transformation import (
    separate_security_hub_findings,
    parse_aws_waf_logs,
    transform,
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
        verify_as_json(parse_aws_waf_logs(event))

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
        verify_as_json(parse_aws_waf_logs(event))

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
        verify_as_json(parse_aws_waf_logs(event))

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
        verify_as_json(parse_aws_waf_logs(event))

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
        verify_as_json(parse_aws_waf_logs(event))

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
        verify_as_json(parse_aws_waf_logs(event))


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
        verify_as_json(separate_security_hub_findings(event))

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
        verify_as_json(separate_security_hub_findings(event))

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
        verify_as_json(separate_security_hub_findings(event))


class TestTransform(unittest.TestCase):
    def setUp(self) -> None:
        self.waf_events = [
            {
                "ddsource": "waf",
                "message": {
                    "httpRequest": {
                        "headers": [
                            {"name": "header1", "value": "value1"},
                            {"name": "header2", "value": "value2"},
                        ]
                    },
                    "request_id": "1",
                },
            },
            {
                "ddsource": "waf",
                "message": {
                    "httpRequest": {
                        "headers": [
                            {"name": "header1", "value": "value1"},
                        ]
                    },
                    "request_id": "2",
                },
            },
            {
                "ddsource": "waf",
                "message": {
                    "httpRequest": {
                        "headers": [
                            {"name": "header3", "value": "value3"},
                        ]
                    },
                    "request_id": "3",
                },
            },
        ]

        self.sec_hub_events = [
            {
                "ddsource": "securityhub",
                "detail": {"findings": [{"finding": "1"}, {"finding": "2"}]},
            },
            {
                "ddsource": "securityhub",
                "detail": {"findings": [{"finding": "3"}, {"finding": "4"}]},
            },
        ]

        self.mixed_events = [
            {
                "ddsource": "waf",
                "message": {
                    "request_id": "1",
                    "httpRequest": {
                        "headers": [{"name": "header2", "value": "value2"}]
                    },
                },
            },
            {
                "ddsource": "securityhub",
                "detail": {"findings": [{"finding": "1"}, {"finding": "2"}]},
            },
            {
                "ddsource": "waf",
                "message": {
                    "request_id": "2",
                    "httpRequest": {
                        "headers": [{"name": "header1", "value": "value1"}]
                    },
                },
            },
        ]

    # respect events order and prevent duplication
    def test_transform_waf(self):
        verify_as_json(transform(self.waf_events))

    def test_transform_mixed(self):
        verify_as_json(transform(self.mixed_events))

    def test_transform_security_hub(self):
        verify_as_json(transform(self.sec_hub_events))

    def test_transform_empty(self):
        self.assertEqual(transform([]), [])


if __name__ == "__main__":
    unittest.main()
