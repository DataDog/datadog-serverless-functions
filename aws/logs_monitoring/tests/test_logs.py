import unittest
from unittest.mock import patch

import settings
class TestFilterLogs(unittest.TestCase):
    example_logs = [
        "START RequestId: ...",
        "This is not a REPORT log",
        "END RequestId: ...",
        "REPORT RequestId: ...",
    ]

    def test_http_filtering(self):
        http_logs = [
            "This is a 500",
            "This is a 200",
        ]

        with patch.multiple(settings, INCLUDE_AT_MATCH=r"\b[4|5][0-9][0-9]\b"):
            from logs import filter_logs

            filtered_logs = filter_logs(http_logs)

        self.assertEqual(
            filtered_logs,
            [
                "This is a 500",
            ],
        )

    def test_include_at_match(self):
        with patch.multiple(settings, INCLUDE_AT_MATCH=r"^(START|END)"):
            from logs import filter_logs

            filtered_logs = filter_logs(self.example_logs)

        self.assertEqual(
            filtered_logs,
            [
                "START RequestId: ...",
                "END RequestId: ...",
            ],
        )

    def test_exclude_at_match(self):
        with patch.multiple(settings, EXCLUDE_AT_MATCH=r"^(START|END)"):
            from logs import filter_logs

            filtered_logs = filter_logs(self.example_logs)

        self.assertEqual(
            filtered_logs,
            [
                "This is not a REPORT log",
                "REPORT RequestId: ...",
            ],
        )

    def test_exclude_overrides_include(self):
        with patch.multiple(
            settings, EXCLUDE_AT_MATCH=r"^END", INCLUDE_AT_MATCH=r"^(START|END)"
        ):
            from logs import filter_logs

            filtered_logs = filter_logs(self.example_logs)

        self.assertEqual(
            filtered_logs,
            [
                "START RequestId: ...",
            ],
        )

    def test_no_filtering_rules(self):
        from logs import filter_logs

        filtered_logs = filter_logs(self.example_logs)
        self.assertEqual(filtered_logs, self.example_logs)
