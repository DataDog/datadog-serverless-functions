// Unless explicitly stated otherwise all files in this repository are licensed
// under the Apache License Version 2.0.
// This product includes software developed at Datadog (https://www.datadoghq.com/).
// Copyright 2026-Present Datadog, Inc.

package parser

import (
	"encoding/json/jsontext"
	"testing"

	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

func TestParse(t *testing.T) {
	t.Parallel()

	tests := map[string]struct {
		event   jsontext.Value
		want    ContentType
		wantErr bool
	}{
		"cloudwatch logs": {
			event: jsontext.Value(`{"awslogs":{"data":"dGVzdA=="}}`),
			want:  ContentTypeCloudwatchLogs,
		},
		"s3": {
			event: jsontext.Value(`{"Records":[{"eventSource":"aws:s3","s3":{"bucket":{"name":"b"},"object":{"key":"k"}}}]}`),
			want:  ContentTypeS3,
		},
		"kinesis": {
			event: jsontext.Value(`{"Records":[{"eventSource":"aws:kinesis","kinesis":{"data":"dGVzdA=="}}]}`),
			want:  ContentTypeKinesis,
		},
		"eventbridge generic": {
			event: jsontext.Value(`{"version":"0","id":"abc","detail-type":"Scheduled Event","source":"aws.events","detail":{}}`),
			want:  ContentTypeEventBridge,
		},
		"eventbridge s3": {
			event: jsontext.Value(`{"version":"0","detail-type":"Object Created","source":"aws.s3","detail":{"bucket":{"name":"my-bucket"},"object":{"key":"my-key"}}}`),
			want:  ContentTypeS3,
		},
		"eventbridge ec2": {
			event: jsontext.Value(`{"version":"0","detail-type":"EC2 Instance State-change Notification","source":"aws.ec2","detail":{"instance-id":"i-123"}}`),
			want:  ContentTypeEventBridge,
		},
		"eventbridge s3 without object created": {
			event: jsontext.Value(`{"version":"0","detail-type":"Object Deleted","source":"aws.s3","detail":{}}`),
			want:  ContentTypeEventBridge,
		},
		"sns with s3": {
			event: jsontext.Value(`{"Records":[{"EventSource":"aws:sns","Sns":{"Type":"Notification","Message":"{\"Records\":[{\"eventSource\":\"aws:s3\",\"s3\":{\"bucket\":{\"name\":\"b\"},\"object\":{\"key\":\"k\"}}}]}"}}]}`),
			want:  ContentTypeS3,
		},
		"sns standalone": {
			event: jsontext.Value(`{"Records":[{"EventSource":"aws:sns","Sns":{"Type":"Notification","Message":"hello world","TopicArn":"arn:aws:sns:us-east-1:123456789012:my-topic"}}]}`),
			want:  ContentTypeSNS,
		},
		"empty object": {
			event:   jsontext.Value(`{}`),
			wantErr: true,
		},
		"unsupported source": {
			event:   jsontext.Value(`{"Records":[{"eventSource":"aws:dynamodb"}]}`),
			wantErr: true,
		},
		"not JSON": {
			event:   jsontext.Value(`not json`),
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
			assert.Equal(t, tc.want, got.ContentType)
			assert.NotEmpty(t, got.Payload)
		})
	}
}

func TestSQS(t *testing.T) {
	t.Parallel()

	tests := map[string]struct {
		event      jsontext.Value
		want       []ContentType
		wantFailed []int
		wantErr    bool
	}{
		"direct s3": {
			event: jsontext.Value(`{"Records":[{"eventSource":"aws:sqs","body":"{\"Records\":[{\"eventSource\":\"aws:s3\",\"s3\":{\"bucket\":{\"name\":\"b\"},\"object\":{\"key\":\"k\"}}}]}"}]}`),
			want:  []ContentType{ContentTypeS3},
		},
		"sns s3": {
			event: jsontext.Value(`{"Records":[{"eventSource":"aws:sqs","body":"{\"Type\":\"Notification\",\"Message\":\"{\\\"Records\\\":[{\\\"eventSource\\\":\\\"aws:s3\\\",\\\"s3\\\":{\\\"bucket\\\":{\\\"name\\\":\\\"b\\\"},\\\"object\\\":{\\\"key\\\":\\\"k\\\"}}}]}\"}"}]}`),
			want:  []ContentType{ContentTypeS3},
		},
		"multiple records": {
			event: jsontext.Value(`{"Records":[` +
				`{"eventSource":"aws:sqs","body":"{\"Records\":[{\"eventSource\":\"aws:s3\",\"s3\":{\"bucket\":{\"name\":\"b1\"},\"object\":{\"key\":\"k1\"}}}]}"},` +
				`{"eventSource":"aws:sqs","body":"{\"Records\":[{\"eventSource\":\"aws:s3\",\"s3\":{\"bucket\":{\"name\":\"b2\"},\"object\":{\"key\":\"k2\"}}}]}"}` +
				`]}`),
			want: []ContentType{ContentTypeS3, ContentTypeS3},
		},
		"sns standalone": {
			event: jsontext.Value(`{"Records":[{"eventSource":"aws:sqs","body":"{\"Type\":\"Notification\",\"Message\":\"hello world\"}"}]}`),
			want:  []ContentType{ContentTypeSNS},
		},
		"subscription confirmation skipped": {
			event:      jsontext.Value(`{"Records":[{"eventSource":"aws:sqs","body":"{\"Type\":\"SubscriptionConfirmation\",\"Message\":\"confirm\"}"}]}`),
			want:       []ContentType{ContentTypeUnknown},
			wantFailed: []int{0},
		},
		"mixed valid and unrecognized": {
			event: jsontext.Value(`{"Records":[` +
				`{"eventSource":"aws:sqs","body":"{\"foo\":\"bar\"}"},` +
				`{"eventSource":"aws:sqs","body":"{\"Records\":[{\"eventSource\":\"aws:s3\",\"s3\":{\"bucket\":{\"name\":\"b\"},\"object\":{\"key\":\"k\"}}}]}"}` +
				`]}`),
			want:       []ContentType{ContentTypeUnknown, ContentTypeS3},
			wantFailed: []int{0},
		},
		"extra fields after body": {
			event: jsontext.Value(`{"Records":[{"eventSource":"aws:sqs","body":"{\"Records\":[{\"eventSource\":\"aws:s3\",\"s3\":{\"bucket\":{\"name\":\"b\"},\"object\":{\"key\":\"k\"}}}]}","messageId":"abc","receiptHandle":"xyz","attributes":{"ApproximateReceiveCount":"1"}}]}`),
			want:  []ContentType{ContentTypeS3},
		},
		"malformed body json": {
			event:      jsontext.Value(`{"Records":[{"eventSource":"aws:sqs","body":"not json"}]}`),
			want:       []ContentType{ContentTypeUnknown},
			wantFailed: []int{0},
		},
		"unreadable batch": {
			event:   jsontext.Value(`{"Records":[{"eventSource":"aws:sqs"`),
			wantErr: true,
		},
	}

	for name, tc := range tests {
		t.Run(name, func(t *testing.T) {
			t.Parallel()

			got, err := SQS(tc.event)

			if tc.wantErr {
				require.Error(t, err)
				return
			}

			require.NoError(t, err)
			require.Len(t, got, len(tc.want))

			failed := make(map[int]bool, len(tc.wantFailed))
			for _, i := range tc.wantFailed {
				failed[i] = true
			}

			for i, se := range got {
				assert.Equal(t, tc.want[i], se.ContentType, "record %d content type", i)

				if failed[i] {
					assert.Error(t, se.Err, "record %d", i)
					continue
				}

				assert.NoError(t, se.Err, "record %d", i)
				assert.NotEmpty(t, se.Payload, "record %d payload", i)
			}
		})
	}
}

func TestSQS_MessageID(t *testing.T) {
	t.Parallel()

	event := jsontext.Value(`{"Records":[{"eventSource":"aws:sqs","body":"{\"Type\":\"Notification\",\"Message\":\"hello\"}","messageId":"abc","receiptHandle":"xyz"}]}`)

	got, err := SQS(event)

	require.NoError(t, err)
	require.Len(t, got, 1)
	assert.Equal(t, "abc", got[0].MessageID)
}
