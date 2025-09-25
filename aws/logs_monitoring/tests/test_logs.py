import os
import sys
import unittest
import unittest.mock
from importlib import reload

from logs.datadog_batcher import DatadogBatcher
from logs.datadog_matcher import DatadogMatcher
from logs.datadog_scrubber import DatadogScrubber


class TestScrubLogs(unittest.TestCase):
    @unittest.mock.patch.dict(os.environ, {"REDACT_IP": "true", "REDACT_EMAIL": "true"})
    def test_scrubbing_rule_config(self):
        reload(sys.modules["settings"])
        from settings import SCRUBBING_RULE_CONFIGS

        scrubber = DatadogScrubber(SCRUBBING_RULE_CONFIGS)
        payload = scrubber.scrub(
            "ip_address is 127.0.0.1, email is abc.edf@example.com"
        )
        self.assertEqual(
            payload, "ip_address is xxx.xxx.xxx.xxx, email is xxxxx@xxxxx.com"
        )
        os.environ.pop("REDACT_IP", None)
        os.environ.pop("REDACT_EMAIL", None)

    @unittest.mock.patch.dict(
        os.environ,
        {
            "DD_SCRUBBING_RULE": "[^\u0001-\u007f]+",
            "DD_SCRUBBING_RULE_REPLACEMENT": "xxxxx",
        },
    )
    def test_non_ascii(self):
        reload(sys.modules["settings"])
        from settings import SCRUBBING_RULE_CONFIGS

        scrubber = DatadogScrubber(SCRUBBING_RULE_CONFIGS)
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
        filtered_logs = filter_logs(
            DatadogMatcher(include_pattern="^(START|END)"), self.example_logs
        )

        self.assertEqual(
            filtered_logs,
            [
                "START RequestId: ...",
                "END RequestId: ...",
            ],
        )

    def test_exclude_at_match(self):
        filtered_logs = filter_logs(
            DatadogMatcher(exclude_pattern="^(START|END)"), self.example_logs
        )

        self.assertEqual(
            filtered_logs,
            [
                "This is not a REPORT log",
                "REPORT RequestId: ...",
            ],
        )

    def test_exclude_overrides_include(self):
        filtered_logs = filter_logs(
            DatadogMatcher(include_pattern="^(START|END)", exclude_pattern="^END"),
            self.example_logs,
        )

        self.assertEqual(
            filtered_logs,
            [
                "START RequestId: ...",
            ],
        )

    def test_no_filtering_rules(self):
        filtered_logs = filter_logs(DatadogMatcher(), self.example_logs)
        self.assertEqual(filtered_logs, self.example_logs)


def filter_logs(matcher, logs):
    filtered = []

    for log in logs:
        if matcher.match(log):
            filtered.append(log)

    return filtered


if __name__ == "__main__":
    unittest.main()
