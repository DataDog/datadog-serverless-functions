// Unless explicitly stated otherwise all files in this repository are licensed
// under the Apache License Version 2.0.
// This product includes software developed at Datadog (https://www.datadoghq.com/).
// Copyright 2026-Present Datadog, Inc.

package config

import (
	"testing"

	"github.com/google/go-cmp/cmp"
	"github.com/google/go-cmp/cmp/cmpopts"
)

func TestLoadConfig(t *testing.T) {
	tests := map[string]struct {
		env  map[string]string
		want Config
	}{
		"default": {
			want: Config{
				Site:      "datadoghq.com",
				IntakeURL: "https://http-intake.logs.datadoghq.com/api/v2/logs",
				APIURL:    "https://api.datadoghq.com",
				LogLevel:  "INFO",
				UseFIPS:   false,
			},
		},
		"eu_site": {
			env: map[string]string{"DD_SITE": "datadoghq.eu"},
			want: Config{
				Site:      "datadoghq.eu",
				IntakeURL: "https://http-intake.logs.datadoghq.eu/api/v2/logs",
				APIURL:    "https://api.datadoghq.eu",
				LogLevel:  "INFO",
			},
		},
		"custom_url": {
			env: map[string]string{
				"DD_SITE": "datadoghq.com",
				"DD_URL":  "https://custom-intake.example.com",
			},
			want: Config{
				Site:      "datadoghq.com",
				IntakeURL: "https://custom-intake.example.com",
				APIURL:    "https://api.datadoghq.com",
				LogLevel:  "INFO",
			},
		},
		"custom_source_host_tags": {
			env: map[string]string{
				"DD_SOURCE": "custom-source",
				"DD_HOST":   "my-host",
				"DD_TAGS":   "env:prod,team:aws",
			},
			want: Config{
				Site:       "datadoghq.com",
				IntakeURL:  "https://http-intake.logs.datadoghq.com/api/v2/logs",
				APIURL:     "https://api.datadoghq.com",
				LogLevel:   "INFO",
				Source:     "custom-source",
				Host:       "my-host",
				CustomTags: "env:prod,team:aws",
			},
		},
		"scrubbing_ip_enabled": {
			env: map[string]string{"REDACT_IP": "true"},
			want: Config{
				Site:      "datadoghq.com",
				IntakeURL: "https://http-intake.logs.datadoghq.com/api/v2/logs",
				APIURL:    "https://api.datadoghq.com",
				LogLevel:  "INFO",
				Scrubbing: ScrubbingConfig{ScrubIP: true},
			},
		},
		"scrubbing_custom_rule": {
			env: map[string]string{
				"DD_SCRUBBING_RULE":             `\d+`,
				"DD_SCRUBBING_RULE_REPLACEMENT": "X",
			},
			want: Config{
				Site:      "datadoghq.com",
				IntakeURL: "https://http-intake.logs.datadoghq.com/api/v2/logs",
				APIURL:    "https://api.datadoghq.com",
				LogLevel:  "INFO",
				Scrubbing: ScrubbingConfig{CustomRule: `\d+`, CustomReplacement: "X"},
			},
		},
		"filtering_include": {
			env: map[string]string{"INCLUDE_AT_MATCH": `error|warn`},
			want: Config{
				Site:      "datadoghq.com",
				IntakeURL: "https://http-intake.logs.datadoghq.com/api/v2/logs",
				APIURL:    "https://api.datadoghq.com",
				LogLevel:  "INFO",
				Filtering: FilteringConfig{IncludePattern: `error|warn`},
			},
		},
		"filtering_exclude": {
			env: map[string]string{"EXCLUDE_AT_MATCH": `DEBUG`},
			want: Config{
				Site:      "datadoghq.com",
				IntakeURL: "https://http-intake.logs.datadoghq.com/api/v2/logs",
				APIURL:    "https://api.datadoghq.com",
				LogLevel:  "INFO",
				Filtering: FilteringConfig{ExcludePattern: `DEBUG`},
			},
		},
	}

	for name, tc := range tests {
		t.Run(name, func(t *testing.T) {
			for k, v := range tc.env {
				t.Setenv(k, v)
			}
			got := loadConfig()
			if diff := cmp.Diff(tc.want, *got, cmpopts.IgnoreFields(Config{}, "APIKey")); diff != "" {
				t.Errorf("mismatch (-want +got):\n%s", diff)
			}
		})
	}
}

func TestLoadS3MultilineLogRegex(t *testing.T) {
	tests := map[string]struct {
		env     string
		wantNil bool
	}{
		"empty_pattern_returns_nil": {
			env:     "",
			wantNil: true,
		},
		"valid_pattern_returns_compiled_regex": {
			env: `\d{4}-\d{2}-\d{2}`,
		},
		"invalid_pattern_returns_nil": {
			env:     `[invalid`,
			wantNil: true,
		},
	}

	for name, tc := range tests {
		t.Run(name, func(t *testing.T) {
			if tc.env != "" {
				t.Setenv("DD_MULTILINE_LOG_REGEX_PATTERN", tc.env)
			}

			got := loadS3MultilineLogRegex()

			if tc.wantNil {
				if got != nil {
					t.Fatalf("want nil, got `%v", got)
				}
				return
			}

			if got == nil {
				t.Fatal("want non-nil, got nil")
			}
		})
	}
}
