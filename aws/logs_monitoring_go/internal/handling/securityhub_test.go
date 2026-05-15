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
		input   string
		wantOK  bool
		wantLen int
		want    []string
	}{
		"no findings field": {
			input:  `{"source":"aws.securityhub"}`,
			wantOK: false,
		},
		"empty findings": {
			input:  `{"detail":{"findings":[]}}`,
			wantOK: false,
		},
		"invalid json": {
			input:  `not json`,
			wantOK: false,
		},
		"one finding no resources": {
			input:   `{"ddsource":"securityhub","detail":{"findings":[{"myattribute":"somevalue"}]}}`,
			wantOK:  true,
			wantLen: 1,
			want: []string{
				`{"ddsource":"securityhub","detail":{"finding":{"myattribute":"somevalue","resources":{}}}}`,
			},
		},
		"two findings one resource each": {
			input:   `{"ddsource":"securityhub","detail":{"findings":[{"myattribute":"somevalue","Resources":[{"Region":"us-east-1","Type":"AwsEc2SecurityGroup"}]},{"myattribute":"somevalue","Resources":[{"Region":"us-east-1","Type":"AwsEc2SecurityGroup"}]}]}}`,
			wantOK:  true,
			wantLen: 2,
			want: []string{
				`{"ddsource":"securityhub","detail":{"finding":{"myattribute":"somevalue","resources":{"AwsEc2SecurityGroup":{"Region":"us-east-1"}}}}}`,
				`{"ddsource":"securityhub","detail":{"finding":{"myattribute":"somevalue","resources":{"AwsEc2SecurityGroup":{"Region":"us-east-1"}}}}}`,
			},
		},
		"multiple findings multiple resources": {
			input:   `{"ddsource":"securityhub","detail":{"findings":[{"myattribute":"somevalue","Resources":[{"Region":"us-east-1","Type":"AwsEc2SecurityGroup"}]},{"myattribute":"somevalue","Resources":[{"Region":"us-east-1","Type":"AwsEc2SecurityGroup"},{"Region":"us-east-1","Type":"AwsOtherSecurityGroup"}]},{"myattribute":"somevalue","Resources":[{"Region":"us-east-1","Type":"AwsEc2SecurityGroup"},{"Region":"us-east-1","Type":"AwsOtherSecurityGroup"},{"Region":"us-east-1","Type":"AwsAnotherSecurityGroup"}]}]}}`,
			wantOK:  true,
			wantLen: 3,
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
			got, ok := separateFindings(json.RawMessage(tc.input))
			assert.Equal(t, tc.wantOK, ok)
			if !tc.wantOK {
				assert.Nil(t, got)
				return
			}
			require.Len(t, got, tc.wantLen)
			for i, want := range tc.want {
				assert.JSONEq(t, want, got[i])
			}
		})
	}
}
