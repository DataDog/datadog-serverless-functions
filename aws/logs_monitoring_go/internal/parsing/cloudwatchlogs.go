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

	"github.com/DataDog/datadog-serverless-functions/aws/logs_monitoring_go/internal/concurrent"
	"github.com/DataDog/datadog-serverless-functions/aws/logs_monitoring_go/internal/config"
	"github.com/DataDog/datadog-serverless-functions/aws/logs_monitoring_go/internal/model"
	"github.com/aws/aws-lambda-go/events"
	"github.com/aws/aws-lambda-go/lambdacontext"
)

func HandleCloudwatchLogs(ctx context.Context, event json.RawMessage, cfg *config.Config, out chan<- model.CloudwatchLogEntry) error {
	logEntries, err := parseCloudwatchLogs(ctx, event, cfg)
	if err != nil {
		slog.Error("failed parse cloudwatch logs", slog.Any("error", err))
	}

	for _, logEntry := range logEntries {
		if err := concurrent.SafeSender(ctx, out, logEntry); err != nil {
			return err
		}
	}

	return nil
}

func parseCloudwatchLogs(ctx context.Context, event json.RawMessage, cfg *config.Config) ([]model.CloudwatchLogEntry, error) {
	var cwEvent events.CloudwatchLogsEvent
	if err := json.Unmarshal(event, &cwEvent); err != nil {
		return nil, fmt.Errorf("unmarshal: %w", err)
	}

	data, err := cwEvent.AWSLogs.Parse()
	if err != nil {
		return nil, fmt.Errorf("parse: %w", err)
	}

	if data.MessageType == "CONTROL_MESSAGE" {
		return nil, nil
	}

	source := getCloudwatchSource(cfg.Source, data.LogGroup, data.LogStream)
	metadata := getCloudwatchMetadata(ctx, data)
	host := getCloudwatchHost(cfg.Host, data.LogGroup)
	tags, service := getTagsAndService(*cfg)
	if service == "" {
		service = source
	}

	var entries []model.CloudwatchLogEntry
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
		entries = append(entries, entry)
	}

	return entries, nil
}

func getCloudwatchSource(sourceOverride, logGroup, logStream string) string {
	if sourceOverride != "" {
		return sourceOverride
	}

	if strings.HasPrefix(logStream, "states/") {
		return "stepfunction"
	}

	var source string
	if strings.Contains(logStream, "_CloudTrail_") {
		source = "cloudtrail"
	} else {
		source = getSourceFromLogGroup(strings.ToLower(logGroup))
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
		slog.Warn("failed to load lambda context, this should not happen in production. The code is either not running from AWS Lambda or context is broken.")
	}

	return metadata
}

func getCloudwatchHost(hostOverride, logGroup string) string {
	if hostOverride != "" {
		return hostOverride
	}

	return logGroup
}
