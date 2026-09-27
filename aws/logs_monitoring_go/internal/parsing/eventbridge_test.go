// Unless explicitly stated otherwise all files in this repository are licensed
// under the Apache License Version 2.0.
// This product includes software developed at Datadog (https://www.datadoghq.com/).
// Copyright 2026-Present Datadog, Inc.

package parsing

import (
	"encoding/json"
	"testing"

	"github.com/aws/aws-lambda-go/events"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

func TestEventBridge(t *testing.T) {
	t.Parallel()

	tests := map[string]struct {
		event      json.RawMessage
		want       ContentType
		wantBucket string
		wantKey    string
		wantErr    bool
	}{
		"s3 object created": {
			event:      json.RawMessage(`{"version":"0","detail-type":"Object Created","source":"aws.s3","detail":{"bucket":{"name":"my-bucket"},"object":{"key":"my-key"}}}`),
			want:       ContentTypeS3,
			wantBucket: "my-bucket",
			wantKey:    "my-key",
		},
		"s3 object created via put": {
			event:      json.RawMessage(`{"version":"0","detail-type":"Object Created: Put","source":"aws.s3","detail":{"bucket":{"name":"b"},"object":{"key":"nested/path/log.gz"}}}`),
			want:       ContentTypeS3,
			wantBucket: "b",
			wantKey:    "nested/path/log.gz",
		},
		"s3 object deleted stays eventbridge": {
			event: json.RawMessage(`{"version":"0","detail-type":"Object Deleted","source":"aws.s3","detail":{}}`),
			want:  ContentTypeEventBridge,
		},
		"non s3 source stays eventbridge": {
			event: json.RawMessage(`{"version":"0","detail-type":"Object Created","source":"aws.ec2","detail":{"instance-id":"i-123"}}`),
			want:  ContentTypeEventBridge,
		},
		"generic event stays eventbridge": {
			event: json.RawMessage(`{"version":"0","id":"abc","detail-type":"Scheduled Event","source":"aws.events","detail":{}}`),
			want:  ContentTypeEventBridge,
		},
		"s3 with malformed detail": {
			event:   json.RawMessage(`{"version":"0","detail-type":"Object Created","source":"aws.s3","detail":"not-an-object"}`),
			wantErr: true,
		},
	}

	for name, tc := range tests {
		t.Run(name, func(t *testing.T) {
			t.Parallel()

			got, err := eventBridge(tc.event)

			if tc.wantErr {
				require.Error(t, err)
				return
			}

			require.NoError(t, err)
			require.Equal(t, tc.want, got.ContentType)

			if tc.want != ContentTypeS3 {
				assert.JSONEq(t, string(tc.event), string(got.Payload))
				return
			}

			var s3Event events.S3Event
			require.NoError(t, json.Unmarshal(got.Payload, &s3Event))
			require.Len(t, s3Event.Records, 1)

			record := s3Event.Records[0]
			assert.Equal(t, eventSourceS3, record.EventSource)
			assert.Equal(t, tc.wantBucket, record.S3.Bucket.Name)
			assert.Equal(t, tc.wantKey, record.S3.Object.Key)
			assert.Equal(t, tc.wantKey, record.S3.Object.URLDecodedKey)
		})
	}
}
