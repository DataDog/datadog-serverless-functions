import unittest
import os

from logs.datadog_scrubber import DatadogScrubber
from logs.datadog_batcher import DatadogBatcher
from logs.helpers import filter_logs
from settings import ScrubbingRuleConfig, SCRUBBING_RULE_CONFIGS, get_env_var


class TestScrubLogs(unittest.TestCase):
    def test_scrubbing_rule_config(self):
        os.environ["REDACT_IP"] = ""
        os.environ["REDACT_EMAIL"] = ""
        scrubber = DatadogScrubber(SCRUBBING_RULE_CONFIGS)
        payload = scrubber.scrub(
            "ip_address is 127.0.0.1, email is abc.edf@example.com"
        )
        self.assertEqual(
            payload, "ip_address is xxx.xxx.xxx.xxx, email is xxxxx@xxxxx.com"
        )
        os.environ.pop("REDACT_IP", None)
        os.environ.pop("REDACT_EMAIL", None)

    def test_non_ascii(self):
        os.environ["DD_SCRUBBING_RULE"] = "[^\u0001-\u007F]+"
        scrubber = DatadogScrubber(
            [
                ScrubbingRuleConfig(
                    "DD_SCRUBBING_RULE",
                    get_env_var("DD_SCRUBBING_RULE", default=None),
                    get_env_var("DD_SCRUBBING_RULE_REPLACEMENT", default="xxxxx"),
                )
            ]
        )
        payload = scrubber.scrub("abcdef日本語efgかきくけこhij")
        self.assertEqual(payload, "abcdefxxxxxefgxxxxxhij")
        os.environ.pop("DD_SCRUBBING_RULE", None)


class TestDatadogBatcher(unittest.TestCase):
    def test_batch(self):
        batcher = DatadogBatcher(256, 512, 1)
        logs = [
            "a" * 100,
            "b" * 100,
            "c" * 100,
            "d" * 100,
        ]
        batches = list(batcher.batch(logs))
        self.assertEqual(len(batches), 4)

        batcher = DatadogBatcher(256, 512, 2)
        batches = list(batcher.batch(logs))
        self.assertEqual(len(batches), 2)


class TestFilterLogs(unittest.TestCase):
    example_logs = [
        "START RequestId: ...",
        "This is not a REPORT log",
        "END RequestId: ...",
        "REPORT RequestId: ...",
    ]

    def test_include_at_match(self):
        filtered_logs = filter_logs(self.example_logs, include_pattern=r"^(START|END)")

        self.assertEqual(
            filtered_logs,
            [
                "START RequestId: ...",
                "END RequestId: ...",
            ],
        )

    def test_exclude_at_match(self):
        filtered_logs = filter_logs(self.example_logs, exclude_pattern=r"^(START|END)")

        self.assertEqual(
            filtered_logs,
            [
                "This is not a REPORT log",
                "REPORT RequestId: ...",
            ],
        )

    def test_exclude_overrides_include(self):
        filtered_logs = filter_logs(
            self.example_logs, include_pattern=r"^(START|END)", exclude_pattern=r"^END"
        )

        self.assertEqual(
            filtered_logs,
            [
                "START RequestId: ...",
            ],
        )

    def test_no_filtering_rules(self):
        filtered_logs = filter_logs(self.example_logs)
        self.assertEqual(filtered_logs, self.example_logs)


if __name__ == "__main__":
    unittest.main()
