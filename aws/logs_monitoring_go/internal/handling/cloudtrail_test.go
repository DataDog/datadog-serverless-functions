// Unless explicitly stated otherwise all files in this repository are licensed
// under the Apache License Version 2.0.
// This product includes software developed at Datadog (https://www.datadoghq.com/).
// Copyright 2026-Present Datadog, Inc.

package handling

import (
	"bytes"
	"testing"

	"github.com/DataDog/datadog-serverless-functions/aws/logs_monitoring_go/internal/testutil"
	"github.com/google/go-cmp/cmp"
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
			got := cloudTrailRegex().MatchString(tc.key)
			if got != tc.want {
				t.Errorf("cloudTrailRegex().MatchString(%q) = %v, want %v", tc.key, got, tc.want)
			}
		})
	}
}

func TestCloudtrailHost(t *testing.T) {
	t.Parallel()

	tests := map[string]struct {
		record map[string]any
		want   string
	}{
		"ec2 instance (17)": {
			record: map[string]any{
				"userIdentity": map[string]any{
					"arn": "arn:aws:sts::601427279990:assumed-role/MyRole/i-08014e4f62ccf762d",
				},
			},
			want: "i-08014e4f62ccf762d",
		},
		"ec2 instance (8)": {
			record: map[string]any{
				"userIdentity": map[string]any{
					"arn": "arn:aws:sts::601427279990:assumed-role/MyRole/i-abcd1234",
				},
			},
			want: "i-abcd1234",
		},
		"non ec2 arn": {
			record: map[string]any{
				"userIdentity": map[string]any{
					"arn": "arn:aws:sts::601427279990:assumed-role/MyRole/my-session",
				},
			},
			want: "",
		},
		"missing userIdentity": {
			record: map[string]any{"eventName": "DescribeTable"},
			want:   "",
		},
		"missing arn": {
			record: map[string]any{
				"userIdentity": map[string]any{
					"type": "AssumedRole",
				},
			},
			want: "",
		},
	}

	for name, tc := range tests {
		t.Run(name, func(t *testing.T) {
			t.Parallel()
			host := cloudtrailHost(tc.record)
			if host != tc.want {
				t.Errorf("want %q, got %q", tc.want, host)
			}
		})
	}
}

func TestDecodeCloudTrail(t *testing.T) {
	t.Parallel()

	tests := map[string]struct {
		input   []byte
		want    []s3Record
		wantErr bool
	}{
		"single record with ec2 host": {
			input: testutil.MustGzipJSON(t, map[string]any{
				"Records": []any{
					map[string]any{
						"eventName": "DescribeTable",
						"userIdentity": map[string]any{
							"arn": "arn:aws:sts::601427279990:assumed-role/MyRole/i-08014e4f62ccf762d",
						},
					},
				},
			}),
			want: []s3Record{
				{
					Message: `{"eventName":"DescribeTable","userIdentity":{"arn":"arn:aws:sts::601427279990:assumed-role/MyRole/i-08014e4f62ccf762d"}}`,
					Host:    "i-08014e4f62ccf762d",
				},
			},
		},
		"single record without ec2 host": {
			input: testutil.MustGzipJSON(t, map[string]any{
				"Records": []any{
					map[string]any{
						"eventName": "DescribeTable",
						"userIdentity": map[string]any{
							"arn": "arn:aws:iam::601427279990:user/admin",
						},
					},
				},
			}),
			want: []s3Record{
				{
					Message: `{"eventName":"DescribeTable","userIdentity":{"arn":"arn:aws:iam::601427279990:user/admin"}}`,
					Host:    "",
				},
			},
		},
		"multiple records": {
			input: testutil.MustGzipJSON(t, map[string]any{
				"Records": []any{
					map[string]any{"eventName": "event1"},
					map[string]any{"eventName": "event2"},
				},
			}),
			want: []s3Record{
				{Message: `{"eventName":"event1"}`},
				{Message: `{"eventName":"event2"}`},
			},
		},
		"empty records array": {
			input: testutil.MustGzipJSON(t, map[string]any{
				"Records": []any{},
			}),
			want: nil,
		},
		"invalid gzip": {
			input:   []byte("not gzip"),
			wantErr: true,
		},
		"invalid json": {
			input:   testutil.MustGzipJSON(t, "not an object"),
			wantErr: true,
		},
	}

	for name, tc := range tests {
		t.Run(name, func(t *testing.T) {
			t.Parallel()

			var got []s3Record
			for rec := range decodeCloudTrail(bytes.NewReader(tc.input)) {
				if rec.Err != nil {
					if !tc.wantErr {
						t.Fatalf("unexpected error: %v", rec.Err)
					}
					return
				}
				got = append(got, rec)
			}

			if tc.wantErr {
				t.Fatal("expected error, got none")
			}
			if diff := cmp.Diff(tc.want, got); diff != "" {
				t.Errorf("mismatch (-want +got):\n%s", diff)
			}
		})
	}
}
