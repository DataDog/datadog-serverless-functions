// Unless explicitly stated otherwise all files in this repository are licensed
// under the Apache License Version 2.0.
// This product includes software developed at Datadog (https://www.datadoghq.com/).
// Copyright 2026-Present Datadog, Inc.

package handling

import (
	"bytes"
	"cmp"
	"compress/gzip"
	"context"
	"encoding/base64"
	"encoding/json"
	"fmt"
	"log/slog"
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

type CloudwatchHandler struct {
	cfg *config.Config
}

func NewCloudwatch(cfg *config.Config) *CloudwatchHandler {
	return &CloudwatchHandler{
		cfg: cfg,
	}
}

func (h CloudwatchHandler) Handle(ctx context.Context, event json.RawMessage, out chan<- model.LogEntry) error {
	var cwEvent events.CloudwatchLogsEvent
	if err := json.Unmarshal(event, &cwEvent); err != nil {
		return fmt.Errorf("unmarshal: %w", err)
	}

	cwData, err := decodeCloudwatchLogs(cwEvent.AWSLogs.Data)
	if err != nil {
		return fmt.Errorf("parse: %w", err)
	}

	return h.handleCloudwatchData(ctx, cwData, out)
}

func decodeCloudwatchLogs(data string) (events.CloudwatchLogsData, error) {
	raw, err := base64.StdEncoding.DecodeString(data)
	if err != nil {
		return events.CloudwatchLogsData{}, fmt.Errorf("base64 decode: %w", err)
	}
	return decompressCloudwatchLogs(raw)
}

func decompressCloudwatchLogs(data []byte) (events.CloudwatchLogsData, error) {
	zr, err := gzip.NewReader(bytes.NewBuffer(data))
	if err != nil {
		return events.CloudwatchLogsData{}, fmt.Errorf("gzip: %w", err)
	}
	defer func() {
		if err := zr.Close(); err != nil {
			slog.Warn("failed to close gzip reader", slog.Any("error", err))
		}
	}()

	var d events.CloudwatchLogsData
	if err := json.NewDecoder(zr).Decode(&d); err != nil {
		return events.CloudwatchLogsData{}, fmt.Errorf("json decode: %w", err)
	}
	return d, nil
}

func (h CloudwatchHandler) handleCloudwatchData(ctx context.Context, cwData events.CloudwatchLogsData, out chan<- model.LogEntry) error {
	if cwData.MessageType == "CONTROL_MESSAGE" {
		return nil
	}

	lambdaOrigin, err := model.GetLambdaOrigin(ctx)
	if err != nil {
		return err
	}

	base := h.newCloudwatchBaseEntry(cwData, lambdaOrigin)
	for _, event := range cwData.LogEvents {
		entry := h.newCloudwatchLogEntry(event, base)
		if h.cfg.Filter.ShouldExclude(entry.Message) {
			continue
		}

		entry.Message = h.cfg.Scrubber.Scrub(entry.Message)
		if err := concurrent.SafeSender(ctx, out, entry); err != nil {
			return err
		}
	}

	return nil
}

func (h CloudwatchHandler) newCloudwatchBaseEntry(data events.CloudwatchLogsData, lambdaOrigin model.LambdaOrigin) model.LogEntry {
	logGroup := data.LogGroup
	logStream := data.LogStream
	metadata := model.CloudwatchMetadata{
		LambdaOrigin: lambdaOrigin,
		Origin: model.CloudwatchOrigin{
			LogGroup:  logGroup,
			LogStream: logStream,
			Owner:     data.Owner,
		},
	}

	entry := model.NewLogEntry()
	entry.Source = cmp.Or(h.cfg.Source, CloudwatchSource(strings.ToLower(logGroup), logStream))
	entry.Host = cmp.Or(h.cfg.Host, logGroup)
	entry.Metadata = metadata
	return entry
}

func (h CloudwatchHandler) newCloudwatchLogEntry(event events.CloudwatchLogsLogEvent, entry model.LogEntry) model.LogEntry {
	tags, service, message := extractFromMessage(event.Message)
	entry.Service = cmp.Or(h.cfg.Service, service, entry.Source)
	entry.Tags = slices.Concat(tags, model.Tags{"service:" + entry.Service}, h.cfg.Tags)
	entry.Message = message
	entry.ID = event.ID
	entry.Timestamp = event.Timestamp
	return entry
}

func CloudwatchSource(logGroup, logStream string) string {
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
