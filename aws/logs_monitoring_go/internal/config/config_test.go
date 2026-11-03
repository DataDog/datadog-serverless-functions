// Unless explicitly stated otherwise all files in this repository are licensed
// under the Apache License Version 2.0.
// This product includes software developed at Datadog (https://www.datadoghq.com/).
// Copyright 2026-Present Datadog, Inc.

package config

import (
	"compress/gzip"
	"strings"
	"testing"

	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

func TestLoad(t *testing.T) {
	tests := map[string]struct {
		env     map[string]string
		want    func(*Config)
		wantErr bool
	}{
		"defaults": {},
		"eu site": {
			env: map[string]string{EnvSite: "datadoghq.eu"},
			want: func(c *Config) {
				c.APIURL = "https://api.datadoghq.eu/api/v1/validate"
				c.IntakeURL = "https://http-intake.logs.datadoghq.eu:443/api/v2/logs"
			},
		},
		"gov": {
			env: map[string]string{EnvSite: "ddog-gov.com"},
			want: func(c *Config) {
				c.APIURL = "https://api.ddog-gov.com/api/v1/validate"
				c.IntakeURL = "https://http-intake.logs.ddog-gov.com:443/api/v2/logs"
			},
		},
		"no ssl and custom port": {
			env: map[string]string{EnvUseHTTP: "true", EnvPort: "8080"},
			want: func(c *Config) {
				c.APIURL = "http://api.datadoghq.com/api/v1/validate"
				c.IntakeURL = "http://http-intake.logs.datadoghq.com:8080/api/v2/logs"
			},
		},
		"proxy urls override site": {
			env: map[string]string{
				EnvSite:      "datadoghq.eu",
				EnvIntakeURL: "https://proxy.internal/logs",
				EnvAPIURL:    "https://proxy.internal/validate",
			},
			want: func(c *Config) {
				c.APIURL = "https://proxy.internal/validate"
				c.IntakeURL = "https://proxy.internal/logs"
			},
		},
		"api key sources are passed through": {
			env: map[string]string{
				EnvAPIKeySecretARN: "arn:aws:secretsmanager:us-east-1:1:secret:dd",
				EnvAPIKeySSMName:   "/datadog/api-key",
				EnvKMSAPIKey:       "Y2lwaGVydGV4dA==",
			},
			want: func(c *Config) {
				c.APIKeySecretARN = "arn:aws:secretsmanager:us-east-1:1:secret:dd"
				c.APIKeySSMName = "/datadog/api-key"
				c.APIKeyKMSKey = "Y2lwaGVydGV4dA=="
			},
		},
		"source override": {
			env: map[string]string{EnvSource: "my-source"},
			want: func(c *Config) {
				c.Source = "my-source"
			},
		},
		"custom tags kept raw": {
			env: map[string]string{EnvTags: "team:backend,service:my-app,env:prod"},
			want: func(c *Config) {
				c.Tags = "team:backend,service:my-app,env:prod"
			},
		},
		"store on fail with storage": {
			env: map[string]string{EnvStoreOnFail: "true", EnvS3BucketName: "my-bucket", EnvSQSQueueURL: "https://sqs/queue"},
			want: func(c *Config) {
				c.S3BucketName = "my-bucket"
				c.SQSQueueURL = "https://sqs/queue"
				c.StoreOnFail = true
			},
		},
		"store on fail with no storage": {
			env:     map[string]string{EnvStoreOnFail: "true"},
			wantErr: true,
		},
		"compression and targets": {
			env: map[string]string{
				EnvCompressionLevel: "9",
				EnvAdditionalTargets: "arn:aws:lambda:us-east-1:123456789012:function:target-one," +
					"arn:aws:lambda:us-east-1:123456789012:function:target-two,",
			},
			want: func(c *Config) {
				c.CompressionLevel = 9
				c.AdditionalTargets = []string{
					"arn:aws:lambda:us-east-1:123456789012:function:target-one",
					"arn:aws:lambda:us-east-1:123456789012:function:target-two",
				}
			},
		},
		"invalid additional target": {
			env:     map[string]string{EnvAdditionalTargets: "not-an-arn"},
			wantErr: true,
		},
		"invalid compression falls back": {
			env: map[string]string{EnvCompressionLevel: "nope"},
		},
		"skip tls and step functions": {
			env: map[string]string{EnvSkipServerCertificate: "true", EnvEnableStepFunctionsTrace: "true"},
			want: func(c *Config) {
				c.SkipServerCertificate = true
				c.StepFunctionsTraceEnabled = true
			},
		},
	}

	for name, tc := range tests {
		t.Run(name, func(t *testing.T) {
			for k, v := range tc.env {
				t.Setenv(k, v)
			}

			got, err := Load()
			if tc.wantErr {
				require.Error(t, err, tc.wantErr)
				return
			}

			require.NoError(t, err)

			want := defaultConfig()
			if tc.want != nil {
				tc.want(&want)
			}
			assert.Equal(t, want, got)
		})
	}
}

func defaultConfig() Config {
	return Config{
		APIURL:           DefaultProtocol + "://api." + DefaultSite + "/api/v1/validate",
		IntakeURL:        DefaultProtocol + "://http-intake.logs." + DefaultSite + ":" + DefaultPort + "/api/v2/logs",
		CompressionLevel: gzip.DefaultCompression,
	}
}

func TestCompilePatternFromEnv(t *testing.T) {
	ddEnvRegexp := "DD_ENV_REGEXP"

	tests := map[string]struct {
		value   string
		wantErr bool
	}{
		"empty":              {value: ""},
		"whitespace only":    {value: "   "},
		"valid":              {value: `\d+`},
		"trimmed":            {value: "  abc  "},
		"anchored":           {value: "^start.*end$"},
		"unclosed class":     {value: "[unclosed", wantErr: true},
		"bare repeat":        {value: "*", wantErr: true},
		"unclosed group":     {value: "(", wantErr: true},
		"positive lookahead": {value: `\w+(?=\s*EUR)`, wantErr: true},
	}

	for name, tc := range tests {
		t.Run(name, func(t *testing.T) {
			tc.value = strings.TrimSpace(tc.value)
			t.Setenv(ddEnvRegexp, tc.value)

			got, err := compilePatternFromEnv(ddEnvRegexp)

			if tc.wantErr {
				require.ErrorContains(t, err, ddEnvRegexp)
				return
			}
			if tc.value != "" {
				require.NotNil(t, got)
			}
			require.NoError(t, err)
		})
	}
}

func TestGetAdditionalTargets(t *testing.T) {
	t.Parallel()

	const (
		arnOne = "arn:aws:lambda:us-east-1:123456789012:function:target-one"
		arnTwo = "arn:aws:lambda:us-east-1:123456789012:function:target-two"
	)

	tests := map[string]struct {
		targets string
		want    []string
		wantErr bool
	}{
		"empty":              {targets: ""},
		"only separators":    {targets: ",,,"},
		"only whitespace":    {targets: " , \t , "},
		"single":             {targets: arnOne, want: []string{arnOne}},
		"multiple":           {targets: arnOne + "," + arnTwo, want: []string{arnOne, arnTwo}},
		"blanks dropped":     {targets: arnOne + ",," + arnTwo + ",", want: []string{arnOne, arnTwo}},
		"padding retained":   {targets: " " + arnOne + " , " + arnTwo + " ", want: []string{" " + arnOne + " ", " " + arnTwo + " "}},
		"not an arn":         {targets: "not-an-arn", wantErr: true},
		"malformed arn":      {targets: "arn:aws:lambda:us-east-1", wantErr: true},
		"non-lambda arn":     {targets: "arn:aws:s3:::my-bucket", wantErr: true},
		"bare function name": {targets: "my-function", wantErr: true},
	}

	for name, tc := range tests {
		t.Run(name, func(t *testing.T) {
			t.Parallel()

			got, err := getAdditionalTargets(tc.targets)

			if tc.wantErr {
				require.Error(t, err)
				return
			}
			require.NoError(t, err)
			assert.Equal(t, tc.want, got)
		})
	}
}

func TestGetCompressionLevel(t *testing.T) {
	t.Parallel()

	tests := map[string]struct {
		level string
		want  int
	}{
		"empty":          {level: "", want: gzip.DefaultCompression},
		"not a number":   {level: "high", want: gzip.DefaultCompression},
		"no compression": {level: "0", want: gzip.NoCompression},
		"best speed":     {level: "1", want: gzip.BestSpeed},
		"best":           {level: "9", want: gzip.BestCompression},
		"huffman only":   {level: "-2", want: gzip.HuffmanOnly},
		"below range":    {level: "-3", want: gzip.DefaultCompression},
		"above range":    {level: "10", want: gzip.DefaultCompression},
	}

	for name, tc := range tests {
		t.Run(name, func(t *testing.T) {
			t.Parallel()

			assert.Equal(t, tc.want, getCompressionLevel(tc.level))
		})
	}
}
