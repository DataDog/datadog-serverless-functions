// Unless explicitly stated otherwise all files in this repository are licensed
// under the Apache License Version 2.0.
// This product includes software developed at Datadog (https://www.datadoghq.com/).
// Copyright 2026-Present Datadog, Inc.

package apikey

import (
	"bytes"
	"context"
	"crypto/fips140"
	"encoding/base64"
	"encoding/json"
	"errors"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"testing/synctest"
	"time"

	"github.com/aws/aws-sdk-go-v2/aws"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

type fakeCredentialsProvider func(context.Context) (aws.Credentials, error)

func (f fakeCredentialsProvider) Retrieve(ctx context.Context) (aws.Credentials, error) {
	return f(ctx)
}

func TestWorkloadIdentityFederationAPIKeySource_Get(t *testing.T) {
	t.Parallel()

	tests := map[string]struct {
		credentials aws.CredentialsProvider
		handler     http.HandlerFunc
		want        APIKey
		wantErr     bool
	}{
		"success": {
			credentials: fakeCredentialsProvider(func(context.Context) (aws.Credentials, error) {
				return aws.Credentials{AccessKeyID: "AKID", SecretAccessKey: "SECRET"}, nil
			}),
			handler: func(w http.ResponseWriter, _ *http.Request) {
				w.WriteHeader(http.StatusOK)
				_, _ = w.Write([]byte(`{"data":{"attributes":{"api_key":"the-key"}}}`))
			},
			want: "the-key",
		},
		"credentials error": {
			credentials: fakeCredentialsProvider(func(context.Context) (aws.Credentials, error) {
				return aws.Credentials{}, errors.New("")
			}),
			wantErr: true,
		},
		"exchange error": {
			credentials: fakeCredentialsProvider(func(context.Context) (aws.Credentials, error) {
				return aws.Credentials{AccessKeyID: "AKID", SecretAccessKey: "SECRET"}, nil
			}),
			handler: func(w http.ResponseWriter, _ *http.Request) {
				w.WriteHeader(http.StatusForbidden)
			},
			wantErr: true,
		},
	}

	for name, tc := range tests {
		t.Run(name, func(t *testing.T) {
			t.Parallel()

			server := httptest.NewTestServer(t, tc.handler)

			ks := NewWorkloadIdentityFederationAPIKeySource("us-east-1", "org-123", server.URL, server.Client(), tc.credentials)
			key, err := ks.Get(t.Context())
			if tc.wantErr {
				require.Error(t, err)
				return
			}
			require.NoError(t, err)
			assert.Equal(t, tc.want, key)
		})
	}
}

func TestWorkloadIdentityFederationAPIKeySource_generateProof(t *testing.T) {
	t.Parallel()

	synctest.Test(t, func(t *testing.T) {
		region := "us-east-1"
		ks := NewWorkloadIdentityFederationAPIKeySource(region, "org-123", "", http.DefaultClient, nil)
		creds := aws.Credentials{AccessKeyID: "AKID", SecretAccessKey: "SECRET"}

		now := time.Now()
		proof, err := ks.generateProof(t.Context(), creds, region)
		require.NoError(t, err)

		parts := strings.Split(proof, "|")
		require.Len(t, parts, 4)

		expectedHost := "sts." + region + ".amazonaws.com"
		if fips140.Enabled() {
			expectedHost = "sts-fips." + region + ".amazonaws.com"
		}

		headersJSON, err := base64.StdEncoding.DecodeString(parts[1])
		require.NoError(t, err)

		var headers http.Header
		require.NoError(t, json.Unmarshal(headersJSON, &headers))

		assert.Equal(t, "org-123", headers.Get(orgIDHeader))
		assert.Equal(t, expectedHost, headers.Get("Host"))
		assert.Equal(t, now.UTC().Format("20060102T150405Z"), headers.Get("X-Amz-Date"))
		assert.Contains(t, headers.Get("Authorization"), "AWS4-HMAC-SHA256 Credential=")
	})
}

func TestWorkloadIdentityFederationAPIKeySource_exchangeProof(t *testing.T) {
	t.Parallel()

	tests := map[string]struct {
		handler http.HandlerFunc
		want    APIKey
		wantErr bool
	}{
		"success": {
			handler: func(w http.ResponseWriter, _ *http.Request) {
				w.WriteHeader(http.StatusOK)
				_, _ = w.Write([]byte(`{"data":{"attributes":{"api_key":"the-key"}}}`))
			},
			want: "the-key",
		},
		"empty api key": {
			handler: func(w http.ResponseWriter, _ *http.Request) {
				w.WriteHeader(http.StatusOK)
				_, _ = w.Write([]byte(`{"data":{"attributes":{"api_key":""}}}`))
			},
			wantErr: true,
		},
		"non-200": {
			handler: func(w http.ResponseWriter, _ *http.Request) {
				w.WriteHeader(http.StatusForbidden)
				_, _ = w.Write([]byte(`{"errors":[{"detail":"not authorized"}]}`))
			},
			wantErr: true,
		},
		"malformed json": {
			handler: func(w http.ResponseWriter, _ *http.Request) {
				w.WriteHeader(http.StatusOK)
				_, _ = w.Write([]byte(`not json`))
			},
			wantErr: true,
		},
		"response too large": {
			handler: func(w http.ResponseWriter, _ *http.Request) {
				w.WriteHeader(http.StatusOK)
				_, _ = w.Write(bytes.Repeat([]byte("a"), maximumResponseSize+2))
			},
			wantErr: true,
		},
	}

	for name, tc := range tests {
		t.Run(name, func(t *testing.T) {
			t.Parallel()

			server := httptest.NewTestServer(t, tc.handler)
			ks := NewWorkloadIdentityFederationAPIKeySource("us-east-1", "org-123", server.URL, server.Client(), nil)

			key, err := ks.exchangeProof(t.Context(), "proof")
			if tc.wantErr {
				require.Error(t, err)
				return
			}
			require.NoError(t, err)
			assert.Equal(t, tc.want, key)
		})
	}
}

func TestParseError(t *testing.T) {
	t.Parallel()

	tests := map[string]struct {
		body string
		want string
	}{
		"single detail": {
			body: `{"errors":[{"detail":"not authorized"}]}`,
			want: ": not authorized",
		},
		"multiple details": {
			body: `{"errors":[{"detail":"a"},{"detail":"b"}]}`,
			want: ": a; b",
		},
		"empty detail skipped": {
			body: `{"errors":[{"detail":""}]}`,
			want: "",
		},
		"no errors": {
			body: `{"errors":[]}`,
			want: "",
		},
		"malformed json": {
			body: `not json`,
			want: "",
		},
	}

	for name, tc := range tests {
		t.Run(name, func(t *testing.T) {
			t.Parallel()

			assert.Equal(t, tc.want, parseError([]byte(tc.body)))
		})
	}
}
