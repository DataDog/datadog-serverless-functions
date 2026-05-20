// Unless explicitly stated otherwise all files in this repository are licensed
// under the Apache License Version 2.0.
// This product includes software developed at Datadog (https://www.datadoghq.com/).
// Copyright 2026-Present Datadog, Inc.

package handling

import (
	"cmp"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"log/slog"
	"slices"
	"strings"

	"github.com/DataDog/datadog-serverless-functions/aws/logs_monitoring_go/internal/concurrent"
	"github.com/DataDog/datadog-serverless-functions/aws/logs_monitoring_go/internal/config"
	"github.com/DataDog/datadog-serverless-functions/aws/logs_monitoring_go/internal/model"
	"github.com/aws/aws-lambda-go/events"
)

const (
	s3KeyKinesis     = "amazon_kinesis"
	s3KeyVpcFlowLogs = "vpcflowlogs"
	s3KeyWAF1        = "aws-waf-logs"
	s3KeyWAF2        = "waflogs"
)

type S3Handler struct {
	cfg *config.Config
}

func NewS3(cfg *config.Config) *S3Handler {
	return &S3Handler{
		cfg: cfg,
	}
}

func (h *S3Handler) Handle(ctx context.Context, event json.RawMessage, out chan<- model.LogEntry) error {
	var s3Event events.S3Event
	if err := json.Unmarshal(event, &s3Event); err != nil {
		return fmt.Errorf("unmarshal: %w", err)
	}

	client, err := getS3APIClient(ctx, h.cfg.UseFIPS)
	if err != nil {
		return fmt.Errorf("get S3 client: %w", err)
	}

	lambdaOrigin, err := model.GetLambdaOrigin(ctx)
	if err != nil {
		return err
	}

	for _, eventRecord := range s3Event.Records {
		if err := h.processRecord(ctx, client, out, eventRecord, lambdaOrigin); err != nil {
			return err
		}
	}
	return nil
}

func (h S3Handler) processRecord(ctx context.Context, client S3APIClient, out chan<- model.LogEntry, eventRecord events.S3EventRecord, lambdaOrigin model.LambdaOrigin) error {
	body, err := getS3Object(ctx, client, eventRecord.S3.Bucket.Name, eventRecord.S3.Object.URLDecodedKey)
	if err != nil {
		return err
	}
	defer func() {
		if err := body.Close(); err != nil {
			slog.Warn("close response body", slog.Any("error", err))
		}
	}()

	reader, close, err := gunzip(body)
	if err != nil {
		return err
	}
	defer func() {
		if err := close(); err != nil {
			slog.Warn("close gunzip", slog.Any("error", err))
		}
	}()

	source := S3Source(eventRecord.S3.Object.URLDecodedKey)
	switch source {
	case sourceCloudtrail:
		err = h.CloudTrail(ctx, out, reader, eventRecord, lambdaOrigin)
	case sourceWAF:
		err = h.WAF(ctx, out, reader, eventRecord, lambdaOrigin)
	default:
		err = h.S3(ctx, out, reader, eventRecord, lambdaOrigin)
	}

	if err != nil {
		return fmt.Errorf("source %s: %w", source, err)
	}
	return nil
}

func S3Source(key string) string {
	if strings.Contains(key, s3KeyWAF1) || strings.Contains(key, s3KeyWAF2) {
		return sourceWAF
	}
	if strings.Contains(key, s3KeyKinesis) {
		return sourceKinesis
	}
	if cloudTrailRegex.Match([]byte(key)) {
		return sourceCloudtrail
	}
	return sourceS3
}

func (h S3Handler) S3(ctx context.Context, out chan<- model.LogEntry, r io.Reader, eventRecord events.S3EventRecord, lambdaOrigin model.LambdaOrigin) error {
	var headerSkipped bool
	isVpcFlowLogs := strings.Contains(eventRecord.S3.Object.URLDecodedKey, s3KeyVpcFlowLogs)

	base := h.newBaseEntry(eventRecord, lambdaOrigin)
	for message, err := range scan(r, h.cfg.S3MultilineLogRegex) {
		if err != nil {
			return err
		}

		if isVpcFlowLogs && !headerSkipped {
			headerSkipped = true
			continue
		}

		tags, service, message := extractFromMessage(message)
		if h.cfg.Filter.ShouldExclude(message) {
			continue
		}

		entry := base
		entry.Message = h.cfg.Scrubber.Scrub(message)
		entry.Service = cmp.Or(service, entry.Service)
		entry.Tags = slices.Concat(tags, entry.Tags)

		if err := concurrent.SafeSender(ctx, out, entry); err != nil {
			return err
		}
	}
	return nil
}

func (h S3Handler) WAF(ctx context.Context, out chan<- model.LogEntry, r io.Reader, eventRecord events.S3EventRecord, lambdaOrigin model.LambdaOrigin) error {
	base := h.newBaseEntry(eventRecord, lambdaOrigin)
	for message, err := range scan(r, nil) {
		if err != nil {
			return err
		}

		message = flattenWAFMessage(message)
		if h.cfg.Filter.ShouldExclude(message) {
			continue
		}

		entry := base
		entry.Message = h.cfg.Scrubber.Scrub(message)

		if err := concurrent.SafeSender(ctx, out, entry); err != nil {
			return err
		}
	}
	return nil
}

func (h S3Handler) CloudTrail(ctx context.Context, out chan<- model.LogEntry, r io.Reader, eventRecord events.S3EventRecord, lambdaOrigin model.LambdaOrigin) error {
	base := h.newBaseEntry(eventRecord, lambdaOrigin)
	for message, err := range decodeCloudTrail(r) {
		if err != nil {
			return err
		}
		if h.cfg.Filter.ShouldExclude(message) {
			continue
		}

		entry := base
		entry.Host = cloudtrailHost(message)
		entry.Message = h.cfg.Scrubber.Scrub(message)

		if err := concurrent.SafeSender(ctx, out, entry); err != nil {
			return err
		}
	}
	return nil
}

func (h S3Handler) newBaseEntry(eventRecord events.S3EventRecord, lambdaOrigin model.LambdaOrigin) model.LogEntry {
	source := S3Source(eventRecord.S3.Object.URLDecodedKey)

	entry := model.NewLogEntry()
	entry.Source = cmp.Or(h.cfg.Source, source)
	entry.Service = cmp.Or(h.cfg.Service, source)
	entry.Tags = h.cfg.Tags
	entry.Metadata = model.S3Metadata{
		LambdaOrigin: lambdaOrigin,
		Origin: model.S3Origin{
			Bucket: eventRecord.S3.Bucket.Name,
			Key:    eventRecord.S3.Object.URLDecodedKey,
		},
	}
	return entry
}
