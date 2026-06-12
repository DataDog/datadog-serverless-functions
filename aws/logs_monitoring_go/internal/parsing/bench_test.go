// Unless explicitly stated otherwise all files in this repository are licensed
// under the Apache License Version 2.0.
// This product includes software developed at Datadog (https://www.datadoghq.com/).
// Copyright 2026-Present Datadog, Inc.

package parsing

import (
	"encoding/json"
	"testing"
)

var (
	benchCloudWatch = json.RawMessage(`{"awslogs":{"data":"dGVzdA=="}}`)
	benchS3         = json.RawMessage(`{"Records":[{"eventSource":"aws:s3","s3":{"bucket":{"name":"b"},"object":{"key":"k"}}}]}`)
	benchSNSS3      = json.RawMessage(`{"Records":[{"EventSource":"aws:sns","Sns":{"Type":"Notification","Message":"{\"Records\":[{\"s3\":{\"bucket\":{\"name\":\"b\"},\"object\":{\"key\":\"k\"}}}]}"}}]}`)
	benchSQSS3 = json.RawMessage(`{"Records":[` +
		`{"eventSource":"aws:sqs","body":"{\"Records\":[{\"s3\":{\"bucket\":{\"name\":\"b1\"},\"object\":{\"key\":\"k1\"}}}]}"},` +
		`{"eventSource":"aws:sqs","body":"{\"Records\":[{\"s3\":{\"bucket\":{\"name\":\"b2\"},\"object\":{\"key\":\"k2\"}}}]}"},` +
		`{"eventSource":"aws:sqs","body":"{\"Records\":[{\"s3\":{\"bucket\":{\"name\":\"b3\"},\"object\":{\"key\":\"k3\"}}}]}"},` +
		`{"eventSource":"aws:sqs","body":"{\"Records\":[{\"s3\":{\"bucket\":{\"name\":\"b4\"},\"object\":{\"key\":\"k4\"}}}]}"},` +
		`{"eventSource":"aws:sqs","body":"{\"Records\":[{\"s3\":{\"bucket\":{\"name\":\"b5\"},\"object\":{\"key\":\"k5\"}}}]}"},` +
		`{"eventSource":"aws:sqs","body":"{\"Records\":[{\"s3\":{\"bucket\":{\"name\":\"b6\"},\"object\":{\"key\":\"k6\"}}}]}"},` +
		`{"eventSource":"aws:sqs","body":"{\"Records\":[{\"s3\":{\"bucket\":{\"name\":\"b7\"},\"object\":{\"key\":\"k7\"}}}]}"},` +
		`{"eventSource":"aws:sqs","body":"{\"Records\":[{\"s3\":{\"bucket\":{\"name\":\"b8\"},\"object\":{\"key\":\"k8\"}}}]}"},` +
		`{"eventSource":"aws:sqs","body":"{\"Records\":[{\"s3\":{\"bucket\":{\"name\":\"b9\"},\"object\":{\"key\":\"k9\"}}}]}"},` +
		`{"eventSource":"aws:sqs","body":"{\"Records\":[{\"s3\":{\"bucket\":{\"name\":\"b10\"},\"object\":{\"key\":\"k10\"}}}]}"}` +
		`]}`)
	benchSQSSNSS3 = json.RawMessage(`{"Records":[` +
		`{"eventSource":"aws:sqs","body":"{\"Type\":\"Notification\",\"Message\":\"{\\\"Records\\\":[{\\\"s3\\\":{\\\"bucket\\\":{\\\"name\\\":\\\"b1\\\"},\\\"object\\\":{\\\"key\\\":\\\"k1\\\"}}}]}\"}"},` +
		`{"eventSource":"aws:sqs","body":"{\"Type\":\"Notification\",\"Message\":\"{\\\"Records\\\":[{\\\"s3\\\":{\\\"bucket\\\":{\\\"name\\\":\\\"b2\\\"},\\\"object\\\":{\\\"key\\\":\\\"k2\\\"}}}]}\"}"},` +
		`{"eventSource":"aws:sqs","body":"{\"Type\":\"Notification\",\"Message\":\"{\\\"Records\\\":[{\\\"s3\\\":{\\\"bucket\\\":{\\\"name\\\":\\\"b3\\\"},\\\"object\\\":{\\\"key\\\":\\\"k3\\\"}}}]}\"}"},` +
		`{"eventSource":"aws:sqs","body":"{\"Type\":\"Notification\",\"Message\":\"{\\\"Records\\\":[{\\\"s3\\\":{\\\"bucket\\\":{\\\"name\\\":\\\"b4\\\"},\\\"object\\\":{\\\"key\\\":\\\"k4\\\"}}}]}\"}"},` +
		`{"eventSource":"aws:sqs","body":"{\"Type\":\"Notification\",\"Message\":\"{\\\"Records\\\":[{\\\"s3\\\":{\\\"bucket\\\":{\\\"name\\\":\\\"b5\\\"},\\\"object\\\":{\\\"key\\\":\\\"k5\\\"}}}]}\"}"},` +
		`{"eventSource":"aws:sqs","body":"{\"Type\":\"Notification\",\"Message\":\"{\\\"Records\\\":[{\\\"s3\\\":{\\\"bucket\\\":{\\\"name\\\":\\\"b6\\\"},\\\"object\\\":{\\\"key\\\":\\\"k6\\\"}}}]}\"}"},` +
		`{"eventSource":"aws:sqs","body":"{\"Type\":\"Notification\",\"Message\":\"{\\\"Records\\\":[{\\\"s3\\\":{\\\"bucket\\\":{\\\"name\\\":\\\"b7\\\"},\\\"object\\\":{\\\"key\\\":\\\"k7\\\"}}}]}\"}"},` +
		`{"eventSource":"aws:sqs","body":"{\"Type\":\"Notification\",\"Message\":\"{\\\"Records\\\":[{\\\"s3\\\":{\\\"bucket\\\":{\\\"name\\\":\\\"b8\\\"},\\\"object\\\":{\\\"key\\\":\\\"k8\\\"}}}]}\"}"},` +
		`{"eventSource":"aws:sqs","body":"{\"Type\":\"Notification\",\"Message\":\"{\\\"Records\\\":[{\\\"s3\\\":{\\\"bucket\\\":{\\\"name\\\":\\\"b9\\\"},\\\"object\\\":{\\\"key\\\":\\\"k9\\\"}}}]}\"}"},` +
		`{"eventSource":"aws:sqs","body":"{\"Type\":\"Notification\",\"Message\":\"{\\\"Records\\\":[{\\\"s3\\\":{\\\"bucket\\\":{\\\"name\\\":\\\"b10\\\"},\\\"object\\\":{\\\"key\\\":\\\"k10\\\"}}}]}\"}"}` +
		`]}`)
	benchEventBridge = json.RawMessage(`{"version":"0","detail-type":"Object Created","source":"aws.s3","detail":{"bucket":{"name":"my-bucket"},"object":{"key":"my-key"}}}`)
)

func BenchmarkParse_Decoder_CloudWatch(b *testing.B) {
	b.ReportAllocs()
	for b.Loop() {
		_, _ = Parse(benchCloudWatch)
	}
}

func BenchmarkParse_Unmarshal_CloudWatch(b *testing.B) {
	b.ReportAllocs()
	for b.Loop() {
		_, _ = ParseUnmarshal(benchCloudWatch)
	}
}

func BenchmarkParse_Decoder_S3(b *testing.B) {
	b.ReportAllocs()
	for b.Loop() {
		_, _ = Parse(benchS3)
	}
}

func BenchmarkParse_Unmarshal_S3(b *testing.B) {
	b.ReportAllocs()
	for b.Loop() {
		_, _ = ParseUnmarshal(benchS3)
	}
}

func BenchmarkParse_Decoder_SNS_S3(b *testing.B) {
	b.ReportAllocs()
	for b.Loop() {
		_, _ = Parse(benchSNSS3)
	}
}

func BenchmarkParse_Unmarshal_SNS_S3(b *testing.B) {
	b.ReportAllocs()
	for b.Loop() {
		_, _ = ParseUnmarshal(benchSNSS3)
	}
}

func BenchmarkParse_Decoder_SQS_S3(b *testing.B) {
	b.ReportAllocs()
	for b.Loop() {
		_, _ = Parse(benchSQSS3)
	}
}

func BenchmarkParse_Unmarshal_SQS_S3(b *testing.B) {
	b.ReportAllocs()
	for b.Loop() {
		_, _ = ParseUnmarshal(benchSQSS3)
	}
}

func BenchmarkParse_Decoder_SQS_SNS_S3(b *testing.B) {
	b.ReportAllocs()
	for b.Loop() {
		_, _ = Parse(benchSQSSNSS3)
	}
}

func BenchmarkParse_Unmarshal_SQS_SNS_S3(b *testing.B) {
	b.ReportAllocs()
	for b.Loop() {
		_, _ = ParseUnmarshal(benchSQSSNSS3)
	}
}

func BenchmarkParse_Decoder_EventBridge(b *testing.B) {
	b.ReportAllocs()
	for b.Loop() {
		_, _ = Parse(benchEventBridge)
	}
}

func BenchmarkParse_Unmarshal_EventBridge(b *testing.B) {
	b.ReportAllocs()
	for b.Loop() {
		_, _ = ParseUnmarshal(benchEventBridge)
	}
}
