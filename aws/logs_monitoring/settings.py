# Unless explicitly stated otherwise all files in this repository are licensed
# under the Apache License Version 2.0.
# This product includes software developed at Datadog (https://www.datadoghq.com/).
# Copyright 2018 Datadog, Inc.

import base64
import os

import boto3
import logging
import re


logger = logging.getLogger()
logger.setLevel(logging.getLevelName(os.environ.get("DD_LOG_LEVEL", "INFO").upper()))


def get_env_var(envvar, default, boolean=False):
    """
    Return the value of the given environment variable with debug logging.
    When boolean=True, parse the value as a boolean case-insensitively.
    """
    value = os.getenv(envvar, default=default)
    if boolean:
        value = value.lower() == "true"
    logger.debug(f"{envvar}: {value}")
    return value


## @param DD_API_KEY - String - conditional - default: none
## The Datadog API key associated with your Datadog Account
## It can be found here:
##
##   * Datadog US Site: https://app.datadoghq.com/account/settings#api
##   * Datadog EU Site: https://app.datadoghq.eu/account/settings#api
##
## Must be set if one of the following is not set: DD_API_KEY_SECRET_ARN, DD_API_KEY_SSM_NAME, DD_KMS_API_KEY
#
DD_API_KEY = "<YOUR_DATADOG_API_KEY>"

## @param DD_API_KEY_SECRET_ARN - String - optional - default: none
## ARN of Datadog API key stored in AWS Secrets Manager
##
## Supercedes: DD_API_KEY_SSM_NAME, DD_KMS_API_KEY, DD_API_KEY

## @param DD_API_KEY_SSM_NAME - String - optional - default: none
## Name of parameter containing Datadog API key in AWS SSM Parameter Store
##
## Supercedes: DD_KMS_API_KEY, DD_API_KEY

## @param DD_KMS_API_KEY - String - optional - default: none
## AWS KMS encrypted Datadog API key
##
## Supercedes: DD_API_KEY

## @param DD_FORWARD_LOG - boolean - optional - default: true
## Set this variable to `False` to disable log forwarding.
## E.g., when you only want to forward metrics and traces from logs.
#
DD_FORWARD_LOG = get_env_var("DD_FORWARD_LOG", "true", boolean=True)

## @param DD_USE_TCP - boolean - optional -default: false
## Change this value to `true` to send your logs and metrics using the TCP network client
## By default, it uses the HTTP client.
#
DD_USE_TCP = get_env_var("DD_USE_TCP", "false", boolean=True)

## @param DD_USE_COMPRESSION - boolean - optional -default: true
## Only valid when sending logs over HTTP
## Change this value to `false` to send your logs without any compression applied
## By default, compression is enabled.
#
DD_USE_COMPRESSION = get_env_var("DD_USE_COMPRESSION", "true", boolean=True)

## @param DD_USE_COMPRESSION - integer - optional -default: 6
## Change this value to set the compression level.
## Values range from 0 (no compression) to 9 (best compression).
## By default, compression is set to level 6.
#
DD_COMPRESSION_LEVEL = int(os.getenv("DD_COMPRESSION_LEVEL", 6))

## @param DD_USE_SSL - boolean - optional -default: false
## Change this value to `true` to disable SSL
## Useful when you are forwarding your logs to a proxy.
#
DD_NO_SSL = get_env_var("DD_NO_SSL", "false", boolean=True)

## @param DD_SKIP_SSL_VALIDATION - boolean - optional -default: false
## Disable SSL certificate validation when forwarding logs via HTTP.
#
DD_SKIP_SSL_VALIDATION = get_env_var("DD_SKIP_SSL_VALIDATION", "false", boolean=True)

## @param DD_SITE - String - optional -default: datadoghq.com
## Define the Datadog Site to send your logs and metrics to.
## Set it to `datadoghq.eu` to send your logs and metrics to Datadog EU site.
#
DD_SITE = get_env_var("DD_SITE", default="datadoghq.com")

## @param DD_TAGS - list of comma separated strings - optional -default: none
## Pass custom tags as environment variable or through this variable.
## Ensure your tags are a comma separated list of strings with no trailing comma in the envvar!
#
DD_TAGS = get_env_var("DD_TAGS", "")

## @param DD_API_URL - Url to use for  validating the the api key.
DD_API_URL = get_env_var(
    "DD_API_URL",
    default="{}://api.{}".format("http" if DD_NO_SSL else "https", DD_SITE),
)

## @param DD_TRACE_INTAKE_URL
DD_TRACE_INTAKE_URL = get_env_var(
    "DD_TRACE_INTAKE_URL",
    default="{}://trace.agent.{}".format("http" if DD_NO_SSL else "https", DD_SITE),
)

if DD_USE_TCP:
    DD_URL = get_env_var("DD_URL", default="lambda-intake.logs." + DD_SITE)
    try:
        if "DD_SITE" in os.environ and DD_SITE == "datadoghq.eu":
            DD_PORT = int(get_env_var("DD_PORT", default="443"))
        else:
            DD_PORT = int(get_env_var("DD_PORT", default="10516"))
    except Exception:
        DD_PORT = 10516
else:
    DD_URL = get_env_var("DD_URL", default="lambda-http-intake.logs." + DD_SITE)
    DD_PORT = int(get_env_var("DD_PORT", default="443"))

## @param DD_USE_PRIVATE_LINK - whether to forward logs via PrivateLink
## Overrides incompatible settings
#
DD_USE_PRIVATE_LINK = get_env_var("DD_USE_PRIVATE_LINK", "false", boolean=True)
if DD_USE_PRIVATE_LINK:
    logger.debug("Private link enabled, overriding configuration settings")
    # Only the US Datadog site is supported when PrivateLink is enabled
    DD_SITE = "datadoghq.com"
    # TCP isn't supported when PrivateLink is enabled
    DD_USE_TCP = False
    DD_NO_SSL = False
    DD_PORT = 443
    # Override URLs
    DD_URL = "api-pvtlink.logs.datadoghq.com"
    DD_API_URL = "https://pvtlink.api.datadoghq.com"
    DD_TRACE_INTAKE_URL = "https://trace-pvtlink.agent.datadoghq.com"


class ScrubbingRuleConfig(object):
    def __init__(self, name, pattern, placeholder):
        self.name = name
        self.pattern = pattern
        self.placeholder = placeholder


# Scrubbing sensitive data
# Option to redact all pattern that looks like an ip address / email address / custom pattern
SCRUBBING_RULE_CONFIGS = [
    ScrubbingRuleConfig(
        "REDACT_IP", "\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}", "xxx.xxx.xxx.xxx"
    ),
    ScrubbingRuleConfig(
        "REDACT_EMAIL",
        "[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+",
        "xxxxx@xxxxx.com",
    ),
    ScrubbingRuleConfig(
        "DD_SCRUBBING_RULE",
        get_env_var("DD_SCRUBBING_RULE", default=None),
        get_env_var("DD_SCRUBBING_RULE_REPLACEMENT", default="xxxxx"),
    ),
]

# Filtering logs
# Option to include or exclude logs based on a pattern match
INCLUDE_AT_MATCH = get_env_var("INCLUDE_AT_MATCH", default=None)
EXCLUDE_AT_MATCH = get_env_var("EXCLUDE_AT_MATCH", default=None)

# DD API Key
if "DD_API_KEY_SECRET_ARN" in os.environ:
    SECRET_ARN = os.environ["DD_API_KEY_SECRET_ARN"]
    DD_API_KEY = boto3.client("secretsmanager").get_secret_value(SecretId=SECRET_ARN)[
        "SecretString"
    ]
elif "DD_API_KEY_SSM_NAME" in os.environ:
    SECRET_NAME = os.environ["DD_API_KEY_SSM_NAME"]
    DD_API_KEY = boto3.client("ssm").get_parameter(
        Name=SECRET_NAME, WithDecryption=True
    )["Parameter"]["Value"]
elif "DD_KMS_API_KEY" in os.environ:
    ENCRYPTED = os.environ["DD_KMS_API_KEY"]
    DD_API_KEY = boto3.client("kms").decrypt(
        CiphertextBlob=base64.b64decode(ENCRYPTED)
    )["Plaintext"]
    if type(DD_API_KEY) is bytes:
        DD_API_KEY = DD_API_KEY.decode("utf-8")
elif "DD_API_KEY" in os.environ:
    DD_API_KEY = os.environ["DD_API_KEY"]

# Strip any trailing and leading whitespace from the API key
DD_API_KEY = DD_API_KEY.strip()
os.environ["DD_API_KEY"] = DD_API_KEY

# DD_MULTILINE_LOG_REGEX_PATTERN: Multiline Log Regular Expression Pattern
DD_MULTILINE_LOG_REGEX_PATTERN = get_env_var(
    "DD_MULTILINE_LOG_REGEX_PATTERN", default=None
)

DD_SOURCE = "ddsource"
DD_CUSTOM_TAGS = "ddtags"
DD_SERVICE = "service"
DD_HOST = "host"
DD_FORWARDER_VERSION = "3.18.0"

# Additional target lambda invoked async with event data
DD_ADDITIONAL_TARGET_LAMBDAS = get_env_var("DD_ADDITIONAL_TARGET_LAMBDAS", default=None)
