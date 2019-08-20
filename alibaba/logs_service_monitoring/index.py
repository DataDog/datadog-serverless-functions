# Unless explicitly stated otherwise all files in this repository are licensed
# under the Apache License Version 2.0.
# This product includes software developed at Datadog (https://www.datadoghq.com/).
# Copyright 2018 Datadog, Inc.

from __future__ import print_function

import base64
import gzip
import json
import os
import re
import socket
import requests
import time
import ssl
import six.moves.urllib as urllib  # for for Python 2.7 urllib.unquote_plus
import itertools
from io import BytesIO, BufferedReader
import logging
from aliyun.log import LogClient

# edit below
DD_ALIBABA_ACCESSKEYID = "<your_alibaba_access_key_id"
DD_ALIBABA_ACCESSKEYSECRET = "<your_alibaba_access_key_secret"
DD_API_KEY = "<your_api_key>"

# TODO: fix validation for passing api key as env var

# TODO: add back metrics
# For backward-compatibility
DD_FORWARD_METRIC = False

# Set this variable to `False` to disable log forwarding.
# E.g., when you only want to forward metrics from logs.
DD_FORWARD_LOG = os.getenv("DD_FORWARD_LOG", default="true").lower() == "true"

# TODO: add back tcp client
# Change this value to change the underlying network client (HTTP or TCP),
# by default, use the TCP client.
DD_USE_TCP = os.getenv("DD_USE_TCP", default="false").lower() == "true"

# Define the destination endpoint to send logs to
DD_SITE = os.getenv("DD_SITE", default="datadoghq.com")

if DD_USE_TCP:
    DD_URL = os.getenv("DD_URL", default="lambda-intake.logs." + DD_SITE)
    try:
        if "DD_SITE" in os.environ and DD_SITE == "datadoghq.eu":
            DD_PORT = int(os.environ.get("DD_PORT", 443))
        else:
            DD_PORT = int(os.environ.get("DD_PORT", 10516))
    except Exception:
        DD_PORT = 10516
else:
    DD_URL = os.getenv("DD_URL", default="lambda-http-intake.logs." + DD_SITE)

DD_SOURCE = "ddsource"
DD_SERVICE = "service"

# TODO: add back tags host fwd version
# DD_CUSTOM_TAGS = "ddtags"
# DD_HOST = "host"
# DD_FORWARDER_VERSION = "0.0.1"

# Pass custom tags as environment variable, ensure comma separated, no trailing comma in envvar!
# DD_TAGS = os.environ.get("DD_TAGS", "")

def logClient(endpoint, creds):
  # TODO: this should be inferrable from creds variable but creds.access_key_id was throwing an authentication error
  # using hardcoded globals instead

  # logger = logging.getLogger()  
  # logger.info(creds.access_key_id)
  # logger.info(creds.access_key_secret)
  # logger.info(creds.security_token)  

  accessKeyId = DD_ALIBABA_ACCESSKEYID
  accessKeySecret = DD_ALIBABA_ACCESSKEYSECRET

  client = LogClient(endpoint, accessKeyId, accessKeySecret)
  return client


def fetchdata(event, context):
  logger = logging.getLogger()
  creds = context.credentials
  loggroup_count = 10
  details = []
  endpoint = event['endpoint']
  project = event['projectName']
  logstore = event['logstoreName']
  start_cursor = event['beginCursor']
  end_cursor = event['endCursor']
  shard_id = event['shardId']
  
  client = logClient(endpoint, creds)

  if client == None:
      return False  

  while True:
      res = client.pull_logs(project, logstore, shard_id, start_cursor, loggroup_count, end_cursor)
      
      # TODO: use helper methods on aliyun https://aliyun-log-python-sdk.readthedocs.io/
      details.append(res.get_body())
      next_cursor = res.get_next_cursor()
      if next_cursor == start_cursor :
          break
      start_cursor = next_cursor
      
  # TODO: add error handling for http requests, make sure to have some breakpoint for number of requests or set max timeout
  return details


def validation(DD_API_KEY):
    # TODO: this wasnt working during testing so using hardcoded api key only for now
    # if "DD_API_KEY" in os.environ:
    #     DD_API_KEY = os.environ["DD_API_KEY"]

    # Strip any trailing and leading whitespace from the API key
    DD_API_KEY = DD_API_KEY.strip()

    # DD_API_KEY must be set
    if DD_API_KEY == "<your_api_key>" or DD_API_KEY == "":
        raise Exception(
            "You must configure your Datadog API key using "
            "DD_KMS_API_KEY or DD_API_KEY"
        )
    # Check if the API key is the correct number of characters
    if len(DD_API_KEY) != 32:
        raise Exception(
            "The API key is not the expected length. "
            "Please confirm that your API key is correct"
        )
    # Validate the API key
    validation_res = requests.get(
        "https://api.{}/api/v1/validate?api_key={}".format(DD_SITE, DD_API_KEY)
    )
    if not validation_res.ok:
        raise Exception("The API key is not valid.")


class RetriableException(Exception):
    pass


class DatadogHTTPClient(object):
    """
    Client that sends a batch of logs over HTTP.
    """

    _POST = "POST"
    _HEADERS = {"Content-type": "application/json"}

    def __init__(self, host, api_key, scrubber=None, timeout=10):
        self._url = "https://{}/v1/input/{}".format(host, api_key)
        # TODO: Add back scrubbing
        # self._scrubber = scrubber
        self._timeout = timeout
        self._session = None

    def _connect(self):
        self._session = requests.Session()
        self._session.headers.update(self._HEADERS)

    def _close(self):
        self._session.close()

    def send(self, logs):
        """
        Sends a batch of log, only retry on server and network errors.
        """
        try:
            resp = self._session.post(
                self._url,
                data="[{}]".format(",".join(logs)),
                timeout=self._timeout,
            )
        # TODO: add back scrubbing
        # except ScrubbingException:
        #     raise Exception("could not scrub the payload")
        except Exception:
            # most likely a network error
            raise RetriableException()
        if resp.status_code >= 500:
            # server error
            raise RetriableException()
        elif resp.status_code >= 400:
            # client error
            raise Exception(
                "client error, status: {}, reason {}".format(
                    resp.status_code, resp.reason
                )
            )
        else:
            # success
            return

    def __enter__(self):
        self._connect()
        return self

    def __exit__(self, ex_type, ex_value, traceback):
        self._close()


class DatadogBatcher(object):
    def __init__(self, max_log_size_bytes, max_size_bytes, max_size_count):
        self._max_log_size_bytes = max_log_size_bytes
        self._max_size_bytes = max_size_bytes
        self._max_size_count = max_size_count

    def _sizeof_bytes(self, log):
        return len(log.encode("UTF-8"))

    def batch(self, logs):
        """
        Returns an array of batches.
        Each batch contains at most max_size_count logs and
        is not strictly greater than max_size_bytes.
        All logs strictly greater than max_log_size_bytes are dropped.
        """
        batches = []
        batch = []
        size_bytes = 0
        size_count = 0
        for log in logs:
            log_size_bytes = self._sizeof_bytes(log)
            if size_count > 0 and (
                size_count >= self._max_size_count
                or size_bytes + log_size_bytes > self._max_size_bytes
            ):
                batches.append(batch)
                batch = []
                size_bytes = 0
                size_count = 0
            # all logs exceeding max_log_size_bytes are dropped here
            if log_size_bytes <= self._max_log_size_bytes:
                batch.append(log)
                size_bytes += log_size_bytes
                size_count += 1
        if size_count > 0:
            batches.append(batch)
        return batches


def datadog_forwarder(event, context):
    """The actual cloud function entry point"""
    # logger = logging.getLogger()
    # logger.info(event.decode().encode())
    info_arr = json.loads(event.decode())
    log_respose_data = fetchdata(info_arr['source'], context)

    events = parse(log_respose_data, context)
    
    # TODO: add back metrics
    # metrics, logs = split(events)
    logs = split(events)
    
    if DD_FORWARD_LOG:
        # TODO: fix validation for api_key as env var
        validation(DD_API_KEY)
        forward_logs(logs)


def forward_logs(logs):
    """Forward logs to Datadog"""
    # TODO: add back scrubbing
    # scrubber = DatadogScrubber(SCRUBBING_RULE_CONFIGS)
    if DD_USE_TCP:
        raise Exception('tcp client not available for alibaba logs at this time')
        # batcher = DatadogBatcher(256 * 1000, 256 * 1000, 1)
        # cli = DatadogTCPClient(DD_URL, DD_PORT, DD_API_KEY, scrubber)
    else:
        batcher = DatadogBatcher(128 * 1000, 1 * 1000 * 1000, 25)
        # TODO: add back scrubbing 
        # cli = DatadogHTTPClient(DD_URL, DD_API_KEY, scrubber)
        cli = DatadogHTTPClient(DD_URL, DD_API_KEY)

    with DatadogClient(cli) as client:
        for batch in batcher.batch(logs):
            try:
                client.send(batch)
            except Exception as e:
                print("Unexpected exception: {}, batch: {}".format(str(e), batch))


def parse(event, context):
    """Parse Lambda input to normalized events"""
    # TODO: add metadata context back
    # logger = logging.getLogger()
    structured_logs = []

    if isinstance(event,list):
      for logs_dictionary in event:
          if logs_dictionary.get("logs"):
              for log_line_dictionary in logs_dictionary["logs"]:
                  #ecs logtail logs
                  if log_line_dictionary.get("content"):
                      log_content = log_line_dictionary["content"]
                  #actiontrail logs
                  else:
                      log_content = log_line_dictionary

                  structured_line = {"alibaba": {}, "message": log_content}
                  structured_logs.append(structured_line)

    return normalize_events(structured_logs)


def split(events):
    """Split events to metrics and logs"""
    # TODO: add metrics back
    # metrics, logs = [], []
    logs = []
    for event in events:
        # metric = extract_metric(event)

        # if metric:
        #     metrics.append(metric)
        # else:
        
        event_json = json.dumps(event)
        logs.append(event_json)
    
    # return metrics, logs
    return logs


class DatadogClient(object):
    """
    Client that implements a exponential retrying logic to send a batch of logs.
    """

    def __init__(self, client, max_backoff=30):
        self._client = client
        self._max_backoff = max_backoff

    def send(self, logs):
        backoff = 1
        while True:
            try:
                self._client.send(logs)
                return
            except RetriableException:
                time.sleep(backoff)
                if backoff < self._max_backoff:
                    backoff *= 2
                continue

    def __enter__(self):
        self._client.__enter__()
        return self

    def __exit__(self, ex_type, ex_value, traceback):
        self._client.__exit__(ex_type, ex_value, traceback)


def merge_dicts(a, b, path=None):
    if path is None:
        path = []
    for key in b:
        if key in a:
            if isinstance(a[key], dict) and isinstance(b[key], dict):
                merge_dicts(a[key], b[key], path + [str(key)])
            elif a[key] == b[key]:
                pass  # same leaf value
            else:
                raise Exception(
                    "Conflict while merging metadatas and the log entry at %s"
                    % ".".join(path + [str(key)])
                )
        else:
            a[key] = b[key]
    return a        


def normalize_events(events):
    metadata = {
        "ddsourcecategory": "alibaba",
        "alibaba": {}
    }

    metadata[DD_SOURCE] = "alibaba"
    metadata[DD_SERVICE] = "alibaba"
    
    normalized = []

    for event in events:
        if isinstance(event, dict):
            normalized.append(merge_dicts(event, metadata))
        else:
            # drop this log
            continue

    return normalized


if DD_FORWARD_METRIC:
    # TODO: incorpoate  metrics
    raise Exception('metric forwarding not available for alibaba logs at this time')
    # Datadog Lambda layer is required to forward metrics
    # lambda_handler = datadog_lambda_wrapper(datadog_forwarder)
else:
    handler = datadog_forwarder