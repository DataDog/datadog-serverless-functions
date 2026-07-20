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
	"regexp"
	"slices"
	"strings"

	"github.com/DataDog/datadog-serverless-functions/aws/logs_monitoring_go/internal/concurrent"
	"github.com/DataDog/datadog-serverless-functions/aws/logs_monitoring_go/internal/filtering"
	"github.com/DataDog/datadog-serverless-functions/aws/logs_monitoring_go/internal/model"
	"github.com/DataDog/datadog-serverless-functions/aws/logs_monitoring_go/internal/scrubbing"
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

const envTag = "env"

// Custom log groups use the log stream format: YYYY/MM/DD/<function_name>[<function_version>][<execution_environment_GUID>]
// The first capture group extracts the function name.
var lambdaLogStreamRegex = regexp.MustCompile(
	`^\d{4}/[01]\d/[0-3]\d/([\w.-]{1,75})\[(?:\$LATEST|[\w-]{1,129})\][0-9a-f]{32}$`,
)

type cloudwatchHandler struct {
	cfg      *Config
	scrubber *scrubbing.Scrubber
	filterer *filtering.Filterer
}

func newCloudwatch(hcfg *Config, scrubber *scrubbing.Scrubber, filterer *filtering.Filterer) *cloudwatchHandler {
	return &cloudwatchHandler{
		cfg:      hcfg,
		scrubber: scrubber,
		filterer: filterer,
	}
}

func (h *cloudwatchHandler) Handle(ctx context.Context, event json.RawMessage, out chan<- model.LogEntry) error {
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

	var cwData events.CloudwatchLogsData
	if err := json.NewDecoder(zr).Decode(&cwData); err != nil {
		return events.CloudwatchLogsData{}, fmt.Errorf("json decode: %w", err)
	}
	return cwData, nil
}

func (h cloudwatchHandler) handleCloudwatchData(ctx context.Context, cwData events.CloudwatchLogsData, out chan<- model.LogEntry) error {
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
		if h.filterer.ShouldExclude(entry.Message) {
			continue
		}

		entry.Message = h.scrubber.Apply(entry.Message)
		if err := concurrent.SafeSender(ctx, out, entry); err != nil {
			return err
		}
	}

	return nil
}

func (h cloudwatchHandler) newCloudwatchBaseEntry(data events.CloudwatchLogsData, lambdaOrigin model.LambdaOrigin) model.LogEntry {
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
	source := cloudwatchSource(strings.ToLower(logGroup), logStream)

	entry := model.NewLogEntry()
	entry.Source = cmp.Or(h.cfg.Source, source)
	entry.Host = cmp.Or(h.cfg.Host, logGroup)
	entry.Metadata = metadata

	if entry.Source == sourceLambda {
		enrichLambdaLog(&entry, lambdaOrigin.ARN, logGroup, logStream, h.cfg)
	}

	return entry
}

func (h cloudwatchHandler) newCloudwatchLogEntry(event events.CloudwatchLogsLogEvent, entry model.LogEntry) model.LogEntry {
	tags, service, message := extractFromMessage(event.Message)
	entry.Service = cmp.Or(h.cfg.Service, service, entry.Source)
	entry.Tags = slices.Concat(tags, entry.Tags, h.cfg.Tags)
	entry.Message = message
	entry.ID = event.ID
	entry.Timestamp = event.Timestamp

	if entry.Source == sourceCloudtrail {
		entry.Host = cloudtrailHost(event.Message)
	}

	return entry
}

func cloudwatchSource(logGroup, logStream string) string {
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
	if strings.HasPrefix(logGroup, logGroupLambda) || lambdaLogStreamRegex.MatchString(logStream) {
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

func enrichLambdaLog(entry *model.LogEntry, forwarderARN, logGroup, logStream string, cfg *Config) {
	name := lambdaName(strings.ToLower(logGroup), logStream)
	if name != "" {
		return
	}

	prefix, _, found := strings.Cut(forwarderARN, "function:")
	if !found {
		return
	}

	arn := prefix + "function:" + name
	entry.Tags = append(entry.Tags, "functionname:"+name)
	entry.Lambda = &model.LambdaLog{ARN: arn}
	entry.Host = cmp.Or(cfg.Host, arn)

	if !hasTag(cfg.Tags, envTag) {
		entry.Tags = append(entry.Tags, envTag+":none")
	}
}

func lambdaName(logGroup, logStream string) string {
	if name := lambdaLogStreamRegex.FindString(logStream); name != "" {
		return strings.ToLower(name)
	}

	if _, name, found := strings.Cut(logGroup, logGroupLambda+"/"); found && name != "" {
		return strings.ToLower(name)
	}
	return ""
}

func hasTag(tags model.Tags, prefix string) bool {
	for _, tag := range tags {
		if strings.HasPrefix(tag, prefix) {
			return true
		}
	}
	return false
}
