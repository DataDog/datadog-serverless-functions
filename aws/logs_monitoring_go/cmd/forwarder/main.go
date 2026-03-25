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

// cfg not used for now, will be when forwarding logic added
func handleRequest(cfg *config.Config) func(context.Context, json.RawMessage) error {
	return func(ctx context.Context, event json.RawMessage) error {
		slog.Info("received event", slog.String("event", string(event)))
		return nil
	}
}
