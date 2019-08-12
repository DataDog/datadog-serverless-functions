import unittest

from lambda_function.lambda_function import DatadogBatcher

class TestBatcher(unittest.TestCase):

    def test_batch(self):
        batcher = DatadogBatcher(max_log_size_bytes=10,max_size_bytes=50,max_size_count=10)
        batches = batcher.batch([])
        self.assertEqual(len(batches), 1)
