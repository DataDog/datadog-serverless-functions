// Unless explicitly stated otherwise all files in this repository are licensed
// under the Apache License Version 2.0.
// This product includes software developed at Datadog (https://www.datadoghq.com/).
// Copyright 2026-Present Datadog, Inc.

package scrubbing

import (
	"regexp"
	"testing"

	"github.com/stretchr/testify/assert"
)

func TestNewScrubber(t *testing.T) {
	t.Parallel()

	tests := map[string]struct {
		customMatchRe *regexp.Regexp
		ip            bool
		email         bool
		nRules        int
	}{
		"no rules": {
			nRules: 0,
		},
		"ip only": {
			ip:     true,
			nRules: 1,
		},
		"email only": {
			email:  true,
			nRules: 1,
		},
		"ip and email": {
			ip:     true,
			email:  true,
			nRules: 2,
		},
		"custom rule": {
			customMatchRe: regexp.MustCompile("error"),
			nRules:        1,
		},
		"all rules": {
			ip:            true,
			email:         true,
			customMatchRe: regexp.MustCompile(`secret`),
			nRules:        3,
		},
	}

	for name, tc := range tests {
		t.Run(name, func(t *testing.T) {
			t.Parallel()

			scrubber := NewScrubber(tc.customMatchRe, "", tc.ip, tc.email)

			assert.Len(t, scrubber.rules, tc.nRules)
		})
	}
}

func TestScrub(t *testing.T) {
	t.Parallel()

	tests := map[string]struct {
		customMatchRe     *regexp.Regexp
		customReplacement string
		ip                bool
		email             bool
		content           string
		want              string
	}{
		"ip_redaction": {
			ip:      true,
			content: "connected from 192.168.1.1 to 10.0.0.1",
			want:    "connected from xxx.xxx.xxx.xxx to xxx.xxx.xxx.xxx",
		},
		"email_redaction": {
			email:   true,
			content: "user john.doe@example.com logged in",
			want:    "user xxxxx@xxxxx.com logged in",
		},
		"custom_pattern": {
			customMatchRe:     regexp.MustCompile(`secret-\w+`),
			customReplacement: "[REDACTED]",
			content:           "token=secret-abc123 visible",
			want:              "token=[REDACTED] visible",
		},
		"custom_empty_replacement": {
			customMatchRe: regexp.MustCompile(`remove-this `),
			content:       "remove-this here",
			want:          "here",
		},
		"ip_and_email_sequential": {
			ip:      true,
			email:   true,
			content: "192.168.1.1 user@host.com",
			want:    "xxx.xxx.xxx.xxx xxxxx@xxxxx.com",
		},
		"no_match": {
			ip:      true,
			email:   true,
			content: "clean message with no sensitive data",
			want:    "clean message with no sensitive data",
		},
		"multiple_ips": {
			ip:      true,
			content: "src=1.2.3.4 dst=5.6.7.8 via=10.0.0.1",
			want:    "src=xxx.xxx.xxx.xxx dst=xxx.xxx.xxx.xxx via=xxx.xxx.xxx.xxx",
		},
		"non_ascii_custom": {
			customMatchRe:     regexp.MustCompile(`[^\x01-\x7f]+`),
			customReplacement: "xxxxx",
			content:           "abcdef\u65e5\u672c\u8a9eefg\u304b\u304d\u304f\u3051\u3053hij", // abcdef日本語efgかきくけこhij
			want:              "abcdefxxxxxefgxxxxxhij",
		},
	}

	for name, tc := range tests {
		t.Run(name, func(t *testing.T) {
			t.Parallel()

			scrubber := NewScrubber(tc.customMatchRe, tc.customReplacement, tc.ip, tc.email)

			assert.Equal(t, tc.want, scrubber.Apply(tc.content))
		})
	}
}
