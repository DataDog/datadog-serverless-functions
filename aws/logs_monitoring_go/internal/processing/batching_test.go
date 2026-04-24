// Unless explicitly stated otherwise all files in this repository are licensed
// under the Apache License Version 2.0.
// This product includes software developed at Datadog (https://www.datadoghq.com/).
// Copyright 2026-Present Datadog, Inc.

package processing

import (
	"encoding/json"
	"strings"
	"testing"

	"github.com/DataDog/datadog-serverless-functions/aws/logs_monitoring_go/internal/model"
)

func TestBatch(t *testing.T) {
	t.Parallel()

	tests := map[string]struct {
		entries         []model.LogEntry
		wantBatchCount  int
		wantEntryCounts []int
	}{
		"empty": {
			entries:        nil,
			wantBatchCount: 0,
		},
		"single entry": {
			entries:         []model.LogEntry{makeTestLogEntry()},
			wantBatchCount:  1,
			wantEntryCounts: []int{1},
		},
		"multiple entries, one batch": {
			entries:         []model.LogEntry{makeTestLogEntry(), makeTestLogEntry(), makeTestLogEntry()},
			wantBatchCount:  1,
			wantEntryCounts: []int{3},
		},
		"drop oversized entry": {
			entries:         []model.LogEntry{model.NewLogEntry(nil, nil, strings.Repeat("x", maxItemSize+1), "", ""), makeTestLogEntry()},
			wantBatchCount:  1,
			wantEntryCounts: []int{1},
		},
		"splits_on_max_items": {
			entries: func() []model.LogEntry {
				entries := make([]model.LogEntry, maxItemsPerBatch+1)
				for i := range entries {
					entries[i] = makeTestLogEntry()
				}
				return entries
			}(),
			wantBatchCount:  2,
			wantEntryCounts: []int{maxItemsPerBatch, 1},
		},
	}

	for name, tc := range tests {
		t.Run(name, func(t *testing.T) {
			t.Parallel()

			batches := collectBatches(t, feedChannel(tc.entries...))
			if len(batches) != tc.wantBatchCount {
				t.Fatalf("expected %d batches, got %d", tc.wantBatchCount, len(batches))
			}

			for i, wantCount := range tc.wantEntryCounts {
				var entries []model.LogEntry
				if err := json.Unmarshal(batches[i], &entries); err != nil {
					t.Fatalf("failed to unmarshal batch %d: %v", i, err)
				}
				if len(entries) != wantCount {
					t.Errorf("batch %d: expected %d entries, got %d", i, wantCount, len(entries))
				}
			}
		})
	}
}

func makeTestLogEntry() model.LogEntry {
	return model.NewLogEntry(nil, nil, "test", "test", "test")
}

func feedChannel(entries ...model.LogEntry) <-chan model.LogEntry {
	ch := make(chan model.LogEntry, len(entries))
	for _, e := range entries {
		ch <- e
	}
	close(ch)
	return ch
}

func collectBatches(t *testing.T, in <-chan model.LogEntry) [][]byte {
	t.Helper()

	out := make(chan []byte, 100)
	batcher := NewBatcher[model.LogEntry]()
	err := batcher.Batch(t.Context(), in, out)
	close(out)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}

	var batches [][]byte
	for b := range out {
		batches = append(batches, b)
	}
	return batches
}
