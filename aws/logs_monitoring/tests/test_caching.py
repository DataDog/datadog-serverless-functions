import unittest
from caching.common import (
    sanitize_aws_tag_string,
    parse_get_resources_response_for_tags_by_arn,
    get_dd_tag_string_from_aws_dict,
)


class TestCaching(unittest.TestCase):
    def test_sanitize_tag_string(self):
        self.assertEqual(sanitize_aws_tag_string("serverless"), "serverless")
        # Don't replace : \ / . in middle of string
        self.assertEqual(sanitize_aws_tag_string("ser-/.ver_less"), "ser-/.ver_less")
        # Remove invalid characters
        self.assertEqual(sanitize_aws_tag_string("s+e@rv_erl_ess"), "s_e_rv_erl_ess")
        # Dedup underscores
        self.assertEqual(sanitize_aws_tag_string("serverl___ess"), "serverl_ess")
        # Keep colons when remove_colons=False
        self.assertEqual(sanitize_aws_tag_string("serv:erless:"), "serv:erless:")
        # Substitute colon when remove_colons=True
        self.assertEqual(
            sanitize_aws_tag_string("serv:erless:", remove_colons=True), "serv_erless"
        )
        # Convert to lower
        self.assertEqual(sanitize_aws_tag_string("serVerLess"), "serverless")
        self.assertEqual(sanitize_aws_tag_string(""), "")
        self.assertEqual(sanitize_aws_tag_string("6.6.6"), ".6.6")
        self.assertEqual(
            sanitize_aws_tag_string("6.6.6", remove_leading_digits=False), "6.6.6"
        )

    def test_get_dd_tag_string_from_aws_dict(self):
        # Sanitize the key and value, combine them into a string
        test_dict = {
            "Key": "region",
            "Value": "us-east-1",
        }

        self.assertEqual(get_dd_tag_string_from_aws_dict(test_dict), "region:us-east-1")

        # Truncate to 200 characters
        long_string = "a" * 300

        test_dict = {
            "Key": "too-long",
            "Value": long_string,
        }

        self.assertEqual(
            get_dd_tag_string_from_aws_dict(test_dict), f"too-long:{long_string[0:191]}"
        )

    def test_generate_custom_tags_cache(self):
        self.assertEqual(
            parse_get_resources_response_for_tags_by_arn(
                {
                    "ResourceTagMappingList": [
                        {
                            "ResourceARN": "arn:aws:lambda:us-east-1:123497598159:function:my-test-lambda-dev",
                            "Tags": [
                                {"Key": "stage", "Value": "dev"},
                                {"Key": "team", "Value": "serverless"},
                                {"Key": "empty", "Value": ""},
                            ],
                        },
                        {
                            "ResourceARN": "arn:aws:lambda:us-east-1:123497598159:function:my-test-lambda-prod",
                            "Tags": [
                                {"Key": "stage", "Value": "prod"},
                                {"Key": "team", "Value": "serverless"},
                                {"Key": "datacenter", "Value": "eu"},
                                {"Key": "empty", "Value": ""},
                            ],
                        },
                    ]
                }
            ),
            {
                "arn:aws:lambda:us-east-1:123497598159:function:my-test-lambda-dev": [
                    "stage:dev",
                    "team:serverless",
                    "empty",
                ],
                "arn:aws:lambda:us-east-1:123497598159:function:my-test-lambda-prod": [
                    "stage:prod",
                    "team:serverless",
                    "datacenter:eu",
                    "empty",
                ],
            },
        )


if __name__ == "__main__":
    unittest.main()
