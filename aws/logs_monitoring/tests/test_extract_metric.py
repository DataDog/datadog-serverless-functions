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
        "DD_ADDITIONAL_TARGET_LAMBDAS": "ironmaiden,megadeth",
    },
)
env_patch.start()
from lambda_function import extract_metric

env_patch.stop()


class TestExtractMetric(unittest.TestCase):
    def test_empty_event(self):
        self.assertEqual(extract_metric({}), None)

    def test_missing_keys(self):
        self.assertEqual(extract_metric({"e": 0, "v": 1, "m": "foo"}), None)

    def test_tags_instance(self):
        self.assertEqual(extract_metric({"e": 0, "v": 1, "m": "foo", "t": 666}), None)

    def test_value_instance(self):
        self.assertEqual(extract_metric({"e": 0, "v": 1.1, "m": "foo", "t": []}), None)

    def test_value_instance_float(self):
        self.assertEqual(extract_metric({"e": 0, "v": None, "m": "foo", "t": []}), None)


if __name__ == "__main__":
    unittest.main()
