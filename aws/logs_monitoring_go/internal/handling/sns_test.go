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

func TestSNSHandler_Handle(t *testing.T) {
	t.Parallel()

	ctx := testutil.LambdaContext(t)

	snsEvent := json.RawMessage(`{"EventSource":"aws:sns","Sns":{"Type":"Notification","Message":"hello world","TopicArn":"arn:aws:sns:us-east-1:123456789012:my-topic"}}`)

	tests := map[string]struct {
		event json.RawMessage
		cfg   *config.Config
		want  []model.LogEntry
	}{
		"basic event": {
			event: snsEvent,
			cfg:   testutil.EmptyConfig(),
			want: []model.LogEntry{
				{
					Message:        string(snsEvent),
					Source:         "sns",
					SourceCategory: "aws",
					Metadata:       testutil.LambdaOrigin(),
				},
			},
		},
		"custom source override": {
			event: snsEvent,
			cfg:   &config.Config{Source: "custom-source"},
			want: []model.LogEntry{
				{
					Message:        string(snsEvent),
					Source:         "custom-source",
					SourceCategory: "aws",
					Metadata:       testutil.LambdaOrigin(),
				},
			},
		},
		"custom service override": {
			event: snsEvent,
			cfg:   &config.Config{Service: "my-svc"},
			want: []model.LogEntry{
				{
					Message:        string(snsEvent),
					Source:         "sns",
					SourceCategory: "aws",
					Service:        "my-svc",
					Metadata:       testutil.LambdaOrigin(),
				},
			},
		},
	}

	for name, tc := range tests {
		t.Run(name, func(t *testing.T) {
			t.Parallel()

			handler := NewSNS(tc.cfg)
			out := make(chan model.LogEntry, len(tc.want))

			err := handler.Handle(ctx, tc.event, out)
			close(out)

			require.NoError(t, err)

			var got []model.LogEntry
			for entry := range out {
				got = append(got, entry)
			}

			assert.Equal(t, tc.want, got)
		})
	}
}
