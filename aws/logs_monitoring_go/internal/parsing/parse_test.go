// Unless explicitly stated otherwise all files in this repository are licensed
// under the Apache License Version 2.0.
// This product includes software developed at Datadog (https://www.datadoghq.com/).
// Copyright 2026-Present Datadog, Inc.

package parsing

import (
	"encoding/json"
	"testing"

	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
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
		"sqs with direct s3": {
			event: json.RawMessage(`{"Records":[{"eventSource":"aws:sqs","body":"{\"Records\":[{\"s3\":{\"bucket\":{\"name\":\"b\"},\"object\":{\"key\":\"k\"}}}]}"}]}`),
			want:  []ContentType{ContentTypeS3},
		},
		"sqs with sns s3": {
			event: json.RawMessage(`{"Records":[{"eventSource":"aws:sqs","body":"{\"Type\":\"Notification\",\"Message\":\"{\\\"Records\\\":[{\\\"s3\\\":{\\\"bucket\\\":{\\\"name\\\":\\\"b\\\"},\\\"object\\\":{\\\"key\\\":\\\"k\\\"}}}]}\"}"}]}`),
			want:  []ContentType{ContentTypeS3},
		},
		"sqs with multiple records": {
			event: json.RawMessage(`{"Records":[` +
				`{"eventSource":"aws:sqs","body":"{\"Records\":[{\"s3\":{\"bucket\":{\"name\":\"b1\"},\"object\":{\"key\":\"k1\"}}}]}"},` +
				`{"eventSource":"aws:sqs","body":"{\"Records\":[{\"s3\":{\"bucket\":{\"name\":\"b2\"},\"object\":{\"key\":\"k2\"}}}]}"}` +
				`]}`),
			want: []ContentType{ContentTypeS3, ContentTypeS3},
		},
		"sqs with sns standalone": {
			event: json.RawMessage(`{"Records":[{"eventSource":"aws:sqs","body":"{\"Type\":\"Notification\",\"Message\":\"hello world\"}"}]}`),
			want:  []ContentType{ContentTypeSNS},
		},
		"sqs with subscription confirmation skipped": {
			event:   json.RawMessage(`{"Records":[{"eventSource":"aws:sqs","body":"{\"Type\":\"SubscriptionConfirmation\",\"Message\":\"confirm\"}"}]}`),
			wantErr: true,
		},
		"sqs mixed valid and unrecognized": {
			event: json.RawMessage(`{"Records":[` +
				`{"eventSource":"aws:sqs","body":"{\"foo\":\"bar\"}"},` +
				`{"eventSource":"aws:sqs","body":"{\"Records\":[{\"s3\":{\"bucket\":{\"name\":\"b\"},\"object\":{\"key\":\"k\"}}}]}"}` +
				`]}`),
			want: []ContentType{ContentTypeS3},
		},
		"sqs with extra fields after body": {
			event: json.RawMessage(`{"Records":[{"eventSource":"aws:sqs","body":"{\"Records\":[{\"s3\":{\"bucket\":{\"name\":\"b\"},\"object\":{\"key\":\"k\"}}}]}","messageId":"abc","receiptHandle":"xyz","attributes":{"ApproximateReceiveCount":"1"}}]}`),
			want:  []ContentType{ContentTypeS3},
		},
		"sqs with malformed body json": {
			event:   json.RawMessage(`{"Records":[{"eventSource":"aws:sqs","body":"not json"}]}`),
			wantErr: true,
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
				require.Error(t, err)
				return
			}

			require.NoError(t, err)
			require.Len(t, got, len(tc.want))

			for i, pe := range got {
				assert.Equal(t, tc.want[i], pe.ContentType)
				assert.NotEmpty(t, pe.Payload)
			}
		})
	}
}
