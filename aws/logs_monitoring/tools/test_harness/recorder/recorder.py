#!/usr/bin/env python3
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import os

PORT_NUMBER = 8080

print("Starting mock server", flush=True)

events = []


class RecorderHandler(BaseHTTPRequestHandler):
    def __init__(self, request, client_address, server):
        super().__init__(request, client_address, server)()

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
            # Record the event to logs
            data = None
            if self.headers["Content-Length"] != None:
                contents = self.rfile.read(int(self.headers["Content-Length"]))
                if self.headers["Content-Type"] == "application/json":
                    # If the input is json, decode it and add to the event directly
                    try:
                        data = json.loads(contents.decode())
                    except:
                        pass

            event = {
                "path": self.path,
                "verb": self.command,
                "content-type": self.headers["Content-Type"],
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

    # Handler for the GET requests
    def do_GET(self):
        self.handle_request()

    def do_POST(self):
        self.handle_request()


port = int(os.environ.get("SERVER_PORT", default=PORT_NUMBER))

try:
    server = HTTPServer(("", port), RecorderHandler)
    print("Started mock server on port {}".format(port), flush=True)
    server.serve_forever()
finally:
    print("Shutting down server", flush=True)
    server.socket.close()
