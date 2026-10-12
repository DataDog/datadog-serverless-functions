// Unless explicitly stated otherwise all files in this repository are licensed
// under the Apache License Version 2.0.
// This product includes software developed at Datadog (https://www.datadoghq.com/).
// Copyright 2026-Present Datadog, Inc.

package sdkclient

import (
	"testing"

	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

func TestRegionFromARN(t *testing.T) {
	t.Parallel()

	tests := map[string]struct {
		value string
		want  string
	}{
		"secret arn":            {value: "arn:aws:secretsmanager:us-east-1:012345678901:secret:dd-api-key", want: "us-east-1"},
		"ssm parameter arn":     {value: "arn:aws:ssm:eu-west-3:012345678901:parameter/datadog/api-key", want: "eu-west-3"},
		"gov partition":         {value: "arn:aws-us-gov:secretsmanager:us-gov-west-1:012345678901:secret:dd", want: "us-gov-west-1"},
		"china partition":       {value: "arn:aws-cn:secretsmanager:cn-north-1:012345678901:secret:dd", want: "cn-north-1"},
		"bare ssm name":         {value: "/datadog/api-key"},
		"empty":                 {},
		"not an arn":            {value: "not:an:arn:at:all:really"},
		"too few segments":      {value: "arn:aws:secretsmanager:us-east-1:012345678901"},
		"empty region segment":  {value: "arn:aws:s3:::my-bucket:key"},
		"trailing colons count": {value: "arn:aws:kms:us-west-2:012345678901:key/abc", want: "us-west-2"},
	}

	for name, tc := range tests {
		t.Run(name, func(t *testing.T) {
			t.Parallel()

			assert.Equal(t, tc.want, regionFromARN(tc.value))
		})
	}
}

func TestAPIKeyFromSecret(t *testing.T) {
	t.Parallel()

	const (
		arn = "arn:aws:secretsmanager:us-east-1:012345678901:secret:dd"
		key = "abcdef1234567890abcdef1234567890"
	)

	tests := map[string]struct {
		secret  string
		want    string
		wantErr string
	}{
		"plain string":              {secret: key, want: key},
		"plain string with symbols": {secret: "not-json-{at-all", want: "not-json-{at-all"},
		"json dd_api_key":           {secret: `{"DD_API_KEY":"` + key + `"}`, want: key},
		"json apikey":               {secret: `{"apiKey":"` + key + `"}`, want: key},
		"dd_api_key wins": {
			secret: `{"apiKey":"wrong-key-wrong-key-wrong-key-00","DD_API_KEY":"` + key + `"}`,
			want:   key,
		},
		"json extra fields ignored": {
			secret: `{"apiKey":"` + key + `","appKey":"other","rotation":7}`,
			want:   key,
		},
		"json value trimmed": {secret: `{"apiKey":"  ` + key + `  "}`, want: key},
		"json without known field": {
			secret:  `{"username":"dd","password":"secret"}`,
			wantErr: `has no DD_API_KEY or apiKey field`,
		},
		"json empty object": {secret: `{}`, wantErr: "has no DD_API_KEY or apiKey field"},
		"json null":         {secret: `null`, wantErr: "has no DD_API_KEY or apiKey field"},
		"json non string value": {
			secret:  `{"apiKey":12345}`,
			wantErr: `field "apiKey" is not a string`,
		},
		"json array is not an object":  {secret: `["a","b"]`, want: `["a","b"]`},
		"json number is not an object": {secret: `1234`, want: "1234"},
	}

	for name, tc := range tests {
		t.Run(name, func(t *testing.T) {
			t.Parallel()

			got, err := apiKeyFromSecret(arn, tc.secret)

			if tc.wantErr != "" {
				require.ErrorContains(t, err, tc.wantErr)
				assert.Empty(t, got)
				return
			}

			require.NoError(t, err)
			assert.Equal(t, tc.want, got)
		})
	}
}
