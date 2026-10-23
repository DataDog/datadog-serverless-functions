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
	"strings"
	"sync"
	"time"

	"github.com/DataDog/datadog-serverless-functions/aws/logs_monitoring_go/internal/apikey"
	"github.com/DataDog/datadog-serverless-functions/aws/logs_monitoring_go/internal/config"
	"github.com/DataDog/datadog-serverless-functions/aws/logs_monitoring_go/internal/filterer"
	"github.com/DataDog/datadog-serverless-functions/aws/logs_monitoring_go/internal/forwarder"
	"github.com/DataDog/datadog-serverless-functions/aws/logs_monitoring_go/internal/handler"
	"github.com/DataDog/datadog-serverless-functions/aws/logs_monitoring_go/internal/httpclient"
	"github.com/DataDog/datadog-serverless-functions/aws/logs_monitoring_go/internal/model"
	"github.com/DataDog/datadog-serverless-functions/aws/logs_monitoring_go/internal/pipeline"
	"github.com/DataDog/datadog-serverless-functions/aws/logs_monitoring_go/internal/scrubber"
	"github.com/DataDog/datadog-serverless-functions/aws/logs_monitoring_go/internal/sdkclient"
	"github.com/DataDog/datadog-serverless-functions/aws/logs_monitoring_go/internal/storage"
	"github.com/DataDog/datadog-serverless-functions/aws/logs_monitoring_go/internal/version"

	"github.com/aws/aws-lambda-go/lambda"
	"github.com/aws/aws-lambda-go/lambdacontext"
)

const initTimeout = 8 * time.Second

func main() {
	initLogger(os.Stderr, os.Getenv(config.EnvLogLevel))

	cfg, err := config.Load()
	if err != nil {
		slog.Error("config load", slog.Any("error", err))
		os.Exit(1)
	}
	slog.Debug("configuration loaded", slog.Any("config", cfg))

	ctx, cancel := context.WithTimeout(context.Background(), initTimeout)
	defer cancel()

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

	lambda.Start(handleRequest(&cfg, newHandlerConfig(&cfg, lambdacontext.FunctionName), apiKey, client))
}

func newHandlerConfig(cfg *config.Config, functionName string) handler.Config {
	service, tags := model.ParseTags(cfg.Tags)

	if cfg.Source != "" {
		tags.Add(model.SourceOverriddenKey, "true")
	}
	tags.Add(model.ForwarderNameKey, strings.ToLower(functionName))
	tags.Add(model.ForwarderVersionKey, version.Forwarder)

	return handler.Config{
		Service:             service,
		Source:              cfg.Source,
		Tags:                tags,
		S3MultilineLogRegex: cfg.S3MultilineLogRegex,
	}
}

func handleRequest(cfg *config.Config, handlerCfg handler.Config, apiKey string, client *http.Client) func(ctx context.Context, awsevent json.RawMessage) (any, error) {
	return func(ctx context.Context, awsevent json.RawMessage) (any, error) {
		slog.DebugContext(ctx, "invocation start", slog.String("event", string(awsevent)))

		var wg sync.WaitGroup

		var invokeErr error
		if cfg.AdditionalTargets != nil {
			wg.Go(func() {
				invokeErr = sdkclient.InvokeTargets(ctx, cfg.AdditionalTargets, awsevent)
			})
		}

		filter := filterer.New(cfg.FilterInclude, cfg.FilterExclude)
		scrub := scrubber.New(cfg.ScrubbingRegex, cfg.ScrubbingReplacement, cfg.ScrubIP, cfg.ScrubEmail)
		forwarderCfg := forwarder.Config{
			APIKey:                    apiKey,
			IntakeURL:                 cfg.IntakeURL,
			CompressionLevel:          cfg.CompressionLevel,
			StepFunctionsTraceEnabled: cfg.StepFunctionsTraceEnabled,
		}

		var store storage.Storage
		var storageErr error
		if cfg.StoreOnFail {
			storageOpts := storage.Options{S3Bucket: cfg.S3BucketName, SQSQueue: cfg.SQSQueueURL}
			if store, storageErr = storage.New(storageOpts); storageErr != nil {
				return nil, fmt.Errorf("new storage: %w", storageErr)
			}
		}

		fwd := forwarder.New(
			forwarderCfg,
			client,
			store,
		)

		out, pipelineErr := pipeline.New(handlerCfg, scrub, filter, fwd).Start(ctx, lambdaOrigin(ctx), awsevent)

		wg.Wait()
		return out, errors.Join(invokeErr, pipelineErr)
	}
}

func lambdaOrigin(ctx context.Context) model.LambdaOrigin {
	var origin model.LambdaOrigin

	if lambdacontext.FunctionVersion != "$LATEST" {
		origin.Version = lambdacontext.FunctionVersion
	}

	if lc, ok := lambdacontext.FromContext(ctx); ok {
		origin.ARN = lc.InvokedFunctionArn
	}

	return origin
}
