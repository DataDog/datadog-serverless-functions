// Unless explicitly stated otherwise all files in this repository are licensed
// under the Apache License Version 2.0.
// This product includes software developed at Datadog (https://www.datadoghq.com/).
// Copyright 2026-Present Datadog, Inc.

package main

import (
	"context"
	"encoding/json"
	"fmt"

	"github.com/DataDog/datadog-serverless-functions/aws/logs_monitoring_go/internal/config"
	"github.com/DataDog/datadog-serverless-functions/aws/logs_monitoring_go/internal/parsing"
	"github.com/DataDog/datadog-serverless-functions/aws/logs_monitoring_go/internal/pipeline"

	"github.com/aws/aws-lambda-go/lambda"
)

func main() {
	cfg, err := config.Load()
	if err != nil {
		panic(err)
	}
	err = cfg.ResolveAPIKey(context.Background())
	if err != nil {
		panic(err)
	}
	err = cfg.ValidateAPIKey(context.Background())
	if err != nil {
		panic(err)
	}

	lambda.Start(handleRequest(cfg))
}

func handleRequest(cfg *config.Config) func(ctx context.Context, event json.RawMessage) error {
	return func(ctx context.Context, event json.RawMessage) error {
		parsed, err := parsing.Parse(event)
		if err != nil {
			return fmt.Errorf("parse: %w", err)
		}
		return pipeline.Start(ctx, parsed, cfg)
	}
}
