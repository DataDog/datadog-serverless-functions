// Unless explicitly stated otherwise all files in this repository are licensed
// under the Apache License Version 2.0.
// This product includes software developed at Datadog (https://www.datadoghq.com/).
// Copyright 2026-Present Datadog, Inc.

package parsing

import (
	"context"
	"encoding/json"
	"log/slog"
	"strings"

	"github.com/DataDog/datadog-serverless-functions/aws/logs_monitoring_go/internal/config"
	"github.com/DataDog/datadog-serverless-functions/aws/logs_monitoring_go/internal/model"
	"github.com/aws/aws-lambda-go/events"
	"github.com/aws/aws-lambda-go/lambdacontext"
)

func parseCloudwatchLogs(ctx context.Context, event json.RawMessage, cfg *config.Config, out chan<- model.CloudwatchLogEntry) {
	var cwEvent events.CloudwatchLogsEvent
	if err := json.Unmarshal(event, &cwEvent); err != nil {
		slog.Error("failed to unmarshal cloudwatch event", slog.Any("error", err))
		return
	}

	data, err := cwEvent.AWSLogs.Parse()
	if err != nil {
		slog.Error("failed to decompress cloudwatch data", slog.Any("error", err))
		return
	}

	if data.MessageType == "CONTROL_MESSAGE" {
		return
	}

	source := getCloudwatchSource(cfg.Source, data.LogGroup, data.LogStream)
	metadata := getCloudwatchMetadata(ctx, data)
	host := getCloudwatchHost(cfg.Host, data.LogGroup)
	tags, service := getTagsAndService(*cfg)
	if service == "" {
		service = source
	}

	for _, le := range data.LogEvents {
		entry := model.CloudwatchLogEntry{
			ID:        le.ID,
			Timestamp: le.Timestamp,
			Message:   le.Message,
			Source:    source,
			Service:   service,
			Host:      host,
			Tags:      tags,
			AWS:       metadata,
		}

		select {
		case out <- entry:
		case <-ctx.Done():
			return
		}
	}
}

func getCloudwatchSource(sourceOverride, logGroup, logStream string) string {
	if sourceOverride != "" {
		return sourceOverride
	}

	var source string
	if strings.Contains(logStream, "_CloudTrail_") {
		source = "cloudtrail"
	} else {
		source = getSourceFromLogGroup(strings.ToLower(logGroup))
	}

	if strings.HasPrefix(logStream, "states/") {
		source = "stepfunction"
	}

	return source
}

func getSourceFromLogGroup(logGroupLower string) string {
	if strings.HasPrefix(logGroupLower, "_cloudtrail_") {
		return "cloudtrail"
	}
	if strings.HasPrefix(logGroupLower, "/aws/kinesis") {
		return "kinesis"
	}
	if strings.HasPrefix(logGroupLower, "/aws/lambda") {
		return "lambda"
	}
	if strings.HasPrefix(logGroupLower, "sns/") {
		return "sns"
	}
	if strings.Contains(logGroupLower, "cloudtrail") {
		return "cloudtrail"
	}
	return "cloudwatch"
}

func getCloudwatchMetadata(ctx context.Context, data events.CloudwatchLogsData) model.CloudwatchMetadata {
	metadata := model.CloudwatchMetadata{
		Logs: model.CloudwatchLogsContext{
			LogGroup:  data.LogGroup,
			LogStream: data.LogStream,
			Owner:     data.Owner,
		},
	}

	if lambdacontext.FunctionVersion != "$LATEST" {
		metadata.FunctionVersion = lambdacontext.FunctionVersion
	}

	if lc, ok := lambdacontext.FromContext(ctx); ok {
		metadata.InvokedFunctionARN = lc.InvokedFunctionArn
	} else {
		slog.Warn("failed lambda context loading")
	}

	return metadata
}

func getCloudwatchHost(hostOverride, logGroup string) string {
	if hostOverride != "" {
		return hostOverride
	}

	return logGroup
}
