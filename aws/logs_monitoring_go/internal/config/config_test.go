// Unless explicitly stated otherwise all files in this repository are licensed
// under the Apache License Version 2.0.
// This product includes software developed at Datadog (https://www.datadoghq.com/).
// Copyright 2026-Present Datadog, Inc.

package config

import (
	"compress/gzip"
	"strings"
	"testing"

	"github.com/DataDog/datadog-serverless-functions/aws/logs_monitoring_go/internal/model"
	"github.com/DataDog/datadog-serverless-functions/aws/logs_monitoring_go/internal/version"
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
		"source override adds tag": {
			env: map[string]string{EnvSource: "my-source"},
			want: func(c *Config) {
				c.Source = "my-source"
				c.Tags = append(model.Tags{"source_overridden:true"}, baseTags()...)
			},
		},
		"custom tags extract service": {
			env: map[string]string{EnvTags: "team:backend,service:my-app,env:prod"},
			want: func(c *Config) {
				c.Service = "my-app"
				c.Tags = append(model.Tags{"team:backend", "env:prod"}, baseTags()...)
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
				EnvCompressionLevel:  "9",
				EnvAdditionalTargets: "arn:one,arn:two,",
			},
			want: func(c *Config) {
				c.CompressionLevel = 9
				c.AdditionalTargets = []string{"arn:one", "arn:two"}
			},
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
			assert.Equal(t, tc.want, got)
		})
	}
}

func baseTags() model.Tags {
	return model.Tags{
		model.ForwarderNameKey + model.KeyValueSeparator,
		model.ForwarderVersionKey + model.KeyValueSeparator + version.Forwarder,
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

	tests := map[string]struct {
		targets string
		want    []string
	}{
		"empty":            {targets: ""},
		"only separators":  {targets: ",,,"},
		"only whitespace":  {targets: " , \t , "},
		"single":           {targets: "arn:one", want: []string{"arn:one"}},
		"multiple":         {targets: "arn:one,arn:two", want: []string{"arn:one", "arn:two"}},
		"blanks dropped":   {targets: "arn:one,,arn:two,", want: []string{"arn:one", "arn:two"}},
		"padding retained": {targets: " arn:one , arn:two ", want: []string{" arn:one ", " arn:two "}},
	}

	for name, tc := range tests {
		t.Run(name, func(t *testing.T) {
			t.Parallel()

			assert.Equal(t, tc.want, getAdditionalTargets(tc.targets))
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

func TestGetTags(t *testing.T) {
	t.Parallel()

	tests := map[string]struct {
		source      string
		customTags  string
		wantService string
		wantTags    model.Tags
	}{
		"no input": {
			wantTags: baseTags(),
		},
		"source override": {
			source:   "my-source",
			wantTags: append(model.Tags{"source_overridden:true"}, baseTags()...),
		},
		"custom tags kept": {
			customTags: "team:backend,env:prod",
			wantTags:   append(model.Tags{"team:backend", "env:prod"}, baseTags()...),
		},
		"service extracted and removed": {
			customTags:  "team:backend,service:my-app",
			wantService: "my-app",
			wantTags:    append(model.Tags{"team:backend"}, baseTags()...),
		},
		"first service wins": {
			customTags:  "service:first,service:second",
			wantService: "first",
			wantTags:    baseTags(),
		},
		"empty service value": {
			customTags: "service:",
			wantTags:   baseTags(),
		},
		"source and custom tags": {
			source:      "my-source",
			customTags:  "service:my-app,env:prod",
			wantService: "my-app",
			wantTags:    append(model.Tags{"env:prod", "source_overridden:true"}, baseTags()...),
		},
		"bare key is kept": {
			customTags: "servicelike",
			wantTags:   append(model.Tags{"servicelike"}, baseTags()...),
		},
		"service prefix is not matched loosely": {
			customTags: "service_name:my-app",
			wantTags:   append(model.Tags{"service_name:my-app"}, baseTags()...),
		},
	}

	for name, tc := range tests {
		t.Run(name, func(t *testing.T) {
			t.Parallel()

			gotService, gotTags := getTags(tc.source, tc.customTags)
			assert.Equal(t, tc.wantService, gotService)
			assert.Equal(t, tc.wantTags, gotTags)
		})
	}
}
