// Unless explicitly stated otherwise all files in this repository are licensed
// under the Apache License Version 2.0.
// This product includes software developed at Datadog (https://www.datadoghq.com/).
// Copyright 2026-Present Datadog, Inc.

package handling

import (
	"bytes"
	"testing"

	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

func TestCloudTrailRegex(t *testing.T) {
	t.Parallel()

	tests := map[string]struct {
		key  string
		want bool
	}{
		"standard cloudtrail": {
			key:  "601427279990_CloudTrail_us-east-1_20210503T0000Z_QrttGEk4ZcBTLwj5.json.gz",
			want: true,
		},
		"cloudtrail digest": {
			key:  "601427279990_CloudTrail-Digest_us-east-1_20210503T0000Z_digest.json.gz",
			want: true,
		},
		"cloudtrail insight": {
			key:  "601427279990_CloudTrail-Insight_us-east-1_20210503T0000Z_insight.json.gz",
			want: true,
		},
		"gov region": {
			key:  "601427279990_CloudTrail_us-gov-west-1_20210503T0000Z_abc.json.gz",
			want: true,
		},
		"cn region": {
			key:  "601427279990_CloudTrail_cn-north-1_20210503T0000Z_abc.json.gz",
			want: true,
		},
		"not cloudtrail": {
			key:  "some-random-log-file.json.gz",
			want: false,
		},
		"waf log": {
			key:  "aws-waf-logs-something.json.gz",
			want: false,
		},
		"plain text file": {
			key:  "access.log",
			want: false,
		},
	}

	for name, tc := range tests {
		t.Run(name, func(t *testing.T) {
			t.Parallel()
			assert.Equal(t, tc.want, cloudTrailRegex.MatchString(tc.key))
		})
	}
}

func TestCloudtrailHost(t *testing.T) {
	t.Parallel()

	tests := map[string]struct {
		message string
		want    string
	}{
		"ec2 instance (17)": {
			message: `{"userIdentity":{"arn":"arn:aws:sts::601427279990:assumed-role/MyRole/i-08014e4f62ccf762d"}}`,
			want:    "i-08014e4f62ccf762d",
		},
		"ec2 instance (8)": {
			message: `{"userIdentity":{"arn":"arn:aws:sts::601427279990:assumed-role/MyRole/i-abcd1234"}}`,
			want:    "i-abcd1234",
		},
		"non ec2 arn": {
			message: `{"userIdentity":{"arn":"arn:aws:sts::601427279990:assumed-role/MyRole/my-session"}}`,
			want:    "",
		},
		"missing userIdentity": {
			message: `{"eventName":"DescribeTable"}`,
			want:    "",
		},
		"missing arn": {
			message: `{"userIdentity":{"type":"AssumedRole"}}`,
			want:    "",
		},
		"invalid json": {
			message: "not json",
			want:    "",
		},
		"empty message": {
			message: "",
			want:    "",
		},
	}

	for name, tc := range tests {
		t.Run(name, func(t *testing.T) {
			t.Parallel()
			assert.Equal(t, tc.want, cloudtrailHost(tc.message))
		})
	}
}

func TestDecodeCloudTrail(t *testing.T) {
	t.Parallel()

	tests := map[string]struct {
		input   []byte
		want    []string
		wantErr bool
	}{
		"single record": {
			input: []byte(`{"Records":[{"eventName":"DescribeTable","userIdentity":{"arn":"arn:aws:sts::601427279990:assumed-role/MyRole/i-08014e4f62ccf762d"}}]}`),
			want: []string{
				`{"eventName":"DescribeTable","userIdentity":{"arn":"arn:aws:sts::601427279990:assumed-role/MyRole/i-08014e4f62ccf762d"}}`,
			},
		},
		"multiple records": {
			input: []byte(`{"Records":[{"eventName":"event1"},{"eventName":"event2"}]}`),
			want: []string{
				`{"eventName":"event1"}`,
				`{"eventName":"event2"}`,
			},
		},
		"empty records array": {
			input: []byte(`{"Records":[]}`),
			want:  nil,
		},
		"invalid json": {
			input:   []byte("not json"),
			wantErr: true,
		},
	}

	for name, tc := range tests {
		t.Run(name, func(t *testing.T) {
			t.Parallel()

			var got []string
			for msg, err := range decodeCloudTrail(bytes.NewReader(tc.input)) {
				if err != nil {
					require.True(t, tc.wantErr, "unexpected error: %v", err)
					return
				}
				got = append(got, msg)
			}

			require.False(t, tc.wantErr, "expected error, got none")
			assert.Equal(t, tc.want, got)
		})
	}
}
