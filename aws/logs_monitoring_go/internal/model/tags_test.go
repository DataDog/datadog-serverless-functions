// Unless explicitly stated otherwise all files in this repository are licensed
// under the Apache License Version 2.0.
// This product includes software developed at Datadog (https://www.datadoghq.com/).
// Copyright 2026-Present Datadog, Inc.

package model

import (
	"encoding/json"
	"testing"

	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

func TestTags_MarshalJSON_UnmarshalJSON(t *testing.T) {
	t.Parallel()

	tests := map[string]struct {
		tags Tags
		want string
	}{
		"nil":      {tags: nil, want: `""`},
		"empty":    {tags: Tags{}, want: `""`},
		"one":      {tags: Tags{"env:prod"}, want: `"env:prod"`},
		"multiple": {tags: Tags{"env:prod", "team:aws"}, want: `"env:prod,team:aws"`},
	}

	for name, tc := range tests {
		t.Run(name, func(t *testing.T) {
			t.Parallel()

			got, err := json.Marshal(tc.tags)

			require.NoError(t, err)
			assert.Equal(t, tc.want, string(got))

			var tags Tags
			require.NoError(t, json.Unmarshal(got, &tags))
			if len(tc.tags) == 0 {
				assert.Empty(t, tags)
				return
			}
			assert.Equal(t, tc.tags, tags)
		})
	}
}

func TestTags_Has(t *testing.T) {
	t.Parallel()

	tests := map[string]struct {
		tags Tags
		key  string
		want bool
	}{
		"nil":                        {tags: nil, key: "env", want: false},
		"present":                    {tags: Tags{"team:infra", "env:prod"}, key: "env", want: true},
		"not present":                {tags: Tags{"team:infra", "service:api"}, key: "env", want: false},
		"not present when separator": {tags: Tags{"team:infra", "service:api"}, key: "service:", want: false},
	}

	for name, tc := range tests {
		t.Run(name, func(t *testing.T) {
			t.Parallel()
			assert.Equal(t, tc.want, tc.tags.Has(tc.key))
		})
	}
}

func TestParseTags(t *testing.T) {
	t.Parallel()

	tests := map[string]struct {
		raw         string
		wantService string
		wantTags    Tags
	}{
		"empty":                              {},
		"custom tags kept":                   {raw: "team:backend,env:prod", wantTags: Tags{"team:backend", "env:prod"}},
		"service extracted and removed":      {raw: "team:backend,service:my-app", wantService: "my-app", wantTags: Tags{"team:backend"}},
		"first service wins":                 {raw: "service:first,service:second", wantService: "first"},
		"empty service value":                {raw: "service:"},
		"bare key is kept":                   {raw: "servicelike", wantTags: Tags{"servicelike"}},
		"service prefix not matched loosely": {raw: "service_name:my-app", wantTags: Tags{"service_name:my-app"}},
	}

	for name, tc := range tests {
		t.Run(name, func(t *testing.T) {
			t.Parallel()

			gotService, gotTags := ParseTags(tc.raw)
			assert.Equal(t, tc.wantService, gotService)
			assert.Equal(t, tc.wantTags, gotTags)
		})
	}
}
