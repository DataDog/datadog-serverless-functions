// Unless explicitly stated otherwise all files in this repository are licensed
// under the Apache License Version 2.0.
// This product includes software developed at Datadog (https://www.datadoghq.com/).
// Copyright 2026-Present Datadog, Inc.

package main

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"log/slog"
	"net/http"
	"os"
	"sync"

	"github.com/DataDog/datadog-serverless-functions/aws/logs_monitoring_go/internal/apikey"
	"github.com/DataDog/datadog-serverless-functions/aws/logs_monitoring_go/internal/config"
	"github.com/DataDog/datadog-serverless-functions/aws/logs_monitoring_go/internal/filtering"
	"github.com/DataDog/datadog-serverless-functions/aws/logs_monitoring_go/internal/forwarding"
	"github.com/DataDog/datadog-serverless-functions/aws/logs_monitoring_go/internal/handling"
	"github.com/DataDog/datadog-serverless-functions/aws/logs_monitoring_go/internal/httpclient"
	"github.com/DataDog/datadog-serverless-functions/aws/logs_monitoring_go/internal/pipeline"
	"github.com/DataDog/datadog-serverless-functions/aws/logs_monitoring_go/internal/scrubbing"
	"github.com/DataDog/datadog-serverless-functions/aws/logs_monitoring_go/internal/sdkclient"
	"github.com/DataDog/datadog-serverless-functions/aws/logs_monitoring_go/internal/storing"

	"github.com/aws/aws-lambda-go/lambda"
)

func main() {
	initLogger(os.Stderr, os.Getenv(config.EnvLogLevel))

	cfg, err := config.Load()
	if err != nil {
		slog.Error("config load", slog.Any("error", err))
		os.Exit(1)
	}
	slog.Debug("configuration loaded", slog.Any("config", cfg))

	ctx := context.Background()
	apiKey, err := apikey.Resolve(ctx, apikey.Source{
		SecretARN: cfg.APIKeySecretARN,
		SSMName:   cfg.APIKeySSMName,
		KMSKey:    cfg.APIKeyKMSKey,
	})
	if err != nil {
		slog.Error("resolve API key", slog.Any("error", err))
		os.Exit(1)
	}

	var tlsOpts []httpclient.TLSOption
	if cfg.SkipServerCertificate {
		tlsOpts = append(tlsOpts, httpclient.WithCertificateSkip())
	}
	client := httpclient.New(tlsOpts...)

	if err = apikey.Validate(ctx, client, cfg.APIURL, apiKey); err != nil {
		if !cfg.StoreOnFail {
			slog.Error("no failed event storage set, validate API key", slog.Any("error", err))
			os.Exit(1)
		}
		slog.Error("API key validation", slog.Any("error", err))
	}

	lambda.Start(handleRequest(&cfg, apiKey, client))
}

func handleRequest(cfg *config.Config, apiKey string, client *http.Client) func(ctx context.Context, awsevent json.RawMessage) (any, error) {
	return func(ctx context.Context, awsevent json.RawMessage) (any, error) {
		slog.DebugContext(ctx, "invocation start", slog.String("event", string(awsevent)))

		var wg sync.WaitGroup

		var invokeErr error
		if cfg.AdditionalTargets != nil {
			wg.Go(func() {
				invokeErr = sdkclient.InvokeTargets(ctx, cfg.AdditionalTargets, awsevent)
			})
		}

		filterer := filtering.NewFilterer(cfg.FilterInclude, cfg.FilterExclude)
		scrubber := scrubbing.NewScrubber(cfg.ScrubbingRegex, cfg.ScrubbingReplacement, cfg.ScrubIP, cfg.ScrubEmail)
		handlerCfg := handling.Config{
			Service:             cfg.Service,
			Source:              cfg.Source,
			Tags:                cfg.Tags,
			S3MultilineLogRegex: cfg.S3MultilineLogRegex,
		}
		forwarderCfg := forwarding.Config{
			APIKey:                    apiKey,
			IntakeURL:                 cfg.IntakeURL,
			CompressionLevel:          cfg.CompressionLevel,
			StepFunctionsTraceEnabled: cfg.StepFunctionsTraceEnabled,
		}

		var storage storing.Storage
		var storageErr error
		if cfg.StoreOnFail {
			storageOpts := storing.Options{S3Bucket: cfg.S3RetryBucketName, SQSQueue: cfg.SQSQueueURL}
			if storage, storageErr = storing.NewStorage(storageOpts); storageErr != nil {
				return nil, fmt.Errorf("new storage: %w", storageErr)
			}
		}

		forwarder := forwarding.NewForwarder(
			forwarderCfg,
			client,
			storage,
		)

		out, pipelineErr := pipeline.New(handlerCfg, scrubber, filterer, forwarder).Start(ctx, awsevent)

		wg.Wait()
		return out, errors.Join(invokeErr, pipelineErr)
	}
}
