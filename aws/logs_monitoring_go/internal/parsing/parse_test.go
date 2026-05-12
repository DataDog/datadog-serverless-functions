// Unless explicitly stated otherwise all files in this repository are licensed
// under the Apache License Version 2.0.
// This product includes software developed at Datadog (https://www.datadoghq.com/).
// Copyright 2026-Present Datadog, Inc.

package parsing

import (
	"encoding/json"
	"testing"
)

func TestParse(t *testing.T) {
	t.Parallel()

	tests := map[string]struct {
		event   json.RawMessage
		want    []ContentType
		wantErr bool
	}{
		"cloudwatch logs": {
			event: json.RawMessage(`{"awslogs":{"data":"dGVzdA=="}}`),
			want:  []ContentType{ContentTypeCloudwatchLogs},
		},
		"s3": {
			event: json.RawMessage(`{"Records":[{"eventSource":"aws:s3","s3":{"bucket":{"name":"b"},"object":{"key":"k"}}}]}`),
			want:  []ContentType{ContentTypeS3},
		},
		"kinesis": {
			event: json.RawMessage(`{"Records":[{"eventSource":"aws:kinesis","kinesis":{"data":"dGVzdA=="}}]}`),
			want:  []ContentType{ContentTypeKinesis},
		},
		"eventbridge generic": {
			event: json.RawMessage(`{"version":"0","id":"abc","detail-type":"Scheduled Event","source":"aws.events","detail":{}}`),
			want:  []ContentType{ContentTypeEventBridge},
		},
		"eventbridge s3": {
			event: json.RawMessage(`{"version":"0","detail-type":"Object Created","source":"aws.s3","detail":{"bucket":{"name":"my-bucket"},"object":{"key":"my-key"}}}`),
			want:  []ContentType{ContentTypeS3},
		},
		"eventbridge ec2": {
			event: json.RawMessage(`{"version":"0","detail-type":"EC2 Instance State-change Notification","source":"aws.ec2","detail":{"instance-id":"i-123"}}`),
			want:  []ContentType{ContentTypeEventBridge},
		},
		"eventbridge s3 without object created": {
			event: json.RawMessage(`{"version":"0","detail-type":"Object Deleted","source":"aws.s3","detail":{}}`),
			want:  []ContentType{ContentTypeEventBridge},
		},
		"sns with s3": {
			event: json.RawMessage(`{"Records":[{"EventSource":"aws:sns","Sns":{"Type":"Notification","Message":"{\"Records\":[{\"s3\":{\"bucket\":{\"name\":\"b\"},\"object\":{\"key\":\"k\"}}}]}"}}]}`),
			want:  []ContentType{ContentTypeS3},
		},
		"sns standalone": {
			event: json.RawMessage(`{"Records":[{"EventSource":"aws:sns","Sns":{"Type":"Notification","Message":"hello world","TopicArn":"arn:aws:sns:us-east-1:123456789012:my-topic"}}]}`),
			want:  []ContentType{ContentTypeSNS},
		},
		"empty object": {
			event:   json.RawMessage(`{}`),
			wantErr: true,
		},
		"unsupported source": {
			event:   json.RawMessage(`{"Records":[{"eventSource":"aws:dynamodb"}]}`),
			wantErr: true,
		},
		"not JSON": {
			event:   json.RawMessage(`not json`),
			wantErr: true,
		},
	}

	for name, tc := range tests {
		t.Run(name, func(t *testing.T) {
			t.Parallel()

			got, err := Parse(tc.event)

			if tc.wantErr {
				if err == nil {
					t.Fatal("expected error, got nil")
				}
				return
			}

			if err != nil {
				t.Fatalf("unexpected error: %v", err)
			}

			if len(got) != len(tc.want) {
				t.Fatalf("got %d events, want %d", len(got), len(tc.want))
			}

			for i, pe := range got {
				if pe.ContentType != tc.want[i] {
					t.Errorf("event[%d]: got ContentType %v, want %v", i, pe.ContentType, tc.want[i])
				}
				if len(pe.Payload) == 0 {
					t.Errorf("event[%d]: empty payload", i)
				}
			}
		})
	}
}
