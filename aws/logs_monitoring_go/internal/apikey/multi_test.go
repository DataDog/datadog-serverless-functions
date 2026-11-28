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

func TestMultiAPIKeySource_Get(t *testing.T) {
	t.Parallel()

	tests := map[string]struct {
		primary            *fakeAPIKeySource
		secondary          *fakeAPIKeySource
		wantPrimaryCalls   int32
		wantSecondaryCalls int32
		wantErr            bool
	}{
		"primary succeeds": {
			primary:            &fakeAPIKeySource{fn: fakeSuccess},
			secondary:          &fakeAPIKeySource{fn: fakeFailure},
			wantPrimaryCalls:   1,
			wantSecondaryCalls: 0,
		},
		"primary fails, secondary succeeds": {
			primary:            &fakeAPIKeySource{fn: fakeFailure},
			secondary:          &fakeAPIKeySource{fn: fakeSuccess},
			wantPrimaryCalls:   1,
			wantSecondaryCalls: 1,
		},
		"both fails": {
			primary:            &fakeAPIKeySource{fn: fakeFailure},
			secondary:          &fakeAPIKeySource{fn: fakeFailure},
			wantPrimaryCalls:   1,
			wantSecondaryCalls: 1,
			wantErr:            true,
		},
	}

	for name, tc := range tests {
		t.Run(name, func(t *testing.T) {
			t.Parallel()

			ks := MultiAPIKeySource{Primary: tc.primary, Secondary: tc.secondary}

			_, err := ks.Get(t.Context())
			if tc.wantErr {
				require.Error(t, err)
			} else {
				require.NoError(t, err)
			}

			assert.Equal(t, tc.wantPrimaryCalls, tc.primary.calls.Load())
			assert.Equal(t, tc.wantSecondaryCalls, tc.secondary.calls.Load())
		})
	}
}
