import unittest
from unittest.mock import MagicMock, patch

import telemetry


def make_context(function_name="my-forwarder", memory_limit_in_mb=128):
    context = MagicMock()
    context.function_name = function_name
    context.memory_limit_in_mb = memory_limit_in_mb
    return context


class TestSetForwarderTelemetryTags(unittest.TestCase):
    def setUp(self):
        telemetry.DD_FORWARDER_TELEMETRY_TAGS = []

    @patch("telemetry.DD_TAGS", "")
    def test_base_tags_without_dd_tags(self):
        context = make_context()
        telemetry.set_forwarder_telemetry_tags(context, "cloudwatch-logs")
        tags = telemetry.DD_FORWARDER_TELEMETRY_TAGS
        self.assertIn("forwardername:my-forwarder", tags)
        self.assertIn("forwarder_memorysize:128", tags)
        self.assertIn("event_type:cloudwatch-logs", tags)
        self.assertEqual(len(tags), 4)

    @patch("telemetry.DD_TAGS", "env:prod,account:123456789")
    def test_dd_tags_appended(self):
        context = make_context()
        telemetry.set_forwarder_telemetry_tags(context, "s3")
        tags = telemetry.DD_FORWARDER_TELEMETRY_TAGS
        self.assertIn("env:prod", tags)
        self.assertIn("account:123456789", tags)
        self.assertEqual(len(tags), 6)

    @patch("telemetry.DD_TAGS", "env:staging")
    def test_single_dd_tag_appended(self):
        context = make_context()
        telemetry.set_forwarder_telemetry_tags(context, "kinesis")
        tags = telemetry.DD_FORWARDER_TELEMETRY_TAGS
        self.assertIn("env:staging", tags)
        self.assertEqual(len(tags), 5)

    @patch("telemetry.DD_TAGS", "env:prod, account:123")
    def test_dd_tags_whitespace_stripped(self):
        context = make_context()
        telemetry.set_forwarder_telemetry_tags(context, "s3")
        tags = telemetry.DD_FORWARDER_TELEMETRY_TAGS
        self.assertIn("account:123", tags)
        self.assertNotIn(" account:123", tags)

    @patch("telemetry.DD_TAGS", "env:prod,,account:123")
    def test_empty_tag_segments_ignored(self):
        context = make_context()
        telemetry.set_forwarder_telemetry_tags(context, "s3")
        tags = telemetry.DD_FORWARDER_TELEMETRY_TAGS
        self.assertIn("env:prod", tags)
        self.assertIn("account:123", tags)
        self.assertNotIn("", tags)

    @patch("telemetry.DD_TAGS", "env:prod,account:123456789")
    def test_function_name_lowercased(self):
        context = make_context(function_name="My-Forwarder")
        telemetry.set_forwarder_telemetry_tags(context, "s3")
        tags = telemetry.DD_FORWARDER_TELEMETRY_TAGS
        self.assertIn("forwardername:my-forwarder", tags)


if __name__ == "__main__":
    unittest.main()
