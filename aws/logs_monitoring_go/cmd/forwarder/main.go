// Unless explicitly stated otherwise all files in this repository are licensed
// under the Apache License Version 2.0.
// This product includes software developed at Datadog (https://www.datadoghq.com/).
// Copyright 2026-Present Datadog, Inc.

package main

import (
	"context"
	"encoding/json"
	"log"
	"log/slog"
	"os"
	"strings"

	"github.com/DataDog/datadog-serverless-functions/aws/logs_monitoring_go/internal/config"

	"github.com/aws/aws-lambda-go/lambda"
)

func initLogger(level string) {
	var slogLevel slog.Level
	switch strings.ToUpper(level) {
	case "DEBUG":
		slogLevel = slog.LevelDebug
	case "INFO":
		slogLevel = slog.LevelInfo
	case "WARNING", "WARN":
		slogLevel = slog.LevelWarn
	case "ERROR":
		slogLevel = slog.LevelError
	default:
		slogLevel = slog.LevelInfo
	}
	slog.SetDefault(slog.New(slog.NewTextHandler(os.Stderr, &slog.HandlerOptions{
		Level: slogLevel,
	})))
}

func handleRequest(cfg *config.Config) func(context.Context, json.RawMessage) error {
	return func(ctx context.Context, event json.RawMessage) error {
		slog.Info("received event", "event", string(event))
		return nil
	}
}

func main() {
	ctx := context.Background()
	cfg, err := config.Load(ctx)
	if err != nil {
		log.Fatalf("config: %v", err)
	}
	// TODO: exit if forwading disabled ?
	initLogger(cfg.LogLevel)
	lambda.Start(handleRequest(cfg))
}
