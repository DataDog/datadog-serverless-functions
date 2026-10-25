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

	"github.com/aws/aws-lambda-go/events"
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

	s3Client, err := sdkclient.GetS3()
	if err != nil {
		slog.Error("s3 client", slog.Any("error", err))
		os.Exit(1)
	}

	store, err := newStorage(&cfg, s3Client)
	if err != nil {
		slog.Error("new storage", slog.Any("error", err))
		os.Exit(1)
	}

	var lambdaClient sdkclient.Lambda
	if cfg.AdditionalTargets != nil {
		if lambdaClient, err = sdkclient.GetLambda(); err != nil {
			slog.Error("lambda client", slog.Any("error", err))
			os.Exit(1)
		}
	}

	fwd := forwarder.New(forwarder.Config{
		APIKey:                    apiKey,
		IntakeURL:                 cfg.IntakeURL,
		CompressionLevel:          cfg.CompressionLevel,
		StepFunctionsTraceEnabled: cfg.StepFunctionsTraceEnabled,
	}, client, store)

	p := pipeline.New(
		newHandlerConfig(&cfg, lambdacontext.FunctionName),
		scrubber.New(cfg.ScrubbingRegex, cfg.ScrubbingReplacement, cfg.ScrubIP, cfg.ScrubEmail),
		filterer.New(cfg.FilterInclude, cfg.FilterExclude),
		fwd,
		s3Client,
	)

	lambda.Start(handleRequest(p, lambdaClient, cfg.AdditionalTargets))
}

func newStorage(cfg *config.Config, s3Client sdkclient.S3) (storage.Storage, error) {
	if !cfg.StoreOnFail {
		return nil, nil
	}

	if cfg.SQSQueueURL != "" {
		sqsClient, err := sdkclient.GetSQS()
		if err != nil {
			return nil, fmt.Errorf("sqs client: %w", err)
		}
		return storage.NewSQS(sqsClient, cfg.SQSQueueURL), nil
	}

	if cfg.S3BucketName != "" {
		return storage.NewS3(s3Client, cfg.S3BucketName), nil
	}

	return nil, nil
}

func newHandlerConfig(cfg *config.Config, functionName string) handler.Config {
	service, tags := model.ParseTags(cfg.Tags)

	if cfg.Source != "" {
		tags.Add(model.SourceOverriddenKey, "true")
	}
	tags.Add(model.ForwarderNameKey, strings.ToLower(functionName))
	tags.Add(model.ForwarderVersionKey, version.Forwarder)

	return handler.Config{
		Template:            handler.NewTemplate(service, cfg.Source, tags),
		S3MultilineLogRegex: cfg.S3MultilineLogRegex,
	}
}

func handleRequest(p pipeline.Pipeline, lambdaClient sdkclient.Lambda, targets []string) func(ctx context.Context, awsevent json.RawMessage) (any, error) {
	return func(ctx context.Context, awsevent json.RawMessage) (any, error) {
		slog.DebugContext(ctx, "invocation start", slog.String("event", string(awsevent)))

		var wg sync.WaitGroup

		var invokeErr error
		if targets != nil {
			wg.Go(func() {
				invokeErr = sdkclient.InvokeTargets(ctx, lambdaClient, targets, awsevent)
			})
		}

		result, pipelineErr := p.Start(ctx, lambdaOrigin(ctx), awsevent)

		wg.Wait()

		if !result.SQSBatch {
			return nil, errors.Join(invokeErr, pipelineErr)
		}

		if invokeErr != nil {
			slog.ErrorContext(ctx, "SQS batch response kept over invoke targets failure", slog.Any("error", invokeErr))
		}

		return sqsResponse(result.Unprocessed), pipelineErr
	}
}

func sqsResponse(unprocessed []string) events.SQSEventResponse {
	var response events.SQSEventResponse
	for _, messageID := range unprocessed {
		response.BatchItemFailures = append(response.BatchItemFailures, events.SQSBatchItemFailure{ItemIdentifier: messageID})
	}

	return response
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
