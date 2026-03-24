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
			env: map[string]string{},
			want: Config{
				Site:      "datadoghq.com",
				IntakeURL: "https://http-intake.logs.datadoghq.com",
				APIURL:    "https://api.datadoghq.com",
				LogLevel:  "INFO",
				UseFIPS:   false,
			},
		},
		"eu_site": {
			env: map[string]string{"DD_SITE": "datadoghq.eu"},
			want: Config{
				Site:      "datadoghq.eu",
				IntakeURL: "https://http-intake.logs.datadoghq.eu",
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
