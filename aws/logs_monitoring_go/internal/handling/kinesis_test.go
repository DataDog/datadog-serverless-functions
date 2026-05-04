// Unless explicitly stated otherwise all files in this repository are licensed
// under the Apache License Version 2.0.
// This product includes software developed at Datadog (https://www.datadoghq.com/).
// Copyright 2026-Present Datadog, Inc.

package handling

import (
	"encoding/json"
	"testing"

	"github.com/DataDog/datadog-serverless-functions/aws/logs_monitoring_go/internal/model"
	"github.com/DataDog/datadog-serverless-functions/aws/logs_monitoring_go/internal/testutil"
)

func TestKinesisHandler_Handle(t *testing.T) {
	t.Parallel()

	ctx := testutil.LambdaContext(t)

	tests := map[string]struct {
		event   json.RawMessage
		wantN   int
		wantErr bool
	}{
		"invalid JSON": {
			event:   json.RawMessage(`not json`),
			wantErr: true,
		},
		"no records": {
			event: json.RawMessage(`{"Records":[]}`),
			wantN: 0,
		},
		"single record": {
			event: testutil.MustKinesisEvent(t, testutil.MustGzipJSON(t, map[string]any{
				"messageType": "DATA_MESSAGE",
				"logGroup":    "/aws/lambda/fn",
				"logStream":   "stream",
				"logEvents":   []map[string]any{{"id": "1", "timestamp": 1000, "message": "hello"}},
			})),
			wantN: 1,
		},
		"multiple records": {
			event: testutil.MustKinesisEvent(t,
				testutil.MustGzipJSON(t, map[string]any{
					"messageType": "DATA_MESSAGE",
					"logGroup":    "/aws/lambda/fn-a",
					"logStream":   "stream",
					"logEvents":   []map[string]any{{"id": "1", "timestamp": 1000, "message": "a"}},
				}),
				testutil.MustGzipJSON(t, map[string]any{
					"messageType": "DATA_MESSAGE",
					"logGroup":    "/aws/lambda/fn-b",
					"logStream":   "stream",
					"logEvents":   []map[string]any{{"id": "2", "timestamp": 2000, "message": "b"}},
				}),
			),
			wantN: 2,
		},
		"bad record is skipped": {
			event: testutil.MustKinesisEvent(t,
				[]byte("not valid gzip"),
				testutil.MustGzipJSON(t, map[string]any{
					"messageType": "DATA_MESSAGE",
					"logGroup":    "/aws/lambda/good",
					"logStream":   "stream",
					"logEvents":   []map[string]any{{"id": "1", "timestamp": 1000, "message": "ok"}},
				}),
			),
			wantN: 1,
		},
	}

	for name, tc := range tests {
		t.Run(name, func(t *testing.T) {
			t.Parallel()

			out := make(chan model.LogEntry, tc.wantN)
			handler := NewKinesis(testutil.EmptyConfig())

			err := handler.Handle(ctx, tc.event, out)
			close(out)

			if tc.wantErr {
				if err == nil {
					t.Fatal("want error, got nil")
				}
				return
			}
			if err != nil {
				t.Fatalf("unexpected error: %v", err)
			}

			var got int
			for range out {
				got++
			}
			if got != tc.wantN {
				t.Errorf("got %d entries, want %d", got, tc.wantN)
			}
		})
	}
}
