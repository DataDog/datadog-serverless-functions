// Unless explicitly stated otherwise all files in this repository are licensed
// under the Apache License Version 2.0.
// This product includes software developed at Datadog (https://www.datadoghq.com/).
// Copyright 2026-Present Datadog, Inc.

package config

import (
	"testing"
)

func TestLoad(t *testing.T) {
	tests := map[string]struct {
		env       map[string]string
		wantSite  string
		wantURL   string
		wantAPI   string
		wantSrc   string
		wantHost  string
		wantFIPS  bool
		wantRegex bool
		wantErr   bool
	}{
		"defaults": {
			wantSite: "datadoghq.com",
			wantURL:  "https://http-intake.logs.datadoghq.com/api/v2/logs",
			wantAPI:  "https://api.datadoghq.com",
		},
		"eu site": {
			env:      map[string]string{"DD_SITE": "datadoghq.eu"},
			wantSite: "datadoghq.eu",
			wantURL:  "https://http-intake.logs.datadoghq.eu/api/v2/logs",
			wantAPI:  "https://api.datadoghq.eu",
		},
		"custom url": {
			env:      map[string]string{"DD_URL": "https://custom.example.com"},
			wantSite: "datadoghq.com",
			wantURL:  "https://custom.example.com",
			wantAPI:  "https://api.datadoghq.com",
		},
		"source and host": {
			env:      map[string]string{"DD_SOURCE": "custom", "DD_HOST": "my-host"},
			wantSite: "datadoghq.com",
			wantURL:  "https://http-intake.logs.datadoghq.com/api/v2/logs",
			wantAPI:  "https://api.datadoghq.com",
			wantSrc:  "custom",
			wantHost: "my-host",
		},
		"fips enabled": {
			env:      map[string]string{"DD_USE_FIPS": "true"},
			wantSite: "datadoghq.com",
			wantURL:  "https://http-intake.logs.datadoghq.com/api/v2/logs",
			wantAPI:  "https://api.datadoghq.com",
			wantFIPS: true,
		},
		"valid multiline regex": {
			env:       map[string]string{"DD_MULTILINE_LOG_REGEX_PATTERN": `\d{4}-\d{2}-\d{2}`},
			wantSite:  "datadoghq.com",
			wantURL:   "https://http-intake.logs.datadoghq.com/api/v2/logs",
			wantAPI:   "https://api.datadoghq.com",
			wantRegex: true,
		},
		"invalid multiline regex": {
			env:     map[string]string{"DD_MULTILINE_LOG_REGEX_PATTERN": `[invalid`},
			wantErr: true,
		},
	}

	for name, tc := range tests {
		t.Run(name, func(t *testing.T) {
			for k, v := range tc.env {
				t.Setenv(k, v)
			}

			got, err := Load()

			if tc.wantErr {
				if err == nil {
					t.Fatal("want error, got nil")
				}
				return
			}
			if err != nil {
				t.Fatalf("unexpected error: %v", err)
			}

			if got.Site != tc.wantSite {
				t.Errorf("Site: got %q, want %q", got.Site, tc.wantSite)
			}
			if got.IntakeURL != tc.wantURL {
				t.Errorf("IntakeURL: got %q, want %q", got.IntakeURL, tc.wantURL)
			}
			if got.APIURL != tc.wantAPI {
				t.Errorf("APIURL: got %q, want %q", got.APIURL, tc.wantAPI)
			}
			if got.Source != tc.wantSrc {
				t.Errorf("Source: got %q, want %q", got.Source, tc.wantSrc)
			}
			if got.Host != tc.wantHost {
				t.Errorf("Host: got %q, want %q", got.Host, tc.wantHost)
			}
			if got.UseFIPS != tc.wantFIPS {
				t.Errorf("UseFIPS: got %v, want %v", got.UseFIPS, tc.wantFIPS)
			}
			if (got.S3MultilineLogRegex != nil) != tc.wantRegex {
				t.Errorf("S3MultilineLogRegex: got nil=%v, want nil=%v", got.S3MultilineLogRegex == nil, !tc.wantRegex)
			}
		})
	}
}
