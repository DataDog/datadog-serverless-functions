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

	"github.com/DataDog/datadog-serverless-functions/aws/logs_monitoring_go/internal/config"
	"github.com/DataDog/datadog-serverless-functions/aws/logs_monitoring_go/internal/model"
	"github.com/aws/aws-lambda-go/events"
)

func HandleSNS(ctx context.Context, event json.RawMessage, cfg *config.Config, out chan<- model.S3LogEntry) error {
	var snsEvent events.SNSEvent
	if err := json.Unmarshal(event, &snsEvent); err != nil {
		return fmt.Errorf("unmarshal: %w", err)
	}

	client, metadata, err := setupS3(ctx, cfg)
	if err != nil {
		return fmt.Errorf("setup s3 for sns: %w", err)
	}

	for _, record := range snsEvent.Records {
		if err := handleSNSRecord(ctx, record, cfg, client, metadata, out); err != nil {
			slog.WarnContext(ctx, "skipping sns record", "error", err)
			continue
		}
	}
	return nil
}

func handleSNSRecord(ctx context.Context, record events.SNSEventRecord, cfg *config.Config, client S3APIClient, metadata model.Metadata, out chan<- model.S3LogEntry) error {
	s3Raw := json.RawMessage(record.SNS.Message)
	return handleS3Event(ctx, s3Raw, cfg, client, metadata, out)
}
