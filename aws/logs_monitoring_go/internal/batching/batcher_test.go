// Unless explicitly stated otherwise all files in this repository are licensed
// under the Apache License Version 2.0.
// This product includes software developed at Datadog (https://www.datadoghq.com/).
// Copyright 2026-Present Datadog, Inc.

package batching

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
			entries:         []model.LogEntry{model.NewLogEntry()},
			wantBatchCount:  1,
			wantEntryCounts: []int{1},
		},
		"multiple entries, one batch": {
			entries:         []model.LogEntry{model.NewLogEntry(), model.NewLogEntry(), model.NewLogEntry()},
			wantBatchCount:  1,
			wantEntryCounts: []int{3},
		},
		"drop oversized entry": {
			entries: func() []model.LogEntry {
				entry := model.NewLogEntry()
				entry.Message = strings.Repeat("a", maxItemSize+1)
				return []model.LogEntry{entry}
			}(),
			wantBatchCount:  0,
			wantEntryCounts: nil,
		},
		"split": {
			entries: func() []model.LogEntry {
				entries := make([]model.LogEntry, maxItemsPerBatch+1)
				for i := range entries {
					entries[i] = model.NewLogEntry()
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

			in := make(chan model.LogEntry, len(tc.entries))
			out := make(chan []byte, len(tc.wantEntryCounts))
			for _, entry := range tc.entries {
				in <- entry
			}
			close(in)

			batcher := NewBatcher()
			err := batcher.Batch(t.Context(), in, out)
			if err != nil {
				t.Fatalf("unexpected error: %v", err)
			}
			close(out)

			var batches [][]byte
			for b := range out {
				batches = append(batches, b)
			}

			if len(batches) != tc.wantBatchCount {
				t.Fatalf("Batch() got %d batches, want %d", len(batches), tc.wantBatchCount)
			}

			for i, wantCount := range tc.wantEntryCounts {
				var entries []model.LogEntry
				if err := json.Unmarshal(batches[i], &entries); err != nil {
					t.Fatalf("Batch() failed to unmarshal batch %d: %v", i, err)
				}
				if len(entries) != wantCount {
					t.Errorf("Batch() batch %d: got %d entries, want %d", i, len(entries), wantCount)
				}
			}
		})
	}
}
