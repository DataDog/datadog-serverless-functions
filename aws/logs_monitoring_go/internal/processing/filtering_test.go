// Unless explicitly stated otherwise all files in this repository are licensed
// under the Apache License Version 2.0.
// This product includes software developed at Datadog (https://www.datadoghq.com/).
// Copyright 2026-Present Datadog, Inc.

package processing

import (
	"testing"

	"github.com/DataDog/datadog-serverless-functions/aws/logs_monitoring_go/internal/config"
)

func TestFilterMatch(t *testing.T) {
	t.Parallel()

	tests := map[string]struct {
		cfg  config.FilteringConfig
		msg  string
		want bool
	}{
		"no_filter": {
			cfg:  config.FilteringConfig{},
			msg:  "hello",
			want: true,
		},
		"include_match": {
			cfg:  config.FilteringConfig{IncludePattern: `error`},
			msg:  "an error occurred",
			want: true,
		},
		"include_no_match": {
			cfg:  config.FilteringConfig{IncludePattern: `error`},
			msg:  "hello",
			want: false,
		},
		"exclude_match": {
			cfg:  config.FilteringConfig{ExcludePattern: `DEBUG`},
			msg:  "DEBUG message",
			want: false,
		},
		"exclude_no_match": {
			cfg:  config.FilteringConfig{ExcludePattern: `DEBUG`},
			msg:  "INFO message",
			want: true,
		},
		"exclude_overrides_include": {
			cfg:  config.FilteringConfig{IncludePattern: `error`, ExcludePattern: `error`},
			msg:  "error message",
			want: false,
		},
		"include_match_exclude_not_match": {
			cfg:  config.FilteringConfig{IncludePattern: `error`, ExcludePattern: `DEBUG`},
			msg:  "error happened",
			want: true,
		},
		"include_and_exclude_neither_match": {
			cfg:  config.FilteringConfig{IncludePattern: `error`, ExcludePattern: `DEBUG`},
			msg:  "INFO normal",
			want: false,
		},
		"partial_match": {
			cfg:  config.FilteringConfig{IncludePattern: `err`},
			msg:  "some error here",
			want: true,
		},
		"case_sensitive": {
			cfg:  config.FilteringConfig{IncludePattern: `ERROR`},
			msg:  "error",
			want: false,
		},
		"special_chars": {
			cfg:  config.FilteringConfig{IncludePattern: `\d{3}`},
			msg:  "error 404",
			want: true,
		},
		"empty": {
			cfg:  config.FilteringConfig{IncludePattern: `error`},
			msg:  "",
			want: false,
		},
	}

	for name, tc := range tests {
		t.Run(name, func(t *testing.T) {
			t.Parallel()
			f := NewFilter(tc.cfg)
			if got := f.Match(tc.msg); got != tc.want {
				t.Errorf("Match(%q) = %v, want %v", tc.msg, got, tc.want)
			}
		})
	}
}
