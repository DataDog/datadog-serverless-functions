// Unless explicitly stated otherwise all files in this repository are licensed
// under the Apache License Version 2.0.
// This product includes software developed at Datadog (https://www.datadoghq.com/).
// Copyright 2026-Present Datadog, Inc.

package config

import (
	"compress/gzip"
	"regexp"
	"testing"

	"github.com/DataDog/datadog-serverless-functions/aws/logs_monitoring_go/internal/model"
	"github.com/DataDog/datadog-serverless-functions/aws/logs_monitoring_go/internal/version"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

func TestLoad(t *testing.T) {
	defaults := Config{
		APIURL:           "https://api.datadoghq.com/api/v1/validate",
		IntakeURL:        "https://http-intake.logs.datadoghq.com:443/api/v2/logs",
		CompressionLevel: gzip.DefaultCompression,
		Tags:             baseTags(),
	}

	tests := map[string]struct {
		env          map[string]string
		want         func(*Config)
		wantPatterns map[string]string
		wantErr      string
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
		"storage enables store on fail": {
			env: map[string]string{EnvS3RetryBucketName: "my-bucket", EnvSQSQueueURL: "https://sqs/queue"},
			want: func(c *Config) {
				c.S3RetryBucketName = "my-bucket"
				c.SQSQueueURL = "https://sqs/queue"
				c.StoreOnFail = true
			},
		},
		"sqs alone enables store on fail": {
			env: map[string]string{EnvSQSQueueURL: "https://sqs/queue"},
			want: func(c *Config) {
				c.SQSQueueURL = "https://sqs/queue"
				c.StoreOnFail = true
			},
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
		"scrubbing and filters compile": {
			env: map[string]string{
				EnvScrubbingRule:            `password=\w+`,
				EnvScrubbingRuleReplacement: "[REDACTED]",
				EnvIncludeAtMatch:           "keep-me",
				EnvExcludeAtMatch:           "drop-me",
				EnvMultilineLogRegex:        `^\d{4}`,
				EnvRedactIP:                 "true",
				EnvRedactEmail:              "true",
			},
			want: func(c *Config) {
				c.ScrubbingReplacement = "[REDACTED]"
				c.ScrubIP = true
				c.ScrubEmail = true
			},
			wantPatterns: map[string]string{
				"scrubbing": `password=\w+`,
				"include":   "keep-me",
				"exclude":   "drop-me",
				"multiline": `^\d{4}`,
			},
		},
		"invalid include pattern": {
			env:     map[string]string{EnvIncludeAtMatch: "[unclosed"},
			wantErr: `compile INCLUDE_AT_MATCH "[unclosed"`,
		},
		"invalid multiline pattern": {
			env:     map[string]string{EnvMultilineLogRegex: "(?P<"},
			wantErr: "compile DD_MULTILINE_LOG_REGEX_PATTERN",
		},
	}

	for name, tc := range tests {
		t.Run(name, func(t *testing.T) {
			for k, v := range tc.env {
				t.Setenv(k, v)
			}

			got, err := Load()

			if tc.wantErr != "" {
				require.ErrorContains(t, err, tc.wantErr)
				return
			}
			require.NoError(t, err)

			assert.Equal(t, tc.wantPatterns, patternsOf(got))

			want := defaults
			if tc.want != nil {
				tc.want(&want)
			}
			clearPatterns(&got)
			assert.Equal(t, want, got)
		})
	}
}

func baseTags() model.Tags {
	return model.Tags{
		model.ForwarderNameKey + model.KeyValueSeparator,
		model.ForwarderVersionKey + model.KeyValueSeparator + version.Forwarder,
	}
}

func TestLoadReportsEveryPatternError(t *testing.T) {
	t.Setenv(EnvScrubbingRule, "(")
	t.Setenv(EnvIncludeAtMatch, "[")
	t.Setenv(EnvExcludeAtMatch, "*")

	_, err := Load()

	require.Error(t, err)
	assert.ErrorContains(t, err, "compile "+EnvScrubbingRule)
	assert.ErrorContains(t, err, "compile "+EnvIncludeAtMatch)
	assert.ErrorContains(t, err, "compile "+EnvExcludeAtMatch)
}

// patternsOf reports the compiled patterns by name so they can be compared as
// strings: reflect.DeepEqual on *regexp.Regexp inspects unexported machine state.
func patternsOf(c Config) map[string]string {
	named := map[string]*regexp.Regexp{
		"scrubbing": c.ScrubbingRegex,
		"include":   c.FilterInclude,
		"exclude":   c.FilterExclude,
		"multiline": c.S3MultilineLogRegex,
	}

	var patterns map[string]string
	for name, re := range named {
		if re == nil {
			continue
		}
		if patterns == nil {
			patterns = map[string]string{}
		}
		patterns[name] = re.String()
	}

	return patterns
}

func clearPatterns(c *Config) {
	c.ScrubbingRegex, c.FilterInclude, c.FilterExclude, c.S3MultilineLogRegex = nil, nil, nil, nil
}

func TestCompilePattern(t *testing.T) {
	tests := map[string]struct {
		value   string
		set     bool
		want    string
		wantErr bool
	}{
		"not set":         {},
		"empty":           {value: "", set: true},
		"whitespace only": {value: "   ", set: true},
		"valid":           {value: `\d+`, set: true, want: `\d+`},
		"trimmed":         {value: "  abc  ", set: true, want: "abc"},
		"anchored":        {value: "^start.*end$", set: true, want: "^start.*end$"},
		"unclosed class":  {value: "[unclosed", set: true, wantErr: true},
		"bare repeat":     {value: "*", set: true, wantErr: true},
		"unclosed group":  {value: "(", set: true, wantErr: true},
	}

	for name, tc := range tests {
		t.Run(name, func(t *testing.T) {
			if tc.set {
				t.Setenv(EnvScrubbingRule, tc.value)
			}

			got, err := compilePattern(EnvScrubbingRule)

			if tc.wantErr {
				require.Error(t, err)
				assert.Nil(t, got)
				assert.ErrorContains(t, err, EnvScrubbingRule)
				return
			}
			require.NoError(t, err)

			if tc.want == "" {
				assert.Nil(t, got)
				return
			}

			require.NotNil(t, got)
			assert.Equal(t, tc.want, got.String())
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

func TestConfigLogValueOmitsSecretsAndPII(t *testing.T) {
	t.Parallel()

	const ciphertext = "Y2lwaGVydGV4dA=="

	cfg := Config{
		APIKeyKMSKey: ciphertext,
		Tags:         model.Tags{"customer:acme", "user_email:someone@example.com"},
	}

	rendered := cfg.LogValue().String()

	assert.NotContains(t, rendered, ciphertext, "the KMS ciphertext is key material")
	assert.NotContains(t, rendered, "acme", "tags are customer supplied and may carry PII")
	assert.NotContains(t, rendered, "someone@example.com", "tags are customer supplied and may carry PII")
	assert.Contains(t, rendered, "api_key_configured=true")
}
