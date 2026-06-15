// Unless explicitly stated otherwise all files in this repository are licensed
// under the Apache License Version 2.0.
// This product includes software developed at Datadog (https://www.datadoghq.com/).
// Copyright 2026-Present Datadog, Inc.

package config

import (
	"context"
	"errors"
	"testing"

	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

func TestBuildURLs(t *testing.T) {
	t.Parallel()

	tests := map[string]struct {
		protocol      string
		site          string
		port          string
		wantIntakeURL string
		wantAPIURL    string
	}{
		"defaults": {
			protocol:      "https",
			site:          "datadoghq.com",
			port:          "443",
			wantIntakeURL: "https://http-intake.logs.datadoghq.com:443/api/v2/logs",
			wantAPIURL:    "https://api.datadoghq.com/api/v1/validate",
		},
		"eu site": {
			protocol:      "https",
			site:          "datadoghq.eu",
			port:          "443",
			wantIntakeURL: "https://http-intake.logs.datadoghq.eu:443/api/v2/logs",
			wantAPIURL:    "https://api.datadoghq.eu/api/v1/validate",
		},
		"gov": {
			protocol:      "https",
			site:          "ddog-gov.com",
			port:          "443",
			wantIntakeURL: "https://http-intake.logs.ddog-gov.com:443/api/v2/logs",
			wantAPIURL:    "https://api.ddog-gov.com/api/v1/validate",
		},
	}

	for name, tc := range tests {
		t.Run(name, func(t *testing.T) {
			t.Parallel()

			intakeURL, apiURL := buildURLs(tc.protocol, tc.site, tc.port)

			assert.Equal(t, tc.wantIntakeURL, intakeURL)
			assert.Equal(t, tc.wantAPIURL, apiURL)
		})
	}
}

func TestResolveAPIKey(t *testing.T) {
	succeed := func(_ context.Context, v string) (string, error) { return v, nil }
	fail := func(_ context.Context, _ string) (string, error) { return "", errors.New("aws error") }

	tests := map[string]struct {
		env       map[string]string
		resolvers []apiKeyResolver
		wantKey   string
		wantErr   bool
	}{
		"succeeds": {
			env:       map[string]string{"DD_API_KEY_SECRET_ARN": "abcdef1234567890abcdef1234567890"},
			resolvers: []apiKeyResolver{{"DD_API_KEY_SECRET_ARN", succeed}},
			wantKey:   "abcdef1234567890abcdef1234567890",
		},
		"no fallback": {
			env: map[string]string{
				"DD_API_KEY_SECRET_ARN": "bad",
				"DD_API_KEY_SSM_NAME":   "abcdef1234567890abcdef1234567890",
			},
			resolvers: []apiKeyResolver{
				{"DD_API_KEY_SECRET_ARN", fail},
				{"DD_API_KEY_SSM_NAME", succeed},
			},
			wantErr: true,
		},
		"none configured": {
			resolvers: []apiKeyResolver{{"DD_API_KEY_SECRET_ARN", succeed}},
			wantErr:   true,
		},
	}

	for name, tc := range tests {
		t.Run(name, func(t *testing.T) {
			for k, v := range tc.env {
				t.Setenv(k, v)
			}

			key, err := resolveAPIKey(t.Context(), tc.resolvers)

			if tc.wantErr {
				require.Error(t, err)
				return
			}
			require.NoError(t, err)
			assert.Equal(t, tc.wantKey, key)
		})
	}
}
