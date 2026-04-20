// Unless explicitly stated otherwise all files in this repository are licensed
// under the Apache License Version 2.0.
// This product includes software developed at Datadog (https://www.datadoghq.com/).
// Copyright 2026-Present Datadog, Inc.

package parsing

import (
	"context"
	"encoding/json"
	"fmt"
	"log/slog"
	"regexp"
	"strings"

	"github.com/DataDog/datadog-serverless-functions/aws/logs_monitoring_go/internal/concurrent"
	"github.com/DataDog/datadog-serverless-functions/aws/logs_monitoring_go/internal/config"
	"github.com/DataDog/datadog-serverless-functions/aws/logs_monitoring_go/internal/model"
	"github.com/aws/aws-lambda-go/events"
)

type s3RecordContext struct {
	metadata       model.Metadata
	tags           model.Tags
	source         string
	service        string
	bucket         string
	key            string
	multilineRegex *regexp.Regexp
}

func HandleS3(ctx context.Context, event json.RawMessage, cfg *config.Config, out chan<- model.S3LogEntry) error {
	var s3Event events.S3Event
	if err := json.Unmarshal(event, &s3Event); err != nil {
		return fmt.Errorf("unmarshal: %w", err)
	}

	client, err := createS3APIClient(ctx, cfg.UseFIPS)
	if err != nil {
		return fmt.Errorf("create S3 client: %w", err)
	}

	forwarderMetadata, err := model.GetMetadata(ctx)
	if err != nil {
		return err
	}

	for _, record := range s3Event.Records {
		bucket := record.S3.Bucket.Name
		key := record.S3.Object.URLDecodedKey

		tags, service := getTagsAndService(cfg)
		source := getS3Source(cfg.Source, key)
		if service == "" {
			service = source
		}

		rc := s3RecordContext{
			forwarderMetadata, tags, source, service, bucket, key, cfg.S3MultilineLogRegex,
		}
		if err := processS3Record(ctx, client, out, rc); err != nil {
			return fmt.Errorf("process S3 record: %w", err)
		}
	}

	return nil
}

func processS3Record(ctx context.Context, client S3APIClient, out chan<- model.S3LogEntry, rc s3RecordContext) error {
	body, err := getS3Object(ctx, client, rc.bucket, rc.key)
	if err != nil {
		return err
	}

	defer func() {
		if err := body.Close(); err != nil {
			slog.Warn("failed to close response body", slog.Any("error", err))
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
		return fmt.Errorf("scan s3://%s/%s: %w", rc.bucket, rc.key, err)
	}

	return nil
}

func makeS3Entry(rc s3RecordContext, message string) model.S3LogEntry {
	ddtags, ddtagsService, message := extractFromMessage(message)

	entryService := rc.service
	if ddtagsService != "" {
		entryService = ddtagsService
	}

	ddtags = append(ddtags, "service:"+entryService)
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
		Tags:           append(ddtags, rc.tags...),
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
