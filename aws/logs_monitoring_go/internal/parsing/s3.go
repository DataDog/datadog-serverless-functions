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
	"log/slog"
	"regexp"
	"slices"
	"strings"

	"github.com/DataDog/datadog-serverless-functions/aws/logs_monitoring_go/internal/concurrent"
	"github.com/DataDog/datadog-serverless-functions/aws/logs_monitoring_go/internal/config"
	"github.com/DataDog/datadog-serverless-functions/aws/logs_monitoring_go/internal/model"
	"github.com/aws/aws-lambda-go/events"
)

type s3Record struct {
	metadata       model.Metadata
	tags           model.Tags
	source         string
	service        string
	bucket         string
	key            string
	multilineRegex *regexp.Regexp
}

func HandleS3(ctx context.Context, event json.RawMessage, cfg *config.Config, out chan<- model.S3LogEntry) error {
	client, metadata, err := setupS3(ctx, cfg)
	if err != nil {
		return fmt.Errorf("setup s3: %w", err)
	}
	return handleS3Event(ctx, event, cfg, client, metadata, out)
}

func setupS3(ctx context.Context, cfg *config.Config) (S3APIClient, model.Metadata, error) {
	client, err := createS3APIClient(ctx, cfg.UseFIPS)
	if err != nil {
		return nil, model.Metadata{}, fmt.Errorf("create S3 client: %w", err)
	}

	metadata, err := model.GetMetadata(ctx)
	if err != nil {
		return nil, model.Metadata{}, fmt.Errorf("get metadata: %w", err)
	}

	return client, metadata, nil
}

func handleS3Event(ctx context.Context, event json.RawMessage, cfg *config.Config, client S3APIClient, metadata model.Metadata, out chan<- model.S3LogEntry) error {
	var s3Event events.S3Event
	if err := json.Unmarshal(event, &s3Event); err != nil {
		return fmt.Errorf("unmarshal: %w", err)
	}

	for _, record := range s3Event.Records {
		bucket := record.S3.Bucket.Name
		key := record.S3.Object.URLDecodedKey

		tags, service := getTagsAndService(cfg)
		source := getS3Source(cfg.Source, key)
		service = cmp.Or(service, source)

		rc := s3Record{
			metadata:       metadata,
			tags:           tags,
			source:         source,
			service:        service,
			bucket:         bucket,
			key:            key,
			multilineRegex: cfg.S3MultilineLogRegex,
		}
		if err := processS3Record(ctx, client, out, rc); err != nil {
			slog.WarnContext(ctx, "skipping s3 record",
				"bucket", bucket, "key", key, "error", err)
			continue
		}
	}

	return nil
}

func processS3Record(ctx context.Context, client S3APIClient, out chan<- model.S3LogEntry, rc s3Record) error {
	body, err := getS3Object(ctx, client, rc.bucket, rc.key)
	if err != nil {
		return err
	}

	defer func() {
		if err := body.Close(); err != nil {
			slog.WarnContext(ctx, "failed to close response body", slog.Any("error", err))
		}
	}()

	scanner := NewScanner(body, rc.multilineRegex)
	for scanner.Scan() {
		message := strings.ToValidUTF8(scanner.Text(), "")
		if err := concurrent.SafeSender(ctx, out, makeS3Entry(rc, message)); err != nil {
			return err
		}
	}

	if err := scanner.Err(); err != nil {
		return fmt.Errorf("scan: %w", err)
	}

	return nil
}

func makeS3Entry(rc s3Record, message string) model.S3LogEntry {
	ddtags, ddtagsService, message := extractFromMessage(message)

	entryService := rc.service
	if ddtagsService != "" {
		entryService = ddtagsService
	}

	tags := slices.Concat(ddtags, model.Tags{"service:" + entryService}, rc.tags)
	metadata := model.S3Metadata{
		Metadata: rc.metadata,
		S3Context: model.S3Context{
			Bucket: rc.bucket,
			Key:    rc.key,
		},
	}

	return model.S3LogEntry{
		Message:        message,
		Source:         rc.source,
		SourceCategory: sourceCategory,
		Service:        entryService,
		Tags:           tags,
		Metadata:       metadata,
	}
}

func getS3Source(sourceOverride, key string) string {
	if sourceOverride != "" {
		return sourceOverride
	}

	if strings.Contains(key, "aws-waf-logs") || strings.Contains(key, "waflogs") {
		return "waf"
	}

	if strings.Contains(key, "amazon_kinesis") {
		return "kinesis"
	}

	if strings.Contains(key, "_CloudTrail_") {
		return "cloudtrail"
	}

	return "s3"
}
