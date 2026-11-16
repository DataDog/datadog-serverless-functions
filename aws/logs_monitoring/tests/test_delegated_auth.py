import base64
import hashlib
import hmac
import json
import os
import sys
import unittest
from importlib import reload
from unittest.mock import MagicMock, patch

from botocore.credentials import ReadOnlyCredentials

import settings  # noqa: F401  reloaded through sys.modules below
from delegated_auth import (
    GET_CALLER_IDENTITY_BODY,
    DelegatedApiKey,
    DelegatedAuthError,
    fetch_delegated_api_key,
    generate_auth_proof,
)

ORG_UUID = "00000000-0000-0000-0000-000000000000"
MINTED_API_KEY = "abcdef1234567890abcdef1234567890"
STATIC_API_KEY = "11111111111111111111111111111111"

# The header set the Datadog Lambda Extension sends; the backend replays it to STS.
PROOF_HEADERS = {"Authorization", "Content-Type", "Host", "X-Amz-Date", "X-Ddog-Org-Id"}
SIGNED_HEADERS = "content-type;host;x-amz-date;x-ddog-org-id"
SIGNED_HEADERS_WITH_TOKEN = (
    "content-type;host;x-amz-date;x-amz-security-token;x-ddog-org-id"
)


def decode(part):
    return base64.b64decode(part).decode("utf-8")


def reference_signature(secret_key, region, headers, signed_headers):
    """SigV4 as computed by the Datadog Lambda Extension's delegated auth client."""
    amz_date = headers["X-Amz-Date"][0]
    date_stamp = amz_date[:8]
    canonical_headers = "".join(
        f"{name}:{headers[next(k for k in headers if k.lower() == name)][0]}\n"
        for name in signed_headers.split(";")
    )
    payload_hash = hashlib.sha256(GET_CALLER_IDENTITY_BODY.encode()).hexdigest()
    canonical_request = (
        f"POST\n/\n\n{canonical_headers}\n{signed_headers}\n{payload_hash}"
    )
    scope = f"{date_stamp}/{region}/sts/aws4_request"
    string_to_sign = (
        f"AWS4-HMAC-SHA256\n{amz_date}\n{scope}\n"
        + hashlib.sha256(canonical_request.encode()).hexdigest()
    )

    def sign(key, msg):
        return hmac.new(key, msg.encode(), hashlib.sha256).digest()

    key = sign(f"AWS4{secret_key}".encode(), date_stamp)
    for part in (region, "sts", "aws4_request"):
        key = sign(key, part)
    return hmac.new(key, string_to_sign.encode(), hashlib.sha256).hexdigest()


class TestGenerateAuthProof(unittest.TestCase):
    def _proof(self, token):
        credentials = ReadOnlyCredentials("AKIDEXAMPLE", "secretkeyexample", token)
        parts = generate_auth_proof(credentials, "us-east-2", ORG_UUID).split("|")
        self.assertEqual(len(parts), 4)
        return parts

    def test_proof_wraps_a_signed_get_caller_identity_request(self):
        body, headers, method, url = self._proof("sessiontoken")

        self.assertEqual(decode(body), GET_CALLER_IDENTITY_BODY)
        self.assertEqual(method, "POST")
        self.assertEqual(decode(url), "https://sts.us-east-2.amazonaws.com")

        headers = json.loads(decode(headers))
        self.assertEqual(headers["X-Ddog-Org-Id"], [ORG_UUID])
        self.assertEqual(headers["X-Amz-Security-Token"], ["sessiontoken"])
        self.assertEqual(headers["Host"], ["sts.us-east-2.amazonaws.com"])

    def test_headers_match_the_extension(self):
        for token, extra, signed in (
            ("sessiontoken", {"X-Amz-Security-Token"}, SIGNED_HEADERS_WITH_TOKEN),
            (None, set(), SIGNED_HEADERS),
        ):
            with self.subTest(token=token):
                headers = json.loads(decode(self._proof(token)[1]))
                authorization = headers["Authorization"][0]

                self.assertEqual(set(headers), PROOF_HEADERS | extra)
                self.assertEqual(
                    authorization.split("SignedHeaders=")[1].split(",")[0], signed
                )
                self.assertEqual(
                    authorization.split("Signature=")[1],
                    reference_signature(
                        "secretkeyexample", "us-east-2", headers, signed
                    ),
                )


class TestFetchDelegatedApiKey(unittest.TestCase):
    def _fetch(self, response, credentials=None, **kwargs):
        session = MagicMock()
        session.return_value.get_credentials.return_value = (
            credentials
            if credentials is not None
            else MagicMock(
                get_frozen_credentials=MagicMock(
                    return_value=ReadOnlyCredentials("AKID", "secret", "token")
                )
            )
        )
        http = MagicMock()
        http.__enter__.return_value = http
        http.post.return_value = response
        with patch("delegated_auth.boto3.Session", session), patch(
            "delegated_auth.requests.Session", return_value=http
        ):
            api_key = fetch_delegated_api_key(
                "https://api.datadoghq.com", ORG_UUID, "us-east-1", **kwargs
            )
        return api_key, http.post

    def _ok(self, api_key=MINTED_API_KEY):
        response = MagicMock(ok=True)
        response.json.return_value = {"data": {"attributes": {"api_key": api_key}}}
        return response

    def test_returns_the_minted_key(self):
        api_key, post = self._fetch(self._ok())

        self.assertEqual(api_key, MINTED_API_KEY)
        self.assertEqual(
            post.call_args.args[0], "https://api.datadoghq.com/api/v2/intake-key"
        )
        self.assertTrue(
            post.call_args.kwargs["headers"]["Authorization"].startswith("Delegated ")
        )

    def test_passes_the_tls_verification_setting(self):
        _, post = self._fetch(self._ok(), verify=False)
        self.assertFalse(post.call_args.kwargs["verify"])

    def test_rejected_request_raises(self):
        with self.assertRaisesRegex(DelegatedAuthError, "HTTP 403"):
            self._fetch(MagicMock(ok=False, status_code=403))

    def test_empty_key_raises(self):
        with self.assertRaisesRegex(DelegatedAuthError, "no API key"):
            self._fetch(self._ok(api_key=""))

    def test_missing_credentials_raise(self):
        session = MagicMock()
        session.return_value.get_credentials.return_value = None
        with patch("delegated_auth.boto3.Session", session):
            with self.assertRaisesRegex(DelegatedAuthError, "No AWS credentials"):
                fetch_delegated_api_key(
                    "https://api.datadoghq.com", ORG_UUID, "us-east-1"
                )


class FakeClock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now


class TestDelegatedApiKey(unittest.TestCase):
    def setUp(self):
        self.clock = FakeClock()
        self.fetch = MagicMock(side_effect=["key-1", "key-2", "key-3"])
        self.api_key = DelegatedApiKey(self.fetch, 3600, clock=self.clock)

    def test_reuses_the_key_until_the_interval_passes(self):
        self.assertEqual(self.api_key.get(), "key-1")
        self.clock.now = 3599
        self.assertEqual(self.api_key.get(), "key-1")
        self.clock.now = 3600
        self.assertEqual(self.api_key.get(), "key-2")
        self.assertEqual(self.fetch.call_count, 2)

    def test_invalidate_re_mints_at_most_once_a_minute(self):
        self.api_key.get()
        self.api_key.invalidate()
        self.clock.now = 59
        self.assertEqual(self.api_key.get(), "key-1")
        self.clock.now = 60
        self.assertEqual(self.api_key.get(), "key-2")
        self.api_key.invalidate()
        self.clock.now = 119
        self.assertEqual(self.api_key.get(), "key-2")
        self.assertEqual(self.fetch.call_count, 2)

    def test_failed_refresh_keeps_the_current_key_and_retries_after_a_minute(self):
        self.fetch.side_effect = ["key-1", DelegatedAuthError("down"), "key-2"]
        self.api_key.get()
        self.clock.now = 3600
        self.assertEqual(self.api_key.get(), "key-1")
        self.clock.now = 3659
        self.assertEqual(self.api_key.get(), "key-1")
        self.clock.now = 3660
        self.assertEqual(self.api_key.get(), "key-2")

    def test_failed_first_mint_raises(self):
        self.fetch.side_effect = DelegatedAuthError("no mapping")
        with self.assertRaises(DelegatedAuthError):
            self.api_key.get()


class TestSettingsDelegatedAuth(unittest.TestCase):
    """The API key is resolved while settings is imported, so each case reloads it."""

    API_KEY_SOURCES = (
        "DD_API_KEY",
        "DD_API_KEY_SECRET_ARN",
        "DD_API_KEY_SSM_NAME",
        "DD_KMS_API_KEY",
    )

    def tearDown(self):
        reload(sys.modules["settings"])

    def _reload_settings(self, env, fetch, clock=None):
        with patch.dict(os.environ, {}), patch(
            "delegated_auth.fetch_delegated_api_key", fetch
        ), patch("delegated_auth.time.monotonic", clock or FakeClock()):
            for var in self.API_KEY_SOURCES:
                os.environ.pop(var, None)
            os.environ.update(env)
            return reload(sys.modules["settings"])

    def test_org_uuid_uses_the_minted_key(self):
        reloaded = self._reload_settings(
            {"DD_ORG_UUID": ORG_UUID, "DD_API_KEY": STATIC_API_KEY},
            MagicMock(return_value=MINTED_API_KEY),
        )
        self.assertEqual(reloaded.DD_API_KEY, MINTED_API_KEY)
        self.assertEqual(reloaded.get_api_key(), MINTED_API_KEY)

    def test_failed_mint_falls_back_to_the_configured_key(self):
        reloaded = self._reload_settings(
            {"DD_ORG_UUID": ORG_UUID, "DD_API_KEY": STATIC_API_KEY},
            MagicMock(side_effect=DelegatedAuthError("no mapping")),
        )
        self.assertIsNone(reloaded.DELEGATED_API_KEY)
        self.assertEqual(reloaded.get_api_key(), STATIC_API_KEY)

    def test_failed_mint_without_fallback_names_delegated_auth(self):
        reloaded = self._reload_settings(
            {"DD_ORG_UUID": ORG_UUID},
            MagicMock(side_effect=DelegatedAuthError("no mapping")),
        )
        with self.assertRaisesRegex(Exception, "DD_ORG_UUID"):
            reloaded.is_api_key_valid()

    def test_get_api_key_re_mints_once_due(self):
        clock = FakeClock()
        reloaded = self._reload_settings(
            {"DD_ORG_UUID": ORG_UUID},
            MagicMock(side_effect=[MINTED_API_KEY, STATIC_API_KEY]),
            clock,
        )
        self.assertEqual(reloaded.get_api_key(), MINTED_API_KEY)
        clock.now = 3600
        self.assertEqual(reloaded.get_api_key(), STATIC_API_KEY)

    def test_without_org_uuid_nothing_is_minted(self):
        fetch = MagicMock()
        reloaded = self._reload_settings({"DD_API_KEY": STATIC_API_KEY}, fetch)
        fetch.assert_not_called()
        self.assertEqual(reloaded.get_api_key(), STATIC_API_KEY)


class TestForwarderApiKeyRefresh(unittest.TestCase):
    def _forwarder(self, api_key):
        from forwarder import Forwarder

        forwarder = Forwarder.__new__(Forwarder)
        forwarder.storage = MagicMock()
        forwarder.trace_connection = MagicMock()
        forwarder._trace_api_key = api_key
        return forwarder

    @patch("forwarder.send_event_metric")
    @patch("forwarder.get_api_key", return_value="key-2")
    def test_trace_connection_is_reconfigured_when_the_key_changes(self, *_):
        forwarder = self._forwarder("key-1")

        forwarder._forward_traces([{"message": "{}", "tags": ""}])

        forwarder.trace_connection.configure.assert_called_once()
        self.assertEqual(
            forwarder.trace_connection.configure.call_args.args[1], "key-2"
        )
        self.assertEqual(forwarder._trace_api_key, "key-2")

    @patch("forwarder.send_event_metric")
    @patch("forwarder.get_api_key", return_value="key-1")
    def test_trace_connection_is_kept_while_the_key_is_unchanged(self, *_):
        forwarder = self._forwarder("key-1")

        forwarder._forward_traces([{"message": "{}", "tags": ""}])

        forwarder.trace_connection.configure.assert_not_called()

    def _forward_logs_failing_with(self, status_code):
        error = Exception(f"HTTP {status_code}")
        error.response = MagicMock(status_code=status_code)
        client = MagicMock()
        client.__enter__.return_value = client
        client.send.side_effect = error

        forwarder = self._forwarder("key-1")
        forwarder._scrubber = MagicMock()
        forwarder._matcher = MagicMock()
        forwarder._matcher.match.return_value = True
        forwarder._batcher = MagicMock()
        forwarder._batcher.batch.return_value = [['"hello"']]

        with patch("forwarder.DatadogHTTPClient", return_value=client), patch(
            "forwarder.get_api_key", return_value="key-1"
        ), patch("forwarder.send_event_metric"), patch(
            "logs.datadog_client.time.sleep"
        ), patch(
            "forwarder.invalidate_api_key"
        ) as invalidate:
            forwarder._forward_logs(["hello"])
        return invalidate

    def test_rejected_key_is_invalidated(self):
        for status_code in (401, 403):
            with self.subTest(status_code=status_code):
                self._forward_logs_failing_with(status_code).assert_called()

    def test_other_errors_keep_the_key(self):
        for status_code in (400, 500):
            with self.subTest(status_code=status_code):
                self._forward_logs_failing_with(status_code).assert_not_called()


if __name__ == "__main__":
    unittest.main()
