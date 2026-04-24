// Unless explicitly stated otherwise all files in this repository are licensed
// under the Apache License Version 2.0.
// This product includes software developed at Datadog (https://www.datadoghq.com/).
// Copyright 2026-Present Datadog, Inc.

package parsing

import (
	"cmp"
	"context"
	"encoding/json"
	"fmt"
	"slices"
	"strings"

	"github.com/DataDog/datadog-serverless-functions/aws/logs_monitoring_go/internal/concurrent"
	"github.com/DataDog/datadog-serverless-functions/aws/logs_monitoring_go/internal/config"
	"github.com/DataDog/datadog-serverless-functions/aws/logs_monitoring_go/internal/model"
	"github.com/aws/aws-lambda-go/events"
)

const (
	logGroupCloudtrail    = "_cloudtrail_"
	logGroupKinesis       = "/aws/kinesis"
	logGroupLambda        = "/aws/lambda"
	logGroupSNS           = "sns/"
	logStreamStepFunction = "states/"
	logStreamCloudtrail   = "_CloudTrail_"
)

type cloudwatchEntryBase struct {
	metadata model.CloudwatchMetadata
	source   string
	host     string
	service  string
	tags     model.Tags
}

func HandleCloudwatch(ctx context.Context, event json.RawMessage, cfg *config.Config, out chan<- model.CloudwatchLogEntry) error {
	var cwEvent events.CloudwatchLogsEvent
	if err := json.Unmarshal(event, &cwEvent); err != nil {
		return fmt.Errorf("unmarshal: %w", err)
	}

	cwData, err := cwEvent.AWSLogs.Parse()
	if err != nil {
		return fmt.Errorf("parse: %w", err)
	}

	if cwData.MessageType == "CONTROL_MESSAGE" {
		return nil
	}

	base, err := newCloudwatchEntryBase(ctx, cwData, cfg)
	if err != nil {
		return fmt.Errorf("create cloudwatch entry base: %w", err)
	}

	for _, event := range cwData.LogEvents {
		if err := concurrent.SafeSender(ctx, out, newCloudwatchLogEntry(base, event)); err != nil {
			return err
		}
	}

	return nil
}

func newCloudwatchEntryBase(ctx context.Context, data events.CloudwatchLogsData, cfg *config.Config) (cloudwatchEntryBase, error) {
	lambdaOrigin, err := model.GetLambdaOrigin(ctx)
	if err != nil {
		return cloudwatchEntryBase{}, err
	}

	source := cmp.Or(cfg.Source, getCloudwatchSource(strings.ToLower(data.LogGroup), data.LogStream))
	host := cmp.Or(cfg.Host, data.LogGroup)
	tags, service := getTagsAndService(cfg)
	service = cmp.Or(service, source)

	return cloudwatchEntryBase{
		metadata: model.CloudwatchMetadata{
			LambdaOrigin: lambdaOrigin,
			Origin: model.CloudwatchOrigin{
				LogGroup:  data.LogGroup,
				LogStream: data.LogStream,
				Owner:     data.Owner,
			},
		},
		source:  source,
		host:    host,
		service: service,
		tags:    tags,
	}, nil
}

func newCloudwatchLogEntry(base cloudwatchEntryBase, event events.CloudwatchLogsLogEvent) model.CloudwatchLogEntry {
	tags, service, message := extractFromMessage(event.Message)
	service = cmp.Or(service, base.service)
	tags = slices.Concat(tags, model.Tags{"service:" + service}, base.tags)
	return model.CloudwatchLogEntry{
		LogEntry:  model.NewLogEntry(base.metadata, tags, message, base.source, service),
		ID:        event.ID,
		Timestamp: event.Timestamp,
		Host:      base.host,
	}
}

func getCloudwatchSource(logGroup, logStream string) string {
	if strings.HasPrefix(logStream, logStreamStepFunction) {
		return sourceStepFunction
	}
	if strings.Contains(logStream, logStreamCloudtrail) {
		return sourceCloudtrail
	}
	if strings.HasPrefix(logGroup, logGroupCloudtrail) {
		return sourceCloudtrail
	}
	if strings.HasPrefix(logGroup, logGroupKinesis) {
		return sourceKinesis
	}
	if strings.HasPrefix(logGroup, logGroupLambda) {
		return sourceLambda
	}
	if strings.HasPrefix(logGroup, logGroupSNS) {
		return sourceSNS
	}
	if strings.Contains(logGroup, sourceCloudtrail) {
		return sourceCloudtrail
	}
	return sourceCloudwatch
}
