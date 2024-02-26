# Unless explicitly stated otherwise all files in this repository are licensed
# under the Apache License Version 2.0.
# This product includes software developed at Datadog (https://www.datadoghq.com/).
# Copyright 2021 Datadog, Inc.

import json
import os
import boto3
import logging
import requests
from datadog_lambda.wrapper import datadog_lambda_wrapper
from datadog import api
from enhanced_lambda_metrics import parse_and_submit_enhanced_metrics
from parsing import parse
from enrichment import enrich
from transformation import transform
from splitting import split
from forwarder import (
    forward_metrics,
    forward_traces,
    forward_logs,
)
from settings import (
    DD_API_KEY,
    DD_FORWARD_LOG,
    DD_SKIP_SSL_VALIDATION,
    DD_API_URL,
    DD_FORWARDER_VERSION,
    DD_ADDITIONAL_TARGET_LAMBDAS,
)

logger = logging.getLogger()
logger.setLevel(logging.getLevelName(os.environ.get("DD_LOG_LEVEL", "INFO").upper()))

# DD_API_KEY must be set
if DD_API_KEY == "<YOUR_DATADOG_API_KEY>" or DD_API_KEY == "":
    raise Exception("Missing Datadog API key")
# Check if the API key is the correct number of characters
if len(DD_API_KEY) != 32:
    raise Exception(
        "The API key is not the expected length. "
        "Please confirm that your API key is correct"
    )
# Validate the API key
logger.debug("Validating the Datadog API key")
validation_res = requests.get(
    "{}/api/v1/validate?api_key={}".format(DD_API_URL, DD_API_KEY),
    verify=(not DD_SKIP_SSL_VALIDATION),
    timeout=10,
)
if not validation_res.ok:
    raise Exception("The API key is not valid.")

# Force the layer to use the exact same API key and host as the forwarder
api._api_key = DD_API_KEY
api._api_host = DD_API_URL
api._cacert = not DD_SKIP_SSL_VALIDATION


def datadog_forwarder(event, context):
    """The actual lambda function entry point"""
    if logger.isEnabledFor(logging.DEBUG):
        logger.debug(f"Received Event:{json.dumps(event)}")
        logger.debug(f"Forwarder version: {DD_FORWARDER_VERSION}")

    if DD_ADDITIONAL_TARGET_LAMBDAS:
        invoke_additional_target_lambdas(event)

    metrics, logs, trace_payloads = split(transform(enrich(parse(event, context))))

    if DD_FORWARD_LOG:
        forward_logs(logs)

    forward_metrics(metrics)

    if len(trace_payloads) > 0:
        forward_traces(trace_payloads)

    parse_and_submit_enhanced_metrics(logs)


def invoke_additional_target_lambdas(event):
    lambda_client = boto3.client("lambda")
    lambda_arns = DD_ADDITIONAL_TARGET_LAMBDAS.split(",")
    lambda_payload = json.dumps(event)

    for lambda_arn in lambda_arns:
        try:
            lambda_client.invoke(
                FunctionName=lambda_arn,
                InvocationType="Event",
                Payload=lambda_payload,
            )
        except Exception as e:
            logger.exception(
                f"Failed to invoke additional target lambda {lambda_arn} due to {e}"
            )

    return


lambda_handler = datadog_lambda_wrapper(datadog_forwarder)
