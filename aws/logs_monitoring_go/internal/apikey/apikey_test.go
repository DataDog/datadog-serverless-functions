// Unless explicitly stated otherwise all files in this repository are licensed
// under the Apache License Version 2.0.
// This product includes software developed at Datadog (https://www.datadoghq.com/).
// Copyright 2026-Present Datadog, Inc.

package apikey

import (
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/stretchr/testify/require"
)

func TestAPIKey_Validate(t *testing.T) {
	t.Parallel()

	tests := map[string]struct {
		key        string
		statusCode int
		wantErr    bool
	}{
		"valid": {
			key:        "0123456789abcdefghij0123456789ab",
			statusCode: http.StatusOK,
		},
		"wrong format": {
			key:     "not32characters",
			wantErr: true,
		},
		"invalid": {
			key:        "myapikeyisexpiredorinvalid012345",
			statusCode: http.StatusForbidden,
			wantErr:    true,
		},
		"unexpected error": {
			key:        "0123456789abcdefghij0123456789ab",
			statusCode: http.StatusInternalServerError,
			wantErr:    true,
		},
	}

	for name, tc := range tests {
		t.Run(name, func(t *testing.T) {
			t.Parallel()

			server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, req *http.Request) {
				require.Equal(t, tc.key, req.Header.Get("DD-API-KEY"))
				w.WriteHeader(tc.statusCode)
			}))
			t.Cleanup(server.Close)

			err := APIKey(tc.key).Validate(t.Context(), server.Client(), server.URL)

			if tc.wantErr {
				require.Error(t, err)
				return
			}
			require.NoError(t, err)
		})
	}
}
