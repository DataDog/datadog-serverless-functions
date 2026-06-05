// Unless explicitly stated otherwise all files in this repository are licensed
// under the Apache License Version 2.0.
// This product includes software developed at Datadog (https://www.datadoghq.com/).
// Copyright 2026-Present Datadog, Inc.

package testutil

import (
	"bytes"
	"compress/gzip"
	"context"
	"encoding/base64"
	"encoding/json"
	"regexp"
	"testing"

	"github.com/DataDog/datadog-serverless-functions/aws/logs_monitoring_go/internal/config"
	"github.com/DataDog/datadog-serverless-functions/aws/logs_monitoring_go/internal/model"
	"github.com/aws/aws-lambda-go/events"
	"github.com/aws/aws-lambda-go/lambdacontext"
)

const ARN = "arn:aws:lambda:us-east-1:123456789012:function:forwarder"

func LambdaContext(t *testing.T) context.Context {
	t.Helper()
	return lambdacontext.NewContext(t.Context(), &lambdacontext.LambdaContext{
		InvokedFunctionArn: ARN,
	})
}

func LambdaOrigin() model.LambdaOrigin {
	return model.LambdaOrigin{ARN: ARN}
}

func EmptyConfig() *config.Config {
	return &config.Config{}
}

type ConfigOption func(t *testing.T, cfg *config.Config)

func Config(t *testing.T, opts ...ConfigOption) *config.Config {
	t.Helper()
	cfg := EmptyConfig()
	for _, opt := range opts {
		opt(t, cfg)
	}
	return cfg
}

func WithMultilineRegex(pattern string) ConfigOption {
	return func(t *testing.T, cfg *config.Config) {
		t.Helper()
		cfg.S3MultilineLogRegex = regexp.MustCompile(pattern)
	}
}

func WithTags(tags ...string) ConfigOption {
	return func(_ *testing.T, cfg *config.Config) {
		cfg.Tags = tags
	}
}

func MustGzip(t *testing.T, data []byte) []byte {
	t.Helper()

	var buf bytes.Buffer
	w := gzip.NewWriter(&buf)
	if _, err := w.Write(data); err != nil {
		t.Fatalf("gzip write: %v", err)
	}
	if err := w.Close(); err != nil {
		t.Fatalf("gzip close: %v", err)
	}
	return buf.Bytes()
}

func MustGzipJSON(t *testing.T, v any) []byte {
	t.Helper()

	raw, err := json.Marshal(v)
	if err != nil {
		t.Fatalf("marshal: %v", err)
	}
	return MustGzip(t, raw)
}

func MustCloudwatchEvent(t *testing.T, data []byte) json.RawMessage {
	t.Helper()

	evt := events.CloudwatchLogsEvent{
		AWSLogs: events.CloudwatchLogsRawData{
			Data: base64.StdEncoding.EncodeToString(data),
		},
	}

	raw, err := json.Marshal(evt)
	if err != nil {
		t.Fatalf("marshal cloudwatch event: %v", err)
	}
	return raw
}

func MustKinesisEvent(t *testing.T, records ...[]byte) json.RawMessage {
	t.Helper()

	var evt events.KinesisEvent
	for _, data := range records {
		evt.Records = append(evt.Records, events.KinesisEventRecord{
			Kinesis: events.KinesisRecord{
				Data: data,
			},
		})
	}

	raw, err := json.Marshal(evt)
	if err != nil {
		t.Fatalf("marshal kinesis event: %v", err)
	}
	return raw
}
