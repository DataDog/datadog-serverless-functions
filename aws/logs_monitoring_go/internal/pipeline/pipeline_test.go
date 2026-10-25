// Unless explicitly stated otherwise all files in this repository are licensed
// under the Apache License Version 2.0.
// This product includes software developed at Datadog (https://www.datadoghq.com/).
// Copyright 2026-Present Datadog, Inc.

package pipeline

import (
	"compress/gzip"
	"context"
	"encoding/json"
	"errors"
	"net/http"
	"net/http/httptest"
	"strings"
	"sync/atomic"
	"testing"

	"github.com/DataDog/datadog-serverless-functions/aws/logs_monitoring_go/internal/forwarder"
	"github.com/DataDog/datadog-serverless-functions/aws/logs_monitoring_go/internal/handler"
	"github.com/DataDog/datadog-serverless-functions/aws/logs_monitoring_go/internal/model"
	"github.com/DataDog/datadog-serverless-functions/aws/logs_monitoring_go/internal/storage"
	"github.com/DataDog/datadog-serverless-functions/aws/logs_monitoring_go/internal/storage/mocks"
	"github.com/DataDog/datadog-serverless-functions/aws/logs_monitoring_go/internal/testutil"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
	"go.uber.org/mock/gomock"

	awsevents "github.com/aws/aws-lambda-go/events"
)

func snsBody(message string) string {
	return `{"Type":"Notification","Message":"` + message + `"}`
}

func newPipeline(t *testing.T, intakeURL string, store storage.Storage) Pipeline {
	t.Helper()

	fwd := forwarder.New(
		forwarder.Config{APIKey: "test-api-key", IntakeURL: intakeURL, CompressionLevel: gzip.NoCompression},
		http.DefaultClient,
		store,
	)

	return New(handler.Config{}, nil, nil, fwd, nil)
}

func TestPipelineStartSQS(t *testing.T) {
	t.Parallel()

	tests := map[string]struct {
		records         []awsevents.SQSMessage
		statuses        []int
		wantUnprocessed []string
		wantCalls       int
	}{
		"all records delivered": {
			records:   []awsevents.SQSMessage{testutil.SQSRecord("msg-1", snsBody("one")), testutil.SQSRecord("msg-2", snsBody("two"))},
			statuses:  []int{http.StatusAccepted, http.StatusAccepted},
			wantCalls: 2,
		},
		"intake failure stops the batch and returns the rest": {
			records: []awsevents.SQSMessage{
				testutil.SQSRecord("msg-1", snsBody("one")),
				testutil.SQSRecord("msg-2", snsBody("two")),
				testutil.SQSRecord("msg-3", snsBody("three")),
			},
			statuses:        []int{http.StatusAccepted, http.StatusServiceUnavailable},
			wantUnprocessed: []string{"msg-2", "msg-3"},
			wantCalls:       2,
		},
		"permanent rejection is dropped and the batch keeps going": {
			records: []awsevents.SQSMessage{
				testutil.SQSRecord("msg-1", snsBody("one")),
				testutil.SQSRecord("msg-2", snsBody("two")),
				testutil.SQSRecord("msg-3", snsBody("three")),
			},
			statuses:  []int{http.StatusAccepted, http.StatusBadRequest, http.StatusAccepted},
			wantCalls: 3,
		},
		"unparseable record does not block healthy ones": {
			records: []awsevents.SQSMessage{
				testutil.SQSRecord("msg-1", snsBody("one")),
				testutil.SQSRecord("msg-2", `{"not":"a known event"}`),
				testutil.SQSRecord("msg-3", snsBody("three")),
			},
			statuses:        []int{http.StatusAccepted, http.StatusAccepted},
			wantUnprocessed: []string{"msg-2"},
			wantCalls:       2,
		},
	}

	for name, tc := range tests {
		t.Run(name, func(t *testing.T) {
			t.Parallel()

			var sent atomic.Int32
			server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
				i := int(sent.Add(1)) - 1
				status := http.StatusAccepted
				if i < len(tc.statuses) {
					status = tc.statuses[i]
				}
				w.WriteHeader(status)
			}))
			t.Cleanup(server.Close)

			result, err := newPipeline(t, server.URL, nil).Start(t.Context(), model.LambdaOrigin{}, testutil.MustSQSEvent(t, tc.records...))

			require.NoError(t, err)
			require.True(t, result.SQSBatch)
			assert.Equal(t, tc.wantUnprocessed, result.Unprocessed, "unprocessed")
			assert.Equal(t, tc.wantCalls, int(sent.Load()), "intake calls")
		})
	}
}

func TestPipelineStartSQSUnparseableEnvelopeFailsInvocation(t *testing.T) {
	t.Parallel()

	event := json.RawMessage(`{"Records":[{"eventSource":"aws:sqs","body":0}]}`)

	result, err := newPipeline(t, "http://127.0.0.1:1", nil).Start(t.Context(), model.LambdaOrigin{}, event)

	require.Error(t, err)
	require.False(t, result.SQSBatch)
	require.Nil(t, result.Unprocessed)
}

func TestPipelineStartSQSRoutesToStorage(t *testing.T) {
	t.Parallel()

	records := []awsevents.SQSMessage{
		testutil.SQSRecord("msg-1", snsBody("one")),
		testutil.SQSRecord("msg-2", snsBody("two")),
		testutil.SQSRecord("msg-3", snsBody("three")),
		testutil.SQSRecord("msg-4", snsBody("four")),
	}

	tests := map[string]struct {
		records         []awsevents.SQSMessage
		failStoreOf     string
		wantUnprocessed []string
	}{
		"remaining messages bypass the intake and are acked": {
			records: records,
		},
		"storage failing during the bypass returns the rest": {
			records:         records,
			failStoreOf:     "four",
			wantUnprocessed: []string{"msg-4"},
		},
		"an unparseable message during the bypass is message scoped": {
			records: []awsevents.SQSMessage{
				testutil.SQSRecord("msg-1", snsBody("one")),
				testutil.SQSRecord("msg-2", snsBody("two")),
				testutil.SQSRecord("msg-3", `{"not":"a known event"}`),
				testutil.SQSRecord("msg-4", snsBody("four")),
			},
			wantUnprocessed: []string{"msg-3"},
		},
	}

	for name, tc := range tests {
		t.Run(name, func(t *testing.T) {
			t.Parallel()

			var sent atomic.Int32
			server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
				status := http.StatusAccepted
				if sent.Add(1) == 2 {
					status = http.StatusServiceUnavailable
				}
				w.WriteHeader(status)
			}))
			t.Cleanup(server.Close)

			store := mocks.NewMockStorage(gomock.NewController(t))
			store.EXPECT().
				Store(gomock.Any(), gomock.Any()).
				DoAndReturn(func(_ context.Context, batch storage.Batch) error {
					if tc.failStoreOf != "" && strings.Contains(string(batch.Data), tc.failStoreOf) {
						return errors.New("bucket unavailable")
					}

					return nil
				}).
				AnyTimes()

			result, err := newPipeline(t, server.URL, store).
				Start(t.Context(), model.LambdaOrigin{}, testutil.MustSQSEvent(t, tc.records...))

			require.NoError(t, err)
			require.True(t, result.SQSBatch)
			assert.Equal(t, tc.wantUnprocessed, result.Unprocessed, "unprocessed")
			assert.Equal(t, 2, int(sent.Load()), "intake calls")
		})
	}
}
