// Unless explicitly stated otherwise all files in this repository are licensed
// under the Apache License Version 2.0.
// This product includes software developed at Datadog (https://www.datadoghq.com/).
// Copyright 2026-Present Datadog, Inc.

package parsing

import (
	"context"
	"encoding/json"
	"fmt"
	"strings"

	"github.com/DataDog/datadog-serverless-functions/aws/logs_monitoring_go/internal/concurrent"
	"github.com/DataDog/datadog-serverless-functions/aws/logs_monitoring_go/internal/config"
	"github.com/DataDog/datadog-serverless-functions/aws/logs_monitoring_go/internal/model"
	"github.com/aws/aws-lambda-go/events"
)

const sourceCategory = "aws"

func HandleCloudwatchLogs(ctx context.Context, event json.RawMessage, cfg *config.Config, out chan<- model.CloudwatchLogEntry) error {
	logEntries, err := parseCloudwatchLogs(ctx, event, cfg)
	if err != nil {
		return err
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

	metadata, err := getCloudwatchMetadata(ctx, data)
	if err != nil {
		return nil, fmt.Errorf("get cloudwatch metadata: %w", err)
	}
	source := getCloudwatchSource(cfg.Source, data.LogGroup, data.LogStream)
	host := getCloudwatchHost(cfg.Host, data.LogGroup)
	tags, service := getTagsAndService(cfg)
	if service == "" {
		service = source
	}

	var entries []model.CloudwatchLogEntry
	for _, le := range data.LogEvents {
		ddtags, ddtagsService, message := extractFromMessage(le.Message)
		entryService := service
		if ddtagsService != "" {
			entryService = ddtagsService
		}
		ddtags = append(ddtags, "service:"+entryService)

		entry := model.CloudwatchLogEntry{
			ID:             le.ID,
			Timestamp:      le.Timestamp,
			Message:        message,
			Source:         source,
			SourceCategory: sourceCategory,
			Service:        entryService,
			Host:           host,
			Tags:           append(ddtags, tags...),
			AWS:            metadata,
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

	if strings.Contains(logStream, "_CloudTrail_") {
		return "cloudtrail"
	}

	return getSourceFromLogGroup(strings.ToLower(logGroup))
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

func getCloudwatchMetadata(ctx context.Context, data events.CloudwatchLogsData) (model.CloudwatchMetadata, error) {
	metadata, err := model.GetMetadata(ctx)
	if err != nil {
		return model.CloudwatchMetadata{}, err
	}

	cwMetadata := model.CloudwatchMetadata{
		Metadata: metadata,
		Logs: model.CloudwatchLogsContext{
			LogGroup:  data.LogGroup,
			LogStream: data.LogStream,
			Owner:     data.Owner,
		},
	}

	return cwMetadata, nil
}

func getCloudwatchHost(hostOverride, logGroup string) string {
	if hostOverride != "" {
		return hostOverride
	}

	return logGroup
}
