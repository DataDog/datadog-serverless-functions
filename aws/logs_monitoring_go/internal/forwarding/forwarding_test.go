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
	"time"

	"github.com/DataDog/datadog-serverless-functions/aws/logs_monitoring_go/internal/config"
	"github.com/DataDog/datadog-serverless-functions/aws/logs_monitoring_go/internal/httpclient"
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
		wantErr    bool
		wantCalls  int
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
			wantCalls:  httpclient.DefaultMaxAttempts,
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
			server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, req *http.Request) {
				callCount.Add(1)

				assert.Equal(t, "test-api-key", req.Header.Get("DD-API-KEY"), "DD-API-KEY")
				assert.Equal(t, "application/json", req.Header.Get("Content-Type"), "Content-Type")
				assert.Equal(t, "gzip", req.Header.Get("Content-Encoding"), "Content-Encoding")
				assert.Equal(t, "aws_forwarder", req.Header.Get("DD-EVP-ORIGIN"), "DD-EVP-ORIGIN")
				assert.Equal(t, config.ForwarderVersion, req.Header.Get("DD-EVP-ORIGIN-VERSION"), "DD-EVP-ORIGIN-VERSION")
				if tc.storage != "" {
					assert.Equal(t, tc.storage, req.Header.Get("DD-STORAGE-TAG"), "DD-STORAGE-TAG")
				}

				gr, err := gzip.NewReader(req.Body)
				if !assert.NoError(t, err, "body is not valid gzip") {
					return
				}
				defer gr.Close() //nolint:errcheck

				_, err = io.ReadAll(gr)
				assert.NoError(t, err, "read gzip body")

				w.WriteHeader(tc.statusCode)
			}))
			t.Cleanup(server.Close)
			client := server.Client()
			client.Transport = httpclient.WithRetry(httpclient.DefaultMaxAttempts, client.Transport)
			forwarder := NewForwarder(&config.Config{IntakeURL: server.URL, APIKey: "test-api-key", CompressionLevel: gzip.DefaultCompression}, client, tc.storage)
			ctx, cancel := context.WithCancel(t.Context())
			t.Cleanup(cancel)

			in := make(chan model.LogEntry, len(tc.entries))
			for _, e := range tc.entries {
				in <- e
			}
			close(in)

			err := forwarder.Start(ctx, in)

			assert.Equal(t, tc.wantCalls, int(callCount.Load()))
			if tc.wantErr {
				require.Error(t, err)
				return
			}
			require.NoError(t, err)
		})
	}
}

func TestForwarder_Start_Context(t *testing.T) {
	t.Parallel()

	tests := map[string]struct {
		ctxBuilder func(t *testing.T) (context.Context, context.CancelFunc)
		throttling time.Duration
		wantErr    error
	}{
		"pre-canceled": {
			ctxBuilder: func(t *testing.T) (context.Context, context.CancelFunc) {
				ctx, cancel := context.WithCancel(t.Context())
				cancel()
				return ctx, cancel
			},
			wantErr: context.Canceled,
		},
		"pre-timeout": {
			ctxBuilder: func(t *testing.T) (context.Context, context.CancelFunc) {
				return context.WithTimeout(t.Context(), -1)
			},
			wantErr: context.DeadlineExceeded,
		},
		"mid-flight timeout": {
			ctxBuilder: func(t *testing.T) (context.Context, context.CancelFunc) {
				return context.WithTimeout(t.Context(), 50*time.Millisecond)
			},
			throttling: 100 * time.Millisecond,
			wantErr:    context.DeadlineExceeded,
		},
	}

	for name, tc := range tests {
		t.Run(name, func(t *testing.T) {
			t.Parallel()

			server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, req *http.Request) {
				time.Sleep(tc.throttling)
			}))
			t.Cleanup(server.Close)
			client := server.Client()
			client.Transport = httpclient.WithRetry(httpclient.DefaultMaxAttempts, client.Transport)
			forwarder := NewForwarder(&config.Config{IntakeURL: server.URL, APIKey: "test-api-key", CompressionLevel: gzip.DefaultCompression}, client, "")
			ctx, cancel := tc.ctxBuilder(t)
			t.Cleanup(cancel)

			in := make(chan model.LogEntry, 1)
			in <- model.LogEntry{}
			close(in)

			err := forwarder.Start(ctx, in)

			if tc.wantErr != nil {
				require.ErrorIs(t, err, tc.wantErr)
				return
			}
			require.NoError(t, err)
		})
	}
}
