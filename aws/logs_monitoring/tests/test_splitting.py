import unittest
from steps.splitting import (
    extract_metric,
    extract_trace_payload,
)


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


class TestLambdaFunctionExtractTracePayload(unittest.TestCase):
    def test_extract_trace_payload_none_no_trace(self):
        message_json = """{
            "key": "value"
        }"""
        self.assertEqual(extract_trace_payload({"message": message_json}), None)

    def test_extract_trace_payload_none_exception(self):
        message_json = """{
            "invalid_json"
        }"""
        self.assertEqual(extract_trace_payload({"message": message_json}), None)

    def test_extract_trace_payload_unrelated_datadog_trace(self):
        message_json = """{"traces":["I am a trace"]}"""
        self.assertEqual(extract_trace_payload({"message": message_json}), None)

    def test_extract_trace_payload_valid_trace(self):
        message_json = """{"traces":[[{"trace_id":1234}]]}"""
        tags_json = """["key0:value", "key1:value1"]"""
        item = {
            "message": '{"traces":[[{"trace_id":1234}]]}',
            "tags": '["key0:value", "key1:value1"]',
        }
        self.assertEqual(
            extract_trace_payload({"message": message_json, "ddtags": tags_json}), item
        )


if __name__ == "__main__":
    unittest.main()
