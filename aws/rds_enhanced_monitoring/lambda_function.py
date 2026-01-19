# Unless explicitly stated otherwise all files in this repository are licensed
# under the Apache License Version 2.0.
# This product includes software developed at Datadog (https://www.datadoghq.com/).
# Copyright 2021 Datadog, Inc.
import gzip
import json
import os
import re
import time
import base64
import random
from io import BufferedReader, BytesIO
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from urllib.parse import urlencode

import botocore
import boto3

DD_SITE = os.getenv("DD_SITE", default="datadoghq.com")


def _datadog_keys():
    if "kmsEncryptedKeys" in os.environ:
        KMS_ENCRYPTED_KEYS = os.environ["kmsEncryptedKeys"]
        kms = boto3.client("kms")
        # kmsEncryptedKeys should be created through the Lambda's encryption
        # helpers and as such will have the EncryptionContext
        return json.loads(
            kms.decrypt(
                CiphertextBlob=base64.b64decode(KMS_ENCRYPTED_KEYS),
                EncryptionContext={
                    "LambdaFunctionName": os.environ["AWS_LAMBDA_FUNCTION_NAME"]
                },
            )["Plaintext"]
        )

    if "DD_API_KEY_SECRET_ARN" in os.environ:
        SECRET_ARN = os.environ["DD_API_KEY_SECRET_ARN"]
        DD_API_KEY = boto3.client("secretsmanager").get_secret_value(
            SecretId=SECRET_ARN
        )["SecretString"]
        return {"api_key": DD_API_KEY}

    if "DD_API_KEY_SSM_NAME" in os.environ:
        SECRET_NAME = os.environ["DD_API_KEY_SSM_NAME"]
        DD_API_KEY = boto3.client("ssm").get_parameter(
            Name=SECRET_NAME, WithDecryption=True
        )["Parameter"]["Value"]
        return {"api_key": DD_API_KEY}

    if "DD_KMS_API_KEY" in os.environ:
        ENCRYPTED = os.environ["DD_KMS_API_KEY"]

        # For interop with other DD Lambdas taking in DD_KMS_API_KEY, we'll
        # optionally try the EncryptionContext associated with this Lambda.
        try:
            DD_API_KEY = boto3.client("kms").decrypt(
                CiphertextBlob=base64.b64decode(ENCRYPTED),
                EncryptionContext={
                    "LambdaFunctionName": os.environ["AWS_LAMBDA_FUNCTION_NAME"]
                },
            )["Plaintext"]
        except botocore.exceptions.ClientError:
            DD_API_KEY = boto3.client("kms").decrypt(
                CiphertextBlob=base64.b64decode(ENCRYPTED),
            )["Plaintext"]

        if type(DD_API_KEY) is bytes:
            # If the CiphertextBlob was encrypted with AWS CLI, we
            # need to re-encode this in base64
            try:
                DD_API_KEY = DD_API_KEY.decode("utf-8")
            except UnicodeDecodeError as e:
                print(
                    "INFO DD_KMS_API_KEY: Could not decode key in utf-8, encoding in b64. Exception:",
                    e,
                )
                DD_API_KEY = base64.b64encode(DD_API_KEY)
                DD_API_KEY = DD_API_KEY.decode("utf-8")
            except Exception as e:
                print("ERROR DD_KMS_API_KEY Unknown exception decoding key:", e)
        return {"api_key": DD_API_KEY}

    if "DD_API_KEY" in os.environ:
        DD_API_KEY = os.environ["DD_API_KEY"]
        return {"api_key": DD_API_KEY}

    raise ValueError(
        "Datadog API key is not defined, see documentation for environment variable options"
    )


# Preload the keys so we can bail out early if they're misconfigured
datadog_keys = _datadog_keys()
print("INFO Lambda function initialized, ready to send metrics")


def _process_rds_enhanced_monitoring_message(ts, message, account, region):
    instance_id = message["instanceID"]
    host_id = message["instanceResourceID"]
    tags = [
        "dbinstanceidentifier:%s" % instance_id,
        "aws_account:%s" % account,
        "engine:%s" % message["engine"],
    ]

    # metrics generation

    # uptime: "54 days, 1:53:04" to be converted into seconds
    uptime = 0
    uptime_msg = re.split(" days?, ", message["uptime"])  # edge case "1 day 1:53:04"
    if len(uptime_msg) == 2:
        uptime += 24 * 3600 * int(uptime_msg[0])
    uptime_day = uptime_msg[-1].split(":")
    uptime += 3600 * int(uptime_day[0])
    uptime += 60 * int(uptime_day[1])
    uptime += int(uptime_day[2])
    stats.gauge("aws.rds.uptime", uptime, timestamp=ts, tags=tags, host=host_id)

    stats.gauge(
        "aws.rds.virtual_cpus",
        message["numVCPUs"],
        timestamp=ts,
        tags=tags,
        host=host_id,
    )

    if "loadAverageMinute" in message:
        stats.gauge(
            "aws.rds.load.1",
            message["loadAverageMinute"]["one"],
            timestamp=ts,
            tags=tags,
            host=host_id,
        )
        stats.gauge(
            "aws.rds.load.5",
            message["loadAverageMinute"]["five"],
            timestamp=ts,
            tags=tags,
            host=host_id,
        )
        stats.gauge(
            "aws.rds.load.15",
            message["loadAverageMinute"]["fifteen"],
            timestamp=ts,
            tags=tags,
            host=host_id,
        )

    for namespace in ["cpuUtilization", "memory", "tasks", "swap"]:
        for key, value in message.get(namespace, {}).items():
            stats.gauge(
                "aws.rds.%s.%s" % (namespace.lower(), key),
                value,
                timestamp=ts,
                tags=tags,
                host=host_id,
            )

    for network_stats in message.get("network", []):
        if "interface" in network_stats:
            network_tag = ["interface:%s" % network_stats.pop("interface")]
        else:
            network_tag = []
        for key, value in network_stats.items():
            stats.gauge(
                "aws.rds.network.%s" % key,
                value,
                timestamp=ts,
                tags=tags + network_tag,
                host=host_id,
            )

    for disk_stats in message.get("diskIO", []):
        disk_tag = []
        if "device" in disk_stats:
            disk_tag.append("%s:%s" % ("device", disk_stats.pop("device")))
        for key, value in disk_stats.items():
            stats.gauge(
                "aws.rds.diskio.%s" % key,
                value,
                timestamp=ts,
                tags=tags + disk_tag,
                host=host_id,
            )

    for fs_stats in message.get("fileSys", []):
        fs_tag = []
        for tag_key in ["name", "mountPoint"]:
            if tag_key in fs_stats:
                fs_tag.append("%s:%s" % (tag_key, fs_stats.pop(tag_key)))
        for key, value in fs_stats.items():
            stats.gauge(
                "aws.rds.filesystem.%s" % key,
                value,
                timestamp=ts,
                tags=tags + fs_tag,
                host=host_id,
            )

    for process_stats in message.get("processList", []):
        process_tag = []
        for tag_key in ["name", "id"]:
            if tag_key in process_stats:
                process_tag.append("%s:%s" % (tag_key, process_stats.pop(tag_key)))
        for key, value in process_stats.items():
            stats.gauge(
                "aws.rds.process.%s" % key,
                value,
                timestamp=ts,
                tags=tags + process_tag,
                host=host_id,
            )

    for pd_stats in message.get("physicalDeviceIO", []):
        pd_tag = []
        if "device" in pd_stats:
            pd_tag.append("%s:%s" % ("device", pd_stats.pop("device")))
        for key, value in pd_stats.items():
            stats.gauge(
                "aws.rds.physicaldeviceio.%s" % key,
                value,
                timestamp=ts,
                tags=tags + pd_tag,
                host=host_id,
            )

    for disks_stats in message.get("disks", []):
        disks_tag = []
        if "name" in disks_stats:
            disks_tag.append("%s:%s" % ("name", disks_stats.pop("name")))
        for key, value in disks_stats.items():
            stats.gauge(
                "aws.rds.disks.%s" % key,
                value,
                timestamp=ts,
                tags=tags + disks_tag,
                host=host_id,
            )

    if "system" in message:
        for key, value in message["system"].items():
            stats.gauge(
                "aws.rds.system.%s" % key,
                value,
                timestamp=ts,
                tags=tags,
                host=host_id,
            )


def extract_json_objects(input_string):
    """
    Extract JSON objects if the log_event["message"] is not properly formatted like this:
    {"a":2}{"b":{"c":3}}
    Supports JSON with a depth of 6 at maximum (recursion requires regex package)
    """
    in_string, open_brackets, json_objects, start = False, 0, [], 0
    for idx, char in enumerate(input_string):
        # Ignore escaped quotes
        if char == '"' and (idx == 0 or input_string[idx - 1] != "\\"):
            in_string = not in_string
        elif char == "{" and not in_string:
            open_brackets += 1
        elif char == "}" and not in_string:
            open_brackets -= 1
            if open_brackets == 0:
                json_objects += [input_string[start : idx + 1]]
                start = idx + 1
    return json_objects


def lambda_handler(event, context):
    """Process a RDS enhanced monitoring DATA_MESSAGE,
    coming from CLOUDWATCH LOGS
    """
    # event is a dict containing a base64 string gzipped
    with gzip.GzipFile(
        fileobj=BytesIO(base64.b64decode(event["awslogs"]["data"]))
    ) as decompress_stream:
        data = b"".join(BufferedReader(decompress_stream))

    event = json.loads(data)

    account = event["owner"]
    region = context.invoked_function_arn.split(":", 4)[3]

    log_events = event["logEvents"]

    for log_event in log_events:
        ts = log_event["timestamp"] / 1000
        # Try to parse all objects as JSON before going into processing
        # In case one of the json.loads operation fails, revert to previous behavior
        json_objects = []
        try:
            messages = extract_json_objects(log_event["message"])
            for json_object in messages:
                json_objects += [json.loads(json_object)]
        except:
            json_objects += [json.loads(log_event["message"])]
        for message in json_objects:
            _process_rds_enhanced_monitoring_message(ts, message, account, region)

    stats.flush()
    return {"Status": "OK"}


# Helpers to send data to Datadog, inspired from https://github.com/DataDog/datadogpy


class Stats(object):
    def __init__(self, base=2, cap=30, max_attempts=5):
        self.series = []
        self.base = base
        self.cap = cap
        self.max_attempts = max_attempts

    def _backoff(self, n):
        v = min(self.cap, pow(2, n) * self.base)
        return random.uniform(0, v)

    def gauge(self, metric, value, timestamp=None, tags=None, host=None):
        base_dict = {
            "metric": metric,
            "points": [(int(timestamp or time.time()), value)],
            "type": "gauge",
            "tags": tags,
        }
        if host:
            base_dict.update({"host": host})
        self.series.append(base_dict)

    def flush(self):
        metrics_dict = {
            "series": self.series,
        }
        self.series = []

        creds = urlencode(datadog_keys)
        data = json.dumps(metrics_dict).encode("ascii")
        url = "%s?%s" % (
            datadog_keys.get("api_host", "https://api.%s/api/v1/series" % DD_SITE),
            creds,
        )
        req = Request(url, data, {"Content-Type": "application/json"})
        for attempt in range(1, self.max_attempts + 1):
            try:
                with urlopen(req) as response:
                    print(
                        "INFO Submitted data with status: {}".format(response.getcode())
                    )
                    break
            except HTTPError as e:
                if e.code in (500, 502, 503, 504):
                    if attempt == self.max_attempts:
                        print(
                            "ERROR Exceeded max number of retries, dropping data: {}".format(
                                e.read()
                            )
                        )
                        break
                    t = self._backoff(attempt)
                    print("ERROR {}. Retrying in {} seconds...".format(e.read(), t))
                    time.sleep(t)
                else:
                    print(
                        "ERROR {}, not retrying with status {}".format(e.read(), e.code)
                    )
                    break
            except Exception as e:
                print("ERROR Dropping data: {}".format(e))
                break


stats = Stats()
