# Unless explicitly stated otherwise all files in this repository are licensed
# under the Apache License Version 2.0.
# This product includes software developed at Datadog (https://www.datadoghq.com/).
# Copyright 2021 Datadog, Inc.

# Deploying
# https://docs.aws.amazon.com/lambda/latest/dg/python-package.html
# zip -g vpc-lambda-datadog-api-client.zip lambda_function.py
# aws-vault exec sandbox-account-admin -- aws lambda update-function-code --function-name TGVPCFlowLogsForwarder --zip-file fileb://vpc-lambda-datadog-api-client.zip
import logging, os, gzip, json, time, base64, datetime
from collections import defaultdict
from urllib.request import Request, urlopen
from urllib.parse import urlencode
from datadog_api_client.v2 import ApiClient, Configuration
from datadog_api_client.v2.api.logs_api import LogsApi

import boto3, botocore


logger = logging.getLogger()
logger.setLevel(logging.getLevelName(os.environ.get("DD_LOG_LEVEL", "INFO").upper()))

logger.info("Loading function")

DD_SITE = os.getenv("DD_SITE", default="datadoghq.com")

def _datadog_keys():
    if 'kmsEncryptedKeys' in os.environ:
        KMS_ENCRYPTED_KEYS = os.environ['kmsEncryptedKeys']
        kms = boto3.client('kms')
        # kmsEncryptedKeys should be created through the Lambda's encryption
        # helpers and as such will have the EncryptionContext
        return json.loads(kms.decrypt(
            CiphertextBlob=base64.b64decode(KMS_ENCRYPTED_KEYS),
            EncryptionContext={'LambdaFunctionName': os.environ['AWS_LAMBDA_FUNCTION_NAME']},
        )['Plaintext'])

    if 'DD_API_KEY_SECRET_ARN' in os.environ:
        SECRET_ARN = os.environ['DD_API_KEY_SECRET_ARN']
        DD_API_KEY = boto3.client('secretsmanager').get_secret_value(SecretId=SECRET_ARN)['SecretString']
        return {'api_key': DD_API_KEY}

    if 'DD_API_KEY_SSM_NAME' in os.environ:
        SECRET_NAME = os.environ['DD_API_KEY_SSM_NAME']
        DD_API_KEY = boto3.client('ssm').get_parameter(
            Name=SECRET_NAME, WithDecryption=True
        )['Parameter']['Value']
        return {'api_key': DD_API_KEY}

    if 'DD_KMS_API_KEY' in os.environ:
        ENCRYPTED = os.environ['DD_KMS_API_KEY']

        # For interop with other DD Lambdas taking in DD_KMS_API_KEY, we'll
        # optionally try the EncryptionContext associated with this Lambda.
        try:
            DD_API_KEY = boto3.client('kms').decrypt(
                CiphertextBlob=base64.b64decode(ENCRYPTED),
                EncryptionContext={'LambdaFunctionName': os.environ['AWS_LAMBDA_FUNCTION_NAME']},
            )['Plaintext']
        except botocore.exceptions.ClientError:
            DD_API_KEY = boto3.client('kms').decrypt(
                CiphertextBlob=base64.b64decode(ENCRYPTED),
            )['Plaintext']

        if type(DD_API_KEY) is bytes:
            DD_API_KEY = DD_API_KEY.decode('utf-8')
        return {'api_key': DD_API_KEY}

    if 'DD_API_KEY' in os.environ:
        DD_API_KEY = os.environ['DD_API_KEY']
        return {'api_key': DD_API_KEY}

    raise ValueError("Datadog API key is not defined, see documentation for environment variable options")


# Preload the keys so we can bail out early if they're misconfigured
# Alternatively set datadog keys directly
# datadog_keys = {
#     "api_key": "abcd",
#     "app_key": "efgh",
# }
datadog_keys = _datadog_keys()
logger.info("Lambda function initialized, ready to send metrics and logs")

# Shared tags for logs
DD_SOURCE="vpc"
DD_TAGS=["env:staging", "version:0.0.1"]
DD_SERVICE="vpc"


def process_log(vpc_log):

    row = vpc_log.split(" ")
    if len(row) != 14:
        return None
    # This has to match VPC Flow Logs filter
    version, account_id, interface_id, srcaddr, dstaddr, srcport, dstport, protocol, packets, _bytes, start, end, action, log_status = vpc_log.split(" ")
    
    protocol_name = protocol_id_to_name(protocol)
    
    enrichment_tags = [
        "interface_id:%s" % interface_id,
        "protocol:%s" % protocol_name,
        "aws_account:%s" % account_id,
    ]

    process_log_status(log_status, enrichment_tags)

    # NODATA is not interesting to send to datadog
    if log_status == 'NODATA':
        return None
    
    start_timestamp = int(start) if len(start) > 1 else None
    process_action(action, enrichment_tags, start_timestamp)
    process_duration(start, end, enrichment_tags, start_timestamp)
    process_packets(packets, enrichment_tags, start_timestamp)
    process_bytes(_bytes, enrichment_tags, start_timestamp)

    # Details about fields 
    # https://docs.aws.amazon.com/vpc/latest/userguide/flow-logs.html
    enriched_vpc_flow_logs = {
        "ddsource": DD_SOURCE,
        "ddtags": ",".join(DD_TAGS),
        "hostname": "",
        "message": vpc_log, 
        "service": DD_SERVICE,
        "src": {
            "ip":srcaddr,
            "port":srcport
        },
        "dst": {
            "ip":dstaddr,
            "port":dstport
        },
        # VPC Flow Logs version is not really interesting
        #"version": version,
        "account_id": account_id,
        "interface_id":interface_id,
        "protocol":protocol_id_to_name(protocol),
        "start": {
            "timestamp": start,
            "human_date": datetime.datetime.utcfromtimestamp(int(start)).strftime('%Y-%m-%dT%H:%M:%SZ')
        },
        "end": {
            "timestamp": end,
            "human_date": datetime.datetime.utcfromtimestamp(int(end)).strftime('%Y-%m-%dT%H:%M:%SZ')
        },
        "action":action
    }
    return enriched_vpc_flow_logs


def protocol_id_to_name(protocol):
    if protocol == '-':
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
        84: "TTP",
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


def process_log_status(log_status, tags):
    stats.increment("log_status", tags=["status:%s" % log_status] + tags)


def process_action(action, tags, timestamp):
    stats.increment("action", tags=["action:%s" % action] + tags, timestamp=timestamp)


def process_duration(start, end, tags, timestamp):
    stats.histogram("duration.per_request", int(int(end) - int(start)), tags=tags, timestamp=timestamp)


def process_packets(packets, tags, timestamp):
    try:
        stats.histogram("packets.per_request", int(packets), tags=tags, timestamp=timestamp)
        stats.increment("packets.total", int(packets), tags=tags, timestamp=timestamp)
    except ValueError:
        pass


def process_bytes(_bytes, tags, timestamp):
    try:
        stats.histogram("bytes.per_request", int(_bytes), tags=tags, timestamp=timestamp)
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

    def increment(self, metric, value=1, timestamp=None, tags=None):
        metric_name = '%s.%s' % (self.metric_prefix, metric)
        timestamp = timestamp or int(time.time())
        _tags = ','.join(sorted(tags))
        self.counts[metric_name][_tags][timestamp] += value

    def histogram(self, metric, value=1, timestamp=None, tags=None):
        metric_name = '%s.%s' % (self.metric_prefix, metric)
        timestamp = timestamp or int(time.time())
        _tags = ','.join(sorted(tags))
        self.histograms[metric_name][_tags][timestamp].append(value)

    def flush(self):
        percentiles_to_submit = [0, 50, 90, 95, 99, 100]
        series = []
        for metric_name, count_payload in self.counts.items():
            for tag_set, datapoints in count_payload.items():
                points = [(ts, val) for ts, val in datapoints.items()]
                series.append(
                    {
                        'metric': metric_name,
                        'points': points,
                        'type': 'count',
                        'tags': tag_set.split(','),
                    }
                )

        for metric_name, histogram_payload in self.histograms.items():
            for tag_set, datapoints in histogram_payload.items():
                percentiles = defaultdict(list)
                for ts, values in datapoints.items():
                    values.sort()
                    total_points = len(values)
                    for pct in percentiles_to_submit:
                        percentiles[pct].append((ts, values[max(0, int((pct - 1) * total_points / 100))]))

                for pct, points in percentiles.items():
                    metric_suffix = 'p%s' % pct
                    if pct == 0:
                        metric_suffix = 'min'
                    if pct == 50:
                        metric_suffix = 'median'
                    if pct == 100:
                        metric_suffix = 'max'
                    series.append(
                        {
                            'metric': '%s.%s' % (metric_name, metric_suffix),
                            'points': points,
                            'type': 'gauge',
                            'tags': tag_set.split(','),
                        }
                    )

        self._initialize()

        metrics_dict = {
            'series': series,
        }

        creds = urlencode(datadog_keys)
        data = json.dumps(metrics_dict).encode('utf-8')
        url = '%s?%s' % (datadog_keys.get('api_host', 'https://app.%s/api/v1/series' % DD_SITE), creds)
        req = Request(url, data, {'Content-Type': 'application/json'})
        response = urlopen(req)
        logger.info(f"Submitted metric with status {response.getcode()}")

stats = Stats()


def lambda_handler(event, context):
    # event :
    #     {
    #         "version": "0",
    #         "id": "50294b5a-6311-8d5e-eb78-e67e6df443d8",
    #         "detail-type": "Object Created",
    #         "source": "aws.s3",
    #         "account": "601427279990",
    #         "time": "2022-03-11T15:50:41Z",
    #         "region": "us-east-1",
    #         "resources": [
    #             "arn:aws:s3:::tg-tests"
    #         ],
    #         "detail": {
    #             "version": "0",
    #             "bucket": {
    #               "name": "tg-tests"
    #             },
    #             "object": {
    #                "key": "AWSLogs/601427279990/vpcflowlogs/us-east-1/2022/03/11/601427279990_vpcflowlogs_us-east-1_fl-0be887e94241898f5_20220311T1545Z_d884c282.log.gz",
    #                "size": 1976,
    #                "etag": "535c762f8ac25e699c70c846262556d8",
    #                "sequencer": "00622B6FD186A86500"
    #             },
    #             "request-id": "M5GCEAE282J9S367",
    #             "requester": "delivery.logs.amazonaws.com",
    #             "source-ip-address": "10.106.141.176",
    #             "reason": "PutObject"
    #         }
    #     }

    bucket = event["detail"]["bucket"]["name"]
    key = event["detail"]["object"]["key"]

    s3 = boto3.resource('s3')

    obj = s3.Object(bucket, key)
    with gzip.GzipFile(fileobj=obj.get()["Body"]) as gzipfile:
        data = gzipfile.read().decode("utf-8")  

    # data is
    # version account-id interface-id srcaddr dstaddr srcport dstport protocol packets bytes start end action log-status
    # 2 601427279990 eni-037792999a8d5fc10 3.233.146.100 172.26.1.100 443 57012 6 20 7571 1646956720 1646956838 ACCEPT OK
    # ...
    
    processed_vpc_flow_logs = list()
    # for each line of the file
    for vpc_log in data.split("\n"):
        # we don't want to process the header
        if vpc_log.startswith("version"):
            continue

        enriched_vpc_flow_lgos = process_log(vpc_log)
        if enriched_vpc_flow_lgos:
            processed_vpc_flow_logs.append(enriched_vpc_flow_lgos)
    
    configuration = Configuration()
    configuration.api_key["apiKeyAuth"] = datadog_keys.get("api_key")
    with ApiClient(configuration) as api_client:
        api_instance = LogsApi(api_client)
        response = api_instance.submit_log(content_encoding="gzip", body=processed_vpc_flow_logs)

    logger.info(f"Submitted {len(processed_vpc_flow_logs)} VPC Flow Logs to Datadog")

    stats.flush()
