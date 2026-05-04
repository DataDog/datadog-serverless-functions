// Unless explicitly stated otherwise all files in this repository are licensed
// under the Apache License Version 2.0.
// This product includes software developed at Datadog (https://www.datadoghq.com/).
// Copyright 2026-Present Datadog, Inc.

package scrubbing

import (
	"testing"
)

func TestNewScrubber(t *testing.T) {
	t.Parallel()

	tests := map[string]struct {
		customMatch       string
		customReplacement string
		ip                bool
		email             bool
		nRules            int
		wantErr           bool
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
			customMatch:       `\d+`,
			customReplacement: "NUM",
			nRules:            1,
		},
		"all rules": {
			ip:                true,
			email:             true,
			customMatch:       `secret`,
			customReplacement: "[REDACTED]",
			nRules:            3,
		},
		"invalid custom regex": {
			customMatch: `([invalid`,
			wantErr:     true,
		},
	}

	for name, tc := range tests {
		t.Run(name, func(t *testing.T) {
			t.Parallel()
			s, err := NewScrubber(tc.customMatch, tc.customReplacement, tc.ip, tc.email)
			if tc.wantErr {
				if err == nil {
					t.Fatal("want error, got nil")
				}
				return
			}
			if err != nil {
				t.Fatalf("unexpected error: %v", err)
			}
			if got := len(s.rules); got != tc.nRules {
				t.Errorf("got %d rules, want %d", got, tc.nRules)
			}
		})
	}
}

func TestScrub(t *testing.T) {
	t.Parallel()

	tests := map[string]struct {
		customMatch       string
		customReplacement string
		ip                bool
		email             bool
		input             string
		want              string
	}{
		"ip_redaction": {
			ip:    true,
			input: "connected from 192.168.1.1 to 10.0.0.1",
			want:  "connected from xxx.xxx.xxx.xxx to xxx.xxx.xxx.xxx",
		},
		"email_redaction": {
			email: true,
			input: "user john.doe@example.com logged in",
			want:  "user xxxxx@xxxxx.com logged in",
		},
		"custom_pattern": {
			customMatch:       `secret-\w+`,
			customReplacement: "[REDACTED]",
			input:             "token=secret-abc123 visible",
			want:              "token=[REDACTED] visible",
		},
		"custom_empty_replacement": {
			customMatch: `remove-this `,
			input:       "remove-this here",
			want:        "here",
		},
		"ip_and_email_sequential": {
			ip:    true,
			email: true,
			input: "192.168.1.1 user@host.com",
			want:  "xxx.xxx.xxx.xxx xxxxx@xxxxx.com",
		},
		"no_match": {
			ip:    true,
			email: true,
			input: "clean message with no sensitive data",
			want:  "clean message with no sensitive data",
		},
		"multiple_ips": {
			ip:    true,
			input: "src=1.2.3.4 dst=5.6.7.8 via=10.0.0.1",
			want:  "src=xxx.xxx.xxx.xxx dst=xxx.xxx.xxx.xxx via=xxx.xxx.xxx.xxx",
		},
		"non_ascii_custom": {
			customMatch:       `[^\x01-\x7f]+`,
			customReplacement: "xxxxx",
			input:             "abcdef\u65e5\u672c\u8a9eefg\u304b\u304d\u304f\u3051\u3053hij", // abcdef日本語efgかきくけこhij
			want:              "abcdefxxxxxefgxxxxxhij",
		},
	}

	for name, tc := range tests {
		t.Run(name, func(t *testing.T) {
			t.Parallel()
			s, err := NewScrubber(tc.customMatch, tc.customReplacement, tc.ip, tc.email)
			if err != nil {
				t.Fatalf("unexpected error: %v", err)
			}
			if got := s.Scrub(tc.input); got != tc.want {
				t.Errorf("got %q, want %q", got, tc.want)
			}
		})
	}
}
