import unittest
import json
from steps.enrichment import (
    extract_host_from_cloudtrails,
    extract_host_from_guardduty,
    extract_host_from_route53,
    extract_ddtags_from_message,
)


class TestMergeMessageTags(unittest.TestCase):
    message_tags = '{"ddtags":"service:my_application_service,custom_tag_1:value1"}'
    custom_tags = "custom_tag_2:value2,service:my_custom_service"

    def test_extract_ddtags_from_message_str(self):
        event = {
            "message": self.message_tags,
            "ddtags": self.custom_tags,
            "service": "my_service",
        }

        extract_ddtags_from_message(event)

        self.assertEqual(
            event["ddtags"],
            "custom_tag_2:value2,service:my_application_service,custom_tag_1:value1",
        )
        self.assertEqual(
            event["service"],
            "my_application_service",
        )

    def test_extract_ddtags_from_message_dict(self):
        loaded_message_tags = json.loads(self.message_tags)
        event = {
            "message": loaded_message_tags,
            "ddtags": self.custom_tags,
            "service": "my_service",
        }

        extract_ddtags_from_message(event)

        self.assertEqual(
            event["ddtags"],
            "custom_tag_2:value2,service:my_application_service,custom_tag_1:value1",
        )
        self.assertEqual(
            event["service"],
            "my_application_service",
        )

    def test_extract_ddtags_from_message_service_tag_setting(self):
        loaded_message_tags = json.loads(self.message_tags)
        loaded_message_tags["ddtags"] = ",".join(
            [
                tag
                for tag in loaded_message_tags["ddtags"].split(",")
                if not tag.startswith("service:")
            ]
        )
        event = {
            "message": loaded_message_tags,
            "ddtags": self.custom_tags,
            "service": "my_custom_service",
        }

        extract_ddtags_from_message(event)

        self.assertEqual(
            event["ddtags"],
            "custom_tag_2:value2,service:my_custom_service,custom_tag_1:value1",
        )
        self.assertEqual(
            event["service"],
            "my_custom_service",
        )

    def test_extract_ddtags_from_message_multiple_service_tag_values(self):
        custom_tags = self.custom_tags + ",service:my_custom_service_2"
        event = {"message": self.message_tags, "ddtags": custom_tags}

        extract_ddtags_from_message(event)

        self.assertEqual(
            event["ddtags"],
            "custom_tag_2:value2,service:my_application_service,custom_tag_1:value1",
        )
        self.assertEqual(
            event["service"],
            "my_application_service",
        )

    def test_extract_ddtags_from_message_multiple_values_tag(self):
        loaded_message_tags = json.loads(self.message_tags)
        loaded_message_tags["ddtags"] += ",custom_tag_3:value4"
        custom_tags = self.custom_tags + ",custom_tag_3:value3"
        event = {"message": loaded_message_tags, "ddtags": custom_tags}

        extract_ddtags_from_message(event)

        self.assertEqual(
            event["ddtags"],
            "custom_tag_2:value2,custom_tag_3:value3,service:my_application_service,custom_tag_1:value1,custom_tag_3:value4",
        )
        self.assertEqual(
            event["service"],
            "my_application_service",
        )


class TestExtractHostFromLogEvents(unittest.TestCase):
    def test_parse_source_cloudtrail(self):
        event = {
            "ddsource": "cloudtrail",
            "message": {
                "userIdentity": {
                    "arn": "arn:aws:sts::601427279990:assumed-role/gke-90725aa7-management/i-99999999"
                }
            },
        }
        extract_host_from_cloudtrails(event)
        self.assertEqual(event["host"], "i-99999999")

    def test_parse_source_guardduty(self):
        event = {
            "ddsource": "guardduty",
            "detail": {"resource": {"instanceDetails": {"instanceId": "i-99999999"}}},
        }
        extract_host_from_guardduty(event)
        self.assertEqual(event["host"], "i-99999999")

    def test_parse_source_route53(self):
        event = {
            "ddsource": "route53",
            "message": {"srcids": {"instance": "i-99999999"}},
        }
        extract_host_from_route53(event)
        self.assertEqual(event["host"], "i-99999999")


if __name__ == "__main__":
    unittest.main()
