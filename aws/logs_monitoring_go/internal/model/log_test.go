// Unless explicitly stated otherwise all files in this repository are licensed
// under the Apache License Version 2.0.
// This product includes software developed at Datadog (https://www.datadoghq.com/).
// Copyright 2026-Present Datadog, Inc.

package model

import (
	"encoding/json"
	"slices"
	"testing"
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
			if err != nil {
				t.Fatalf("unexpected marshal error: %v", err)
			}
			if string(got) != tc.want {
				t.Errorf("got %s, want %s", got, tc.want)
			}

			var tags Tags
			err = json.Unmarshal(got, &tags)
			if err != nil {
				t.Fatalf("unexpected unmarshal error: %v", err)
			}
			if !slices.Equal(tc.tags, tags) {
				t.Errorf("expected %v, got %v", tc.tags, tags)
			}
		})
	}
}
