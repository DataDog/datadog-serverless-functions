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
	"fmt"
	"regexp"
	"strings"
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
			EventSource: "aws:kinesis",
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

func GenerateJSONLog(t *testing.T, size int) json.RawMessage {
	t.Helper()

	const template = `{"id":"0","timestamp":1718540400000,"message":"%s","ddsourcecategory":"aws"}`
	overhead := len(fmt.Sprintf(template, ""))

	padding := size - overhead
	if padding < 0 {
		t.Fatalf("GenerateJSONLog: requested size %d is smaller than the fixed overhead %d", size, overhead)
	}

	return json.RawMessage(fmt.Sprintf(template, strings.Repeat("x", padding)))
}

func GenerateJSONLogs(t *testing.T, sizes ...int) json.RawMessage {
	t.Helper()

	logs := make([]json.RawMessage, 0, len(sizes))
	for _, size := range sizes {
		logs = append(logs, GenerateJSONLog(t, size))
	}

	data, err := json.Marshal(logs)
	if err != nil {
		t.Fatalf("GenerateJSONLogs: marshal: %v", err)
	}
	return data
}

func ToChannel[T any](t *testing.T, values []T) chan T {
	t.Helper()

	ch := make(chan T, len(values))
	for _, v := range values {
		ch <- v
	}
	close(ch)

	return ch
}

func Drain[T any](t *testing.T, ch <-chan T) (values []T) {
	t.Helper()

	for v := range ch {
		values = append(values, v)
	}

	return values
}
