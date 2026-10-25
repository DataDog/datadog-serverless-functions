// Unless explicitly stated otherwise all files in this repository are licensed
// under the Apache License Version 2.0.
// This product includes software developed at Datadog (https://www.datadoghq.com/).
// Copyright 2026-Present Datadog, Inc.

package pipeline

import (
	"compress/gzip"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"sync/atomic"
	"testing"

	"github.com/DataDog/datadog-serverless-functions/aws/logs_monitoring_go/internal/forwarder"
	"github.com/DataDog/datadog-serverless-functions/aws/logs_monitoring_go/internal/handler"
	"github.com/DataDog/datadog-serverless-functions/aws/logs_monitoring_go/internal/model"
	"github.com/DataDog/datadog-serverless-functions/aws/logs_monitoring_go/internal/testutil"
	"github.com/stretchr/testify/require"

	awsevents "github.com/aws/aws-lambda-go/events"
)

func snsBody(message string) string {
	return `{"Type":"Notification","Message":"` + message + `"}`
}

func newPipeline(t *testing.T, intakeURL string) Pipeline {
	t.Helper()

	fwd := forwarder.New(
		forwarder.Config{APIKey: "test-api-key", IntakeURL: intakeURL, CompressionLevel: gzip.NoCompression},
		http.DefaultClient,
		nil,
	)

	return New(handler.Config{}, nil, nil, fwd, nil)
}

func TestPipelineStartSQS(t *testing.T) {
	t.Parallel()

	tests := map[string]struct {
		records         []awsevents.SQSMessage
		statuses        []int
		wantUnprocessed []string
	}{
		"all records delivered": {
			records:  []awsevents.SQSMessage{testutil.SQSRecord("msg-1", snsBody("one")), testutil.SQSRecord("msg-2", snsBody("two"))},
			statuses: []int{http.StatusAccepted, http.StatusAccepted},
		},
		"intake failure stops the batch and returns the rest": {
			records: []awsevents.SQSMessage{
				testutil.SQSRecord("msg-1", snsBody("one")),
				testutil.SQSRecord("msg-2", snsBody("two")),
				testutil.SQSRecord("msg-3", snsBody("three")),
			},
			statuses:        []int{http.StatusAccepted, http.StatusServiceUnavailable},
			wantUnprocessed: []string{"msg-2", "msg-3"},
		},
		"permanent rejection is message scoped": {
			records: []awsevents.SQSMessage{
				testutil.SQSRecord("msg-1", snsBody("one")),
				testutil.SQSRecord("msg-2", snsBody("two")),
				testutil.SQSRecord("msg-3", snsBody("three")),
			},
			statuses:        []int{http.StatusAccepted, http.StatusBadRequest, http.StatusAccepted},
			wantUnprocessed: []string{"msg-2"},
		},
		"unparseable record does not block healthy ones": {
			records: []awsevents.SQSMessage{
				testutil.SQSRecord("msg-1", snsBody("one")),
				testutil.SQSRecord("msg-2", `{"not":"a known event"}`),
				testutil.SQSRecord("msg-3", snsBody("three")),
			},
			statuses:        []int{http.StatusAccepted, http.StatusAccepted},
			wantUnprocessed: []string{"msg-2"},
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

			result, err := newPipeline(t, server.URL).Start(t.Context(), model.LambdaOrigin{}, testutil.MustSQSEvent(t, tc.records...))

			require.NoError(t, err)
			require.True(t, result.SQSBatch)
			require.Equal(t, tc.wantUnprocessed, result.Unprocessed)
		})
	}
}

func TestPipelineStartSQSUnparseableEnvelopeFailsInvocation(t *testing.T) {
	t.Parallel()

	event := json.RawMessage(`{"Records":[{"eventSource":"aws:sqs","body":0}]}`)

	result, err := newPipeline(t, "http://127.0.0.1:1").Start(t.Context(), model.LambdaOrigin{}, event)

	require.Error(t, err)
	require.False(t, result.SQSBatch)
	require.Nil(t, result.Unprocessed)
}
