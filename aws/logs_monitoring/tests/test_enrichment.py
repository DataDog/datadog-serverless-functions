import json
import os
import sys
import unittest
from importlib import reload
from unittest.mock import MagicMock, patch

from approvaltests.approvals import verify_as_json

from caching.cache_layer import CacheLayer
from steps.enrichment import (
    add_metadata_to_lambda_log,
    extract_ddtags_from_message,
    extract_host_from_cloudtrails,
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

    def test_extract_ddtags_from_message_service_only_in_extracted_ddtags_values(self):
        loaded_message_tags = {"ddtags": "key:my-service-repo"}
        event = {"message": loaded_message_tags, "ddtags": self.custom_tags}

        extract_ddtags_from_message(event)

        self.assertEqual(
            event["ddtags"],
            "custom_tag_2:value2,service:my_custom_service,key:my-service-repo",
        )
        self.assertNotIn(
            "service",
            event,
        )

    def test_extract_ddtags_handles_empty_spaces(self):
        loaded_message_tags = {
            "ddtags": "key:my-service-repo,  service:  my_custom_service  "
        }
        event = {"message": loaded_message_tags, "ddtags": "custom_tag_2:value2,"}

        extract_ddtags_from_message(event)

        self.assertEqual(
            event["ddtags"],
            "custom_tag_2:value2,key:my-service-repo,service:my_custom_service",
        )
        self.assertEqual(
            event["service"],
            "my_custom_service",
        )


class TestExtractHostFromLogEvents(unittest.TestCase):
    def test_parse_source_cloudtrail(self):
        event = {
            "ddsource": "cloudtrail",
            "message": {
                "userIdentity": {
                    "arn": (
                        "arn:aws:sts::601427279990:assumed-role/gke-90725aa7-management/i-99999999"
                    )
                }
            },
        }
        extract_host_from_cloudtrails(event)
        self.assertEqual(event["host"], "i-99999999")


class TestLambdaMetadataEnrichment(unittest.TestCase):
    def test_empty_event(self):
        cache_layer = CacheLayer("")
        event = {}
        add_metadata_to_lambda_log(event, cache_layer)

        self.assertEqual(event, {})

    def test_non_lambda_event(self):
        cache_layer = CacheLayer("")
        event = {"lambda": {}}
        add_metadata_to_lambda_log(event, cache_layer)

        verify_as_json(event)

    def test_lambda_event_bad_arn(self):
        cache_layer = CacheLayer("")
        event = {"lambda": {"arn": "bad_arn"}}
        add_metadata_to_lambda_log(event, cache_layer)
        verify_as_json(event)

    @patch.dict(os.environ, {"DD_FETCH_LAMBDA_TAGS": "false"})
    def test_lambda_event_wo_service(self):
        reload(sys.modules["settings"])

        cache_layer = CacheLayer("")
        event = {
            "lambda": {
                "arn": "arn:aws:lambda:us-east-1:123456789012:function:my-function"
            }
        }
        add_metadata_to_lambda_log(event, cache_layer)
        verify_as_json(event)

    @patch.dict(os.environ, {"DD_FETCH_LAMBDA_TAGS": "true"})
    def test_lambda_event_w_custom_tags_wo_service(self):
        reload(sys.modules["settings"])

        cache_layer = CacheLayer("")
        cache_layer._lambda_cache.get = MagicMock(
            return_value=["service:customtags_service"]
        )
        event = {
            "lambda": {
                "arn": "arn:aws:lambda:us-east-1:123456789012:function:my-function"
            }
        }
        add_metadata_to_lambda_log(event, cache_layer)
        verify_as_json(event)

    @patch.dict(os.environ, {"DD_FETCH_LAMBDA_TAGS": "true"})
    def test_lambda_event_w_custom_tags_w_service(self):
        reload(sys.modules["settings"])

        cache_layer = CacheLayer("")
        cache_layer._lambda_cache.get = MagicMock(
            return_value=["service:customtags_service"]
        )
        event = {
            "lambda": {
                "arn": "arn:aws:lambda:us-east-1:123456789012:function:my-function"
            },
            "service": "my_service",
        }
        add_metadata_to_lambda_log(event, cache_layer)
        verify_as_json(event)

    @patch.dict(os.environ, {"DD_FETCH_LAMBDA_TAGS": "false"})
    def test_lambda_event_w_service(self):
        reload(sys.modules["settings"])

        cache_layer = CacheLayer("")
        event = {
            "lambda": {
                "arn": "arn:aws:lambda:us-east-1:123456789012:function:my-function"
            },
            "service": "my_service",
        }
        add_metadata_to_lambda_log(event, cache_layer)
        verify_as_json(event)

    @patch.dict(os.environ, {"DD_FETCH_LAMBDA_TAGS": "false"})
    def test_lambda_event_w_service_and_ddtags(self):
        reload(sys.modules["settings"])

        cache_layer = CacheLayer("")
        event = {
            "lambda": {
                "arn": "arn:aws:lambda:us-east-1:123456789012:function:my-function"
            },
            "service": "my_service",
            "ddtags": "service:ddtags_service",
        }
        add_metadata_to_lambda_log(event, cache_layer)
        verify_as_json(event)

    @patch.dict(os.environ, {"DD_FETCH_LAMBDA_TAGS": "true"})
    def test_lambda_event_w_custom_tags_env(self):
        reload(sys.modules["settings"])

        cache_layer = CacheLayer("")
        cache_layer._lambda_cache.get = MagicMock(return_value=["env:customtags_env"])
        event = {
            "lambda": {
                "arn": "arn:aws:lambda:us-east-1:123456789012:function:my-function"
            },
            "ddtags": "env:none",
        }
        add_metadata_to_lambda_log(event, cache_layer)
        verify_as_json(event)


if __name__ == "__main__":
    unittest.main()
