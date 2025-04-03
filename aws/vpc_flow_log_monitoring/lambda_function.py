# Unless explicitly stated otherwise all files in this repository are licensed
# under the Apache License Version 2.0.
# This product includes software developed at Datadog (https://www.datadoghq.com/).
# Copyright 2021 Datadog, Inc.
import logging
import os
import gzip
import json
import time
import base64
from io import BufferedReader, BytesIO
from collections import defaultdict, Counter
from urllib.request import Request, urlopen
from urllib.parse import urlencode

import boto3
import botocore


logger = logging.getLogger()
logger.setLevel(logging.getLevelName(os.environ.get("DD_LOG_LEVEL", "INFO").upper()))

logger.info("Loading function")

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
# Alternatively set datadog keys directly
# datadog_keys = {
#     "api_key": "abcd",
#     "app_key": "efgh",
# }
datadog_keys = _datadog_keys()
logger.info("Lambda function initialized, ready to send metrics")


def process_message(message, tags, timestamp, node_ip):
    (
        _,
        _,
        interface_id,
        srcaddr,
        dstaddr,
        _,
        _,
        protocol,
        packets,
        _bytes,
        start,
        end,
        action,
        log_status,
    ) = message.split(" ")

    detailed_tags = [
        "interface_id:%s" % interface_id,
        "protocol:%s" % protocol_id_to_name(protocol),
        "ip:%s" % node_ip,
    ] + tags
    if srcaddr == node_ip:
        detailed_tags.append("direction:outbound")
    if dstaddr == node_ip:
        detailed_tags.append("direction:inbound")

    process_log_status(log_status, detailed_tags, timestamp)
    if log_status == "NODATA":
        return

    process_action(action, detailed_tags, timestamp)
    process_duration(start, end, detailed_tags, timestamp)
    process_packets(packets, detailed_tags, timestamp)
    process_bytes(_bytes, detailed_tags, timestamp)


def compute_node_ip(events):
    ip_count = Counter()
    for event in events:
        src_ip, dest_ip = event["message"].split(" ", 5)[3:5]
        if len(src_ip) > 1 and len(dest_ip) > 1:  # account for '-'
            ip_count[src_ip] += 1
            ip_count[dest_ip] += 1
    most_comm = ip_count.most_common()
    if most_comm:
        if most_comm[0][1] > 1:  # we have several events
            return ip_count.most_common()[0][0]
    return "unknown"


def protocol_id_to_name(protocol):
    if protocol == "-":
        return protocol
    protocol_map = {
        0: "HOPOPT",
        1: "ICMP",
        2: "IGMP",
        3: "GGP",
        4: "IPv4",
        5: "ST",
        6: "TCP",
        7: "CBT",
        8: "EGP",
        9: "IGP",
        10: "BBN-RCC-MON",
        11: "NVP-II",
        12: "PUP",
        13: "ARGUS",
        14: "EMCON",
        15: "XNET",
        16: "CHAOS",
        17: "UDP",
        18: "MUX",
        19: "DCN-MEAS",
        20: "HMP",
        21: "PRM",
        22: "XNS-IDP",
        23: "TRUNK-1",
        24: "TRUNK-2",
        25: "LEAF-1",
        26: "LEAF-2",
        27: "RDP",
        28: "IRTP",
        29: "ISO-TP4",
        30: "NETBLT",
        31: "MFE-NSP",
        32: "MERIT-INP",
        33: "DCCP",
        34: "3PC",
        35: "IDPR",
        36: "XTP",
        37: "DDP",
        38: "IDPR-CMTP",
        39: "TP++",
        40: "IL",
        41: "IPv6",
        42: "SDRP",
        43: "IPv6-Route",
        44: "IPv6-Frag",
        45: "IDRP",
        46: "RSVP",
        47: "GRE",
        48: "DSR",
        49: "BNA",
        50: "ESP",
        51: "AH",
        52: "I-NLSP",
        53: "SWIPE",
        54: "NARP",
        55: "MOBILE",
        56: "TLSP",
        57: "SKIP",
        58: "IPv6-ICMP",
        59: "IPv6-NoNxt",
        60: "IPv6-Opts",
        62: "CFTP",
        64: "SAT-EXPAK",
        65: "KRYPTOLAN",
        66: "RVD",
        67: "IPPC",
        69: "SAT-MON",
        70: "VISA",
        71: "IPCV",
        72: "CPNX",
        73: "CPHB",
        74: "WSN",
        75: "PVP",
        76: "BR-SAT-MON",
        77: "SUN-ND",
        78: "WB-MON",
        79: "WB-EXPAK",
        80: "ISO-IP",
        81: "VMTP",
        82: "SECURE-VMTP",
        83: "VINES",
        84: "IPTM",
        85: "NSFNET-IGP",
        86: "DGP",
        87: "TCF",
        88: "EIGRP",
        89: "OSPFIGP",
        90: "Sprite-RPC",
        91: "LARP",
        92: "MTP",
        93: "AX.25",
        94: "IPIP",
        95: "MICP",
        96: "SCC-SP",
        97: "ETHERIP",
        98: "ENCAP",
        100: "GMTP",
        101: "IFMP",
        102: "PNNI",
        103: "PIM",
        104: "ARIS",
        105: "SCPS",
        106: "QNX",
        107: "A/N",
        108: "IPComp",
        109: "SNP",
        110: "Compaq-Peer",
        111: "IPX-in-IP",
        112: "VRRP",
        113: "PGM",
        115: "L2TP",
        116: "DDX",
        117: "IATP",
        118: "STP",
        119: "SRP",
        120: "UTI",
        121: "SMP",
        122: "SM",
        123: "PTP",
        124: "ISIS",
        125: "FIRE",
        126: "CRTP",
        127: "CRUDP",
        128: "SSCOPMCE",
        129: "IPLT",
        130: "SPS",
        131: "PIPE",
        132: "SCTP",
        133: "FC",
        134: "RSVP-E2E-IGNORE",
        135: "Mobility",
        136: "UDPLite",
        137: "MPLS-in-IP",
        138: "manet",
        139: "HIP",
        140: "Shim6",
        141: "WESP",
        142: "ROHC",
    }
    return protocol_map.get(int(protocol), protocol)


def process_log_status(log_status, tags, timestamp):
    stats.increment(
        "log_status", tags=["status:%s" % log_status] + tags, timestamp=timestamp
    )


def process_action(action, tags, timestamp):
    stats.increment("action", tags=["action:%s" % action] + tags, timestamp=timestamp)


def process_duration(start, end, tags, timestamp):
    stats.histogram(
        "duration.per_request",
        int(int(end) - int(start)),
        tags=tags,
        timestamp=timestamp,
    )


def process_packets(packets, tags, timestamp):
    try:
        stats.histogram(
            "packets.per_request", int(packets), tags=tags, timestamp=timestamp
        )
        stats.increment("packets.total", int(packets), tags=tags, timestamp=timestamp)
    except ValueError:
        pass


def process_bytes(_bytes, tags, timestamp):
    try:
        stats.histogram(
            "bytes.per_request", int(_bytes), tags=tags, timestamp=timestamp
        )
        stats.increment("bytes.total", int(_bytes), tags=tags, timestamp=timestamp)
    except ValueError:
        pass


class Stats(object):
    def _initialize(self):
        self.counts = defaultdict(lambda: defaultdict(lambda: defaultdict(int)))
        self.histograms = defaultdict(lambda: defaultdict(lambda: defaultdict(list)))

    def __init__(self):
        self._initialize()
        self.metric_prefix = "aws.vpc.flowlogs"
        # limit input size at 3.2MB see https://docs.datadoghq.com/api/latest/metrics/#submit-metrics
        # set to 3MB to account for the overhead of the json encoding
        self.max_batch_size_bytes = 3000000

    def increment(self, metric, value=1, timestamp=None, tags=None):
        metric_name = "%s.%s" % (self.metric_prefix, metric)
        timestamp = timestamp or int(time.time())
        _tags = ",".join(sorted(tags))
        self.counts[metric_name][_tags][timestamp] += value

    def histogram(self, metric, value=1, timestamp=None, tags=None):
        metric_name = "%s.%s" % (self.metric_prefix, metric)
        timestamp = timestamp or int(time.time())
        _tags = ",".join(sorted(tags))
        self.histograms[metric_name][_tags][timestamp].append(value)

    def flush(self):
        percentiles_to_submit = [0, 50, 90, 95, 99, 100]
        series = []
        for metric_name, count_payload in self.counts.items():
            for tag_set, datapoints in count_payload.items():
                points = [(ts, val) for ts, val in datapoints.items()]
                series.append(
                    {
                        "metric": metric_name,
                        "points": points,
                        "type": "count",
                        "tags": tag_set.split(","),
                    }
                )

        for metric_name, histogram_payload in self.histograms.items():
            for tag_set, datapoints in histogram_payload.items():
                percentiles = defaultdict(list)
                for ts, values in datapoints.items():
                    values.sort()
                    total_points = len(values)
                    for pct in percentiles_to_submit:
                        percentiles[pct].append(
                            (ts, values[max(0, int((pct - 1) * total_points / 100))])
                        )

                for pct, points in percentiles.items():
                    metric_suffix = "p%s" % pct
                    if pct == 0:
                        metric_suffix = "min"
                    if pct == 50:
                        metric_suffix = "median"
                    if pct == 100:
                        metric_suffix = "max"
                    series.append(
                        {
                            "metric": "%s.%s" % (metric_name, metric_suffix),
                            "points": points,
                            "type": "gauge",
                            "tags": tag_set.split(","),
                        }
                    )

        self._initialize()

        creds = urlencode(datadog_keys)
        url = "%s?%s" % (
            datadog_keys.get("api_host", "https://api.%s/api/v1/series" % DD_SITE),
            creds,
        )
        batches = self.batch_series(series)
        for batch in batches:
            metrics_dict = {
                "series": batch,
            }
            data = json.dumps(metrics_dict).encode("utf-8")
            req = Request(url, data, {"Content-Type": "application/json"})
            response = urlopen(req)
            logger.info(f"INFO Submitted data with status {response.getcode()}")

    def batch_series(self, series):
        batches = []
        batch = []
        size_bytes = 0
        for s in series:
            item_size_bytes = self._sizeof_bytes(s)
            if size_bytes + item_size_bytes > self.max_batch_size_bytes:
                batches.append(batch)
                batch = []
                size_bytes = 0
            # all items exceeding max_item_size_bytes are dropped here
            if item_size_bytes > self.max_batch_size_bytes:
                continue
            batch.append(s)
            size_bytes += item_size_bytes
        # add the last batch if it's not empty
        if size_bytes > 0:
            batches.append(batch)
        return batches

    def _sizeof_bytes(self, item):
        return len(str(item).encode("UTF-8"))


stats = Stats()


def lambda_handler(event, context):
    # event is a dict containing a base64 string gzipped
    with gzip.GzipFile(
        fileobj=BytesIO(base64.b64decode(event["awslogs"]["data"]))
    ) as decompress_stream:
        data = b"".join(BufferedReader(decompress_stream))

    event = json.loads(data)
    function_arn = context.invoked_function_arn
    # 'arn:aws:lambda:us-east-1:1234123412:function:VPCFlowLogs'
    region, account = function_arn.split(":", 5)[3:5]

    tags = ["region:%s" % region, "aws_account:%s" % account]
    unsupported_messages = 0

    node_ip = compute_node_ip(event["logEvents"])

    for event in event["logEvents"]:
        message = event["message"]
        if message[0] != "2":
            unsupported_messages += 1
            continue
        timestamp = event["timestamp"] / 1000
        process_message(message, tags, timestamp, node_ip)

    if unsupported_messages:
        logger.info("Unsupported vpc flowlog message type, please contact Datadog")
        stats.increment("unsupported_message", value=unsupported_messages, tags=tags)

    stats.flush()
