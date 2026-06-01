// Unless explicitly stated otherwise all files in this repository are licensed
// under the Apache License Version 2.0.
// This product includes software developed at Datadog (https://www.datadoghq.com/).
// Copyright 2026-Present Datadog, Inc.

package httpclient

import (
	"io"
	"net/http"
	"strings"
	"sync/atomic"
	"testing"

	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

func TestWithRetry(t *testing.T) {
	t.Parallel()

	tests := map[string]struct {
		maxAttempts int
		statusCodes []int
		wantCalls   int
		wantStatus  int
	}{
		"one success": {
			maxAttempts: 3,
			statusCodes: []int{http.StatusAccepted},
			wantCalls:   1,
			wantStatus:  http.StatusAccepted,
		},
		"two retriable, one success": {
			maxAttempts: 3,
			statusCodes: []int{http.StatusTooManyRequests, http.StatusRequestTimeout, http.StatusAccepted},
			wantCalls:   3,
			wantStatus:  http.StatusAccepted,
		},
		"all retries exhausted": {
			maxAttempts: 3,
			statusCodes: []int{http.StatusTooManyRequests, http.StatusRequestTimeout, http.StatusInternalServerError},
			wantCalls:   3,
			wantStatus:  http.StatusInternalServerError,
		},
		"non-retryable error": {
			maxAttempts: 3,
			statusCodes: []int{http.StatusUnauthorized},
			wantCalls:   1,
			wantStatus:  http.StatusUnauthorized,
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
			assert.Equal(t, tc.wantStatus, resp.StatusCode, "response status")
			assert.NoError(t, err, "RoundTrip error")
		})
	}
}
