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

const benchS3Records = 500

var (
	smallCWEvent        = json.RawMessage(`{"awslogs":{"data":"dGVzdA=="}}`)
	largeS3EventFirst   = makeS3EventSourceFirst(benchS3Records)
	largeS3EventLast    = makeS3EventSourceLast(benchS3Records)
)

var benchCases = []struct {
	name  string
	event json.RawMessage
}{
	{"SmallCW", smallCWEvent},
	{"LargeS3_SourceFirst", largeS3EventFirst},
	{"LargeS3_SourceLast", largeS3EventLast},
}

func BenchmarkDetectInvocationSource(b *testing.B) {
	for _, tc := range benchCases {
		b.Run(tc.name, func(b *testing.B) {
			for b.Loop() {
				DetectInvocationSource(tc.event)
			}
		})
	}
}

func makeS3EventSourceFirst(nRecords int) json.RawMessage {
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
