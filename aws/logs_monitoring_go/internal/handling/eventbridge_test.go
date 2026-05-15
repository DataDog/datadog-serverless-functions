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
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

func TestEventBridgeHandler_Handle(t *testing.T) {
	t.Parallel()

	ctx := testutil.LambdaContext(t)

	tests := map[string]struct {
		event   json.RawMessage
		cfg     *config.Config
		want    []model.LogEntry
		wantErr bool
		jsonEq  bool
	}{
		"scheduled event": {
			event: json.RawMessage(`{"version":"0","id":"abc","detail-type":"Scheduled Event","source":"aws.events","account":"123456789012","time":"1970-01-01T00:00:00Z","region":"us-east-1","resources":[],"detail":{}}`),
			cfg:   testutil.EmptyConfig(),
			want: []model.LogEntry{
				{
					Message:        `{"version":"0","id":"abc","detail-type":"Scheduled Event","source":"aws.events","account":"123456789012","time":"1970-01-01T00:00:00Z","region":"us-east-1","resources":[],"detail":{}}`,
					Source:         "events",
					SourceCategory: "aws",
					Service:        "events",
					Metadata:       testutil.LambdaOrigin(),
				},
			},
		},
		"ec2 event": {
			event: json.RawMessage(`{"version":"0","id":"abc","detail-type":"EC2 Instance State-change Notification","source":"aws.ec2","account":"123456789012","time":"1970-01-01T00:00:00Z","region":"us-east-1","resources":[],"detail":{"instance-id":"i-123","state":"running"}}`),
			cfg:   testutil.EmptyConfig(),
			want: []model.LogEntry{
				{
					Message:        `{"version":"0","id":"abc","detail-type":"EC2 Instance State-change Notification","source":"aws.ec2","account":"123456789012","time":"1970-01-01T00:00:00Z","region":"us-east-1","resources":[],"detail":{"instance-id":"i-123","state":"running"}}`,
					Source:         "ec2",
					SourceCategory: "aws",
					Service:        "ec2",
					Metadata:       testutil.LambdaOrigin(),
				},
			},
		},
		"custom source override": {
			event: json.RawMessage(`{"version":"0","id":"abc","detail-type":"Scheduled Event","source":"aws.events","account":"123456789012","time":"1970-01-01T00:00:00Z","region":"us-east-1","resources":[],"detail":{}}`),
			cfg:   &config.Config{Source: "custom-source"},
			want: []model.LogEntry{
				{
					Message:        `{"version":"0","id":"abc","detail-type":"Scheduled Event","source":"aws.events","account":"123456789012","time":"1970-01-01T00:00:00Z","region":"us-east-1","resources":[],"detail":{}}`,
					Source:         "custom-source",
					SourceCategory: "aws",
					Service:        "custom-source",
					Metadata:       testutil.LambdaOrigin(),
				},
			},
		},
		"invalid JSON": {
			event:   json.RawMessage(`not json`),
			cfg:     testutil.EmptyConfig(),
			wantErr: true,
		},
		"securityhub one finding": {
			event:  json.RawMessage(`{"source":"aws.securityhub","detail-type":"Security Hub Findings - Imported","detail":{"findings":[{"myattribute":"somevalue","Resources":[{"Region":"us-east-1","Type":"AwsEc2SecurityGroup"}]}]}}`),
			cfg:    testutil.EmptyConfig(),
			jsonEq: true,
			want: []model.LogEntry{
				{
					Message:        `{"source":"aws.securityhub","detail-type":"Security Hub Findings - Imported","detail":{"finding":{"myattribute":"somevalue","resources":{"AwsEc2SecurityGroup":{"Region":"us-east-1"}}}}}`,
					Source:         sourceSecurityHub,
					SourceCategory: "aws",
					Service:        sourceSecurityHub,
					Metadata:       testutil.LambdaOrigin(),
				},
			},
		},
		"securityhub multiple findings": {
			event:  json.RawMessage(`{"source":"aws.securityhub","detail":{"findings":[{"id":"f1","Resources":[{"Type":"AwsEc2SecurityGroup","Region":"us-east-1"}]},{"id":"f2","Resources":[{"Type":"AwsIamRole","Region":"us-west-2"}]}]}}`),
			cfg:    testutil.EmptyConfig(),
			jsonEq: true,
			want: []model.LogEntry{
				{
					Message:        `{"source":"aws.securityhub","detail":{"finding":{"id":"f1","resources":{"AwsEc2SecurityGroup":{"Region":"us-east-1"}}}}}`,
					Source:         sourceSecurityHub,
					SourceCategory: "aws",
					Service:        sourceSecurityHub,
					Metadata:       testutil.LambdaOrigin(),
				},
				{
					Message:        `{"source":"aws.securityhub","detail":{"finding":{"id":"f2","resources":{"AwsIamRole":{"Region":"us-west-2"}}}}}`,
					Source:         sourceSecurityHub,
					SourceCategory: "aws",
					Service:        sourceSecurityHub,
					Metadata:       testutil.LambdaOrigin(),
				},
			},
		},
		"securityhub no findings falls back": {
			event: json.RawMessage(`{"source":"aws.securityhub","detail":{}}`),
			cfg:   testutil.EmptyConfig(),
			want: []model.LogEntry{
				{
					Message:        `{"source":"aws.securityhub","detail":{}}`,
					Source:         sourceSecurityHub,
					SourceCategory: "aws",
					Service:        sourceSecurityHub,
					Metadata:       testutil.LambdaOrigin(),
				},
			},
		},
		"securityhub with filtering": {
			event:  json.RawMessage(`{"source":"aws.securityhub","detail":{"findings":[{"id":"keep","Resources":[]},{"id":"drop","Resources":[]}]}}`),
			cfg:    testutil.Config(t, testutil.WithExcludeFilter(`"id":"drop"`)),
			jsonEq: true,
			want: []model.LogEntry{
				{
					Message:        `{"source":"aws.securityhub","detail":{"finding":{"id":"keep","resources":{}}}}`,
					Source:         sourceSecurityHub,
					SourceCategory: "aws",
					Service:        sourceSecurityHub,
					Metadata:       testutil.LambdaOrigin(),
				},
			},
		},
	}

	for name, tc := range tests {
		t.Run(name, func(t *testing.T) {
			t.Parallel()

			handler := NewEventBridge(tc.cfg)
			out := make(chan model.LogEntry, 10)

			err := handler.Handle(ctx, tc.event, out)
			close(out)

			if tc.wantErr {
				require.Error(t, err)
				return
			}

			require.NoError(t, err)

			var got []model.LogEntry
			for entry := range out {
				got = append(got, entry)
			}

			require.Len(t, got, len(tc.want))
			for i := range tc.want {
				if tc.jsonEq {
					assert.JSONEq(t, tc.want[i].Message, got[i].Message)
					// Compare non-message fields
					tc.want[i].Message = got[i].Message
				}
				assert.Equal(t, tc.want[i], got[i])
			}
		})
	}
}
