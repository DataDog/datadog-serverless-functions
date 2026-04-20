// Unless explicitly stated otherwise all files in this repository are licensed
// under the Apache License Version 2.0.
// This product includes software developed at Datadog (https://www.datadoghq.com/).
// Copyright 2026-Present Datadog, Inc.

package main

import (
	"context"
	"encoding/json"
	"log/slog"

	"github.com/DataDog/datadog-serverless-functions/aws/logs_monitoring_go/internal/config"
	"github.com/DataDog/datadog-serverless-functions/aws/logs_monitoring_go/internal/forwarding"
	"github.com/DataDog/datadog-serverless-functions/aws/logs_monitoring_go/internal/parsing"
	"github.com/DataDog/datadog-serverless-functions/aws/logs_monitoring_go/internal/pipeline"

	"github.com/aws/aws-lambda-go/lambda"
)

func main() {
	ctx := context.Background()
	cfg, err := config.Load(ctx)
	if err != nil {
		slog.Error("config load failed", slog.Any("error", err))
		return
	}

	lambda.Start(handleRequest(cfg))
}

func handleRequest(cfg *config.Config) func(context.Context, json.RawMessage) error {
	return func(ctx context.Context, event json.RawMessage) error {
		invocationSource := parsing.DetectInvocationSource(event)
		switch invocationSource {
		case parsing.InvocationSourceCloudwatchLogs:
			return pipeline.Run(ctx, event, cfg, forwarding.CloudwatchStorage, parsing.HandleCloudwatchLogs)
		case parsing.InvocationSourceS3:
			return pipeline.Run(ctx, event, cfg, forwarding.S3Storage, parsing.HandleS3)
		default:
			slog.Error("unsupported invocation source", slog.String("source", invocationSource.String()))
			return nil
		}
	}
}
