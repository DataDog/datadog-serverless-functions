import io
import json
import logging
import os
import gzip

from fdk import context, response
import requests
from requests.adapters import HTTPAdapter
from requests.exceptions import HTTPError


logger = logging.getLogger(__name__)


OUTPUT_MESSAGE_VERSION = "v1.0"

_max_pool = int(os.environ.get("DD_MAX_POOL", 10))
_session = requests.Session()
_session.mount("https://", HTTPAdapter(pool_connections=_max_pool))


def _get_serialized_metric_data(raw_metrics: io.BytesIO) -> str:
    return raw_metrics.getvalue().decode("utf-8")


def _generate_metrics_msg(
    ctx: context.InvokeContext,
    serialized_metric_data: str,
) -> str:
    tenancy_ocid = os.environ.get("TENANCY_OCID")

    if not tenancy_ocid:
        raise ValueError("Missing environment variable: TENANCY_OCID")

    # Bump OUTPUT_MESSAGE_VERSION any time this
    # structure gets updated
    message_dict = {
        "version": OUTPUT_MESSAGE_VERSION,
        "payload": {
            "headers": {
                "tenancy_ocid": tenancy_ocid,
                "source_fn_app_ocid": ctx.AppID(),
                "source_fn_app_name": ctx.AppName(),
                "source_fn_ocid": ctx.FnID(),
                "source_fn_name": ctx.FnName(),
                "source_fn_call_id": ctx.CallID(),
            },
            "body": serialized_metric_data,
        },
    }

    return json.dumps(message_dict)


def _should_compress_payload() -> bool:
    return os.environ.get("DD_COMPRESS", "false").lower() == "true"


def _send_metrics_msg_to_datadog(metrics_message: str) -> str:
    endpoint = os.environ.get("DD_INTAKE_HOST")
    api_key = os.environ.get("DD_API_KEY")

    if not endpoint or not api_key:
        raise ValueError(
            "Missing one of the following environment variables: DD_INTAKE_HOST, DD_API_KEY"
        )

    url = f"https://{endpoint}/api/v2/ocimetrics"
    api_headers = {"content-type": "application/json", "dd-api-key": api_key}

    if _should_compress_payload():
        serialized = gzip.compress(metrics_message.encode())
        api_headers["content-encoding"] = "gzip"
    else:
        serialized = metrics_message

    http_response = _session.post(url, data=serialized, headers=api_headers)
    http_response.raise_for_status()

    logger.info(
        f"Sent payload size={len(metrics_message)} encoding={api_headers.get('content-encoding', None)}"
    )
    return http_response.text


def handler(ctx: context.InvokeContext, data: io.BytesIO = None) -> response.Response:
    """
    Submits incoming metrics data to Datadog.

    Wraps incoming metrics data in a message payload and forwards this
    payload to a Datadog endpoint.

    Args:
      ctx:
        An fdk InvokeContext.
      data:
        A BytesIO stream containing a JSON representation of metrics.
        Each metric has the form:

        {
            "namespace": "<Example Namespace>",
            "resourceGroup": "<Example Resource Group>",
            "compartmentId": "<Example Compartment ID>",
            "name": "<Example Metric Name>",
            "dimensions": {
                "<Example Dimension Key>": "<Example Dimension Value>",
            },
            "metadata": {
                "<Example Metadata Key>": "<Example Metadata Value>",
            },
            "datapoints": [
                {
                    "timestamp": "<Example Timestamp in ms since Unix Epoch>",
                    "value": "<Example Value>",
                    "count": "<Example count>",
                },
            ]
        }

    Returns:
      An fdk Response in which the body contains any error
      messages encountered during processing. At present, HTTP 200
      responses will always be returned.
    """

    try:
        serialized_metric_data = _get_serialized_metric_data(
            data,
        )

        metrics_message = _generate_metrics_msg(
            ctx,
            serialized_metric_data,
        )

        result = _send_metrics_msg_to_datadog(metrics_message)
    except HTTPError as e:
        logger.exception(f"Error sending metrics to Datadog")
        result = e.response.text
    except Exception as e:
        logger.exception("Unexpected error while processing input data")
        result = str(e)

    return response.Response(
        ctx,
        response_data=json.dumps({"result": result}),
        headers={"Content-Type": "application/json"},
    )

