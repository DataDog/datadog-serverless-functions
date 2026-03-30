// Unless explicitly stated otherwise all files in this repository are licensed
// under the Apache License Version 2.0.
// This product includes software developed at Datadog (https://www.datadoghq.com/).
// Copyright 2026-Present Datadog, Inc.

package parsing

import (
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
)

func Parse(ctx context.Context, event json.RawMessage, cfg *config.Config, out chan<- model.LogEntry) {
	switch detectInvocationSource(event) {
	case invocationSourceCloudwatchLogs:
		parseCloudwatchLogs(ctx, event, cfg, out)
	default:
		slog.Error("unsupported invocation source", slog.Any("event", event))
	}
}

func detectInvocationSource(event json.RawMessage) invocationSource {
	var probe struct {
		AWSLogs *json.RawMessage `json:"awslogs"`
	}

	if err := json.Unmarshal(event, &probe); err != nil {
		slog.Error("failed unmarshal", slog.Any("error", err))
		return invocationSourceUnknown
	}

	if probe.AWSLogs != nil {
		return invocationSourceCloudwatchLogs
	}

	return invocationSourceUnknown
}

func parseCloudwatchLogs(ctx context.Context, event json.RawMessage, cfg *config.Config, out chan<- model.LogEntry) {

}
