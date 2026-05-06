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
	"iter"
	"log/slog"
	"slices"
	"strings"

	"github.com/DataDog/datadog-serverless-functions/aws/logs_monitoring_go/internal/concurrent"
	"github.com/DataDog/datadog-serverless-functions/aws/logs_monitoring_go/internal/config"
	"github.com/DataDog/datadog-serverless-functions/aws/logs_monitoring_go/internal/model"
	"github.com/aws/aws-lambda-go/events"
)

const (
	s3KeyWAF1       = "aws-waf-logs"
	s3KeyWAF2       = "waflogs"
	s3KeyKinesis    = "amazon_kinesis"
	s3KeyCloudtrail = "_CloudTrail_"
)

type S3Handler struct {
	cfg *config.Config
}

func NewS3(cfg *config.Config) *S3Handler {
	return &S3Handler{
		cfg: cfg,
	}
}

func (h S3Handler) Handle(ctx context.Context, event json.RawMessage, out chan<- model.LogEntry) error {
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
	bucket := eventRecord.S3.Bucket.Name
	key := eventRecord.S3.Object.URLDecodedKey

	body, err := getS3Object(ctx, client, bucket, key)
	if err != nil {
		return err
	}
	defer func() {
		if err := body.Close(); err != nil {
			slog.Warn("failed to close response body", slog.Any("error", err))
		}
	}()

	var records iter.Seq2[string, error]
	isCloudTrail := cloudTrailRegex.MatchString(key)
	if isCloudTrail {
		records = decodeCloudTrail(body)
	} else {
		records = scan(body, h.cfg.S3MultilineLogRegex)
	}

	for message, err := range records {
		if err != nil {
			return err
		}
		entry := h.newS3LogEntry(eventRecord, message, lambdaOrigin)
		if h.cfg.Filter.ShouldExclude(entry.Message) {
			continue
		}

		if isCloudTrail {
			entry.Host = cloudtrailHost(message)
		}
		entry.Message = h.cfg.Scrubber.Scrub(entry.Message)
		if err := concurrent.SafeSender(ctx, out, entry); err != nil {
			return err
		}
	}
	return nil
}

func (h S3Handler) newS3LogEntry(eventRecord events.S3EventRecord, message string, lambdaOrigin model.LambdaOrigin) model.LogEntry {
	key := eventRecord.S3.Object.URLDecodedKey
	metadata := model.S3Metadata{
		LambdaOrigin: lambdaOrigin,
		Origin: model.S3Origin{
			Bucket: eventRecord.S3.Bucket.Name,
			Key:    key,
		},
	}
	tags, service, message := extractFromMessage(message)

	entry := model.NewLogEntry()
	entry.Message = message
	entry.Metadata = metadata
	entry.Source = cmp.Or(h.cfg.Source, S3Source(key))
	entry.Service = cmp.Or(h.cfg.Service, service, entry.Source)
	entry.Tags = slices.Concat(tags, h.cfg.Tags)
	return entry
}

func S3Source(key string) string {
	if strings.Contains(key, s3KeyWAF1) || strings.Contains(key, s3KeyWAF2) {
		return sourceWAF
	}
	if strings.Contains(key, s3KeyKinesis) {
		return sourceKinesis
	}
	if strings.Contains(key, s3KeyCloudtrail) {
		return sourceCloudtrail
	}
	return sourceS3
}
