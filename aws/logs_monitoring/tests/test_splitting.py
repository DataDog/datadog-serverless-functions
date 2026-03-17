import unittest
from steps.splitting import (
    extract_metric,
    is_trace,
)


class TestExtractMetric(unittest.TestCase):
    def test_empty_parsed(self):
        self.assertEqual(extract_metric({}, {}), None)

    def test_missing_keys(self):
        self.assertEqual(extract_metric({"e": 0, "v": 1, "m": "foo"}, {}), None)

    def test_tags_instance(self):
        self.assertEqual(
            extract_metric({"e": 0, "v": 1, "m": "foo", "t": 666}, {}), None
        )

    def test_value_not_numeric(self):
        self.assertEqual(
            extract_metric({"e": 0, "v": None, "m": "foo", "t": []}, {}), None
        )

    def test_value_instance_int(self):
        event = {"ddtags": "env:test"}
        parsed = {"e": 0, "v": 1, "m": "foo", "t": []}
        result = extract_metric(parsed, event)
        self.assertIsNotNone(result)
        self.assertIn("env:test", result["t"])

    def test_value_instance_float(self):
        event = {"ddtags": "env:test"}
        parsed = {"e": 0, "v": 1.1, "m": "foo", "t": []}
        result = extract_metric(parsed, event)
        self.assertIsNotNone(result)
        self.assertIn("env:test", result["t"])


class TestIsTrace(unittest.TestCase):
    def test_no_traces_key(self):
        self.assertFalse(is_trace({"key": "value"}))

    def test_invalid_json_type(self):
        self.assertFalse(is_trace("not a dict"))

    def test_unrelated_traces_array(self):
        self.assertFalse(is_trace({"traces": ["I am a trace"]}))

    def test_valid_trace(self):
        self.assertTrue(is_trace({"traces": [[{"trace_id": 1234}]]}))

    def test_empty_traces(self):
        self.assertFalse(is_trace({"traces": []}))

    def test_traces_not_list(self):
        self.assertFalse(is_trace({"traces": "not a list"}))


if __name__ == "__main__":
    unittest.main()
