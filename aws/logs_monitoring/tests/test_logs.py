import unittest

from logs import filter_logs

# \"awsRegion\":\"us-east-1\"

class TestFilterLogs(unittest.TestCase):
    example_logs = [
        "START RequestId: ...",
        "This is not a REPORT log",
        "END RequestId: ...",
        "REPORT RequestId: ...",
    ]

    def test_json_filtering(self):
        json_logs = [r"\"awsRegion\":\"us-east-1\""]

        filtered_logs = filter_logs(json_logs, include_pattern=r'\\"awsRegion\\":\\"us-east-1\\"'

        self.assertEqual(
            filtered_logs,
            [
                r"\"awsRegion\":\"us-east-1\"",
            ],
        )

    def test_http_filtering(self):
        http_logs = [
            "This is a 500",
            "This is a 200",
        ]

        filtered_logs = filter_logs(http_logs, include_pattern=r"\b[4|5][0-9][0-9]\b")

        self.assertEqual(
            filtered_logs,
            [
                "This is a 500",
            ],
        )

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
