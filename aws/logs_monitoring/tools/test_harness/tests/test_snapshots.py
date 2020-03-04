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

    def test_snapshots(self):
        print(recorder_url, flush=True)
        self.get_recording()
        self.get_recording()
        self.assertEqual(True, False)
