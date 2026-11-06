import unittest

from customized_log_group import (
    get_lambda_function_name_from_logstream_name,
    get_lambda_function_version_from_logstream_name,
    is_lambda_customized_log_group,
)


class TestCustomizedLogGroup(unittest.TestCase):
    def test_is_lambda_customized_log_group(self):
        # default log group for lambda
        default_log_stream_name = "2023/11/04/[$LATEST]4426346c2cdf4c54a74d3bd2b929fc44"
        self.assertEqual(is_lambda_customized_log_group(default_log_stream_name), False)
        # customized log group for lambda LATEST
        customized_log_stream_name_latest = "2023/11/06/test-customized-log-group1[$LATEST]13e304cba4b9446eb7ef082a00038990"
        self.assertEqual(
            is_lambda_customized_log_group(customized_log_stream_name_latest), True
        )
        # customized log group for lambda
        customized_log_stream_name_version = "2023/11/06/test-customized-log-group1[version2023_11]13e304cba4b9446eb7ef082a00038990"
        self.assertEqual(
            is_lambda_customized_log_group(customized_log_stream_name_version), True
        )
        # stepfunction log stream
        stepfunction_log_stream_name = (
            "states/rc-auto-statemachine-staging/2023-11-14-20-05/507c6089"
        )
        self.assertEqual(
            is_lambda_customized_log_group(stepfunction_log_stream_name), False
        )

    def get_lambda_function_name_from_logstream_name(self):
        # default log group for lambda
        default_log_stream_name = "2023/11/04/[$LATEST]4426346c2cdf4c54a74d3bd2b929fc44"
        self.assertEqual(
            get_lambda_function_name_from_logstream_name(default_log_stream_name), None
        )
        # customized log group for lambda LATEST
        customized_log_stream_name_latest = "2023/11/06/test-customized-log-group1[$LATEST]13e304cba4b9446eb7ef082a00038990"
        self.assertEqual(
            get_lambda_function_name_from_logstream_name(
                customized_log_stream_name_latest
            ),
            "test-customized-log-group1",
        )
        # customized log group for lambda
        customized_log_stream_name_version = "2023/11/06/test-customized-log-group1[version2023_11]13e304cba4b9446eb7ef082a00038990"
        self.assertEqual(
            get_lambda_function_name_from_logstream_name(
                customized_log_stream_name_version
            ),
            "test-customized-log-group1",
        )
        # stepfunction log stream
        stepfunction_log_stream_name = (
            "states/rc-auto-statemachine-staging/2023-11-14-20-05/507c6089"
        )
        self.assertEqual(
            get_lambda_function_name_from_logstream_name(stepfunction_log_stream_name),
            None,
        )

    def test_get_lambda_function_version_from_logstream_name(self):
        for log_stream_name, expected_version in [
            (
                "2023/11/06/test-customized-log-group1[$LATEST]13e304cba4b9446eb7ef082a00038990",
                "$LATEST",
            ),
            (
                "2026/10/14/my-example-function[51]4ba11538c2434a5c94732afdb6eda1e0",
                "51",
            ),
            (
                "2023/11/06/test-customized-log-group1[Version2023_11]13e304cba4b9446eb7ef082a00038990",
                "Version2023_11",
            ),
        ]:
            with self.subTest(log_stream_name=log_stream_name):
                self.assertEqual(
                    get_lambda_function_version_from_logstream_name(log_stream_name),
                    expected_version,
                )
