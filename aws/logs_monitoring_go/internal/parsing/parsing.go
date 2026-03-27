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

type invokationSource int

const (
	invokationSourceUnknown invokationSource = iota
	invokationSourceCloudWatch
)

// Parse detects the invokation source and sends parsed log entries to the out channel.
// Errors are logged and skipped, unless the lambda timeout is reached.
func Parse(ctx context.Context, event json.RawMessage, cfg *config.Config, out chan<- model.LogEntry) {
	switch detectInvokationSource(event) {
	case invokationSourceCloudWatch:
		parseCloudWatch(ctx, event, cfg, out)
	default:
		slog.Error("unsupported invokation source")
	}
}

// detectInvokationSource inspects the raw JSON to determine the invokation type.
func detectInvokationSource(event json.RawMessage) invokationSource {
	var probe struct {
		AWSLogs *json.RawMessage `json:"awslogs"`
	}

	if err := json.Unmarshal(event, &probe); err != nil {
		slog.Error("failed unmarshal", slog.Any("error", err))
		return invokationSourceUnknown
	}

	if probe.AWSLogs != nil {
		return invokationSourceCloudWatch
	}

	return invokationSourceUnknown
}

func parseCloudWatch(ctx context.Context, event json.RawMessage, cfg *config.Config, out chan<- model.LogEntry) {

}
