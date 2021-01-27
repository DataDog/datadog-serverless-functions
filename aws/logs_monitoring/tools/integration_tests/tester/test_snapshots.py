import unittest
import base64
import os
import urllib.request
import json
import re
import gzip
from time import sleep
from deepdiff import DeepDiff

recorder_url = os.environ.get("RECORDER_URL", default="")
forwarder_url = os.environ.get("FORWARDER_URL", default="")
update_snapshot = os.environ.get("UPDATE_SNAPSHOTS")
if not update_snapshot:
    update_snapshot = "false"
update_snapshot = update_snapshot.lower() == "true"

snapshot_dir = "snapshots"


class TestForwarderSnapshots(unittest.TestCase):
    maxDiff = None
    recorder_has_been_initialized = False

    def get_recording(self):
        with urllib.request.urlopen(recorder_url) as url:
            message = self.filter_snapshot(url.read().decode())
            data = json.loads(message)
        return data

    def create_cloudwatch_log_event_from_data(self, data):
        # CloudWatch log event data is a base64-encoded ZIP archive
        # see https://docs.aws.amazon.com/lambda/latest/dg/services-cloudwatchlogs.html
        gzipped_data = gzip.compress(bytes(data, encoding="utf-8"))
        encoded_data = base64.b64encode(gzipped_data).decode("utf-8")
        return f'{{"awslogs": {{"data": "{encoded_data}"}}}}'

    def send_log_event(self, event):
        request = urllib.request.Request(forwarder_url, data=event.encode("utf-8"))
        urllib.request.urlopen(request)

    def filter_snapshot(self, snapshot):
        # Remove things that can vary during each test run
        # Forwarder version in tags
        snapshot = re.sub(
            r"forwarder_version:\d+\.\d+\.\d+",
            "forwarder_version:<redacted from snapshot>",
            snapshot,
        )
        # Forwarder version in trace payloads
        snapshot = re.sub(
            r"\"forwarder_version\":\s\"\d+\.\d+\.\d+\"",
            '"forwarder_version": "<redacted from snapshot>"',
            snapshot,
        )
        snapshot = re.sub(
            r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
            "<redacted from snapshot>",
            snapshot,
        )
        # Metric points
        snapshot = re.sub(
            r"\"points\":.*?,(?=\s*\")",
            '"points": "<redacted from snapshot>",',
            snapshot,
            flags=re.MULTILINE,
        )
        return snapshot

    def compare_snapshot(self, input_filename, snapshot_filename):
        with open(input_filename, "r") as input_file:
            input_data = input_file.read()

        cloudwatch_event = self.create_cloudwatch_log_event_from_data(input_data)

        snapshot_data = {}
        try:
            with open(snapshot_filename, "r") as snapshot_file:
                snapshot_data = json.loads(snapshot_file.read())
        except:
            pass  # Valid if snapshot data doesn't exist

        self.send_log_event(cloudwatch_event)
        output_data = self.get_recording()

        if update_snapshot:
            with open(snapshot_filename, "w") as snapshot_file:
                snapshot_file.write(json.dumps(output_data, indent=2, sort_keys=True))
                # snapshot_file.write(json.dumps(output_data, indent=2))
        else:
            message = f"Snapshots didn't match for {input_filename}. To update run `integration_tests.sh --update`."
            d = DeepDiff(snapshot_data, output_data)
            self.assertFalse(d, message)
            pass

    def setUp(self):
        # Clears any previously recorded state
        self.get_recording()

        # If this is the first test we are running, we first need to capture
        # startup http calls like /validate
        if not self.__class__.recorder_has_been_initialized:
            self.send_log_event("{}")
            recording = self.get_recording()
            self.assertEqual(
                recording["events"][0]["path"],
                "/api/v1/validate?api_key=abcdefghijklmnopqrstuvwxyz012345",
            )
            self.__class__.recorder_has_been_initialized = True

    def test_cloudwatch_log(self):
        input_filename = f"{snapshot_dir}/cloudwatch_log.json"
        snapshot_filename = f"{input_filename}~snapshot"
        self.compare_snapshot(input_filename, snapshot_filename)

    def test_cloudwatch_apigateway_log(self):
        input_filename = f"{snapshot_dir}/cloudwatch_log_apigateway.json"
        snapshot_filename = f"{input_filename}~snapshot"
        self.compare_snapshot(input_filename, snapshot_filename)

    def test_cloudwatch_cloudtrail_log(self):
        input_filename = f"{snapshot_dir}/cloudwatch_log_cloudtrail.json"
        snapshot_filename = f"{input_filename}~snapshot"
        self.compare_snapshot(input_filename, snapshot_filename)

    def test_cloudwatch_log_cold_start(self):
        input_filename = f"{snapshot_dir}/cloudwatch_log_coldstart.json"
        snapshot_filename = f"{input_filename}~snapshot"
        self.compare_snapshot(input_filename, snapshot_filename)

    def test_cloudwatch_log_custom_tags(self):
        input_filename = f"{snapshot_dir}/cloudwatch_log_custom_tags.json"
        snapshot_filename = f"{input_filename}~snapshot"
        self.compare_snapshot(input_filename, snapshot_filename)

    def test_cloudwatch_log_lambda_invocation(self):
        input_filename = f"{snapshot_dir}/cloudwatch_log_lambda_invocation.json"
        snapshot_filename = f"{input_filename}~snapshot"
        self.compare_snapshot(input_filename, snapshot_filename)

    def test_cloudwatch_log_timeout(self):
        input_filename = f"{snapshot_dir}/cloudwatch_log_timeout.json"
        snapshot_filename = f"{input_filename}~snapshot"
        self.compare_snapshot(input_filename, snapshot_filename)
