// Unless explicitly stated otherwise all files in this repository are licensed
// under the Apache License Version 2.0.
// This product includes software developed at Datadog (https://www.datadoghq.com/).
// Copyright 2026-Present Datadog, Inc.

package config

import (
	"testing"

	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

func TestLoad(t *testing.T) {
	defaultURL := "https://http-intake.logs." + DefaultSite + ":443/api/v2/logs"
	defaultAPI := "https://api." + DefaultSite

	tests := map[string]struct {
		env       map[string]string
		want      Config
		wantRegex bool
		wantErr   bool
	}{
		"defaults": {
			want: Config{Site: DefaultSite, IntakeURL: defaultURL, APIURL: defaultAPI},
		},
		"eu site": {
			env:  map[string]string{EnvSite: "datadoghq.eu"},
			want: Config{Site: "datadoghq.eu", IntakeURL: "https://http-intake.logs.datadoghq.eu:443/api/v2/logs", APIURL: "https://api.datadoghq.eu"},
		},
		"custom url": {
			env:  map[string]string{EnvURL: "https://custom.example.com"},
			want: Config{Site: DefaultSite, IntakeURL: "https://custom.example.com", APIURL: defaultAPI},
		},
		"source and host": {
			env:  map[string]string{EnvSource: "custom", EnvHost: "my-host"},
			want: Config{Site: DefaultSite, IntakeURL: defaultURL, APIURL: defaultAPI, Source: "custom", Host: "my-host"},
		},
		"fips enabled": {
			env:  map[string]string{EnvUseFIPS: "true"},
			want: Config{Site: DefaultSite, IntakeURL: defaultURL, APIURL: defaultAPI, UseFIPS: true},
		},
		"valid multiline regex": {
			env:       map[string]string{EnvMultilineLogRegex: `\d{4}-\d{2}-\d{2}`},
			want:      Config{Site: DefaultSite, IntakeURL: defaultURL, APIURL: defaultAPI},
			wantRegex: true,
		},
		"invalid multiline regex": {
			env:     map[string]string{EnvMultilineLogRegex: `[invalid`},
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
				require.Error(t, err)
				return
			}
			require.NoError(t, err)

			assert.Equal(t, tc.want.Site, got.Site)
			assert.Equal(t, tc.want.IntakeURL, got.IntakeURL)
			assert.Equal(t, tc.want.APIURL, got.APIURL)
			assert.Equal(t, tc.want.Source, got.Source)
			assert.Equal(t, tc.want.Host, got.Host)
			assert.Equal(t, tc.want.UseFIPS, got.UseFIPS)
			assert.Equal(t, tc.wantRegex, got.S3MultilineLogRegex != nil)
		})
	}
}
