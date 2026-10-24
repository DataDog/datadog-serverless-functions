# Unless explicitly stated otherwise all files in this repository are licensed
# under the Apache License Version 2.0.
# This product includes software developed at Datadog (https://www.datadoghq.com/).
# Copyright 2026 Datadog, Inc.

import base64
import json
import logging
import os
import time

import boto3
import requests
from botocore.auth import SigV4Auth
from botocore.awsrequest import AWSRequest

logger = logging.getLogger()
logger.setLevel(logging.getLevelName(os.environ.get("DD_LOG_LEVEL", "INFO").upper()))

INTAKE_KEY_PATH = "/api/v2/intake-key"
GET_CALLER_IDENTITY_BODY = "Action=GetCallerIdentity&Version=2011-06-15"
STS_CONTENT_TYPE = "application/x-www-form-urlencoded; charset=utf-8"
ORG_ID_HEADER = "X-Ddog-Org-Id"
RETRY_AFTER_FAILURE_SECONDS = 60


class DelegatedAuthError(Exception):
    pass


def b64(value):
    return base64.b64encode(value.encode("utf-8")).decode("utf-8")


def generate_auth_proof(credentials, region, org_uuid):
    """
    Sign an STS GetCallerIdentity request for Datadog to replay. The org UUID
    is a signed header, so the proof is only valid for that organization.
    """
    sts_host = f"sts.{region}.amazonaws.com"
    sts_url = f"https://{sts_host}"
    request = AWSRequest(
        method="POST",
        url=sts_url,
        data=GET_CALLER_IDENTITY_BODY,
        headers={
            "Content-Type": STS_CONTENT_TYPE,
            "Host": sts_host,
            ORG_ID_HEADER: org_uuid,
        },
    )
    SigV4Auth(credentials, "sts", region).add_auth(request)
    headers = {name: [value] for name, value in request.headers.items()}
    return "|".join(
        [
            b64(GET_CALLER_IDENTITY_BODY),
            b64(json.dumps(headers, sort_keys=True)),
            "POST",
            b64(sts_url),
        ]
    )


def fetch_delegated_api_key(api_url, org_uuid, region, verify=True, timeout=(3, 5)):
    """Exchange the function's AWS credentials for a Datadog API key."""
    credentials = boto3.Session().get_credentials()
    if credentials is None:
        raise DelegatedAuthError("No AWS credentials are available for delegated auth")

    proof = generate_auth_proof(credentials.get_frozen_credentials(), region, org_uuid)
    with requests.Session() as session:
        # urllib3 does not retry POST unless allowed_methods is None.
        retries = requests.adapters.Retry(
            total=2,
            backoff_factor=0.5,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=None,
        )
        session.mount("http://", requests.adapters.HTTPAdapter(max_retries=retries))
        session.mount("https://", requests.adapters.HTTPAdapter(max_retries=retries))
        response = session.post(
            f"{api_url}{INTAKE_KEY_PATH}",
            headers={
                "Authorization": f"Delegated {proof}",
                "Content-Type": "application/json",
            },
            data="",
            timeout=timeout,
            verify=verify,
        )
    if not response.ok:
        raise DelegatedAuthError(
            f"Datadog rejected the delegated auth request (HTTP {response.status_code}). "
            "Check that an AWS intake mapping authorizes this function's execution role."
        )

    api_key = response.json().get("data", {}).get("attributes", {}).get("api_key", "")
    if not api_key:
        raise DelegatedAuthError("Datadog returned no API key for delegated auth")
    return api_key.strip()


class DelegatedApiKey:
    """
    Holds an API key minted through delegated auth and re-mints it once it is
    older than the refresh interval, or after invalidate(). Attempts after the
    first are at least RETRY_AFTER_FAILURE_SECONDS apart, so a rejection that
    a new key does not cure cannot trigger a mint on every invocation.
    """

    def __init__(self, fetch, refresh_interval_seconds, clock=None):
        self._fetch = fetch
        self._refresh_interval_seconds = refresh_interval_seconds
        self._clock = clock or time.monotonic
        self._api_key = None
        self._minted_at = None
        self._last_attempt = None
        self._invalidated = False

    def get(self):
        if self._api_key is None or self._is_due():
            self._refresh()
        return self._api_key

    def invalidate(self):
        self._invalidated = True

    def _is_due(self):
        now = self._clock()
        if now - self._last_attempt < RETRY_AFTER_FAILURE_SECONDS:
            return False
        return (
            self._invalidated or now - self._minted_at >= self._refresh_interval_seconds
        )

    def _refresh(self):
        self._last_attempt = self._clock()
        try:
            api_key = self._fetch()
        except Exception as e:
            if self._api_key is None:
                raise
            logger.error(f"Failed to refresh the delegated Datadog API key: {e}")
            return

        self._api_key = api_key
        self._minted_at = self._last_attempt
        self._invalidated = False
        logger.info("Obtained a Datadog API key through delegated auth")
