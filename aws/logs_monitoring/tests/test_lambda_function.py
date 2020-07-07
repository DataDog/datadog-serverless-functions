from mock import MagicMock, patch
import os
import sys
import unittest

sys.modules["datadog_lambda.wrapper"] = MagicMock()
sys.modules["datadog_lambda.metric"] = MagicMock()
sys.modules["datadog"] = MagicMock()
sys.modules["requests"] = MagicMock()

env_patch = patch.dict(
    os.environ, {"DD_API_KEY": "11111111111111111111111111111111"}
)
env_patch.start()
from lambda_function import batch_trace_payloads

env_patch.stop()


class TestBatchTracePayloads(unittest.TestCase):
    def test_batch_trace_payloads(self):
        trace_payloads = [
            {"tags": "tag1:value", "message": '{"traces":[[{"trace_id":"1"}]]}\n',},
            {
                "tags": "tag1:value",
                "message": '{"traces":[[{"trace_id":"2"}, {"trace_id":"3"}]]}\n',
            },
            {
                "tags": "tag2:value",
                "message": '{"traces":[[{"trace_id":"4"}], [{"trace_id":"5"}]]}\n',
            },
        ]

        batched_payloads = batch_trace_payloads(trace_payloads)

        expected_batched_payloads = [
            {
                "tags": "tag1:value",
                "message": '{"traces": [[{"trace_id": "1"}], [{"trace_id": "2"}, {"trace_id": "3"}]]}',
            },
            {
                "tags": "tag2:value",
                "message": '{"traces": [[{"trace_id": "4"}], [{"trace_id": "5"}]]}',
            },
        ]

        self.assertEqual(batched_payloads, expected_batched_payloads)


if __name__ == "__main__":
    unittest.main()
