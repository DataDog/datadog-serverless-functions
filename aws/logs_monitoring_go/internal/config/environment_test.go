// Unless explicitly stated otherwise all files in this repository are licensed
// under the Apache License Version 2.0.
// This product includes software developed at Datadog (https://www.datadoghq.com/).
// Copyright 2026-Present Datadog, Inc.

package config

import "testing"

func TestEnvOrDefault(t *testing.T) {
	tests := map[string]struct {
		key      string
		value    string
		set      bool
		fallback string
		want     string
	}{
		"env_set":       {key: "DD_TEST_VAR", value: "from_env", set: true, fallback: "default", want: "from_env"},
		"env_not_set":   {key: "DD_TEST_VAR", value: "", set: false, fallback: "default", want: "default"},
		"env_set_empty": {key: "DD_TEST_VAR", value: "", set: true, fallback: "default", want: ""},
	}

	for name, tc := range tests {
		t.Run(name, func(t *testing.T) {
			if tc.set {
				t.Setenv(tc.key, tc.value)
			}
			got := envOrDefault(tc.key, tc.fallback)
			if got != tc.want {
				t.Errorf("got %q, want %q", got, tc.want)
			}
		})
	}
}

func TestEnvOrDefaultBool(t *testing.T) {
	tests := map[string]struct {
		value    string
		set      bool
		fallback bool
		want     bool
	}{
		"env_not_set":           {value: "", set: false, fallback: false, want: false},
		"env_not_set_fallback":  {value: "", set: false, fallback: true, want: true},
		"true_lowercase":        {value: "true", set: true, fallback: false, want: true},
		"true_uppercase":        {value: "TRUE", set: true, fallback: false, want: true},
		"true_mixed_case":       {value: "True", set: true, fallback: false, want: true},
		"false_value":           {value: "false", set: true, fallback: true, want: false},
		"one_is_true":           {value: "1", set: true, fallback: false, want: true},
		"zero_is_false":         {value: "0", set: true, fallback: true, want: false},
		"invalid_uses_fallback": {value: "yes", set: true, fallback: true, want: true},
		"empty_uses_fallback":   {value: "", set: true, fallback: true, want: true},
	}

	for name, tc := range tests {
		t.Run(name, func(t *testing.T) {
			if tc.set {
				t.Setenv("DD_TEST_BOOL", tc.value)
			}
			got := envOrDefaultBool("DD_TEST_BOOL", tc.fallback)
			if got != tc.want {
				t.Errorf("got %v, want %v", got, tc.want)
			}
		})
	}
}
