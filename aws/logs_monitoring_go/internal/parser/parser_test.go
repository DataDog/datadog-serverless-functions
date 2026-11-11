// Unless explicitly stated otherwise all files in this repository are licensed
// under the Apache License Version 2.0.
// This product includes software developed at Datadog (https://www.datadoghq.com/).
// Copyright 2026-Present Datadog, Inc.

package parser

import (
	"encoding/json/jsontext"
	"encoding/json/v2"
	"errors"
	"testing"

	"github.com/aws/aws-lambda-go/events"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

func TestParse(t *testing.T) {
	t.Parallel()

	cloudwatchEvent := jsontext.Value(`{"awslogs":{"data":"dGVzdA=="}}`)
	s3Event := jsontext.Value(`{"Records":[{"eventSource":"aws:s3","s3":{"bucket":{"name":"b"},"object":{"key":"k"}}}]}`)
	kinesisEvent := jsontext.Value(`{"Records":[{"eventSource":"aws:kinesis","kinesis":{"data":"dGVzdA=="}}]}`)
	eventBridgeEvent := jsontext.Value(`{"version":"0","id":"abc","detail-type":"Scheduled Event","source":"aws.events","detail":{}}`)
	eventBridgeS3Event := jsontext.Value(`{"version":"0","detail-type":"Object Created","source":"aws.s3","detail":{"bucket":{"name":"my-bucket"},"object":{"key":"my-key"}}}`)
	eventBridgeS3Payload, _ := toS3("my-bucket", "my-key")
	eventBridgeS3PutEvent := jsontext.Value(`{"version":"0","detail-type":"Object Created: Put","source":"aws.s3","detail":{"bucket":{"name":"b"},"object":{"key":"nested/path/log.gz"}}}`)
	eventBridgeS3PutPayload, _ := toS3("b", "nested/path/log.gz")

	tests := map[string]struct {
		event   jsontext.Value
		want    Event
		wantErr bool
	}{
		"cloudwatch logs": {
			event: cloudwatchEvent,
			want:  Event{ContentType: ContentTypeCloudwatchLogs, Payload: cloudwatchEvent},
		},
		"s3": {
			event: s3Event,
			want:  Event{ContentType: ContentTypeS3, Payload: s3Event},
		},
		"kinesis": {
			event: kinesisEvent,
			want:  Event{ContentType: ContentTypeKinesis, Payload: kinesisEvent},
		},
		"eventbridge generic": {
			event: eventBridgeEvent,
			want:  Event{ContentType: ContentTypeEventBridge, Payload: eventBridgeEvent},
		},
		"eventbridge s3": {
			event: eventBridgeS3Event,
			want: Event{
				ContentType: ContentTypeS3,
				Payload:     eventBridgeS3Payload,
			},
		},
		"eventbridge s3 via put": {
			event: eventBridgeS3PutEvent,
			want: Event{
				ContentType: ContentTypeS3,
				Payload:     eventBridgeS3PutPayload,
			},
		},
		"sns generic": {
			event: jsontext.Value(`{"Records":[{"EventSource":"aws:sns","Sns":{"Type":"Notification","Message":"hello world","TopicArn":"arn:aws:sns:us-east-1:123456789012:my-topic"}}]}`),
			want:  Event{ContentType: ContentTypeSNS, Payload: jsontext.Value(`hello world`)},
		},
		"sns generic with json": {
			event: jsontext.Value(`{"Records":[{"EventSource":"aws:sns","Sns":{"Type":"Notification","Message":"{\"ddtags\":\"service:myapp\",\"msg\":\"hi\"}"}}]}`),
			want:  Event{ContentType: ContentTypeSNS, Payload: jsontext.Value(`{"ddtags":"service:myapp","msg":"hi"}`)},
		},
		"sns s3": {
			event: jsontext.Value(`{"Records":[{"EventSource":"aws:sns","Sns":{"Type":"Notification","Message":"{\"Records\":[{\"eventSource\":\"aws:s3\",\"s3\":{\"bucket\":{\"name\":\"b\"},\"object\":{\"key\":\"k\"}}}]}"}}]}`),
			want:  Event{ContentType: ContentTypeS3, Payload: jsontext.Value(`{"Records":[{"eventSource":"aws:s3","s3":{"bucket":{"name":"b"},"object":{"key":"k"}}}]}`)},
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
			assert.Equal(t, tc.want, got)
		})
	}
}

func TestSQS(t *testing.T) {
	t.Parallel()

	errExpected := errors.New("expected failure")

	tests := map[string]struct {
		event   jsontext.Value
		want    []SQSEvent
		wantErr bool
	}{
		"direct s3": {
			event: jsontext.Value(`{"Records":[{"eventSource":"aws:sqs","body":"{\"Records\":[{\"eventSource\":\"aws:s3\",\"s3\":{\"bucket\":{\"name\":\"b\"},\"object\":{\"key\":\"k\"}}}]}"}]}`),
			want: []SQSEvent{
				{ContentType: ContentTypeS3, Payload: jsontext.Value(`{"Records":[{"eventSource":"aws:s3","s3":{"bucket":{"name":"b"},"object":{"key":"k"}}}]}`)},
			},
		},
		"sns s3": {
			event: jsontext.Value(`{"Records":[{"eventSource":"aws:sqs","body":"{\"Type\":\"Notification\",\"Message\":\"{\\\"Records\\\":[{\\\"eventSource\\\":\\\"aws:s3\\\",\\\"s3\\\":{\\\"bucket\\\":{\\\"name\\\":\\\"b\\\"},\\\"object\\\":{\\\"key\\\":\\\"k\\\"}}}]}\"}"}]}`),
			want: []SQSEvent{
				{ContentType: ContentTypeS3, Payload: jsontext.Value(`{"Records":[{"eventSource":"aws:s3","s3":{"bucket":{"name":"b"},"object":{"key":"k"}}}]}`)},
			},
		},
		"multiple records": {
			event: jsontext.Value(`{"Records":[` +
				`{"eventSource":"aws:sqs","body":"{\"Records\":[{\"eventSource\":\"aws:s3\",\"s3\":{\"bucket\":{\"name\":\"b1\"},\"object\":{\"key\":\"k1\"}}}]}"},` +
				`{"eventSource":"aws:sqs","body":"{\"Records\":[{\"eventSource\":\"aws:s3\",\"s3\":{\"bucket\":{\"name\":\"b2\"},\"object\":{\"key\":\"k2\"}}}]}"}` +
				`]}`),
			want: []SQSEvent{
				{ContentType: ContentTypeS3, Payload: jsontext.Value(`{"Records":[{"eventSource":"aws:s3","s3":{"bucket":{"name":"b1"},"object":{"key":"k1"}}}]}`)},
				{ContentType: ContentTypeS3, Payload: jsontext.Value(`{"Records":[{"eventSource":"aws:s3","s3":{"bucket":{"name":"b2"},"object":{"key":"k2"}}}]}`)},
			},
		},
		"sns standalone": {
			event: jsontext.Value(`{"Records":[{"eventSource":"aws:sqs","body":"{\"Type\":\"Notification\",\"Message\":\"hello world\"}"}]}`),
			want: []SQSEvent{
				{ContentType: ContentTypeSNS, Payload: jsontext.Value(`hello world`)},
			},
		},
		"sns standalone with ddtags-bearing json message": {
			event: jsontext.Value(`{"Records":[{"eventSource":"aws:sqs","body":"{\"Type\":\"Notification\",\"Message\":\"{\\\"ddtags\\\":\\\"service:myapp\\\",\\\"msg\\\":\\\"hi\\\"}\"}"}]}`),
			want: []SQSEvent{
				{ContentType: ContentTypeSNS, Payload: jsontext.Value(`{"ddtags":"service:myapp","msg":"hi"}`)},
			},
		},
		"subscription confirmation skipped": {
			event: jsontext.Value(`{"Records":[{"eventSource":"aws:sqs","body":"{\"Type\":\"SubscriptionConfirmation\",\"Message\":\"confirm\"}"}]}`),
			want: []SQSEvent{
				{Err: errExpected},
			},
		},
		"mixed valid and unrecognized": {
			event: jsontext.Value(`{"Records":[` +
				`{"eventSource":"aws:sqs","body":"{\"foo\":\"bar\"}"},` +
				`{"eventSource":"aws:sqs","body":"{\"Records\":[{\"eventSource\":\"aws:s3\",\"s3\":{\"bucket\":{\"name\":\"b\"},\"object\":{\"key\":\"k\"}}}]}"}` +
				`]}`),
			want: []SQSEvent{
				{Err: errExpected},
				{ContentType: ContentTypeS3, Payload: jsontext.Value(`{"Records":[{"eventSource":"aws:s3","s3":{"bucket":{"name":"b"},"object":{"key":"k"}}}]}`)},
			},
		},
		"extra fields after body": {
			event: jsontext.Value(`{"Records":[{"eventSource":"aws:sqs","body":"{\"Records\":[{\"eventSource\":\"aws:s3\",\"s3\":{\"bucket\":{\"name\":\"b\"},\"object\":{\"key\":\"k\"}}}]}","messageId":"abc","receiptHandle":"xyz","attributes":{"ApproximateReceiveCount":"1"}}]}`),
			want: []SQSEvent{
				{ContentType: ContentTypeS3, Payload: jsontext.Value(`{"Records":[{"eventSource":"aws:s3","s3":{"bucket":{"name":"b"},"object":{"key":"k"}}}]}`), MessageID: "abc"},
			},
		},
		"malformed body json": {
			event: jsontext.Value(`{"Records":[{"eventSource":"aws:sqs","body":"not json"}]}`),
			want: []SQSEvent{
				{Err: errExpected},
			},
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

			for i, want := range tc.want {
				assert.Equal(t, want.MessageID, got[i].MessageID, "record %d message id", i)

				if want.Err != nil {
					assert.Error(t, got[i].Err, "record %d", i)
					continue
				}

				assert.NoError(t, got[i].Err, "record %d", i)
				assert.Equal(t, want.Event, got[i].Event, "record %d", i)
			}
		})
	}
}

func TestToS3(t *testing.T) {
	t.Parallel()

	tests := map[string]struct {
		bucket         string
		key            string
		wantEncodedKey string
	}{
		"plain key": {
			bucket:         "my-bucket",
			key:            "my-key",
			wantEncodedKey: "my-key",
		},
		"key with slashes": {
			bucket:         "b",
			key:            "nested/path/log.gz",
			wantEncodedKey: "nested%2Fpath%2Flog.gz",
		},
		"key with plus": {
			bucket:         "b",
			key:            "logs/a+b.log",
			wantEncodedKey: "logs%2Fa%2Bb.log",
		},
		"key with percent": {
			bucket:         "b",
			key:            "logs/100%.log",
			wantEncodedKey: "logs%2F100%25.log",
		},
		"key with space": {
			bucket:         "b",
			key:            "logs/my file.log",
			wantEncodedKey: "logs%2Fmy+file.log",
		},
	}

	for name, tc := range tests {
		t.Run(name, func(t *testing.T) {
			t.Parallel()

			payload, err := toS3(tc.bucket, tc.key)
			require.NoError(t, err)

			var s3Event events.S3Event
			require.NoError(t, json.Unmarshal(payload, &s3Event))
			require.Len(t, s3Event.Records, 1)

			record := s3Event.Records[0]
			assert.Equal(t, eventSourceS3, record.EventSource)
			assert.Equal(t, tc.bucket, record.S3.Bucket.Name)
			assert.Equal(t, tc.wantEncodedKey, record.S3.Object.Key)
			assert.Equal(t, tc.key, record.S3.Object.URLDecodedKey)
		})
	}
}
