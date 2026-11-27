// Unless explicitly stated otherwise all files in this repository are licensed
// under the Apache License Version 2.0.
// This product includes software developed at Datadog (https://www.datadoghq.com/).
// Copyright 2026-Present Datadog, Inc.

package apikey

import (
	"testing"

	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

func TestStaticAPIKeySource_Get(t *testing.T) {
	t.Parallel()

	tests := map[string]struct {
		source    *fakeAPIKeySource
		calls     int32
		wantCalls int32
		wantErr   bool
	}{
		"success": {
			source:    &fakeAPIKeySource{fn: fakeSuccess},
			calls:     1,
			wantCalls: 1,
		},
		"multiple calls": {
			source:    &fakeAPIKeySource{fn: fakeSuccess},
			calls:     5,
			wantCalls: 1,
		},
		"error": {
			source:    &fakeAPIKeySource{fn: fakeFailure},
			calls:     1,
			wantCalls: 1,
			wantErr:   true,
		},
	}

	for name, tc := range tests {
		t.Run(name, func(t *testing.T) {
			t.Parallel()

			ks := &StaticAPIKeySource{Source: tc.source}

			for range tc.calls {
				_, err := ks.Get(t.Context())
				if tc.wantErr {
					require.Error(t, err)
				} else {
					require.NoError(t, err)
				}
			}

			assert.Equal(t, tc.wantCalls, tc.source.calls.Load())
		})
	}
}
