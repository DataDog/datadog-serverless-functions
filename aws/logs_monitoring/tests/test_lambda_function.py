import unittest

from lambda_function import batch_trace_payloads

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