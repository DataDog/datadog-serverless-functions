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

const (
	s3KeyWAF1       = "aws-waf-logs"
	s3KeyWAF2       = "waflogs"
	s3KeyKinesis    = "amazon_kinesis"
	s3KeyCloudtrail = "_CloudTrail_"
)

type s3EntryBase struct {
	metadata       model.S3Metadata
	source         string
	service        string
	tags           model.Tags
	multilineRegex *regexp.Regexp
}

func HandleS3(ctx context.Context, event json.RawMessage, cfg *config.Config, out chan<- model.S3LogEntry) error {
	var s3Event events.S3Event
	if err := json.Unmarshal(event, &s3Event); err != nil {
		return fmt.Errorf("unmarshal: %w", err)
	}

	client, err := getS3APIClient(ctx, cfg.UseFIPS)
	if err != nil {
		return fmt.Errorf("get S3 client: %w", err)
	}

	lambdaOrigin, err := model.GetLambdaOrigin(ctx)
	if err != nil {
		return err
	}

	for _, record := range s3Event.Records {
		base := newS3EntryBase(record, cfg, lambdaOrigin)
		if err := processS3Record(ctx, client, out, base); err != nil {
			return fmt.Errorf("process s3://%s/%s: %w", base.metadata.Origin.Bucket, base.metadata.Origin.Key, err)
		}
	}
	return nil
}

func processS3Record(ctx context.Context, client S3APIClient, out chan<- model.S3LogEntry, base s3EntryBase) error {
	body, err := getS3Object(ctx, client, base.metadata.Origin.Bucket, base.metadata.Origin.Key)
	if err != nil {
		return err
	}
	defer func() {
		if err := body.Close(); err != nil {
			slog.Warn("failed to close response body", slog.Any("error", err))
		}
	}()

	scanner := NewScanner(body, base.multilineRegex)
	for scanner.Scan() {
		message := strings.ToValidUTF8(scanner.Text(), "")
		if err := concurrent.SafeSender(ctx, out, newS3LogEntry(base, message)); err != nil {
			return err
		}
	}

	if err := scanner.Err(); err != nil {
		return err
	}
	return nil
}

func newS3EntryBase(record events.S3EventRecord, cfg *config.Config, lambdaOrigin model.LambdaOrigin) s3EntryBase {
	bucket := record.S3.Bucket.Name
	key := record.S3.Object.URLDecodedKey
	source := cmp.Or(cfg.Source, getS3Source(key))
	tags, service := getTagsAndService(cfg)
	service = cmp.Or(service, source)

	return s3EntryBase{
		metadata: model.S3Metadata{
			LambdaOrigin: lambdaOrigin,
			Origin: model.S3Origin{
				Bucket: bucket,
				Key:    key,
			},
		},
		source:         source,
		service:        service,
		tags:           tags,
		multilineRegex: cfg.S3MultilineLogRegex,
	}
}

func newS3LogEntry(base s3EntryBase, message string) model.S3LogEntry {
	tags, service, message := extractFromMessage(message)
	service = cmp.Or(service, base.service)
	tags = slices.Concat(tags, model.Tags{"service:" + service}, base.tags)
	return model.S3LogEntry{
		LogEntry: model.NewLogEntry(base.metadata, tags, message, base.source, service),
	}
}

func getS3Source(key string) string {
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
