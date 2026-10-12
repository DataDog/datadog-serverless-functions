// Unless explicitly stated otherwise all files in this repository are licensed
// under the Apache License Version 2.0.
// This product includes software developed at Datadog (https://www.datadoghq.com/).
// Copyright 2026-Present Datadog, Inc.

package apikey

import (
	"context"
	"errors"
	"testing"

	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

const testAPIKey = "abcdef1234567890abcdef1234567890"

func TestResolve(t *testing.T) {
	t.Parallel()

	succeed := func(_ context.Context, v string) (string, error) { return v, nil }
	fail := func(_ context.Context, _ string) (string, error) { return "", errors.New("aws error") }

	tests := map[string]struct {
		resolvers []resolver
		wantKey   string
		wantErr   bool
	}{
		"first source wins": {
			resolvers: []resolver{
				{"secrets manager", testAPIKey, succeed},
				{"ssm", "ignored", succeed},
			},
			wantKey: testAPIKey,
		},
		"skips unset source": {
			resolvers: []resolver{
				{"secrets manager", "", fail},
				{"ssm", testAPIKey, succeed},
			},
			wantKey: testAPIKey,
		},
		"blank value is skipped": {
			resolvers: []resolver{
				{"secrets manager", "   ", fail},
				{"ssm", testAPIKey, succeed},
			},
			wantKey: testAPIKey,
		},
		"value is trimmed": {
			resolvers: []resolver{{"ssm", "  " + testAPIKey + "  ", succeed}},
			wantKey:   testAPIKey,
		},
		"no fallback after failure": {
			resolvers: []resolver{
				{"secrets manager", "bad", fail},
				{"ssm", testAPIKey, succeed},
			},
			wantErr: true,
		},
		"none configured": {
			resolvers: []resolver{{"secrets manager", "", succeed}},
			wantErr:   true,
		},
		"no resolvers": {
			wantErr: true,
		},
	}

	for name, tc := range tests {
		t.Run(name, func(t *testing.T) {
			t.Parallel()

			key, err := resolve(t.Context(), tc.resolvers)

			if tc.wantErr {
				require.Error(t, err)
				assert.Empty(t, key)
				return
			}

			require.NoError(t, err)
			assert.Equal(t, tc.wantKey, key)
		})
	}
}

func TestResolveOrdersSourcesByPrecedence(t *testing.T) {
	t.Parallel()

	var tried []string
	record := func(_ context.Context, v string) (string, error) {
		tried = append(tried, v)
		return "", errors.New("unavailable")
	}

	_, err := resolve(t.Context(), []resolver{
		{"secrets manager", "arn", record},
		{"ssm", "name", record},
		{"kms", "cipher", record},
	})

	require.Error(t, err)
	assert.Equal(t, []string{"arn"}, tried, "resolution must stop at the first configured source")
}

func TestResolveSourceFieldOrder(t *testing.T) {
	t.Parallel()

	_, err := Resolve(t.Context(), Source{})

	require.ErrorContains(t, err, "no Datadog API key configured")
}
