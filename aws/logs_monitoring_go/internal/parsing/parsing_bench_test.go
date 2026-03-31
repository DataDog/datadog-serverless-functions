// Unless explicitly stated otherwise all files in this repository are licensed
// under the Apache License Version 2.0.
// This product includes software developed at Datadog (https://www.datadoghq.com/).
// Copyright 2026-Present Datadog, Inc.

package parsing

import (
	"bytes"
	"encoding/json"
	"fmt"
	"strings"
	"testing"
)

func detectInvocationSourceProbe(event json.RawMessage) invocationSource {
	var probe struct {
		AWSLogs *json.RawMessage `json:"awslogs"`
		Records []struct {
			EventSource string `json:"eventSource"`
		} `json:"Records"`
	}
	json.Unmarshal(event, &probe)
	if probe.AWSLogs != nil {
		return invocationSourceCloudwatchLogs
	}
	if len(probe.Records) > 0 {
		switch probe.Records[0].EventSource {
		case "aws:s3":
			return invocationSourceS3
		case "aws:sns":
			return invocationSourceSNS
		case "aws:sqs":
			return invocationSourceSQS
		case "aws:kinesis":
			return invocationSourceKinesis
		}
	}
	return invocationSourceUnknown
}

var detectInvocationSourceDecoder = detectInvocationSource

func makeLargeS3Event(nRecords int) json.RawMessage {
	var buf bytes.Buffer
	buf.WriteString(`{"Records":[`)
	for i := range nRecords {
		if i > 0 {
			buf.WriteByte(',')
		}
		fmt.Fprintf(&buf, `{"eventSource":"aws:s3","s3":{"bucket":{"name":"bucket-%d"},"object":{"key":"%s"}}}`, i, strings.Repeat("x", 200))
	}
	buf.WriteString(`]}`)
	return json.RawMessage(buf.Bytes())
}

func makeS3EventSourceLast(nRecords int) json.RawMessage {
	var buf bytes.Buffer
	buf.WriteString(`{"Records":[`)
	for i := range nRecords {
		if i > 0 {
			buf.WriteByte(',')
		}
		fmt.Fprintf(&buf, `{"s3":{"bucket":{"name":"bucket-%d"},"object":{"key":"%s"}},"eventSource":"aws:s3"}`, i, strings.Repeat("x", 200))
	}
	buf.WriteString(`]}`)
	return json.RawMessage(buf.Bytes())
}

var smallCWEvent = json.RawMessage(`{"awslogs":{"data":"dGVzdA=="}}`)
var largeS3Event = makeLargeS3Event(500)
var largeS3EventSourceLast = makeS3EventSourceLast(500)

var benchCases = []struct {
	name  string
	event json.RawMessage
}{
	{"SmallCW", smallCWEvent},
	{"LargeS3", largeS3Event},
	{"LargeS3_SourceLast", largeS3EventSourceLast},
}

func BenchmarkDetect(b *testing.B) {
	for _, tc := range benchCases {
		b.Run("Probe/"+tc.name, func(b *testing.B) {
			for b.Loop() {
				detectInvocationSourceProbe(tc.event)
			}
		})
		b.Run("Decoder/"+tc.name, func(b *testing.B) {
			for b.Loop() {
				detectInvocationSourceDecoder(tc.event)
			}
		})
	}
}
