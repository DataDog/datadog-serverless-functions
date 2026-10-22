// Unless explicitly stated otherwise all files in this repository are licensed
// under the Apache License Version 2.0.
// This product includes software developed at Datadog (https://www.datadoghq.com/).
// Copyright 2026-Present Datadog, Inc.

package parser

import (
	"encoding/json"
	"testing"

	"github.com/aws/aws-lambda-go/events"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

func TestEventBridge(t *testing.T) {
	t.Parallel()

	type want struct {
		contentType ContentType
		bucket      string
		key         string
		encodedKey  string
		err         bool
	}

	tests := map[string]struct {
		event json.RawMessage
		want  want
	}{
		"s3 object created": {
			event: json.RawMessage(`{"version":"0","detail-type":"Object Created","source":"aws.s3","detail":{"bucket":{"name":"my-bucket"},"object":{"key":"my-key"}}}`),
			want: want{
				contentType: ContentTypeS3,
				bucket:      "my-bucket",
				key:         "my-key",
				encodedKey:  "my-key",
			},
		},
		"s3 object created via put": {
			event: json.RawMessage(`{"version":"0","detail-type":"Object Created: Put","source":"aws.s3","detail":{"bucket":{"name":"b"},"object":{"key":"nested/path/log.gz"}}}`),
			want: want{
				contentType: ContentTypeS3,
				bucket:      "b",
				key:         "nested/path/log.gz",
				encodedKey:  "nested%2Fpath%2Flog.gz",
			},
		},
		"s3 key with plus": {
			event: json.RawMessage(`{"version":"0","detail-type":"Object Created","source":"aws.s3","detail":{"bucket":{"name":"b"},"object":{"key":"logs/a+b.log"}}}`),
			want: want{
				contentType: ContentTypeS3,
				bucket:      "b",
				key:         "logs/a+b.log",
				encodedKey:  "logs%2Fa%2Bb.log",
			},
		},
		"s3 key with percent": {
			event: json.RawMessage(`{"version":"0","detail-type":"Object Created","source":"aws.s3","detail":{"bucket":{"name":"b"},"object":{"key":"logs/100%.log"}}}`),
			want: want{
				contentType: ContentTypeS3,
				bucket:      "b",
				key:         "logs/100%.log",
				encodedKey:  "logs%2F100%25.log",
			},
		},
		"s3 key with space": {
			event: json.RawMessage(`{"version":"0","detail-type":"Object Created","source":"aws.s3","detail":{"bucket":{"name":"b"},"object":{"key":"logs/my file.log"}}}`),
			want: want{
				contentType: ContentTypeS3,
				bucket:      "b",
				key:         "logs/my file.log",
				encodedKey:  "logs%2Fmy+file.log",
			},
		},
		"s3 object deleted stays eventbridge": {
			event: json.RawMessage(`{"version":"0","detail-type":"Object Deleted","source":"aws.s3","detail":{}}`),
			want:  want{contentType: ContentTypeEventBridge},
		},
		"non s3 source stays eventbridge": {
			event: json.RawMessage(`{"version":"0","detail-type":"Object Created","source":"aws.ec2","detail":{"instance-id":"i-123"}}`),
			want:  want{contentType: ContentTypeEventBridge},
		},
		"generic event stays eventbridge": {
			event: json.RawMessage(`{"version":"0","id":"abc","detail-type":"Scheduled Event","source":"aws.events","detail":{}}`),
			want:  want{contentType: ContentTypeEventBridge},
		},
		"s3 with malformed detail": {
			event: json.RawMessage(`{"version":"0","detail-type":"Object Created","source":"aws.s3","detail":"not-an-object"}`),
			want:  want{err: true},
		},
	}

	for name, tc := range tests {
		t.Run(name, func(t *testing.T) {
			t.Parallel()

			got, err := eventBridge(tc.event)

			if tc.want.err {
				require.Error(t, err)
				return
			}

			require.NoError(t, err)
			require.Equal(t, tc.want.contentType, got.ContentType)

			if tc.want.contentType != ContentTypeS3 {
				assert.JSONEq(t, string(tc.event), string(got.Payload))
				return
			}

			var s3Event events.S3Event
			require.NoError(t, json.Unmarshal(got.Payload, &s3Event))
			require.Len(t, s3Event.Records, 1)

			record := s3Event.Records[0]
			assert.Equal(t, eventSourceS3, record.EventSource)
			assert.Equal(t, tc.want.bucket, record.S3.Bucket.Name)
			assert.Equal(t, tc.want.encodedKey, record.S3.Object.Key)
			assert.Equal(t, tc.want.key, record.S3.Object.URLDecodedKey)
		})
	}
}
