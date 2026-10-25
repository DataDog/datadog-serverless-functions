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
	"fmt"
	"io"
	"iter"
	"net/http"
	"net/http/httptest"
	"strings"
	"sync"
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

			err := forwarder.Start(ctx, in, tc.storageTag, ToIntake)

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

			require.NoError(t, forwarder.Start(ctx, in, "", ToIntake))

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

			err = forwarder.Start(t.Context(), in, "", ToIntake)

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
	go func() { done <- forwarder.Start(t.Context(), in, "", ToIntake) }()

	select {
	case err := <-done:
		var sendErr *SendError
		require.ErrorAs(t, err, &sendErr)
		assert.False(t, sendErr.Stored)
	case <-time.After(30 * time.Second):
		t.Fatal("Start never returned")
	}
}

func TestForwarder_Retry(t *testing.T) {
	t.Parallel()

	const (
		goodBatch = `[{"message":"good"}]`
		badBatch  = `[{"message":"poison"}]`
	)

	tests := map[string]struct {
		batches     []storage.Batch
		deleteErr   error
		deadline    time.Duration
		wantDeletes []string
		wantCalls   int
		wantErr     bool
	}{
		"permanent rejection is deleted and the drain continues": {
			batches: []storage.Batch{
				{Data: json.RawMessage(badBatch), DeleteKey: "key-1"},
				{Data: json.RawMessage(goodBatch), DeleteKey: "key-2"},
				{Data: json.RawMessage(goodBatch), DeleteKey: "key-3"},
			},
			wantDeletes: []string{"key-1", "key-2", "key-3"},
			wantCalls:   3,
		},
		"accepted batches are drained": {
			batches: []storage.Batch{
				{Data: json.RawMessage(goodBatch), DeleteKey: "key-1"},
				{Data: json.RawMessage(goodBatch), DeleteKey: "key-2"},
			},
			wantDeletes: []string{"key-1", "key-2"},
			wantCalls:   2,
		},
		"a delete failure does not stop the drain": {
			batches: []storage.Batch{
				{Data: json.RawMessage(goodBatch), DeleteKey: "key-1"},
				{Data: json.RawMessage(goodBatch), DeleteKey: "key-2"},
			},
			deleteErr:   errors.New("access denied"),
			wantDeletes: []string{"key-1", "key-2"},
			wantCalls:   2,
			wantErr:     true,
		},
		"the deadline budget stops the drain": {
			batches: []storage.Batch{
				{Data: json.RawMessage(goodBatch), DeleteKey: "key-1"},
			},
			deadline:  time.Second,
			wantCalls: 0,
		},
	}

	for name, tc := range tests {
		t.Run(name, func(t *testing.T) {
			t.Parallel()

			var callCount atomic.Int32
			server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, req *http.Request) {
				callCount.Add(1)

				body, err := io.ReadAll(req.Body)
				if !assert.NoError(t, err, "read body") {
					return
				}

				assert.Equal(t, "true", req.Header.Get(ddRetryHeader), ddRetryHeader)

				if strings.Contains(string(body), "poison") {
					w.WriteHeader(http.StatusBadRequest)
					return
				}
				w.WriteHeader(http.StatusAccepted)
			}))
			t.Cleanup(server.Close)

			var (
				mu      sync.Mutex
				deleted []string
			)
			store := mocks.NewMockStorage(gomock.NewController(t))
			store.EXPECT().
				Fetch(gomock.Any()).
				Return(iter.Seq2[storage.Batch, error](func(yield func(storage.Batch, error) bool) {
					for _, batch := range tc.batches {
						if !yield(batch, nil) {
							return
						}
					}
				}))
			store.EXPECT().
				Delete(gomock.Any(), gomock.Any()).
				DoAndReturn(func(_ context.Context, batch storage.Batch) error {
					mu.Lock()
					deleted = append(deleted, batch.DeleteKey)
					mu.Unlock()

					return tc.deleteErr
				}).
				AnyTimes()

			forwarder := New(
				Config{IntakeURL: server.URL, APIKey: "test-api-key", CompressionLevel: gzip.NoCompression},
				server.Client(),
				store,
			)

			ctx := t.Context()
			if tc.deadline != 0 {
				var cancel context.CancelFunc
				ctx, cancel = context.WithDeadline(ctx, time.Now().Add(tc.deadline))
				t.Cleanup(cancel)
			}

			err := forwarder.Retry(ctx)

			assert.Equal(t, tc.wantCalls, int(callCount.Load()), "intake calls")
			assert.ElementsMatch(t, tc.wantDeletes, deleted, "deleted keys")
			if tc.wantErr {
				require.Error(t, err)
				return
			}
			require.NoError(t, err)
		})
	}
}

func TestForwarder_RetryStopsOnRetryableFailure(t *testing.T) {
	t.Parallel()

	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		w.WriteHeader(http.StatusServiceUnavailable)
	}))
	t.Cleanup(server.Close)

	batches := make([]storage.Batch, 0, 50)
	for i := range 50 {
		batches = append(batches, storage.Batch{
			Data:      json.RawMessage(`[{"message":"good"}]`),
			DeleteKey: fmt.Sprintf("key-%d", i),
		})
	}

	store := mocks.NewMockStorage(gomock.NewController(t))
	store.EXPECT().
		Fetch(gomock.Any()).
		Return(iter.Seq2[storage.Batch, error](func(yield func(storage.Batch, error) bool) {
			for _, batch := range batches {
				if !yield(batch, nil) {
					return
				}
			}
		}))
	store.EXPECT().Delete(gomock.Any(), gomock.Any()).Times(0)

	forwarder := New(
		Config{IntakeURL: server.URL, APIKey: "test-api-key", CompressionLevel: gzip.NoCompression},
		server.Client(),
		store,
	)

	require.Error(t, forwarder.Retry(t.Context()))
}

func TestForwarder_StartDoesNotSetTheRetryHeader(t *testing.T) {
	t.Parallel()

	var got string
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, req *http.Request) {
		got = req.Header.Get(ddRetryHeader)
		w.WriteHeader(http.StatusAccepted)
	}))
	t.Cleanup(server.Close)

	forwarder := New(
		Config{IntakeURL: server.URL, APIKey: "test-api-key", CompressionLevel: gzip.NoCompression},
		server.Client(),
		nil,
	)

	in := make(chan json.RawMessage, 1)
	raw, err := json.Marshal(model.LogEntry{Message: "test payload"})
	require.NoError(t, err)
	in <- raw
	close(in)

	require.NoError(t, forwarder.Start(t.Context(), in, "", ToIntake))
	assert.Empty(t, got)
}

func TestForwarder_StartStoresUnsentBatchesAfterPermanentRejection(t *testing.T) {
	t.Parallel()

	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		w.WriteHeader(http.StatusBadRequest)
	}))
	t.Cleanup(server.Close)

	store := mocks.NewMockStorage(gomock.NewController(t))
	store.EXPECT().Store(gomock.Any(), gomock.Any()).Return(nil).MinTimes(1)

	forwarder := New(
		Config{IntakeURL: server.URL, APIKey: "test-api-key", CompressionLevel: gzip.NoCompression},
		server.Client(),
		store,
	)

	entries := maxLogsPerBatch * (maxBatchesInMemory + httpclient.MaxConcurrency + 10)
	raw, err := json.Marshal(model.LogEntry{Message: "test payload"})
	require.NoError(t, err)

	in := make(chan json.RawMessage, entries)
	for range entries {
		in <- raw
	}
	close(in)

	var sendErr *SendError
	require.ErrorAs(t, forwarder.Start(t.Context(), in, "", ToIntake), &sendErr)
	assert.True(t, sendErr.Permanent, "permanent")
	assert.True(t, sendErr.Stored, "stored")
}

func TestForwarder_StartToStorage(t *testing.T) {
	t.Parallel()

	tests := map[string]struct {
		storage  func(t *testing.T) storage.Storage
		wantErr  bool
		wantSent bool
	}{
		"every batch is stored without reaching the intake": {
			storage: func(t *testing.T) storage.Storage {
				t.Helper()

				store := mocks.NewMockStorage(gomock.NewController(t))
				store.EXPECT().Store(gomock.Any(), gomock.Any()).Return(nil).MinTimes(1)

				return store
			},
		},
		"a store failure still drains the producer": {
			storage: func(t *testing.T) storage.Storage {
				t.Helper()

				store := mocks.NewMockStorage(gomock.NewController(t))
				store.EXPECT().Store(gomock.Any(), gomock.Any()).Return(errors.New("bucket unavailable")).MinTimes(1)

				return store
			},
			wantErr: true,
		},
		"without storage configured it refuses rather than dropping": {
			wantErr: true,
		},
	}

	for name, tc := range tests {
		t.Run(name, func(t *testing.T) {
			t.Parallel()

			var callCount atomic.Int32
			server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
				callCount.Add(1)
				w.WriteHeader(http.StatusAccepted)
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

			entries := maxLogsPerBatch * (maxBatchesInMemory + httpclient.MaxConcurrency + 10)
			raw, err := json.Marshal(model.LogEntry{Message: "test payload"})
			require.NoError(t, err)

			in := make(chan json.RawMessage, entries)
			for range entries {
				in <- raw
			}
			close(in)

			done := make(chan error, 1)
			go func() { done <- forwarder.Start(t.Context(), in, "cloudwatch", ToStorage) }()

			select {
			case err := <-done:
				assert.Zero(t, callCount.Load(), "intake calls")
				if tc.wantErr {
					require.Error(t, err)
					return
				}
				require.NoError(t, err)
			case <-time.After(30 * time.Second):
				t.Fatal("Start never returned")
			}
		})
	}
}
