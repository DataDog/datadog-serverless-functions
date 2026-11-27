// Unless explicitly stated otherwise all files in this repository are licensed
// under the Apache License Version 2.0.
// This product includes software developed at Datadog (https://www.datadoghq.com/).
// Copyright 2026-Present Datadog, Inc.

package apikey

import (
	"context"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

func TestAuthRoundTripper_RoundTrip(t *testing.T) {
	t.Parallel()

	tests := map[string]struct {
		statusCode     int
		source         APIKeySource
		wantInvalidate int32
	}{
		"401 invalidates": {
			statusCode:     http.StatusUnauthorized,
			source:         &fakeInvalidatableAPIKeySource{APIKeySource: &fakeAPIKeySource{fn: fakeSuccess}},
			wantInvalidate: 1,
		},
		"403 invalidates": {
			statusCode:     http.StatusForbidden,
			source:         &fakeInvalidatableAPIKeySource{APIKeySource: &fakeAPIKeySource{fn: fakeSuccess}},
			wantInvalidate: 1,
		},
		"200 does not invalidate": {
			statusCode:     http.StatusOK,
			source:         &fakeInvalidatableAPIKeySource{APIKeySource: &fakeAPIKeySource{fn: fakeSuccess}},
			wantInvalidate: 0,
		},
		"403 without Invalidator is safe": {
			statusCode: http.StatusForbidden,
			source:     &fakeAPIKeySource{fn: fakeSuccess},
		},
	}

	for name, tc := range tests {
		t.Run(name, func(t *testing.T) {
			t.Parallel()

			server := httptest.NewTestServer(t, http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
				w.WriteHeader(tc.statusCode)
			}))

			rt := &AuthRoundTripper{Source: tc.source, Next: server.Client().Transport}

			req, err := http.NewRequest(http.MethodGet, server.URL, nil)
			require.NoError(t, err)

			resp, err := rt.RoundTrip(req)
			require.NoError(t, err)
			defer func() { _ = resp.Body.Close() }()

			assert.Equal(t, tc.statusCode, resp.StatusCode)

			if invalidatable, ok := tc.source.(*fakeInvalidatableAPIKeySource); ok {
				assert.Equal(t, tc.wantInvalidate, invalidatable.invalidateCalls.Load())
			}
		})
	}

	t.Run("adds header without mutating original request", func(t *testing.T) {
		t.Parallel()

		var gotHeader string
		server := httptest.NewTestServer(t, http.HandlerFunc(func(w http.ResponseWriter, req *http.Request) {
			gotHeader = req.Header.Get(authenticationHeader)
			w.WriteHeader(http.StatusOK)
		}))

		source := &fakeAPIKeySource{fn: func(context.Context) (APIKey, error) { return "the-key", nil }}
		rt := &AuthRoundTripper{Source: source, Next: server.Client().Transport}

		req, err := http.NewRequest(http.MethodGet, server.URL, nil)
		require.NoError(t, err)

		resp, err := rt.RoundTrip(req)
		require.NoError(t, err)
		defer func() { _ = resp.Body.Close() }()

		assert.Equal(t, http.StatusOK, resp.StatusCode)
		assert.Equal(t, "the-key", gotHeader)
		assert.Empty(t, req.Header.Get(authenticationHeader))
	})

	t.Run("source error prevents next roundtripper", func(t *testing.T) {
		t.Parallel()

		called := false
		server := httptest.NewTestServer(t, http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
			called = true
			w.WriteHeader(http.StatusOK)
		}))

		source := &fakeAPIKeySource{fn: fakeFailure}
		rt := &AuthRoundTripper{Source: source, Next: server.Client().Transport}

		req, err := http.NewRequest(http.MethodGet, server.URL, nil)
		require.NoError(t, err)

		resp, err := rt.RoundTrip(req)
		require.Error(t, err)
		assert.Nil(t, resp)
		assert.False(t, called)
	})
}
