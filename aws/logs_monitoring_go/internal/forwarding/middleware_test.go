// Unless explicitly stated otherwise all files in this repository are licensed
// under the Apache License Version 2.0.
// This product includes software developed at Datadog (https://www.datadoghq.com/).
// Copyright 2026-Present Datadog, Inc.

package forwarding

import (
	"compress/gzip"
	"io"
	"net/http"
	"strings"
	"sync/atomic"
	"testing"

	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

func TestWithCompression(t *testing.T) {
	t.Parallel()

	tests := map[string]struct {
		input string
	}{
		"non empty": {
			input: "oof",
		},
		"empty": {
			input: "",
		},
	}

	for name, tc := range tests {
		t.Run(name, func(t *testing.T) {
			t.Parallel()

			req, err := http.NewRequestWithContext(t.Context(), http.MethodPost, "http://test", io.NopCloser(strings.NewReader(tc.input)))
			require.NoError(t, err)

			next := RoundTripperFunc(func(req *http.Request) (*http.Response, error) {
				assert.Equal(t, "gzip", req.Header.Get("Content-Encoding"), "Content-Encoding header")

				gr, err := gzip.NewReader(req.Body)
				require.NoError(t, err)
				got, err := io.ReadAll(gr)
				require.NoError(t, err)
				assert.Equal(t, tc.input, string(got), "decompressed body")

				body, err := req.GetBody()
				require.NoError(t, err)
				gr2, err := gzip.NewReader(body)
				require.NoError(t, err)
				got2, err := io.ReadAll(gr2)
				require.NoError(t, err)
				assert.Equal(t, tc.input, string(got2), "GetBody decompressed body")

				return &http.Response{StatusCode: http.StatusAccepted, Body: io.NopCloser(strings.NewReader(""))}, nil
			})

			compress := WithCompression(next)
			_, err = compress.RoundTrip(req)
			assert.NoError(t, err, "WithCompression RoundTrip")
		})
	}
}

func TestWithRetry(t *testing.T) {
	t.Parallel()

	tests := map[string]struct {
		maxAttempts int
		statusCodes []int
		wantCalls   int
		wantStatus  int
		wantErr     error
	}{
		"one success": {
			maxAttempts: defaultMaxAttempts,
			statusCodes: []int{http.StatusAccepted},
			wantCalls:   1,
			wantStatus:  http.StatusAccepted,
		},
		"two retriable, one success": {
			maxAttempts: defaultMaxAttempts,
			statusCodes: []int{http.StatusTooManyRequests, http.StatusRequestTimeout, http.StatusAccepted},
			wantCalls:   3,
			wantStatus:  http.StatusAccepted,
		},
		"all retries exhausted": {
			maxAttempts: defaultMaxAttempts,
			statusCodes: []int{http.StatusTooManyRequests, http.StatusRequestTimeout, http.StatusInternalServerError},
			wantCalls:   defaultMaxAttempts,
			wantStatus:  http.StatusInternalServerError,
		},
		"permanent error": {
			maxAttempts: defaultMaxAttempts,
			statusCodes: []int{http.StatusUnauthorized},
			wantCalls:   1,
			wantStatus:  http.StatusUnauthorized,
			wantErr:     &PermanentError{},
		},
	}

	for name, tc := range tests {
		t.Run(name, func(t *testing.T) {
			t.Parallel()

			req, err := http.NewRequestWithContext(t.Context(), http.MethodPost, "http://test", io.NopCloser(strings.NewReader("")))
			require.NoError(t, err)

			var callCount atomic.Int32
			next := RoundTripperFunc(func(req *http.Request) (*http.Response, error) {
				resp := &http.Response{
					StatusCode: tc.statusCodes[callCount.Load()],
					Body:       io.NopCloser(strings.NewReader("")),
				}
				callCount.Add(1)
				return resp, nil
			})

			retry := WithRetry(tc.maxAttempts, next)
			resp, err := retry.RoundTrip(req)

			assert.Equal(t, tc.wantCalls, int(callCount.Load()), "call count")
			if tc.wantErr != nil {
				var permErr *PermanentError
				require.ErrorAs(t, err, &permErr)
				return
			}
			assert.Equal(t, tc.wantStatus, resp.StatusCode, "response status")
			assert.NoError(t, err, "RoundTrip error")
		})
	}
}
