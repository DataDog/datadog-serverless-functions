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
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
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
				entry.Message = strings.Repeat("a", 1*1024*1024+1)
				return []model.LogEntry{entry}
			}(),
			wantBatchCount:  0,
			wantEntryCounts: nil,
		},
		"split": {
			entries:         make([]model.LogEntry, 1001),
			wantBatchCount:  2,
			wantEntryCounts: []int{1000, 1},
		},
	}

	for name, tc := range tests {
		t.Run(name, func(t *testing.T) {
			t.Parallel()

			in := make(chan model.LogEntry, len(tc.entries))
			out := make(chan json.RawMessage, len(tc.wantEntryCounts))
			for _, entry := range tc.entries {
				in <- entry
			}
			close(in)

			batcher := New()
			err := batcher.Start(t.Context(), in, out)
			require.NoError(t, err)
			close(out)

			var batches [][]byte
			for b := range out {
				batches = append(batches, b)
			}

			require.Len(t, batches, tc.wantBatchCount)

			for i, wantCount := range tc.wantEntryCounts {
				var entries []model.LogEntry
				require.NoError(t, json.Unmarshal(batches[i], &entries))
				assert.Len(t, entries, wantCount)
			}
		})
	}
}
