// Unless explicitly stated otherwise all files in this repository are licensed
// under the Apache License Version 2.0.
// This product includes software developed at Datadog (https://www.datadoghq.com/).
// Copyright 2026-Present Datadog, Inc.

package parsing

import (
	"encoding/json"
	"testing"
)

func TestDetectInvocationSource(t *testing.T) {
	tests := map[string]struct {
		event   json.RawMessage
		wantKey InvocationSource
	}{
		"cloudwatch logs": {
			event:   json.RawMessage(`{"awslogs":{"data":"dGVzdA=="}}`),
			wantKey: InvocationSourceCloudwatchLogs,
		},
		"empty object": {
			event:   json.RawMessage(`{}`),
			wantKey: InvocationSourceUnknown,
		},
		"s3 not yet implemented": {
			event:   json.RawMessage(`{"Records":[{"s3":{"bucket":{"name":"my-bucket"},"object":{"key":"my-key"}}}]}`),
			wantKey: InvocationSourceUnknown,
		},
		"not JSON": {
			event:   json.RawMessage(`not a json`),
			wantKey: InvocationSourceUnknown,
		},
		"empty input": {
			event:   json.RawMessage(``),
			wantKey: InvocationSourceUnknown,
		},
	}

	for name, tc := range tests {
		t.Run(name, func(t *testing.T) {
			got := DetectInvocationSource(tc.event)
			if got != tc.wantKey {
				t.Errorf("got %d, want %d", got, tc.wantKey)
			}
		})
	}
}
