import unittest
import os
from unittest.mock import patch, MagicMock
from lambda_function import Stats
from urllib.error import HTTPError
from io import BytesIO

env_patch = patch.dict(
    os.environ,
    {
        "DD_API_KEY": "11111111111111111111111111111111",
    },
)
env_patch.start()
from lambda_function import extract_json_objects

env_patch.stop()

full_message_example = """
{
        "engine": "Aurora",
        "instanceID": "instanceid",
        "instanceResourceID": "db-QPCTQVLJ4WIQPCTQVLJ4WIJ4WI",
        "timestamp": "2016-01-01T01:01:01Z",
        "version": 1.00,
        "uptime": "10 days, 1:53:04",
        "numVCPUs": 2,
        "cpuUtilization": {
            "guest": 0.00,
            "irq": 0.00,
            "system": 0.88,
            "wait": 0.54,
            "idle": 97.57,
            "user": 0.68,
            "total": 1.56,
            "steal": 0.07,
            "nice": 0.25
        },
        "loadAverageMinute": {
            "fifteen": 0.14,
            "five": 0.17,
            "one": 0.18
        },
        "memory": {
            "writeback": 0,
            "hugePagesFree": 0,
            "hugePagesRsvd": 0,
            "hugePagesSurp": 0,
            "cached": 11742648,
            "hugePagesSize": 2048,
            "free": 259016,
            "hugePagesTotal": 0,
            "inactive": 1817176,
            "pageTables": 25808,
            "dirty": 660,
            "mapped": 8087612,
            "active": 13016084,
            "total": 15670012,
            "slab": 437916,
            "buffers": 272136
        },
        "tasks": {
            "sleeping": 223,
            "zombie": 0,
            "running": 1,
            "stopped": 0,
            "total": 224,
            "blocked": 0
        },
        "swap": {
            "cached": 0,
            "total": 0,
            "free": 0
        },
        "network": [{
            "interface": "eth0",
            "rx": 217.57,
            "tx": 2319.67
        }],
        "diskIO": [{
            "writeKbPS": 2301.6,
            "readIOsPS": 0.03,
            "await": 4.04,
            "readKbPS": 0.13,
            "rrqmPS": 0,
            "util": 0.2,
            "avgQueueLen": 0.11,
            "tps": 28.27,
            "readKb": 4,
            "device": "rdsdev",
            "writeKb": 69048,
            "avgReqSz": 162.86,
            "wrqmPS": 0,
            "writeIOsPS": 28.23
        },{
            "writeKbPS": 177.2,
            "readIOsPS": 0.03,
            "await": 1.52,
            "readKbPS": 0.13,
            "rrqmPS": 0,
            "util": 0.35,
            "avgQueueLen": 0.03,
            "tps": 25.67,
            "readKb": 4,
            "device": "filesystem",
            "writeKb": 5316,
            "avgReqSz": 13.82,
            "wrqmPS": 8.3,
            "writeIOsPS": 25.63
        }],
        "fileSys": [{
            "used": 7006720,
            "name": "rdsfilesys",
            "usedFiles": 2650,
            "usedFilePercent": 0.13,
            "maxFiles": 1966080,
            "mountPoint": "/rdsdbdata",
            "total": 30828540,
            "usedPercent": 22.73
        }],
        "physicalDeviceIO": [{
            "writeKbPS": 583.6,
            "readIOsPS": 0,
            "await": 2.32,
            "readKbPS": 0,
            "rrqmPS": 0,
            "util": 0.09,
            "avgQueueLen": 0.02,
            "tps": 9.9,
            "readKb": 0,
            "device": "nvme3n1",
            "writeKb": 17508,
            "avgReqSz": 117.9,
            "wrqmPS": 4.97,
            "writeIOsPS": 9.9
        }, {
            "writeKbPS": 575.07,
            "readIOsPS": 0,
            "await": 3.04,
            "readKbPS": 0,
            "rrqmPS": 0,
            "util": 0.09,
            "avgQueueLen": 0.03,
            "tps": 9.47,
            "readKb": 0,
            "device": "nvme1n1",
            "writeKb": 17252,
            "avgReqSz": 121.49,
            "wrqmPS": 3.97,
            "writeIOsPS": 9.47
        }, {
            "writeKbPS": 567.33,
            "readIOsPS": 0.03,
            "await": 2.69,
            "readKbPS": 0.13,
            "rrqmPS": 0,
            "util": 0.09,
            "avgQueueLen": 0.02,
            "tps": 9.47,
            "readKb": 4,
            "device": "nvme5n1",
            "writeKb": 17020,
            "avgReqSz": 119.89,
            "wrqmPS": 3.07,
            "writeIOsPS": 9.43
        }, {
            "writeKbPS": 576.53,
            "readIOsPS": 0,
            "await": 2.64,
            "readKbPS": 0,
            "rrqmPS": 0,
            "util": 0.09,
            "avgQueueLen": 0.02,
            "tps": 9.8,
            "readKb": 0,
            "device": "nvme2n1",
            "writeKb": 17296,
            "avgReqSz": 117.66,
            "wrqmPS": 3.9,
            "writeIOsPS": 9.8
        }],
        "processList": [{
            "vss": 11170084,
            "name": "aurora",
            "tgid": 8455,
            "parentID": 1,
            "memoryUsedPc": 66.93,
            "cpuUsedPc": 0.00,
            "id": 8455,
            "rss": 10487696
        }, {
            "vss": 11170084,
            "name": "aurora",
            "tgid": 8455,
            "parentID": 1,
            "memoryUsedPc": 66.93,
            "cpuUsedPc": 0.82,
            "id": 8782,
            "rss": 10487696
        }, {
            "vss": 11170084,
            "name": "aurora",
            "tgid": 8455,
            "parentID": 1,
            "memoryUsedPc": 66.93,
            "cpuUsedPc": 0.05,
            "id": 8784,
            "rss": 10487696
        }, {
            "vss": 647304,
            "name": "OS processes",
            "tgid": 0,
            "parentID": 0,
            "memoryUsedPc": 0.18,
            "cpuUsedPc": 0.02,
            "id": 0,
            "rss": 22600
        }, {
            "vss": 3244792,
            "name": "RDS processes",
            "tgid": 0,
            "parentID": 0,
            "memoryUsedPc": 2.80,
            "cpuUsedPc": 0.78,
            "id": 0,
            "rss": 441652
        }]
    }
""".replace(" ", "").replace("\n", "")


class TestRDSEnhancedMetrics(unittest.TestCase):
    def test_extract_json_objects(self):
        # Basic JSON
        input_string = """{"a":2}{"b":3}"""
        output_list = ['{"a":2}', '{"b":3}']
        self.assertEqual(extract_json_objects(input_string), output_list)

        # JSON including brackets
        input_string = """{"a":2}{"b":"{}{}"}"""
        output_list = ['{"a":2}', '{"b":"{}{}"}']
        self.assertEqual(extract_json_objects(input_string), output_list)

        # Highly nested JSON
        input_string = """{"a":2}{"b":{"c":{"d":{"e":{"f":2}}}}}"""
        output_list = ['{"a":2}', '{"b":{"c":{"d":{"e":{"f":2}}}}}']
        self.assertEqual(extract_json_objects(input_string), output_list)

        # JSON with AWS example
        input_string = full_message_example
        output_list = [input_string]
        self.assertEqual(extract_json_objects(input_string), output_list)

        # JSON with AWS example concatenated
        input_string = full_message_example + full_message_example
        output_list = [full_message_example, full_message_example]
        self.assertEqual(extract_json_objects(input_string), output_list)

        # Empty JSON
        input_string = """{}{}"""
        output_list = ["{}", "{}"]
        self.assertEqual(extract_json_objects(input_string), output_list)

        # Empty JSON
        input_string = """{}"""
        output_list = ["{}"]
        self.assertEqual(extract_json_objects(input_string), output_list)

        # Won't check for properly closed [] characters
        input_string = """{"a":[]]}"""
        output_list = ['{"a":[]]}']
        self.assertEqual(extract_json_objects(input_string), output_list)


class TestStats(unittest.TestCase):
    @patch("lambda_function.urlopen")
    def test_flush_retries_on_5xx_errors(self, mock_urlopen):
        mock_response = MagicMock()
        mock_response.__enter__.return_value = mock_response
        mock_response.getcode.return_value = 200
        mock_urlopen.side_effect = [
            HTTPError(
                url="mockurl",
                code=500,
                msg="Server Error",
                hdrs={},
                fp=BytesIO(b"Error"),
            ),
            HTTPError(
                url="mockurl",
                code=502,
                msg="Bad Gateway",
                hdrs={},
                fp=BytesIO(b"Error"),
            ),
            HTTPError(
                url="mockurl",
                code=503,
                msg="Service Unavailable",
                hdrs={},
                fp=BytesIO(b"Error"),
            ),
            HTTPError(
                url="mockurl",
                code=504,
                msg="Gateway Timeout",
                hdrs={},
                fp=BytesIO(b"Error"),
            ),
            mock_response,
        ]
        stats = Stats(cap=0.01)
        stats.gauge("test.metric", 42)
        stats.flush()
        self.assertEqual(mock_urlopen.call_count, 5)

    @patch("lambda_function.urlopen")
    def test_flush_no_retry_on_4xx_error(self, mock_urlopen):
        mock_response = MagicMock()
        mock_response.__enter__.return_value = mock_response
        mock_response.getcode.return_value = 200
        mock_urlopen.side_effect = [
            HTTPError(
                url="mockurl", code=403, msg="Forbidden", hdrs={}, fp=BytesIO(b"Error")
            ),
        ]
        stats = Stats()
        stats.gauge("test.metric", 42)
        stats.flush()
        self.assertEqual(mock_urlopen.call_count, 1)

    @patch("lambda_function.urlopen")
    def test_flush_retries_max_attempts(self, mock_urlopen):
        mock_urlopen.side_effect = [
            HTTPError(
                url="mockurl",
                code=500,
                msg="Server Error",
                hdrs={},
                fp=BytesIO(b"Error"),
            ),
            HTTPError(
                url="mockurl",
                code=502,
                msg="Bad Gateway",
                hdrs={},
                fp=BytesIO(b"Error"),
            ),
        ]
        stats = Stats(max_attempts=1)
        stats.gauge("test.metric", 42)
        stats.flush()
        self.assertEqual(mock_urlopen.call_count, 1)

    @patch("lambda_function.urlopen")
    def test_flush_drop(self, mock_urlopen):
        mock_urlopen.side_effect = [
            Exception("Error"),
        ]
        stats = Stats()
        stats.gauge("test.metric", 42)
        stats.flush()
        self.assertEqual(mock_urlopen.call_count, 1)


if __name__ == "__main__":
    unittest.main()
