// Unless explicitly stated otherwise all files in this repository are licensed
// under the Apache License Version 2.0.
// This product includes software developed at Datadog (https://www.datadoghq.com/).
// Copyright 2026-Present Datadog, Inc.

package filtering

import (
	"regexp"
	"testing"

	"github.com/stretchr/testify/assert"
)

func TestFilterer_ShouldExclude(t *testing.T) {
	t.Parallel()

	tests := map[string]struct {
		includeRe *regexp.Regexp
		excludeRe *regexp.Regexp
		msg       string
		want      bool
	}{
		"no filter": {
			msg:  "hello",
			want: false,
		},
		"include match": {
			includeRe: regexp.MustCompile(`error`),
			msg:       "an error occurred",
			want:      false,
		},
		"include no match": {
			includeRe: regexp.MustCompile(`error`),
			msg:       "hello",
			want:      true,
		},
		"exclude match": {
			excludeRe: regexp.MustCompile(`DEBUG`),
			msg:       "DEBUG message",
			want:      true,
		},
		"exclude no match": {
			excludeRe: regexp.MustCompile(`DEBUG`),
			msg:       "INFO message",
			want:      false,
		},
		"exclude overrides include": {
			includeRe: regexp.MustCompile(`error`),
			excludeRe: regexp.MustCompile(`error`),
			msg:       "error message",
			want:      true,
		},
		"include match exclude not match": {
			includeRe: regexp.MustCompile(`error`),
			excludeRe: regexp.MustCompile(`DEBUG`),
			msg:       "error happened",
			want:      false,
		},
		"include and exclude neither match": {
			includeRe: regexp.MustCompile(`error`),
			excludeRe: regexp.MustCompile(`DEBUG`),
			msg:       "INFO normal",
			want:      true,
		},
		"partial match": {
			includeRe: regexp.MustCompile(`err`),
			msg:       "some error here",
			want:      false,
		},
		"case sensitive": {
			includeRe: regexp.MustCompile(`ERROR`),
			msg:       "error",
			want:      true,
		},
		"special chars": {
			includeRe: regexp.MustCompile(`\d{3}`),
			msg:       "error 404",
			want:      false,
		},
		"empty message": {
			includeRe: regexp.MustCompile(`error`),
			msg:       "",
			want:      true,
		},
	}

	for name, tc := range tests {
		t.Run(name, func(t *testing.T) {
			t.Parallel()

			filterer := NewFilterer(tc.includeRe, tc.excludeRe)

			assert.Equal(t, tc.want, filterer.ShouldExclude(tc.msg))
		})
	}
}
