import unittest

from enhanced_metrics import sanitize_aws_tag_string


class TestEnhancedMetrics(unittest.TestCase):
    def test_sanitize_tag_string(self):
        self.assertEqual(sanitize_aws_tag_string("serverless"), "serverless")
        self.assertEqual(sanitize_aws_tag_string("ser:ver_less"), "ser_ver_less")
        self.assertEqual(sanitize_aws_tag_string("s-erv:erl_ess"), "s_erv_erl_ess")

    def test_parse_logs_metrics(self):
        pass


if __name__ == "__main__":
    unittest.main()
