// Unless explicitly stated otherwise all files in this repository are licensed
// under the Apache License Version 2.0.
// This product includes software developed at Datadog (https://www.datadoghq.com/).
// Copyright 2026-Present Datadog, Inc.

package filtering

import (
	"testing"
)

func TestFilterShouldExclude(t *testing.T) {
	t.Parallel()

	tests := map[string]struct {
		include string
		exclude string
		msg     string
		want    bool
	}{
		"no filter": {
			msg:  "hello",
			want: false,
		},
		"include match": {
			include: `error`,
			msg:     "an error occurred",
			want:    false,
		},
		"include no match": {
			include: `error`,
			msg:     "hello",
			want:    true,
		},
		"exclude match": {
			exclude: `DEBUG`,
			msg:     "DEBUG message",
			want:    true,
		},
		"exclude no match": {
			exclude: `DEBUG`,
			msg:     "INFO message",
			want:    false,
		},
		"exclude overrides include": {
			include: `error`,
			exclude: `error`,
			msg:     "error message",
			want:    true,
		},
		"include match exclude not match": {
			include: `error`,
			exclude: `DEBUG`,
			msg:     "error happened",
			want:    false,
		},
		"include and exclude neither match": {
			include: `error`,
			exclude: `DEBUG`,
			msg:     "INFO normal",
			want:    true,
		},
		"partial match": {
			include: `err`,
			msg:     "some error here",
			want:    false,
		},
		"case sensitive": {
			include: `ERROR`,
			msg:     "error",
			want:    true,
		},
		"special chars": {
			include: `\d{3}`,
			msg:     "error 404",
			want:    false,
		},
		"empty message": {
			include: `error`,
			msg:     "",
			want:    true,
		},
	}

	for name, tc := range tests {
		t.Run(name, func(t *testing.T) {
			t.Parallel()
			f, err := NewFilter(tc.include, tc.exclude)
			if err != nil {
				t.Fatalf("NewFilter: %v", err)
			}
			if got := f.ShouldExclude(tc.msg); got != tc.want {
				t.Errorf("ShouldExclude(%q) = %v, want %v", tc.msg, got, tc.want)
			}
		})
	}
}
