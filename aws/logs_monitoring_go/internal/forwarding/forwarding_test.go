// Unless explicitly stated otherwise all files in this repository are licensed
// under the Apache License Version 2.0.
// This product includes software developed at Datadog (https://www.datadoghq.com/).
// Copyright 2026-Present Datadog, Inc.

package forwarding

import (
	"compress/gzip"
	"context"
	"io"
	"net/http"
	"net/http/httptest"
	"sync/atomic"
	"testing"

	"github.com/DataDog/datadog-serverless-functions/aws/logs_monitoring_go/internal/config"
	"github.com/DataDog/datadog-serverless-functions/aws/logs_monitoring_go/internal/model"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

func TestForwarder_Start(t *testing.T) {
	t.Parallel()

	tests := map[string]struct {
		statusCode int
		storage    string
		entries    []model.LogEntry
		cancelCtx  bool
		wantErr   bool
		wantCalls int
	}{
		"single message accepted": {
			statusCode: http.StatusAccepted,
			storage:    cloudwatchStorage,
			entries:    []model.LogEntry{{Message: "test payload"}},
			wantCalls:  1,
		},
		"empty channel": {
			statusCode: http.StatusAccepted,
			storage:    cloudwatchStorage,
			entries:    []model.LogEntry{},
			wantCalls:  0,
		},
		"server returns 400": {
			statusCode: http.StatusBadRequest,
			storage:    cloudwatchStorage,
			entries:    []model.LogEntry{{Message: "test payload"}},
			wantErr:    true,
			wantCalls:  1,
		},
		"server returns 500": {
			statusCode: http.StatusInternalServerError,
			storage:    cloudwatchStorage,
			entries:    []model.LogEntry{{Message: "test payload"}},
			wantErr:    true,
			wantCalls:  1,
		},
		"context cancelled": {
			statusCode: http.StatusAccepted,
			storage:    cloudwatchStorage,
			entries:    []model.LogEntry{{Message: "test payload"}},
			cancelCtx:  true,
			wantErr:    true,
			wantCalls:  0,
		},
		"s3 storage": {
			statusCode: http.StatusAccepted,
			storage:    s3Storage,
			entries:    []model.LogEntry{{Message: "test payload"}},
			wantCalls:  1,
		},
	}

	for name, tc := range tests {
		t.Run(name, func(t *testing.T) {
			t.Parallel()

			var callCount atomic.Int32

			server := httptest.NewServer(http.HandlerFunc(func(rw http.ResponseWriter, req *http.Request) {
				callCount.Add(1)

				assert.Equal(t, "test-api-key", req.Header.Get("DD-API-KEY"), "DD-API-KEY")
				assert.Equal(t, "application/json", req.Header.Get("Content-Type"), "Content-Type")
				assert.Equal(t, "gzip", req.Header.Get("Content-Encoding"), "Content-Encoding")
				assert.Equal(t, "aws_forwarder", req.Header.Get("DD-EVP-ORIGIN"), "DD-EVP-ORIGIN")
				assert.Equal(t, config.ForwarderVersion, req.Header.Get("DD-EVP-ORIGIN-VERSION"), "DD-EVP-ORIGIN-VERSION")
				assert.Equal(t, tc.storage, req.Header.Get("DD-STORAGE-TAG"), "DD-STORAGE-TAG")

				gr, err := gzip.NewReader(req.Body)
				if !assert.NoError(t, err, "body is not valid gzip") {
					return
				}
				defer gr.Close() //nolint:errcheck

				_, err = io.ReadAll(gr)
				assert.NoError(t, err, "read gzip body")

				rw.WriteHeader(tc.statusCode)
			}))
			t.Cleanup(server.Close)

			f := NewForwarder(&config.Config{IntakeURL: server.URL, APIKey: "test-api-key"}, server.Client(), tc.storage)

			ctx, cancel := context.WithCancel(t.Context())
			t.Cleanup(cancel)

			if tc.cancelCtx {
				cancel()
			}

			in := make(chan model.LogEntry, len(tc.entries))
			for _, e := range tc.entries {
				in <- e
			}
			close(in)

			err := f.Start(ctx, in)

			if tc.wantErr {
				require.Error(t, err)
				return
			}
			require.NoError(t, err)
			assert.Equal(t, tc.wantCalls, int(callCount.Load()))
		})
	}
}
