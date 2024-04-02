# Unless explicitly stated otherwise all files in this repository are licensed
# under the Apache License Version 2.0.
# This product includes software developed at Datadog (https://www.datadoghq.com/).
# Copyright 2021 Datadog, Inc.


import os
import socket
import ssl
import logging

from logs.exceptions import RetriableException, ScrubbingException

logger = logging.getLogger()
logger.setLevel(logging.getLevelName(os.environ.get("DD_LOG_LEVEL", "INFO").upper()))


class DatadogTCPClient(object):
    """
    Client that sends a batch of logs over TCP.
    """

    def __init__(self, host, port, no_ssl, api_key, scrubber):
        self.host = host
        self.port = port
        self._use_ssl = not no_ssl
        self._api_key = api_key
        self._scrubber = scrubber
        self._sock = None
        if logger.isEnabledFor(logging.DEBUG):
            logger.debug(
                f"Initialized tcp client for logs intake: "
                f"<host: {host}, port: {port}, no_ssl: {no_ssl}>"
            )

    def _connect(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        if self._use_ssl:
            context = ssl.create_default_context()
            context.options |= ssl.OP_NO_TLSv1 | ssl.OP_NO_TLSv1_1
            context.minimum_version = ssl.TLSVersion.TLSv1_2
            sock = context.wrap_socket(sock, server_hostname=self.host)
        sock.connect((self.host, self.port))
        self._sock = sock

    def _close(self):
        if self._sock:
            self._sock.close()

    def _reset(self):
        self._close()
        self._connect()

    def send(self, logs):
        try:
            frame = self._scrubber.scrub(
                "".join(["{} {}\n".format(self._api_key, log) for log in logs])
            )
            self._sock.sendall(frame.encode("UTF-8"))
        except ScrubbingException:
            raise Exception("could not scrub the payload")
        except Exception:
            # most likely a network error, reset the connection
            self._reset()
            raise RetriableException()

    def __enter__(self):
        self._connect()
        return self

    def __exit__(self, ex_type, ex_value, traceback):
        self._close()
