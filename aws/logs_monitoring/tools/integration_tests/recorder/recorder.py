#!/usr/bin/env python3
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import os
import zlib

from google.protobuf.json_format import MessageToDict
import pb.trace_payload_pb2 as TracePayloadProtobuf


PORT_NUMBER = 8080

print("Starting recorder", flush=True)

events = []


class RecorderHandler(BaseHTTPRequestHandler):
    def __init__(self, request, client_address, server):
        super().__init__(request, client_address, server)

    def handle_request(self):
        global events
        response = '{"status":200}'
        response_type = "text/json"

        if self.path == "/recording":
            # Return the recent events and clear the recording
            response = json.dumps({"events": events})
            events = []

        else:
            print("Recorded: {} {}".format(self.command, self.path), flush=True)

            data = None
            if self.headers["Content-Length"] != None:
                contents = self.rfile.read(int(self.headers["Content-Length"]))
                if self.headers["Content-Type"] == "application/json":
                    if self.headers["Content-Encoding"] == "deflate":
                        contents = zlib.decompress(contents)
                    try:
                        data = json.loads(contents.decode())
                    except:
                        pass
                elif self.headers["Content-Type"] == "application/x-protobuf":
                    # Assume that protobuf calls contain trace payloads
                    message = TracePayloadProtobuf.TracePayload()
                    message.ParseFromString(contents)
                    data = MessageToDict(message)

            event = {
                "path": self.path,
                "verb": self.command,
                "headers": {k: v for k, v in self.headers.items()},
                "data": data,
            }

            events.append(event)

        # Send an OK response
        self.send_response(200)
        self.send_header("Content-type", response_type)
        self.end_headers()

        # Send the html message
        self.wfile.write(response.encode("utf-8"))
        return

    def do_GET(self):
        self.handle_request()

    def do_POST(self):
        self.handle_request()


port = int(os.environ.get("SERVER_PORT", default=PORT_NUMBER))

try:
    server = HTTPServer(("", port), RecorderHandler)
    print("Started recorder on port {}".format(port), flush=True)
    server.serve_forever()
finally:
    print("Shutting down recorder", flush=True)
    server.socket.close()
