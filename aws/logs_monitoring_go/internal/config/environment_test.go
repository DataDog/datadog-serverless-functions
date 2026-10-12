// Unless explicitly stated otherwise all files in this repository are licensed
// under the Apache License Version 2.0.
// This product includes software developed at Datadog (https://www.datadoghq.com/).
// Copyright 2026-Present Datadog, Inc.

package config

import (
	"testing"

	"github.com/stretchr/testify/assert"
)

const (
	envTestString = "DD_TEST_VAR"
	envTestBool   = "DD_TEST_BOOL"
)

func TestEnvOrDefault(t *testing.T) {
	tests := map[string]struct {
		env      map[string]string
		fallback string
		want     string
	}{
		"env_set":       {env: map[string]string{envTestString: "from_env"}, fallback: "default", want: "from_env"},
		"env_not_set":   {fallback: "default", want: "default"},
		"env_set_empty": {env: map[string]string{envTestString: ""}, fallback: "default", want: ""},
	}

	for name, tc := range tests {
		t.Run(name, func(t *testing.T) {
			for k, v := range tc.env {
				t.Setenv(k, v)
			}

			assert.Equal(t, tc.want, envOrDefault(envTestString, tc.fallback))
		})
	}
}

func TestEnvOrDefaultBool(t *testing.T) {
	tests := map[string]struct {
		env      map[string]string
		fallback bool
		want     bool
	}{
		"env_not_set":           {fallback: false, want: false},
		"env_not_set_fallback":  {fallback: true, want: true},
		"true_lowercase":        {env: map[string]string{envTestBool: "true"}, fallback: false, want: true},
		"true_uppercase":        {env: map[string]string{envTestBool: "TRUE"}, fallback: false, want: true},
		"true_mixed_case":       {env: map[string]string{envTestBool: "True"}, fallback: false, want: true},
		"false_value":           {env: map[string]string{envTestBool: "false"}, fallback: true, want: false},
		"one_is_true":           {env: map[string]string{envTestBool: "1"}, fallback: false, want: true},
		"zero_is_false":         {env: map[string]string{envTestBool: "0"}, fallback: true, want: false},
		"invalid_uses_fallback": {env: map[string]string{envTestBool: "yes"}, fallback: true, want: true},
		"empty_uses_fallback":   {env: map[string]string{envTestBool: ""}, fallback: true, want: true},
	}

	for name, tc := range tests {
		t.Run(name, func(t *testing.T) {
			for k, v := range tc.env {
				t.Setenv(k, v)
			}

			assert.Equal(t, tc.want, envOrDefaultBool(envTestBool, tc.fallback))
		})
	}
}
