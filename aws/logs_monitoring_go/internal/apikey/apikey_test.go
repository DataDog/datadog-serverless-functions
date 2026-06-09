// Unless explicitly stated otherwise all files in this repository are licensed
// under the Apache License Version 2.0.
// This product includes software developed at Datadog (https://www.datadoghq.com/).
// Copyright 2026-Present Datadog, Inc.

package apikey

import (
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

func TestValidate(t *testing.T) {
	t.Parallel()

	tests := map[string]struct {
		key        string
		statusCode int
		wantErr    bool
		err        error
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
			err:        ErrInvalidAPIKey,
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
				assert.Equal(t, tc.key, req.Header.Get("DD-API-KEY"))
				w.WriteHeader(tc.statusCode)
			}))
			t.Cleanup(server.Close)

			err := Validate(t.Context(), server.Client(), server.URL, tc.key)

			if tc.wantErr {
				if tc.err != nil {
					require.ErrorIs(t, err, tc.err)
				}
				require.Error(t, err)
				return
			}

			require.NoError(t, err)
		})
	}
}
