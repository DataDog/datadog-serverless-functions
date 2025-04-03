import unittest
import unittest.mock
import os
import json


class TestLambdaFunction(unittest.TestCase):
    @unittest.mock.patch.dict(os.environ, {"DD_API_KEY": "1234"})
    def test_series_batching(self):
        from lambda_function import Stats

        series = []
        for i in range(0, 100000):
            series.append(
                {
                    "metric": f"test_metric-{i}",
                    "points": [
                        ("2021-01-01T00:00:00Z", 1),
                        ("2021-01-01T00:00:01Z", 2),
                        ("2021-01-01T00:00:02Z", 3),
                    ],
                    "type": "count",
                    "tags": ["tag1", "tag2", "tag3"],
                }
            )

        stats = Stats()
        batched_series = stats.batch_series(series)

        batches_length = 0
        for batch in batched_series:
            batch_json = json.dumps(batch).encode("utf-8")
            self.assertLessEqual(len(batch_json), 3200000)
            batches_length += len(batch)

        self.assertEqual(len(series), batches_length)
