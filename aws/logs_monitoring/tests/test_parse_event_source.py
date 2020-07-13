from mock import MagicMock, patch
import os
import sys
import unittest

sys.modules["trace_forwarder.connection"] = MagicMock()
sys.modules["datadog_lambda.wrapper"] = MagicMock()
sys.modules["datadog_lambda.metric"] = MagicMock()
sys.modules["datadog"] = MagicMock()
sys.modules["requests"] = MagicMock()

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
                {},
                "cloud-trail/AWSLogs/123456779121/CloudTrail/us-west-3/2018/01/07/123456779121_CloudTrail_eu-west-3_20180707T1735Z_abcdefghi0MCRL2O.json.gz",
            ),
            "cloudtrail",
        )

    def test_cloudtrail_event_with_service_substrings(self):
        # Assert that source "cloudtrail" is parsed even though substrings "waf" and "sns" are present in the key
        self.assertEqual(
            parse_event_source(
                {},
                "cloud-trail/AWSLogs/123456779121/CloudTrail/us-west-3/2018/01/07/123456779121_CloudTrail_eu-west-3_20180707T1735Z_xywafKsnsXMBrdsMCRL2O.json.gz",
            ),
            "cloudtrail",
        )

    def test_rds_event(self):
        self.assertEqual(parse_event_source({}, "/aws/rds/my-rds-resource"), "rds")

    def test_cloudwatch_source_if_none_found(self):
        self.assertEqual(parse_event_source({"awslogs": "logs"}, ""), "cloudwatch")

    def test_s3_source_if_none_found(self):
        self.assertEqual(parse_event_source({"Records": ["logs-from-s3"]}, ""), "s3")


if __name__ == "__main__":
    unittest.main()
