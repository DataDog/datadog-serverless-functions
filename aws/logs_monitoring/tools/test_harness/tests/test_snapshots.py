import unittest
import os
import urllib.request, json

recorder_url = os.environ.get("RECORDER_URL", default="")
forwarder_url = os.environ.get("FORWARDER_URL", default="")


class TestForwarderSnapshots(unittest.TestCase):
    def get_recording(self):
        with urllib.request.urlopen(recorder_url) as url:
            data = json.loads(url.read().decode())
        return data

    def send_log_event(self, event):
        request = urllib.request.Request(forwarder_url, data=event.encode("utf-8"))
        urllib.request.urlopen(request)

    def setup(self):
        # Clear the recording before each test
        self.get_recording()

    def test_initialization(self):
        # We run this step before the snapshots, to capture startup http calls like validate
        self.send_log_event("{}")
        recording = self.get_recording()
        self.assertEqual(
            recording["events"][0]["path"],
            "/api/v1/validate?api_key=abcdefghijklmnopqrstuvwxyz012345",
        )

    def test_snapshots(self):
        pass
