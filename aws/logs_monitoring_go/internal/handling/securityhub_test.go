// Unless explicitly stated otherwise all files in this repository are licensed
// under the Apache License Version 2.0.
// This product includes software developed at Datadog (https://www.datadoghq.com/).
// Copyright 2026-Present Datadog, Inc.

package handling

import (
	"encoding/json"
	"testing"

	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

func TestSeparateFindings(t *testing.T) {
	t.Parallel()

	tests := map[string]struct {
		input string
		want  []string
	}{
		"no findings field": {
			input: `{"source":"aws.securityhub"}`,
		},
		"empty findings": {
			input: `{"detail":{"findings":[]}}`,
		},
		"invalid json": {
			input: `not json`,
		},
		"one finding no resources": {
			input: `{"ddsource":"securityhub","detail":{"findings":[{"myattribute":"somevalue"}]}}`,
			want: []string{
				`{"ddsource":"securityhub","detail":{"finding":{"myattribute":"somevalue","resources":{}}}}`,
			},
		},
		"two findings one resource each": {
			input: `{"ddsource":"securityhub","detail":{"findings":[{"myattribute":"somevalue","Resources":[{"Region":"us-east-1","Type":"AwsEc2SecurityGroup"}]},{"myattribute":"somevalue","Resources":[{"Region":"us-east-1","Type":"AwsEc2SecurityGroup"}]}]}}`,
			want: []string{
				`{"ddsource":"securityhub","detail":{"finding":{"myattribute":"somevalue","resources":{"AwsEc2SecurityGroup":{"Region":"us-east-1"}}}}}`,
				`{"ddsource":"securityhub","detail":{"finding":{"myattribute":"somevalue","resources":{"AwsEc2SecurityGroup":{"Region":"us-east-1"}}}}}`,
			},
		},
		"multiple findings multiple resources": {
			input: `{"ddsource":"securityhub","detail":{"findings":[{"myattribute":"somevalue","Resources":[{"Region":"us-east-1","Type":"AwsEc2SecurityGroup"}]},{"myattribute":"somevalue","Resources":[{"Region":"us-east-1","Type":"AwsEc2SecurityGroup"},{"Region":"us-east-1","Type":"AwsOtherSecurityGroup"}]},{"myattribute":"somevalue","Resources":[{"Region":"us-east-1","Type":"AwsEc2SecurityGroup"},{"Region":"us-east-1","Type":"AwsOtherSecurityGroup"},{"Region":"us-east-1","Type":"AwsAnotherSecurityGroup"}]}]}}`,
			want: []string{
				`{"ddsource":"securityhub","detail":{"finding":{"myattribute":"somevalue","resources":{"AwsEc2SecurityGroup":{"Region":"us-east-1"}}}}}`,
				`{"ddsource":"securityhub","detail":{"finding":{"myattribute":"somevalue","resources":{"AwsEc2SecurityGroup":{"Region":"us-east-1"},"AwsOtherSecurityGroup":{"Region":"us-east-1"}}}}}`,
				`{"ddsource":"securityhub","detail":{"finding":{"myattribute":"somevalue","resources":{"AwsAnotherSecurityGroup":{"Region":"us-east-1"},"AwsEc2SecurityGroup":{"Region":"us-east-1"},"AwsOtherSecurityGroup":{"Region":"us-east-1"}}}}}`,
			},
		},
	}

	for name, tc := range tests {
		t.Run(name, func(t *testing.T) {
			t.Parallel()
			got := separateFindings(json.RawMessage(tc.input))
			require.Len(t, got, len(tc.want))
			for i, want := range tc.want {
				assert.JSONEq(t, want, got[i])
			}
		})
	}
}
