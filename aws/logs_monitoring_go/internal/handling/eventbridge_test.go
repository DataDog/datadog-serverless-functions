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

func TestEventBridgeHandler_Handle(t *testing.T) {
	t.Parallel()

	ctx := testutil.LambdaContext(t)

	tests := map[string]struct {
		event   json.RawMessage
		cfg     *config.Config
		want    []model.LogEntry
		wantErr bool
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
	}

	for name, tc := range tests {
		t.Run(name, func(t *testing.T) {
			t.Parallel()

			handler := NewEventBridge(tc.cfg)
			out := make(chan model.LogEntry, len(tc.want))

			err := handler.Handle(ctx, tc.event, out)
			close(out)

			if tc.wantErr {
				if err == nil {
					t.Fatal("expected error, got nil")
				}
				return
			}

			if err != nil {
				t.Fatalf("unexpected error: %v", err)
			}

			var got []model.LogEntry
			for entry := range out {
				got = append(got, entry)
			}

			if diff := cmp.Diff(tc.want, got); diff != "" {
				t.Errorf("entries mismatch (-want +got):\n%s", diff)
			}
		})
	}
}

func TestEventBridgeSource(t *testing.T) {
	t.Parallel()

	tests := map[string]struct {
		source string
		want   string
	}{
		"aws.events":   {source: "aws.events", want: "events"},
		"aws.ec2":      {source: "aws.ec2", want: "ec2"},
		"aws.s3":       {source: "aws.s3", want: "s3"},
		"custom.app":   {source: "custom.app", want: "app"},
		"no dot":       {source: "nodot", want: "cloudwatch"},
		"empty string": {source: "", want: "cloudwatch"},
	}

	for name, tc := range tests {
		t.Run(name, func(t *testing.T) {
			t.Parallel()
			got := eventBridgeSource(tc.source)
			if got != tc.want {
				t.Errorf("got %q, want %q", got, tc.want)
			}
		})
	}
}
