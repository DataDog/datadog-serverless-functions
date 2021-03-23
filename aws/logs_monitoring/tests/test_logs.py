import unittest

from logs import filter_logs


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
