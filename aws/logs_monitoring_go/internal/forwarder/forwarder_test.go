// Unless explicitly stated otherwise all files in this repository are licensed
// under the Apache License Version 2.0.
// This product includes software developed at Datadog (https://www.datadoghq.com/).
// Copyright 2026-Present Datadog, Inc.

package forwarder

import (
	"compress/gzip"
	"context"
	"encoding/json"
	"errors"
	"io"
	"net/http"
	"net/http/httptest"
	"sync/atomic"
	"testing"
	"time"

	"github.com/DataDog/datadog-serverless-functions/aws/logs_monitoring_go/internal/httpclient"
	"github.com/DataDog/datadog-serverless-functions/aws/logs_monitoring_go/internal/model"
	"github.com/DataDog/datadog-serverless-functions/aws/logs_monitoring_go/internal/storage"
	"github.com/DataDog/datadog-serverless-functions/aws/logs_monitoring_go/internal/storage/mocks"
	"github.com/DataDog/datadog-serverless-functions/aws/logs_monitoring_go/internal/version"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
	"go.uber.org/mock/gomock"
)

func TestForwarder_Start(t *testing.T) {
	t.Parallel()

	tests := map[string]struct {
		statusCode int
		storageTag string
		entries    []model.LogEntry
		wantErr    bool
		wantCalls  int
	}{
		"single message accepted": {
			statusCode: http.StatusAccepted,
			storageTag: "cloudwatch",
			entries:    []model.LogEntry{{Message: "test payload"}},
			wantCalls:  1,
		},
		"empty channel": {
			statusCode: http.StatusAccepted,
			storageTag: "cloudwatch",
			entries:    []model.LogEntry{},
			wantCalls:  0,
		},
		"server returns 400": {
			statusCode: http.StatusBadRequest,
			storageTag: "cloudwatch",
			entries:    []model.LogEntry{{Message: "test payload"}},
			wantErr:    true,
			wantCalls:  1,
		},
		"server returns 500": {
			statusCode: http.StatusInternalServerError,
			storageTag: "cloudwatch",
			entries:    []model.LogEntry{{Message: "test payload"}},
			wantErr:    true,
			wantCalls:  httpclient.DefaultMaxAttempts,
		},
		"s3 storage": {
			statusCode: http.StatusAccepted,
			storageTag: "s3",
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
				assert.Equal(t, version.Forwarder, req.Header.Get("DD-EVP-ORIGIN-VERSION"), "DD-EVP-ORIGIN-VERSION")
				if tc.storageTag != "" {
					assert.Equal(t, tc.storageTag, req.Header.Get("DD-STORAGE-TAG"), "DD-STORAGE-TAG")
				}

				gr, err := gzip.NewReader(req.Body)
				if !assert.NoError(t, err, "body is not valid gzip") {
					return
				}
				defer func() { _ = gr.Close() }()

				_, err = io.ReadAll(gr)
				assert.NoError(t, err, "read gzip body")

				w.WriteHeader(tc.statusCode)
			}))
			t.Cleanup(server.Close)
			client := server.Client()
			client.Transport = httpclient.WithRetry(httpclient.DefaultMaxAttempts, client.Transport)
			forwarder := New(Config{IntakeURL: server.URL, APIKey: "test-api-key", CompressionLevel: gzip.DefaultCompression}, client, nil)
			ctx, cancel := context.WithCancel(t.Context())
			t.Cleanup(cancel)

			in := make(chan json.RawMessage, len(tc.entries))
			for _, e := range tc.entries {
				raw, err := json.Marshal(e)
				require.NoError(t, err)
				in <- raw
			}
			close(in)

			err := forwarder.Start(ctx, in, tc.storageTag)

			assert.Equal(t, tc.wantCalls, int(callCount.Load()))
			if tc.wantErr {
				require.Error(t, err)
				return
			}
			require.NoError(t, err)
		})
	}
}

func TestForwarder_StepFunctionsTraceHeader(t *testing.T) {
	t.Parallel()

	tests := map[string]struct {
		enabled bool
	}{
		"enabled": {
			enabled: true,
		},
		"disabled": {
			enabled: false,
		},
	}

	for name, tc := range tests {
		t.Run(name, func(t *testing.T) {
			t.Parallel()

			var got string
			server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, req *http.Request) {
				got = req.Header.Get("DD-STEP-FUNCTIONS-TRACE-ENABLED")
				w.WriteHeader(http.StatusAccepted)
			}))
			t.Cleanup(server.Close)
			client := server.Client()

			forwarder := New(Config{
				IntakeURL:                 server.URL,
				StepFunctionsTraceEnabled: tc.enabled,
			}, client, nil)

			ctx, cancel := context.WithCancel(t.Context())
			t.Cleanup(cancel)

			in := make(chan json.RawMessage, 1)
			raw, err := json.Marshal(model.LogEntry{})
			require.NoError(t, err)
			in <- raw
			close(in)

			require.NoError(t, forwarder.Start(ctx, in, ""))

			want := ""
			if tc.enabled {
				want = "true"
			}
			assert.Equal(t, want, got)
		})
	}
}

func TestForwarder_StartSendError(t *testing.T) {
	t.Parallel()

	tests := map[string]struct {
		status        int
		storage       func(t *testing.T) storage.Storage
		wantStored    bool
		wantPermanent bool
	}{
		"undelivered batches reach the storage": {
			status: http.StatusForbidden,
			storage: func(t *testing.T) storage.Storage {
				t.Helper()

				store := mocks.NewMockStorage(gomock.NewController(t))
				store.EXPECT().Store(gomock.Any(), gomock.Any()).Return(nil).MinTimes(1)

				return store
			},
			wantStored: true,
		},
		"storage refuses the batches": {
			status: http.StatusForbidden,
			storage: func(t *testing.T) storage.Storage {
				t.Helper()

				store := mocks.NewMockStorage(gomock.NewController(t))
				store.EXPECT().Store(gomock.Any(), gomock.Any()).Return(errors.New("storage unavailable")).MinTimes(1)

				return store
			},
		},
		"no storage configured": {
			status: http.StatusForbidden,
		},
		"bad request is never stored": {
			status: http.StatusBadRequest,
			storage: func(t *testing.T) storage.Storage {
				t.Helper()

				store := mocks.NewMockStorage(gomock.NewController(t))
				store.EXPECT().Store(gomock.Any(), gomock.Any()).Times(0)

				return store
			},
			wantPermanent: true,
		},
		"payload too large is never stored": {
			status: http.StatusRequestEntityTooLarge,
			storage: func(t *testing.T) storage.Storage {
				t.Helper()

				store := mocks.NewMockStorage(gomock.NewController(t))
				store.EXPECT().Store(gomock.Any(), gomock.Any()).Times(0)

				return store
			},
			wantPermanent: true,
		},
	}

	for name, tc := range tests {
		t.Run(name, func(t *testing.T) {
			t.Parallel()

			server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
				w.WriteHeader(tc.status)
			}))
			t.Cleanup(server.Close)

			var store storage.Storage
			if tc.storage != nil {
				store = tc.storage(t)
			}

			forwarder := New(
				Config{IntakeURL: server.URL, APIKey: "test-api-key", CompressionLevel: gzip.NoCompression},
				server.Client(),
				store,
			)

			in := make(chan json.RawMessage, 1)
			raw, err := json.Marshal(model.LogEntry{Message: "test payload"})
			require.NoError(t, err)
			in <- raw
			close(in)

			err = forwarder.Start(t.Context(), in, "")

			var sendErr *SendError
			require.ErrorAs(t, err, &sendErr)
			assert.Equal(t, tc.wantStored, sendErr.Stored)
			assert.Equal(t, tc.wantPermanent, sendErr.Permanent)
		})
	}
}

func TestForwarder_StartDrainsAfterFailure(t *testing.T) {
	t.Parallel()

	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		w.WriteHeader(http.StatusForbidden)
	}))
	t.Cleanup(server.Close)

	forwarder := New(
		Config{IntakeURL: server.URL, APIKey: "test-api-key", CompressionLevel: gzip.NoCompression},
		server.Client(),
		nil,
	)

	entries := maxLogsPerBatch * (maxBatchesInMemory + httpclient.MaxConcurrency + 10)
	raw, err := json.Marshal(model.LogEntry{Message: "test payload"})
	require.NoError(t, err)

	in := make(chan json.RawMessage, entries)
	for range entries {
		in <- raw
	}
	close(in)

	done := make(chan error, 1)
	go func() { done <- forwarder.Start(t.Context(), in, "") }()

	select {
	case err := <-done:
		var sendErr *SendError
		require.ErrorAs(t, err, &sendErr)
		assert.False(t, sendErr.Stored)
	case <-time.After(30 * time.Second):
		t.Fatal("Start never returned")
	}
}
