// Unless explicitly stated otherwise all files in this repository are licensed
// under the Apache License Version 2.0.
// This product includes software developed at Datadog (https://www.datadoghq.com/).
// Copyright 2026-Present Datadog, Inc.

package model

import (
	"encoding/json"
	"testing"

	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

func TestTags(t *testing.T) {
	t.Parallel()

	tests := map[string]struct {
		tags Tags
		want string
	}{
		"multiple_tags": {
			tags: Tags{"env:prod", "team:aws"},
			want: `"env:prod,team:aws"`,
		},
		"single_tag": {
			tags: Tags{"env:prod"},
			want: `"env:prod"`,
		},
		"empty": {
			tags: Tags{},
			want: `""`,
		},
		"nil": {
			tags: nil,
			want: `""`,
		},
	}

	for name, tc := range tests {
		t.Run(name, func(t *testing.T) {
			t.Parallel()
			got, err := json.Marshal(tc.tags)
			require.NoError(t, err, "marshal")
			assert.Equal(t, tc.want, string(got))

			var tags Tags
			require.NoError(t, json.Unmarshal(got, &tags), "unmarshal")
			if len(tc.tags) == 0 {
				assert.Empty(t, tags)
			} else {
				assert.Equal(t, tc.tags, tags)
			}
		})
	}
}
