// Unless explicitly stated otherwise all files in this repository are licensed
// under the Apache License Version 2.0.
// This product includes software developed at Datadog (https://www.datadoghq.com/).
// Copyright 2026-Present Datadog, Inc.

package main

import (
	"context"
	"encoding/json"
	"errors"

	"github.com/DataDog/datadog-serverless-functions/aws/logs_monitoring_go/internal/config"
	"github.com/DataDog/datadog-serverless-functions/aws/logs_monitoring_go/internal/forwarding"
	"github.com/DataDog/datadog-serverless-functions/aws/logs_monitoring_go/internal/handling"
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

	cwHandler := handling.NewCloudwatch(cfg)
	kinesisHandler := handling.NewKinesis(cfg)
	s3Handler := handling.NewS3(cfg)
	handling.Register(parsing.InvocationSourceCloudwatchLogs, cwHandler)
	handling.Register(parsing.InvocationSourceKinesis, kinesisHandler)
	handling.Register(parsing.InvocationSourceS3, s3Handler)

	lambda.Start(handleRequest(cfg))
}

func handleRequest(cfg *config.Config) func(ctx context.Context, event json.RawMessage) error {
	return func(ctx context.Context, event json.RawMessage) error {
		invocation := parsing.DetectInvocationSource(event)
		if invocation == parsing.InvocationSourceUnknown {
			return errors.New("unknown invocation")
		}

		run := pipeline.NewRun(cfg, handling.Handlers[invocation], forwarding.Storage(invocation))
		return pipeline.Start(ctx, event, run)
	}
}
