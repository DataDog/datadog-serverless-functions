// Unless explicitly stated otherwise all files in this repository are licensed
// under the Apache License Version 2.0.
// This product includes software developed at Datadog (https://www.datadoghq.com/).
// Copyright 2026-Present Datadog, Inc.

package handling

import (
	"encoding/json"
	"testing"

	"github.com/DataDog/datadog-serverless-functions/aws/logs_monitoring_go/internal/config"
	"github.com/DataDog/datadog-serverless-functions/aws/logs_monitoring_go/internal/model"
	"github.com/DataDog/datadog-serverless-functions/aws/logs_monitoring_go/internal/testutil"
	"github.com/google/go-cmp/cmp"
)

func TestCloudwatchHandler_Handle(t *testing.T) {
	t.Parallel()

	ctx := testutil.LambdaContext(t)

	tests := map[string]struct {
		event    json.RawMessage
		config   *config.Config
		chanSize int
		want     []model.LogEntry
		wantErr  bool
	}{
		"invalid JSON": {
			event:   json.RawMessage(`not json`),
			config:  testutil.EmptyConfig(),
			wantErr: true,
		},
		"invalid base64": {
			event:   json.RawMessage(`{"awslogs":{"data":"!!!not-base64!!!"}}`),
			config:  testutil.EmptyConfig(),
			wantErr: true,
		},
		"invalid gzip": {
			event:   testutil.MustCloudwatchEvent(t, []byte("not gzip")),
			config:  testutil.EmptyConfig(),
			wantErr: true,
		},
		"control message": {
			event: testutil.MustCloudwatchEvent(t, testutil.MustGzipJSON(t, map[string]any{
				"messageType": "CONTROL_MESSAGE",
				"logGroup":    "/aws/lambda/test",
				"logStream":   "stream",
				"logEvents":   []map[string]any{},
			})),
			config: testutil.EmptyConfig(),
			want:   nil,
		},
		"single log": {
			event: testutil.MustCloudwatchEvent(t, testutil.MustGzipJSON(t, map[string]any{
				"messageType": "DATA_MESSAGE",
				"owner":       "601427279990",
				"logGroup":    "/aws/lambda/testing-datadog",
				"logStream":   "2024/10/10/[$LATEST]20bddfd5a2dc4c6b97ac02800eae90d0",
				"logEvents": []map[string]any{
					{"id": "ev1", "timestamp": 1583425836114, "message": "hello"},
				},
			})),
			config:   testutil.EmptyConfig(),
			chanSize: 1,
			want: []model.LogEntry{
				{
					Message:        "hello",
					Source:         "lambda",
					SourceCategory: "aws",
					Service:        "lambda",
					Host:           "/aws/lambda/testing-datadog",
					ID:             "ev1",
					Timestamp:      1583425836114,
					Metadata: model.CloudwatchMetadata{
						LambdaOrigin: model.LambdaOrigin{ARN: "arn:aws:lambda:us-east-1:123456789012:function:forwarder"},
						Origin: model.CloudwatchOrigin{
							LogGroup:  "/aws/lambda/testing-datadog",
							LogStream: "2024/10/10/[$LATEST]20bddfd5a2dc4c6b97ac02800eae90d0",
							Owner:     "601427279990",
						},
					},
				},
			},
		},
		"multiple log events": {
			event: testutil.MustCloudwatchEvent(t, testutil.MustGzipJSON(t, map[string]any{
				"messageType": "DATA_MESSAGE",
				"owner":       "111111111111",
				"logGroup":    "/aws/lambda/fn",
				"logStream":   "stream",
				"logEvents": []map[string]any{
					{"id": "a1", "timestamp": 1000, "message": "first"},
					{"id": "a2", "timestamp": 2000, "message": "second"},
				},
			})),
			config:   testutil.EmptyConfig(),
			chanSize: 2,
			want: []model.LogEntry{
				{
					Message: "first", Source: "lambda", SourceCategory: "aws",
					Service: "lambda",
					Host: "/aws/lambda/fn", ID: "a1", Timestamp: 1000,
					Metadata: model.CloudwatchMetadata{
						LambdaOrigin: model.LambdaOrigin{ARN: "arn:aws:lambda:us-east-1:123456789012:function:forwarder"},
						Origin:       model.CloudwatchOrigin{LogGroup: "/aws/lambda/fn", LogStream: "stream", Owner: "111111111111"},
					},
				},
				{
					Message: "second", Source: "lambda", SourceCategory: "aws",
					Service: "lambda",
					Host: "/aws/lambda/fn", ID: "a2", Timestamp: 2000,
					Metadata: model.CloudwatchMetadata{
						LambdaOrigin: model.LambdaOrigin{ARN: "arn:aws:lambda:us-east-1:123456789012:function:forwarder"},
						Origin:       model.CloudwatchOrigin{LogGroup: "/aws/lambda/fn", LogStream: "stream", Owner: "111111111111"},
					},
				},
			},
		},
		"cloudtrail with ec2 host": {
			event: testutil.MustCloudwatchEvent(t, testutil.MustGzipJSON(t, map[string]any{
				"messageType": "DATA_MESSAGE",
				"owner":       "601427279990",
				"logGroup":    "cloudtrail-logs",
				"logStream":   "601427279990_CloudTrail_us-east-1",
				"logEvents": []map[string]any{
					{
						"id":        "ct1",
						"timestamp": 1620000000000,
						"message":   `{"eventName":"DescribeTable","userIdentity":{"arn":"arn:aws:sts::601427279990:assumed-role/MyRole/i-08014e4f62ccf762d"}}`,
					},
				},
			})),
			config:   testutil.EmptyConfig(),
			chanSize: 1,
			want: []model.LogEntry{
				{
					Message:        `{"eventName":"DescribeTable","userIdentity":{"arn":"arn:aws:sts::601427279990:assumed-role/MyRole/i-08014e4f62ccf762d"}}`,
					Source:         "cloudtrail",
					SourceCategory: "aws",
					Service:        "cloudtrail",
					Host:           "i-08014e4f62ccf762d",
					ID:             "ct1",
					Timestamp:      1620000000000,
					Metadata: model.CloudwatchMetadata{
						LambdaOrigin: model.LambdaOrigin{ARN: testutil.ARN},
						Origin: model.CloudwatchOrigin{
							LogGroup:  "cloudtrail-logs",
							LogStream: "601427279990_CloudTrail_us-east-1",
							Owner:     "601427279990",
						},
					},
				},
			},
		},
		"cloudtrail without ec2 host": {
			event: testutil.MustCloudwatchEvent(t, testutil.MustGzipJSON(t, map[string]any{
				"messageType": "DATA_MESSAGE",
				"owner":       "601427279990",
				"logGroup":    "cloudtrail-logs",
				"logStream":   "601427279990_CloudTrail_us-east-1",
				"logEvents": []map[string]any{
					{
						"id":        "ct2",
						"timestamp": 1620000000000,
						"message":   `{"eventName":"DescribeTable","userIdentity":{"arn":"arn:aws:iam::601427279990:user/admin"}}`,
					},
				},
			})),
			config:   testutil.EmptyConfig(),
			chanSize: 1,
			want: []model.LogEntry{
				{
					Message:        `{"eventName":"DescribeTable","userIdentity":{"arn":"arn:aws:iam::601427279990:user/admin"}}`,
					Source:         "cloudtrail",
					SourceCategory: "aws",
					Service:        "cloudtrail",
					Host:           "",
					ID:             "ct2",
					Timestamp:      1620000000000,
					Metadata: model.CloudwatchMetadata{
						LambdaOrigin: model.LambdaOrigin{ARN: testutil.ARN},
						Origin: model.CloudwatchOrigin{
							LogGroup:  "cloudtrail-logs",
							LogStream: "601427279990_CloudTrail_us-east-1",
							Owner:     "601427279990",
						},
					},
				},
			},
		},
		"config overrides source, host, service and tags": {
			event: testutil.MustCloudwatchEvent(t, testutil.MustGzipJSON(t, map[string]any{
				"messageType": "DATA_MESSAGE",
				"owner":       "111111111111",
				"logGroup":    "/aws/lambda/fn",
				"logStream":   "stream",
				"logEvents": []map[string]any{
					{"id": "ev1", "timestamp": 1000, "message": "hello"},
				},
			})),
			config: &config.Config{
				Source:  "custom-source",
				Host:    "custom-host",
				Service: "custom-service",
				Tags:    model.Tags{"env:prod", "team:infra"},
			},
			chanSize: 1,
			want: []model.LogEntry{
				{
					Message: "hello", Source: "custom-source", SourceCategory: "aws",
					Service: "custom-service",
					Tags:    model.Tags{"env:prod", "team:infra"},
					Host:    "custom-host", ID: "ev1", Timestamp: 1000,
					Metadata: model.CloudwatchMetadata{
						LambdaOrigin: model.LambdaOrigin{ARN: "arn:aws:lambda:us-east-1:123456789012:function:forwarder"},
						Origin:       model.CloudwatchOrigin{LogGroup: "/aws/lambda/fn", LogStream: "stream", Owner: "111111111111"},
					},
				},
			},
		},
	}

	for name, tc := range tests {
		t.Run(name, func(t *testing.T) {
			t.Parallel()

			out := make(chan model.LogEntry, tc.chanSize)
			handler := NewCloudwatch(tc.config)

			err := handler.Handle(ctx, tc.event, out)
			close(out)

			var got []model.LogEntry
			for entry := range out {
				got = append(got, entry)
			}

			if tc.wantErr {
				if err == nil {
					t.Fatal("want error, got nil")
				}
				return
			}
			if err != nil {
				t.Fatalf("unexpected error: %v", err)
			}
			if diff := cmp.Diff(tc.want, got); diff != "" {
				t.Errorf("mismatch (-want +got):\n%s", diff)
			}
		})
	}
}

func TestCloudwatchSource(t *testing.T) {
	t.Parallel()

	tests := map[string]struct {
		logGroup  string
		logStream string
		want      string
	}{
		"step function":             {logGroup: "/aws/vendedlogs", logStream: "states/my-machine/abc", want: "stepfunction"},
		"cloudtrail via log stream": {logGroup: "/aws/something", logStream: "123_CloudTrail_us-east-1", want: "cloudtrail"},
		"cloudtrail via log group":  {logGroup: "_cloudtrail_logs", logStream: "stream", want: "cloudtrail"},
		"cloudtrail via contains":   {logGroup: "my-cloudtrail-group", logStream: "stream", want: "cloudtrail"},
		"kinesis":                   {logGroup: "/aws/kinesis/my-stream", logStream: "stream", want: "kinesis"},
		"lambda":                    {logGroup: "/aws/lambda/my-function", logStream: "stream", want: "lambda"},
		"sns":                       {logGroup: "sns/us-east-1/123/topic", logStream: "stream", want: "sns"},
		"fallback cloudwatch":       {logGroup: "/aws/rds/cluster", logStream: "stream", want: "cloudwatch"},
	}

	for name, tc := range tests {
		t.Run(name, func(t *testing.T) {
			t.Parallel()
			if got := CloudwatchSource(tc.logGroup, tc.logStream); got != tc.want {
				t.Errorf("CloudwatchSource(%q, %q) = %q, want %q", tc.logGroup, tc.logStream, got, tc.want)
			}
		})
	}
}
