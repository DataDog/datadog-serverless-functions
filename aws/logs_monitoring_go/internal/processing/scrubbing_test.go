// Unless explicitly stated otherwise all files in this repository are licensed
// under the Apache License Version 2.0.
// This product includes software developed at Datadog (https://www.datadoghq.com/).
// Copyright 2026-Present Datadog, Inc.

package transform

import (
	"testing"

	"github.com/DataDog/datadog-serverless-functions/aws/logs_monitoring_go/internal/config"
)

func TestNewScrubber(t *testing.T) {
	t.Parallel()

	tests := map[string]struct {
		cfg    config.ScrubbingConfig
		nRules int
	}{
		"no_rules": {
			cfg:    config.ScrubbingConfig{},
			nRules: 0,
		},
		"ip_only": {
			cfg:    config.ScrubbingConfig{ScrubIP: true},
			nRules: 1,
		},
		"email_only": {
			cfg:    config.ScrubbingConfig{ScrubEmail: true},
			nRules: 1,
		},
		"ip_and_email": {
			cfg:    config.ScrubbingConfig{ScrubIP: true, ScrubEmail: true},
			nRules: 2,
		},
		"custom_rule": {
			cfg:    config.ScrubbingConfig{CustomRule: `\d+`, CustomReplacement: "NUM"},
			nRules: 1,
		},
		"all_rules": {
			cfg:    config.ScrubbingConfig{ScrubIP: true, ScrubEmail: true, CustomRule: `secret`, CustomReplacement: "[REDACTED]"},
			nRules: 3,
		},
		"invalid_custom_regex": {
			cfg:    config.ScrubbingConfig{CustomRule: `([invalid`},
			nRules: 0,
		},
	}

	for name, tc := range tests {
		t.Run(name, func(t *testing.T) {
			t.Parallel()
			s := NewScrubber(tc.cfg)
			if got := len(s.rules); got != tc.nRules {
				t.Errorf("got %d rules, want %d", got, tc.nRules)
			}
		})
	}
}

func TestScrubMessage(t *testing.T) {
	tests := map[string]struct {
		cfg   config.ScrubbingConfig
		input string
		want  string
	}{
		"ip_redaction": {
			cfg:   config.ScrubbingConfig{ScrubIP: true},
			input: "connected from 192.168.1.1 to 10.0.0.1",
			want:  "connected from xxx.xxx.xxx.xxx to xxx.xxx.xxx.xxx",
		},
		"email_redaction": {
			cfg:   config.ScrubbingConfig{ScrubEmail: true},
			input: "user john.doe@example.com logged in",
			want:  "user xxxxx@xxxxx.com logged in",
		},
		"custom_pattern": {
			cfg:   config.ScrubbingConfig{CustomRule: `secret-\w+`, CustomReplacement: "[REDACTED]"},
			input: "token=secret-abc123 visible",
			want:  "token=[REDACTED] visible",
		},
		"custom_empty_replacement": {
			cfg:   config.ScrubbingConfig{CustomRule: `remove-this `},
			input: "remove-this here",
			want:  "here",
		},
		"ip_and_email_sequential": {
			cfg:   config.ScrubbingConfig{ScrubIP: true, ScrubEmail: true},
			input: "192.168.1.1 user@host.com",
			want:  "xxx.xxx.xxx.xxx xxxxx@xxxxx.com",
		},
		"no_match": {
			cfg:   config.ScrubbingConfig{ScrubIP: true, ScrubEmail: true},
			input: "clean message with no sensitive data",
			want:  "clean message with no sensitive data",
		},
		"multiple_ips": {
			cfg:   config.ScrubbingConfig{ScrubIP: true},
			input: "src=1.2.3.4 dst=5.6.7.8 via=10.0.0.1",
			want:  "src=xxx.xxx.xxx.xxx dst=xxx.xxx.xxx.xxx via=xxx.xxx.xxx.xxx",
		},
		"non_ascii_custom": {
			cfg:   config.ScrubbingConfig{CustomRule: `[^\x01-\x7f]+`, CustomReplacement: "xxxxx"},
			input: "abcdef\u65e5\u672c\u8a9eefg\u304b\u304d\u304f\u3051\u3053hij",
			want:  "abcdefxxxxxefgxxxxxhij",
		},
	}

	for name, tc := range tests {
		t.Run(name, func(t *testing.T) {
			t.Parallel()
			s := NewScrubber(tc.cfg)
			got := s.ScrubMessage(tc.input)
			if got != tc.want {
				t.Errorf("got %q, want %q", got, tc.want)
			}
		})
	}
}
