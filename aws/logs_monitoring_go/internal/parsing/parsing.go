// Unless explicitly stated otherwise all files in this repository are licensed
// under the Apache License Version 2.0.
// This product includes software developed at Datadog (https://www.datadoghq.com/).
// Copyright 2026-Present Datadog, Inc.

package parsing

import (
	"bytes"
	"context"
	"encoding/json"
	"log/slog"

	"github.com/DataDog/datadog-serverless-functions/aws/logs_monitoring_go/internal/config"
	"github.com/DataDog/datadog-serverless-functions/aws/logs_monitoring_go/internal/model"
)

type invocationSource int

const (
	invocationSourceUnknown invocationSource = iota
	invocationSourceCloudwatchLogs
	invocationSourceS3
	invocationSourceSNS
	invocationSourceSQS
	invocationSourceKinesis
)

func Parse(ctx context.Context, event json.RawMessage, cfg *config.Config, out chan<- model.LogEntry) {
	switch detectInvocationSource(event) {
	case invocationSourceCloudwatchLogs:
		parseCloudwatchLogs(ctx, event, cfg, out)
	default:
		slog.Error("unsupported invocation source", slog.String("event", string(event)))
	}
}

func detectInvocationSource(event json.RawMessage) invocationSource {
	dec := json.NewDecoder(bytes.NewReader(event))

	t, err := dec.Token()
	if err != nil || t != json.Delim('{') {
		return invocationSourceUnknown
	}

	key, err := dec.Token()
	if err != nil {
		return invocationSourceUnknown
	}
	if key == "awslogs" {
		return invocationSourceCloudwatchLogs
	}

	if key == "Records" {
		return detectFromRecords(dec)
	}

	return invocationSourceUnknown
}

func detectFromRecords(dec *json.Decoder) invocationSource {
	t, err := dec.Token()
	if err != nil || t != json.Delim('[') {
		return invocationSourceUnknown
	}

	t, err = dec.Token()
	if err != nil || t != json.Delim('{') {
		return invocationSourceUnknown
	}

	for dec.More() {
		key, err := dec.Token()
		if err != nil {
			return invocationSourceUnknown
		}
		if key == "eventSource" {
			val, err := dec.Token()
			if err != nil {
				return invocationSourceUnknown
			}
			switch val {
			case "aws:s3":
				return invocationSourceS3
			case "aws:sns":
				return invocationSourceSNS
			case "aws:sqs":
				return invocationSourceSQS
			case "aws:kinesis":
				return invocationSourceKinesis
			default:
				return invocationSourceUnknown
			}
		}
		var skip json.RawMessage
		if err := dec.Decode(&skip); err != nil {
			return invocationSourceUnknown
		}
	}

	return invocationSourceUnknown
}

func parseCloudwatchLogs(ctx context.Context, event json.RawMessage, cfg *config.Config, out chan<- model.LogEntry) {

}
