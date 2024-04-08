# Unless explicitly stated otherwise all files in this repository are licensed
# under the Apache License Version 2.0.
# This product includes software developed at Datadog (https://www.datadoghq.com/).
# Copyright 2021 Datadog, Inc.

import json
import os
import boto3
import logging
import requests
from hashlib import sha1
from datadog_lambda.wrapper import datadog_lambda_wrapper
from datadog import api
from enhanced_lambda_metrics import parse_and_submit_enhanced_metrics
from steps.parsing import parse
from steps.enrichment import enrich
from steps.transformation import transform
from steps.splitting import split
from caching.cache_layer import CacheLayer
from forwarder import Forwarder
from settings import (
    DD_API_KEY,
    DD_SKIP_SSL_VALIDATION,
    DD_API_URL,
    DD_FORWARDER_VERSION,
    DD_ADDITIONAL_TARGET_LAMBDAS,
    DD_RETRY_KEYWORD,
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

cache_layer = None
forwarder = None


def datadog_forwarder(event, context):
    """The actual lambda function entry point"""
    if logger.isEnabledFor(logging.DEBUG):
        logger.debug(f"Received Event:{json.dumps(event)}")
        logger.debug(f"Forwarder version: {DD_FORWARDER_VERSION}")

    if DD_ADDITIONAL_TARGET_LAMBDAS:
        invoke_additional_target_lambdas(event)

    function_prefix = get_function_arn_digest(context)
    init_cache_layer(function_prefix)
    init_forwarder(function_prefix)

    parsed = parse(event, context, cache_layer)
    enriched = enrich(parsed, cache_layer)
    transformed = transform(enriched)
    metrics, logs, trace_payloads = split(transformed)

    forwarder.forward(logs, metrics, trace_payloads)
    parse_and_submit_enhanced_metrics(logs, cache_layer)

    try:
        if bool(event.get(DD_RETRY_KEYWORD, False)) is True:
            forwarder.retry()
    except Exception as e:
        if logger.isEnabledFor(logging.DEBUG):
            logger.debug(f"Failed to retry forwarding {e}")
        pass


def init_cache_layer(function_prefix):
    global cache_layer
    if cache_layer is None:
        # set the prefix for cache layer
        try:
            if cache_layer is None:
                cache_layer = CacheLayer(function_prefix)
        except Exception as e:
            logger.exception(f"Failed to create cache layer due to {e}")
            raise


def init_forwarder(function_prefix):
    global forwarder
    if forwarder is None:
        forwarder = Forwarder(function_prefix)


def get_function_arn_digest(context):
    function_arn = context.invoked_function_arn.lower()
    prefix = sha1(function_arn.encode("UTF-8")).hexdigest()
    return prefix


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
