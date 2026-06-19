// Unless explicitly stated otherwise all files in this repository are licensed
// under the Apache License Version 2.0.
// This product includes software developed at Datadog (https://www.datadoghq.com/).
// Copyright 2026-Present Datadog, Inc.

package batching

import (
	"encoding/json"
	"testing"

	"github.com/DataDog/datadog-serverless-functions/aws/logs_monitoring_go/internal/testutil"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

func TestBatch(t *testing.T) {
	t.Parallel()

	tests := map[string]struct {
		items          []any
		wantBatchItems []int
	}{
		"empty": {
			items:          nil,
			wantBatchItems: nil,
		},
		"single entry": {
			items:          []any{testutil.GenerateJSONLogs(t, 1024)},
			wantBatchItems: []int{1},
		},
		"multiple entries, one batch": {
			items:          []any{testutil.GenerateJSONLogs(t, 1024), testutil.GenerateJSONLogs(t, 1024), testutil.GenerateJSONLogs(t, 1024)},
			wantBatchItems: []int{3},
		},
		"drop oversized entry": {
			items:          []any{testutil.GenerateJSONLogs(t, 1*1024*1024+1)},
			wantBatchItems: nil,
		},
		"split": {
			items: func() (items []any) {
				for range 1001 {
					items = append(items, testutil.GenerateJSONLog(t, 100))
				}
				return
			}(),
			wantBatchItems: []int{1000, 1},
		},
	}

	for name, tc := range tests {
		t.Run(name, func(t *testing.T) {
			t.Parallel()

			cfg := Config{maxItemSize: 1 * 1024 * 1024, maxBatchSize: 5 * 1024 * 1024, maxItemsPerBatch: 1000}
			batcher := New[any](cfg)
			in := testutil.ToChannel(t, tc.items)
			out := make(chan json.RawMessage, len(tc.wantBatchItems))

			err := batcher.Start(t.Context(), in, out)
			close(out)

			got := testutil.Drain(t, out)
			require.NoError(t, err)
			for i := range len(tc.wantBatchItems) {
				var gotItems []json.RawMessage
				_ = json.Unmarshal(got[i], &gotItems)
				assert.Equal(t, len(gotItems), tc.wantBatchItems[i])
			}
		})
	}
}
