# Unless explicitly stated otherwise all files in this repository are licensed
# under the Apache License Version 2.0.
# This product includes software developed at Datadog (https://www.datadoghq.com/).
# Copyright 2021 Datadog, Inc.

import json
import logging
import os
from hashlib import sha1

import boto3
from datadog import api
from datadog_lambda.wrapper import datadog_lambda_wrapper

from caching.cache_layer import CacheLayer
from enhanced_lambda_metrics import parse_and_submit_enhanced_metrics
from forwarder import Forwarder
from settings import (
    DD_ADDITIONAL_TARGET_LAMBDAS,
    DD_API_KEY,
    DD_API_URL,
    DD_FORWARDER_VERSION,
    DD_RETRY_KEYWORD,
    DD_SKIP_SSL_VALIDATION,
    DD_STORE_FAILED_EVENTS,
    is_api_key_valid,
)
from steps.enrichment import enrich
from steps.parsing import parse
from steps.splitting import split
from steps.transformation import transform

logger = logging.getLogger()
logger.setLevel(logging.getLevelName(os.environ.get("DD_LOG_LEVEL", "INFO").upper()))


if not is_api_key_valid() and not DD_STORE_FAILED_EVENTS:
    raise Exception(
        "Failed to check if API Key is valid and no storage of failed events, aborting."
    )


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

    if len(event) == 1 and str(event.get(DD_RETRY_KEYWORD, "false")).lower() == "true":
        logger.info("Retry-only invocation")

        try:
            forwarder.retry()
        except Exception as e:
            if logger.isEnabledFor(logging.DEBUG):
                logger.debug(f"Failed to retry forwarding {e}")

        return

    parsed = parse(event, context, cache_layer)
    enriched = enrich(parsed, cache_layer)
    transformed = transform(enriched)
    metrics, logs, trace_payloads = split(transformed)

    forwarder.forward(logs, metrics, trace_payloads)
    parse_and_submit_enhanced_metrics(logs, cache_layer)

    try:
        if str(event.get(DD_RETRY_KEYWORD, "false")).lower() == "true":
            forwarder.retry()
    except Exception as e:
        if logger.isEnabledFor(logging.DEBUG):
            logger.debug(f"Failed to retry forwarding {e}")


def init_cache_layer(function_prefix):
    global cache_layer
    if cache_layer is None:
        # set the prefix for cache layer
        try:
            if cache_layer is None:
                cache_layer = CacheLayer(function_prefix)
        except Exception as e:
            logger.error(f"Failed to create cache layer due to {e}")
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
            logger.error(
                f"Failed to invoke additional target lambda {lambda_arn} due to {e}"
            )

    return


lambda_handler = datadog_lambda_wrapper(datadog_forwarder)
