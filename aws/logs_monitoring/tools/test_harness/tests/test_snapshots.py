import unittest
import os
import urllib.request, json

recorder_url = os.environ.get("RECORDER_URL", default="")
forwarder_url = os.environ.get("FORWARDER_URL", default="")
snapshot_dir = os.environ.get("SNAPSHOT_DIR", default="snapshots")
update_snapshot = os.environ.get("UPDATE_SNAPSHOTS")
if not update_snapshot:
    update_snapshot = "false"
update_snapshot = update_snapshot.lower() == "true"


class TestForwarderSnapshots(unittest.TestCase):
    def get_recording(self):
        with urllib.request.urlopen(recorder_url) as url:
            data = json.loads(url.read().decode())
        return data

    def send_log_event(self, event):
        request = urllib.request.Request(forwarder_url, data=event.encode("utf-8"))
        urllib.request.urlopen(request)

    def compare_snapshot(self, input_filename, snapshot_filename):
        with open(input_filename, "r") as input_file:
            input_data = input_file.read()

        snapshot_data = {}
        try:
            with open(snapshot_filename, "r") as snapshot_file:
                snapshot_data = json.loads(snapshot_file.read())
        except:
            pass  # Valid if snapshot data doesn't exist

        self.send_log_event(input_data)
        output_data = self.get_recording()

        if update_snapshot:
            with open(snapshot_filename, "w") as snapshot_file:
                snapshot_file.write(json.dumps(output_data, indent=2))
        else:
            message = f"Snapshot's didn't match for {input_filename}. To update run `UPDATE_SNAPSHOTS=true ./tools/integration_test.sh"
            self.assertEqual(output_data, snapshot_data, message)
            pass

    def setup(self):
        # Clears any recorded state from the mock server
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
        self.maxDiff = None

        for input_filename in os.listdir(snapshot_dir):
            input_filename = f"{snapshot_dir}/{input_filename}"
            if not input_filename.endswith(".json"):
                continue

            snapshot_filename = f"{input_filename}~snapshot"
            self.compare_snapshot(input_filename, snapshot_filename)
