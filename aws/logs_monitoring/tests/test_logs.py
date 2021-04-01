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

    def test_lambda_log_filtering(self):
        test_logs = [
            r"{""id"": ""36066792698255887077657542242395828641987352994149040130"", ""timestamp"": 1617290919078, ""message"": ""REPORT RequestId: 5dc261fc-3372-46bf-ac1c-1c973f14b519\tDuration: 1.19 ms\tBilled Duration: 2 ms\tMemory Size: 128 MB\tMax Memory Used: 51 MB\t"", ""aws"": {""awslogs"": {""logGroup"": ""/aws/lambda/nick-hello-world"", ""logStream"": ""2021/04/01/[$LATEST]12ce3b729d5848228bf22770e609a5e7"", ""owner"": ""601427279990""}, ""function_version"": ""$LATEST"", ""invoked_function_arn"": ""arn:aws:lambda:sa-east-1:601427279990:function:NickTestForwarder""}, ""lambda"": {""arn"": ""arn:aws:lambda:sa-east-1:601427279990:function:nick-hello-world""}, ""ddsourcecategory"": ""aws"", ""ddtags"": ""forwardername:nicktestforwarder,forwarder_memorysize:1024,forwarder_version:3.30.0,env:none,account_id:601427279990,aws_account:601427279990,functionname:nick-hello-world,region:sa-east-1,service:nick-hello-world"", ""ddsource"": ""lambda"", ""service"": ""nick-hello-world"", ""host"": ""arn:aws:lambda:sa-east-1:601427279990:function:nick-hello-world""}"
        ]

        filtered_logs = filter_logs(
            test_logs, exclude_pattern=r"(START|END|REPORT)/s"
        )

        self.assert_equal(filtered_logs, [])


